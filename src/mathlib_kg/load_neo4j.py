"""Load structure.jsonl + extract.jsonl records into Neo4j."""
from neo4j import Driver, GraphDatabase

from .config import get_config
from .models import ModuleRecord

KIND_TO_LABEL = {
    "theorem": "Theorem",
    "lemma": "Lemma",
    "def": "Definition",
    "instance": "Instance",
    "class": "Class",
    "structure": "Structure",
    "inductive": "Inductive",
    "axiom": "Axiom",
    "abbrev": "Abbreviation",
    "notation": "Notation",
}

BATCH = 1000


def connect() -> Driver:
    cfg = get_config()
    # 大批量装载下连接可能因 Neo4j GC 暂停而暂时无响应；放宽超时与重试上限
    return GraphDatabase.driver(
        cfg.neo4j_uri,
        auth=(cfg.neo4j_user, cfg.neo4j_password),
        connection_timeout=120,
        connection_acquisition_timeout=120,
        max_connection_lifetime=3600,
        max_transaction_retry_time=600,
    )


def _decl_to_props(d) -> dict:
    return {
        "name": d.name,
        "shortName": d.shortName,
        "kind": d.kind,
        "namespace": d.namespace,
        "docstring": d.docstring,
        "sourceFile": d.sourceFile,
        "startLine": d.startLine,
        "endLine": d.endLine,
        "sourceText": d.sourceText,
        "attrs": list(d.attrs),
        "isProtected": d.isProtected,
        "isExternal": d.isExternal,
        "isDeprecated": d.isDeprecated,
        "deprecatedSince": d.deprecatedSince.isoformat() if d.deprecatedSince else None,
    }


def load_modules(tx, records: list[ModuleRecord]) -> None:
    rows = [
        {
            "name": r.module,
            "path": r.path,
            "docstring": r.docstring,
            "title": r.title,
            "tags": list(r.tags),
            "authors": list(r.authors),
            "isDeprecated": r.isDeprecated,
        }
        for r in records
    ]
    for i in range(0, len(rows), BATCH):
        tx.run(
            "UNWIND $batch AS r MERGE (m:Module {name: r.name}) "
            "SET m.path=r.path, m.docstring=r.docstring, m.title=r.title, "
            "m.tags=r.tags, m.authors=r.authors, m.isDeprecated=r.isDeprecated",
            batch=rows[i : i + BATCH],
        )


def load_namespaces(tx, records: list[ModuleRecord]) -> None:
    seen: set[str] = set()
    ns_rows: list[dict] = []
    rel_rows: list[dict] = []
    for r in records:
        for ns in list(r.namespaces) + [d.namespace for d in r.declarations]:
            segs = [s for s in ns.split(".") if s] if ns else []
            prefix = ""
            for depth, seg in enumerate(segs, 1):
                parent = prefix
                prefix = (prefix + "." + seg) if prefix else seg
                if prefix in seen:
                    continue
                seen.add(prefix)
                ns_rows.append({"name": prefix, "depth": depth})
                if parent:
                    rel_rows.append({"child": prefix, "parent": parent})
    for i in range(0, len(ns_rows), BATCH):
        tx.run(
            "UNWIND $batch AS r MERGE (n:Namespace {name: r.name}) SET n.depth=r.depth",
            batch=ns_rows[i : i + BATCH],
        )
    for i in range(0, len(rel_rows), BATCH):
        tx.run(
            "UNWIND $batch AS r MATCH (c:Namespace {name:r.child}), "
            "(p:Namespace {name:r.parent}) MERGE (c)-[:SUBNAMESPACE_OF]->(p)",
            batch=rel_rows[i : i + BATCH],
        )


def load_declarations(tx, records: list[ModuleRecord]) -> None:
    decl_rows: list[dict] = []
    ns_rel: list[dict] = []
    mod_rel: list[dict] = []
    for r in records:
        for d in r.declarations:
            decl_rows.append(_decl_to_props(d))
            if d.namespace:
                ns_rel.append({"name": d.name, "ns": d.namespace})
            mod_rel.append({"name": d.name, "module": r.module})
    for i in range(0, len(decl_rows), BATCH):
        tx.run(
            "UNWIND $batch AS d MERGE (n:Declaration {name: d.name}) SET n += d",
            batch=decl_rows[i : i + BATCH],
        )
    # 种类标签（label 来自固定映射，可安全字符串拼接）
    for kind, label in KIND_TO_LABEL.items():
        tx.run("MATCH (n:Declaration {kind:$k}) SET n:%s" % label, k=kind)
    for i in range(0, len(ns_rel), BATCH):
        tx.run(
            "UNWIND $batch AS r MATCH (d:Declaration {name:r.name}), "
            "(ns:Namespace {name:r.ns}) MERGE (d)-[:IN_NAMESPACE]->(ns)",
            batch=ns_rel[i : i + BATCH],
        )
    for i in range(0, len(mod_rel), BATCH):
        tx.run(
            "UNWIND $batch AS r MATCH (d:Declaration {name:r.name}), "
            "(m:Module {name:r.module}) MERGE (d)-[:DEFINED_IN]->(m)",
            batch=mod_rel[i : i + BATCH],
        )


def load_imports(tx, records: list[ModuleRecord]) -> None:
    rows: list[dict] = []
    for r in records:
        for imp in r.imports:
            rows.append(
                {
                    "src": r.module,
                    "dst": imp.name,
                    "isPublic": imp.isPublic,
                    "isDeprecated": imp.isDeprecated,
                }
            )
    for i in range(0, len(rows), BATCH):
        tx.run(
            "UNWIND $batch AS r MERGE (a:Module {name:r.src}) "
            "MERGE (b:Module {name:r.dst}) "
            "MERGE (a)-[rel:IMPORTS]->(b) "
            "SET rel.isPublic=r.isPublic, rel.isDeprecated=r.isDeprecated",
            batch=rows[i : i + BATCH],
        )


def _context(in_type: bool, in_value: bool) -> str:
    if in_type and in_value:
        return "both"
    return "type" if in_type else "value"


def load_dependencies(tx, records: list) -> None:
    # 收集所有被引用的依赖名，为不存在的建外部占位节点（ON CREATE 只标记新建的）
    dep_names: list[str] = []
    seen_names: set[str] = set()
    for er in records:
        for d in er.deps:
            if d.name not in seen_names:
                seen_names.add(d.name)
                dep_names.append(d.name)
    for i in range(0, len(dep_names), BATCH):
        tx.run(
            "UNWIND $batch AS name MERGE (n:Declaration {name: name}) "
            "ON CREATE SET n.isExternal = true",
            batch=dep_names[i : i + BATCH],
        )
    # typeSignature 写入声明
    sig_rows = [{"name": er.name, "typeSignature": er.typeSignature} for er in records]
    for i in range(0, len(sig_rows), BATCH):
        tx.run(
            "UNWIND $batch AS r MATCH (d:Declaration {name:r.name}) "
            "SET d.typeSignature=r.typeSignature",
            batch=sig_rows[i : i + BATCH],
        )
    # DEPENDS_ON 边
    edge_rows: list[dict] = []
    for er in records:
        for d in er.deps:
            edge_rows.append(
                {
                    "src": er.name,
                    "dst": d.name,
                    "context": _context(d.inType, d.inValue),
                }
            )
    for i in range(0, len(edge_rows), BATCH):
        tx.run(
            "UNWIND $batch AS r MATCH (a:Declaration {name:r.src}), "
            "(b:Declaration {name:r.dst}) "
            "CREATE (a)-[rel:DEPENDS_ON]->(b) SET rel.context=r.context",
            batch=edge_rows[i : i + BATCH],
        )


def load_dependencies_chunked(session, records: list, chunk: int = 2000) -> None:
    """按记录分块、每块独立事务提交——避免把数百万依赖边塞进单个巨型事务。

    `load_dependencies` 本身把占位/typeSig/边都在 *一个* 事务里做（适合小数据）；
    全量装载时必须切成多个已提交事务，否则 Neo4j 事务状态会撑爆内存/超时。
    """
    for i in range(0, len(records), chunk):
        session.execute_write(load_dependencies, records[i : i + chunk])


def load_relationships_chunked(session, records: list, chunk: int = 2000) -> None:
    """v2 关系边分块提交，镜像 load_dependencies_chunked：避免单巨型事务。

    spec §11：关系边 ~4 万量级，分块 2000/事务。
    `load_relationships` 已按 list 取 records 且逐 record 正确；这里只是把记录
    切到多个独立已提交事务里。占位端点用 MERGE，跨块安全（幂等）。
    """
    for i in range(0, len(records), chunk):
        session.execute_write(load_relationships, records[i : i + chunk])


def _rel_targets(er) -> list[str]:
    """收集一条 extract 记录里所有关系端点的目标名（供外部占位）。"""
    out: list[str] = []
    for it in er.extends:
        out.append(it.parent)
    if er.instantiates:
        out.append(er.instantiates)
    if er.deprecatedBy:
        out.append(er.deprecatedBy.replacement)
    if er.additiveVersion:
        out.append(er.additiveVersion)
    return out


def load_relationships(tx, records: list) -> None:
    """v2：从 extract 记录的四类关系字段造 EXTENDS/INSTANTIATES/DEPRECATED_BY/HAS_ADDITIVE_VERSION 边。

    全量重建路径下图已 drop，故用 CREATE（空图无重边风险）。外部端点（不在声明集中的类型类/替换名）
    用 ON CREATE SET isExternal=true 建占位，保证边挂得上。
    """
    # ① 为所有目标端建占位（已存在的真实声明不受影响）
    target_names: list[str] = []
    seen: set[str] = set()
    for er in records:
        for cand in _rel_targets(er):
            if cand not in seen:
                seen.add(cand)
                target_names.append(cand)
    for i in range(0, len(target_names), BATCH):
        tx.run(
            "UNWIND $batch AS name MERGE (n:Declaration {name: name}) "
            "ON CREATE SET n.isExternal = true",
            batch=target_names[i : i + BATCH],
        )

    # ② EXTENDS（含 position）
    ext_rows = [
        {"src": er.name, "dst": it.parent, "position": it.position}
        for er in records
        for it in er.extends
    ]
    for i in range(0, len(ext_rows), BATCH):
        tx.run(
            "UNWIND $batch AS r MATCH (a:Declaration {name:r.src}), "
            "(b:Declaration {name:r.dst}) "
            "CREATE (a)-[:EXTENDS {position:r.position}]->(b)",
            batch=ext_rows[i : i + BATCH],
        )

    # ③ INSTANTIATES（含 priority）
    inst_rows = [
        {"src": er.name, "dst": er.instantiates, "priority": er.instancePriority}
        for er in records
        if er.instantiates
    ]
    for i in range(0, len(inst_rows), BATCH):
        tx.run(
            "UNWIND $batch AS r MATCH (a:Declaration {name:r.src}), "
            "(b:Declaration {name:r.dst}) "
            "CREATE (a)-[:INSTANTIATES {priority:r.priority}]->(b)",
            batch=inst_rows[i : i + BATCH],
        )

    # ④ DEPRECATED_BY（含 message, since）
    dep_rows = [
        {
            "src": er.name,
            "dst": er.deprecatedBy.replacement,
            "message": er.deprecatedBy.message,
            "since": er.deprecatedBy.since,
        }
        for er in records
        if er.deprecatedBy
    ]
    for i in range(0, len(dep_rows), BATCH):
        tx.run(
            "UNWIND $batch AS r MATCH (a:Declaration {name:r.src}), "
            "(b:Declaration {name:r.dst}) "
            "CREATE (a)-[:DEPRECATED_BY {message:r.message, since:r.since}]->(b)",
            batch=dep_rows[i : i + BATCH],
        )

    # ⑤ HAS_ADDITIVE_VERSION
    add_rows = [
        {"src": er.name, "dst": er.additiveVersion}
        for er in records
        if er.additiveVersion
    ]
    for i in range(0, len(add_rows), BATCH):
        tx.run(
            "UNWIND $batch AS r MATCH (a:Declaration {name:r.src}), "
            "(b:Declaration {name:r.dst}) "
            "CREATE (a)-[:HAS_ADDITIVE_VERSION]->(b)",
            batch=add_rows[i : i + BATCH],
        )


def load_fields_constructors(tx, records: list, type_names: set[str]) -> None:
    """v2.5：把 mathlib 类型（er.name ∈ type_names）的字段/构造子扶正为 :Field/:Constructor
    节点并挂 HAS_FIELD/HAS_CONSTRUCTOR 边。

    全量重建路径下图已 drop，故边用 CREATE（空图无重边风险）。范围判据在 Python 侧
    （type_names 来自 structure.jsonl 的 mathlib 类型声明集），外部类型不展开。
    字段/构造子若第 5 步未被任何声明依赖（未建点），此处首次建点并补 typeSignature。
    """
    # name → typeSignature 索引（字段/构造子常量自己的记录带 typeSig，复用补写）
    sig_by_name = {er.name: er.typeSignature for er in records}

    # 收集字段行（仅 er.name ∈ type_names 的类型）
    field_rows = [
        {"name": f.name, "type": er.name, "position": f.position,
         "sig": sig_by_name.get(f.name, "")}
        for er in records if er.name in type_names
        for f in er.fields
    ]
    ctor_rows = [
        {"name": c.name, "type": er.name, "position": c.position,
         "sig": sig_by_name.get(c.name, "")}
        for er in records if er.name in type_names
        for c in er.constructors
    ]

    # ① 扶正字段节点（MERGE 兜底建点保反向 DEPENDS_ON 边；SET 标签/kind/isExternal/typeSig）
    for i in range(0, len(field_rows), BATCH):
        tx.run(
            "UNWIND $batch AS r MERGE (n:Declaration {name: r.name}) "
            "ON CREATE SET n.isExternal = true "
            "SET n:Field, n.kind = 'field', n.isExternal = false, n.typeSignature = r.sig",
            batch=field_rows[i : i + BATCH],
        )
    # ② 扶正构造子节点
    for i in range(0, len(ctor_rows), BATCH):
        tx.run(
            "UNWIND $batch AS r MERGE (n:Declaration {name: r.name}) "
            "ON CREATE SET n.isExternal = true "
            "SET n:Constructor, n.kind = 'constructor', n.isExternal = false, n.typeSignature = r.sig",
            batch=ctor_rows[i : i + BATCH],
        )
    # ③ HAS_FIELD 边（类型节点已在 load_declarations 建好；字段节点刚扶正）
    for i in range(0, len(field_rows), BATCH):
        tx.run(
            "UNWIND $batch AS r MATCH (t:Declaration {name:r.type}), "
            "(f:Declaration {name:r.name}) "
            "CREATE (t)-[:HAS_FIELD {position:r.position}]->(f)",
            batch=field_rows[i : i + BATCH],
        )
    # ④ HAS_CONSTRUCTOR 边
    for i in range(0, len(ctor_rows), BATCH):
        tx.run(
            "UNWIND $batch AS r MATCH (t:Declaration {name:r.type}), "
            "(c:Declaration {name:r.name}) "
            "CREATE (t)-[:HAS_CONSTRUCTOR {position:r.position}]->(c)",
            batch=ctor_rows[i : i + BATCH],
        )


def load_fields_constructors_chunked(session, records: list, type_names: set[str],
                                     chunk: int = 2000) -> None:
    """v2.5 字段/构造子边分块提交，镜像 load_relationships_chunked：避免单巨型事务。
    全量装载 fields/constructors 量级 ~15 万，分块 2000/事务。
    """
    for i in range(0, len(records), chunk):
        session.execute_write(load_fields_constructors, records[i : i + chunk], type_names)

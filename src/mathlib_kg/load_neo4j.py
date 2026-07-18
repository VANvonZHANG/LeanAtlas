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
            "MERGE (a)-[rel:DEPENDS_ON]->(b) SET rel.context=r.context",
            batch=edge_rows[i : i + BATCH],
        )

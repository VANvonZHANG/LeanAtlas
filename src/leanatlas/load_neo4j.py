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
    # Under bulk loads the connection may stall during Neo4j GC pauses; relax
    # timeouts and retry limits
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
    # Kind labels (the label comes from a fixed mapping, so %-interpolation is safe)
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
    # Collect all referenced dependency names and create external placeholder
    # nodes for missing ones (ON CREATE only marks newly created ones)
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
    # Write typeSignature onto declarations
    sig_rows = [{"name": er.name, "typeSignature": er.typeSignature} for er in records]
    for i in range(0, len(sig_rows), BATCH):
        tx.run(
            "UNWIND $batch AS r MATCH (d:Declaration {name:r.name}) "
            "SET d.typeSignature=r.typeSignature",
            batch=sig_rows[i : i + BATCH],
        )
    # DEPENDS_ON edges
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
    """Commit in record chunks, one committed transaction per chunk — avoids
    pushing millions of dependency edges into a single giant transaction.

    `load_dependencies` itself does placeholders/typeSig/edges in *one*
    transaction (fine for small data); full loads must split into multiple
    committed transactions or Neo4j transaction state exhausts memory / times out.
    """
    for i in range(0, len(records), chunk):
        session.execute_write(load_dependencies, records[i : i + chunk])


def load_relationships_chunked(session, records: list, chunk: int = 2000) -> None:
    """Chunked commits of v2 relationship edges, mirroring
    load_dependencies_chunked: avoid a single giant transaction.

    spec §11: relationship edges number ~40k; chunk at 2000/transaction.
    `load_relationships` already takes a records list and handles each record
    correctly; here we merely split the records across multiple independent
    committed transactions. Placeholder endpoints use MERGE, safe across chunks
    (idempotent).
    """
    for i in range(0, len(records), chunk):
        session.execute_write(load_relationships, records[i : i + chunk])


def _rel_targets(er) -> list[str]:
    """Collect the target names of all relationship endpoints in one extract
    record (for external placeholders)."""
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
    """v2: build EXTENDS/INSTANTIATES/DEPRECATED_BY/HAS_ADDITIVE_VERSION edges
    from the four relationship fields of extract records.

    On the full-rebuild path the graph has been dropped, so use CREATE (an empty
    graph carries no duplicate-edge risk). External endpoints (typeclass /
    replacement names not in the declaration set) get placeholders via
    ON CREATE SET isExternal=true so the edges can attach.
    """
    # ① Create placeholders for all target endpoints (existing real declarations are unaffected)
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

    # ② EXTENDS (with position)
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

    # ③ INSTANTIATES (with priority)
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

    # ④ DEPRECATED_BY (with message, since)
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


def load_fields_constructors(tx, records: list, type_names: set[str],
                             sig_by_name: dict[str, str] | None = None) -> None:
    """v2.5: promote the fields/constructors of mathlib types (er.name ∈
    type_names) to :Field/:Constructor nodes and attach HAS_FIELD/HAS_CONSTRUCTOR
    edges.

    On the full-rebuild path the graph has been dropped, so edges use CREATE
    (an empty graph carries no duplicate-edge risk). The scope predicate lives
    on the Python side (type_names comes from the mathlib type declaration set
    in structure.jsonl); external types are not expanded. Fields/constructors
    not depended on by any declaration in step 5 (no node created) get their
    node created here for the first time, with a typeSignature backfill.

    sig_by_name: optional full name → typeSignature index; if None (default,
    single-transaction / unit-test path) it is built in place from records.
    The chunked path must build it fully before chunking and pass it in,
    otherwise the field constants' own records (carrying typeSig) and their
    parent type records (carrying fields) landing in different chunks cannot
    be backfilled.
    """
    # name → typeSignature index (the field/constructor constants' own records
    # carry typeSig; reuse for backfill)
    if sig_by_name is None:
        sig_by_name = {er.name: er.typeSignature for er in records}

    # Collect field rows (only for types with er.name ∈ type_names)
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

    # ① Promote field nodes (MERGE backstop creates the node to keep reverse
    # DEPENDS_ON edges attachable; SET label/kind/isExternal/typeSig)
    for i in range(0, len(field_rows), BATCH):
        tx.run(
            "UNWIND $batch AS r MERGE (n:Declaration {name: r.name}) "
            "ON CREATE SET n.isExternal = true "
            "SET n:Field, n.kind = 'field', n.isExternal = false, n.typeSignature = r.sig",
            batch=field_rows[i : i + BATCH],
        )
    # ② Promote constructor nodes
    for i in range(0, len(ctor_rows), BATCH):
        tx.run(
            "UNWIND $batch AS r MERGE (n:Declaration {name: r.name}) "
            "ON CREATE SET n.isExternal = true "
            "SET n:Constructor, n.kind = 'constructor', n.isExternal = false, n.typeSignature = r.sig",
            batch=ctor_rows[i : i + BATCH],
        )
    # ③ HAS_FIELD edges (type nodes were created by load_declarations; field
    # nodes were just promoted)
    for i in range(0, len(field_rows), BATCH):
        tx.run(
            "UNWIND $batch AS r MATCH (t:Declaration {name:r.type}), "
            "(f:Declaration {name:r.name}) "
            "CREATE (t)-[:HAS_FIELD {position:r.position}]->(f)",
            batch=field_rows[i : i + BATCH],
        )
    # ④ HAS_CONSTRUCTOR edges
    for i in range(0, len(ctor_rows), BATCH):
        tx.run(
            "UNWIND $batch AS r MATCH (t:Declaration {name:r.type}), "
            "(c:Declaration {name:r.name}) "
            "CREATE (t)-[:HAS_CONSTRUCTOR {position:r.position}]->(c)",
            batch=ctor_rows[i : i + BATCH],
        )


def load_fields_constructors_chunked(session, records: list, type_names: set[str],
                                     chunk: int = 2000) -> None:
    """v2.5 chunked commits of field/constructor edges, mirroring
    load_relationships_chunked: avoid a single giant transaction.
    Full loads carry ~150k fields/constructors; chunk at 2000/transaction.

    sig_by_name is built fully before chunking (visible across chunks) — the
    field constants' own ExtractRecord (carrying typeSig) and their parent
    type's record often land in different chunks; a per-chunk index would lose
    the typeSig.
    """
    sig_by_name = {er.name: er.typeSignature for er in records}
    for i in range(0, len(records), chunk):
        session.execute_write(load_fields_constructors, records[i : i + chunk],
                              type_names, sig_by_name)

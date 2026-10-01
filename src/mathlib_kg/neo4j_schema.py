"""Neo4j schema DDL for v1 (constraints, indexes, fulltext).

Note: the running Neo4j is Community Edition, which has no multi-database
support, so KG data goes into the default `neo4j` database and is isolated from
existing data by KG-specific labels (Declaration/Module/Namespace). drop_kg
deletes only nodes carrying these labels and leaves other data untouched.
"""

# Named explicitly for SHOW CONSTRAINTS/INDEXES assertions and idempotent rebuilds
SCHEMA_STATEMENTS = [
    "CREATE CONSTRAINT decl_name_unique IF NOT EXISTS "
    "FOR (n:Declaration) REQUIRE n.name IS UNIQUE",
    "CREATE CONSTRAINT module_name_unique IF NOT EXISTS "
    "FOR (n:Module) REQUIRE n.name IS UNIQUE",
    "CREATE CONSTRAINT namespace_name_unique IF NOT EXISTS "
    "FOR (n:Namespace) REQUIRE n.name IS UNIQUE",
    "CREATE INDEX decl_kind_idx IF NOT EXISTS FOR (n:Declaration) ON (n.kind)",
    "CREATE INDEX decl_sourcefile_idx IF NOT EXISTS FOR (n:Declaration) ON (n.sourceFile)",
    "CREATE INDEX decl_shortname_idx IF NOT EXISTS FOR (n:Declaration) ON (n.shortName)",
    "CREATE INDEX decl_namespace_idx IF NOT EXISTS FOR (n:Declaration) ON (n.namespace)",
    "CREATE INDEX module_path_idx IF NOT EXISTS FOR (n:Module) ON (n.path)",
    "CREATE FULLTEXT INDEX decl_fulltext IF NOT EXISTS "
    "FOR (n:Declaration) ON EACH [n.docstring, n.shortName, n.typeSignature, n.sourceText]",
]


def apply_schema(tx) -> None:
    """Run all DDL inside a transaction (for use with session.execute_write)."""
    for stmt in SCHEMA_STATEMENTS:
        tx.run(stmt)


def drop_kg(tx) -> None:
    """Delete all KG nodes (Declaration/Module/Namespace) and relationships, keep other data."""
    tx.run("MATCH (n:Declaration) DETACH DELETE n")
    tx.run("MATCH (n:Module) DETACH DELETE n")
    tx.run("MATCH (n:Namespace) DETACH DELETE n")


def drop_kg_batched(session) -> None:
    """Batched KG wipe (delete edges first, then nodes), suited to large graphs.

    A direct DETACH DELETE of high-degree hub nodes (e.g. `id`/`Nat`) makes a
    single transaction touch millions of edges and OOM; so DEPENDS_ON and other
    edges are deleted in batches first, then the isolated nodes are batch-deleted.
    """
    # All edge types are deleted in batches uniformly (M1 hardening: HAS_FIELD
    # reaches ~150k edges in production, 8x the ~20k per-transaction DEPENDS_ON
    # ceiling validated in v2, so a single-transaction DELETE risks OOM; hence
    # every edge type mirrors DEPENDS_ON's while...LIMIT...DELETE pattern)
    for t in ("DEPENDS_ON", "IMPORTS", "IN_NAMESPACE", "SUBNAMESPACE_OF", "DEFINED_IN",
              "EXTENDS", "INSTANTIATES", "DEPRECATED_BY", "HAS_ADDITIVE_VERSION",
              "HAS_FIELD", "HAS_CONSTRUCTOR"):
        while session.run(f"MATCH ()-[r:{t}]->() RETURN count(r)").single()[0] > 0:
            session.run(f"MATCH ()-[r:{t}]->() WITH r LIMIT 200000 DELETE r")
    for label in ("Declaration", "Module", "Namespace"):
        while session.run(f"MATCH (n:{label}) RETURN count(n)").single()[0] > 0:
            session.run(f"MATCH (n:{label}) WITH n LIMIT 50000 DELETE n")

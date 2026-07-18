"""Neo4j schema DDL for v1 (constraints, indexes, fulltext).

注意：运行中的 Neo4j 为社区版，不支持多数据库，因此 KG 数据装入默认 `neo4j`
库，靠 KG 专有标签（Declaration/Module/Namespace）与既有数据隔离。drop_kg 只
删除这些标签的节点，不影响库内其它数据。
"""

# 显式命名，便于 SHOW CONSTRAINTS/INDEXES 断言与幂等重建
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
    """在事务中执行全部 DDL（供 session.execute_write 使用）。"""
    for stmt in SCHEMA_STATEMENTS:
        tx.run(stmt)


def drop_kg(tx) -> None:
    """删除全部 KG 节点（Declaration/Module/Namespace）及其关系，保留库内其它数据。"""
    tx.run("MATCH (n:Declaration) DETACH DELETE n")
    tx.run("MATCH (n:Module) DETACH DELETE n")
    tx.run("MATCH (n:Namespace) DETACH DELETE n")


def drop_kg_batched(session) -> None:
    """批量清空 KG（先删边、再删节点），适合大图。

    直接 DETACH DELETE 高度数枢纽节点（如 `id`/`Nat`）会令单事务触及百万边而 OOM；
    故先分批删 DEPENDS_ON 等边，节点变孤立后再批量删。
    """
    while session.run("MATCH ()-[r:DEPENDS_ON]->() RETURN count(r)").single()[0] > 0:
        session.run("MATCH ()-[r:DEPENDS_ON]->() WITH r LIMIT 200000 DELETE r")
    for t in ("IMPORTS", "IN_NAMESPACE", "SUBNAMESPACE_OF", "DEFINED_IN",
              "EXTENDS", "INSTANTIATES", "DEPRECATED_BY", "HAS_ADDITIVE_VERSION"):
        session.run(f"MATCH ()-[r:{t}]->() DELETE r")
    for label in ("Declaration", "Module", "Namespace"):
        while session.run(f"MATCH (n:{label}) RETURN count(n)").single()[0] > 0:
            session.run(f"MATCH (n:{label}) WITH n LIMIT 50000 DELETE n")

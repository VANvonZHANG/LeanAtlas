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
    """批量删除 KG 节点（CALL IN TRANSACTIONS 分批提交），适合大图清空，避免单事务删除百万边 OOM。"""
    session.run(
        "MATCH (n:Declaration) "
        "CALL { WITH n DETACH DELETE n } IN TRANSACTIONS OF 50000 ROWS"
    ).consume()
    session.run("MATCH (n:Module) DETACH DELETE n")
    session.run("MATCH (n:Namespace) DETACH DELETE n")

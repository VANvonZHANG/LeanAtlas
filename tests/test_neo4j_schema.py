import os

import pytest
from neo4j import GraphDatabase

from mathlib_kg.config import get_config
from mathlib_kg.neo4j_schema import apply_schema, drop_kg

pytestmark = pytest.mark.skipif(
    not os.environ.get("MATHLIB_KG_NEO4J_PASSWORD"),
    reason="需要 Neo4j 凭据（MATHLIB_KG_NEO4J_PASSWORD）",
)


def test_apply_schema_creates_constraints():
    cfg = get_config()
    assert cfg.neo4j_db == "neo4j"  # 社区版用默认库
    driver = GraphDatabase.driver(cfg.neo4j_uri, auth=(cfg.neo4j_user, cfg.neo4j_password))
    with driver.session(database=cfg.neo4j_db) as s:
        s.execute_write(drop_kg)
        s.execute_write(apply_schema)
        cons = [r[0] for r in s.run("SHOW CONSTRAINTS YIELD name RETURN name")]
        assert any("decl_name" in c for c in cons)
        assert any("module_name" in c for c in cons)
        idx = [r[0] for r in s.run("SHOW INDEXES YIELD name RETURN name")]
        assert any("decl_kind" in i for i in idx)
        assert any("decl_fulltext" in i for i in idx)
        # schema 幂等：再跑一次不报错
        s.execute_write(apply_schema)
    driver.close()

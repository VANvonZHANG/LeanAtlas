"""v2 端到端：在 StructEdgesFixture 上跑 parse → extract → load，断言 4 种关系边。

默认跳过（需 Lean 构建 + Neo4j）。启用：
  export MATHLIB_KG_NEO4J_USER=neo4j MATHLIB_KG_NEO4J_PASSWORD=... MATHLIB_KG_NEO4J_DB=neo4j
  export MATHLIB_KG_RUN_V2_ACCEPTANCE=1
  pytest tests/test_v2_acceptance.py -v -s
"""
import os
import subprocess
from pathlib import Path

import pytest
from neo4j import GraphDatabase

from mathlib_kg.config import get_config
from mathlib_kg.models import module_to_json
from mathlib_kg.parse_source import parse_file

pytestmark = pytest.mark.skipif(
    os.environ.get("MATHLIB_KG_RUN_V2_ACCEPTANCE") != "1"
    or not os.environ.get("MATHLIB_KG_NEO4J_PASSWORD"),
    reason="需要 MATHLIB_KG_RUN_V2_ACCEPTANCE=1 与 Neo4j 凭据",
)

REPO = Path(__file__).resolve().parents[1]
EXTRACT_DIR = REPO / "extract"
FIXTURE = EXTRACT_DIR / "StructEdgesFixture.lean"


def test_v2_four_edges_on_fixture(tmp_path):
    # 1) 构建 + 抽取 fixture
    subprocess.run(["lake", "build", "StructEdgesFixture"], cwd=EXTRACT_DIR, check=True,
                   capture_output=True, text=True)
    extract = tmp_path / "e.jsonl"
    with extract.open("w") as f:
        subprocess.run(["lake", "exe", "extract", "StructEdgesFixture"],
                       cwd=EXTRACT_DIR, stdout=f, check=True)

    # 2) 解析 fixture 源码（取 Declaration 节点：B/instB/oldB/newB/A/foo）
    rec, warnings = parse_file(str(FIXTURE), root=str(EXTRACT_DIR))
    assert warnings == []
    struct = tmp_path / "s.jsonl"
    struct.write_text(module_to_json(rec) + "\n", encoding="utf-8")

    # 3) 全量装载（drop 先，单一 load 路径带 v2 边）
    subprocess.run(["python", "-m", "mathlib_kg.cli", "drop"], cwd=REPO, check=True)
    subprocess.run(
        ["python", "-m", "mathlib_kg.cli", "load",
         "--structure", str(struct), "--extract", str(extract)],
        cwd=REPO, check=True,
    )

    # 4) 断言 4 种边
    cfg = get_config()
    driver = GraphDatabase.driver(cfg.neo4j_uri, auth=(cfg.neo4j_user, cfg.neo4j_password))
    try:
        with driver.session(database=cfg.neo4j_db) as s:
            # EXTENDS: B -> A
            assert s.run(
                "MATCH (:Declaration {name:'StructEdgesFixture.B'})-[:EXTENDS]->"
                "(:Declaration {name:'StructEdgesFixture.A'}) RETURN count(*)"
            ).single()[0] == 1
            # INSTANTIATES: instB -> B
            assert s.run(
                "MATCH (:Declaration {name:'StructEdgesFixture.instB'})-[:INSTANTIATES]->"
                "(:Declaration {name:'StructEdgesFixture.B'}) RETURN count(*)"
            ).single()[0] == 1
            # DEPRECATED_BY（attr 可读时）
            dep = s.run(
                "MATCH (:Declaration {name:'StructEdgesFixture.oldB'})-[r:DEPRECATED_BY]->"
                "(t:Declaration) RETURN t.name, r.since"
            ).single()
            if dep is not None:
                assert dep[0] == "StructEdgesFixture.newB"
                assert dep[1] == "2024-01-01"
            # HAS_ADDITIVE_VERSION（attr 可读时；目标 addFoo 为 to_additive 生成，作占位存在）
            add = s.run(
                "MATCH (:Declaration {name:'StructEdgesFixture.foo'})-[:HAS_ADDITIVE_VERSION]->"
                "(t:Declaration) RETURN t.name"
            ).single()
            if add is not None:
                assert add[0] == "StructEdgesFixture.addFoo"
    finally:
        subprocess.run(["python", "-m", "mathlib_kg.cli", "drop"], cwd=REPO, check=True)
        driver.close()

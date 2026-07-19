"""v2.5 端到端：在 StructEdgesFixture 上跑 parse → extract → load，断言 HAS_FIELD/HAS_CONSTRUCTOR。

默认跳过（需 Lean 构建 + Neo4j）。启用：
  export MATHLIB_KG_NEO4J_USER=neo4j MATHLIB_KG_NEO4J_PASSWORD=REDACTED MATHLIB_KG_NEO4J_DB=neo4j
  export MATHLIB_KG_RUN_V2_5_ACCEPTANCE=1
  pytest tests/test_v2_5_acceptance.py -v -s
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
    os.environ.get("MATHLIB_KG_RUN_V2_5_ACCEPTANCE") != "1"
    or not os.environ.get("MATHLIB_KG_NEO4J_PASSWORD"),
    reason="需要 MATHLIB_KG_RUN_V2_5_ACCEPTANCE=1 与 Neo4j 凭据",
)

REPO = Path(__file__).resolve().parents[1]
EXTRACT_DIR = REPO / "extract"
FIXTURE = EXTRACT_DIR / "StructEdgesFixture.lean"


def test_v2_5_fields_constructors_on_fixture(tmp_path):
    # 1) 构建 + 抽取 fixture
    subprocess.run(["lake", "build", "StructEdgesFixture"], cwd=EXTRACT_DIR, check=True,
                   capture_output=True, text=True)
    extract = tmp_path / "e.jsonl"
    with extract.open("w") as f:
        subprocess.run(["lake", "exe", "extract", "StructEdgesFixture"],
                       cwd=EXTRACT_DIR, stdout=f, check=True)

    # 2) 解析 fixture 源码（取 Declaration 节点：D2/Foo 是 mathlib 类型 → 进 type_names）
    rec, warnings = parse_file(str(FIXTURE), root=str(EXTRACT_DIR))
    assert warnings == []
    struct = tmp_path / "s.jsonl"
    struct.write_text(module_to_json(rec) + "\n", encoding="utf-8")

    # 3) 全量装载（drop 先，单一 load 路径带 v2.5 边）
    subprocess.run(["python", "-m", "mathlib_kg.cli", "drop"], cwd=REPO, check=True)
    subprocess.run(
        ["python", "-m", "mathlib_kg.cli", "load",
         "--structure", str(struct), "--extract", str(extract)],
        cwd=REPO, check=True,
    )

    # 4) 断言 HAS_FIELD / HAS_CONSTRUCTOR + 扶正
    cfg = get_config()
    driver = GraphDatabase.driver(cfg.neo4j_uri, auth=(cfg.neo4j_user, cfg.neo4j_password))
    try:
        with driver.session(database=cfg.neo4j_db) as s:
            # HAS_FIELD: D2 -> D2.d2（自有字段，硬断言）
            assert s.run(
                "MATCH (:Declaration {name:'StructEdgesFixture.D2'})-[:HAS_FIELD]->"
                "(:Declaration {name:'StructEdgesFixture.D2.d2'}) RETURN count(*)"
            ).single()[0] == 1
            # HAS_FIELD 含继承字段 D1.d1（硬断言——T2 实证：继承字段的投影是父结构投影，
            # 即 D1.d1，而非子合成 D2.d1；这是扁平继承证明）
            assert s.run(
                "MATCH (:Declaration {name:'StructEdgesFixture.D2'})-[:HAS_FIELD]->"
                "(:Declaration {name:'StructEdgesFixture.D1.d1'}) RETURN count(*)"
            ).single()[0] == 1
            # HAS_CONSTRUCTOR: D2 -> D2.mk（structure 构造子）
            assert s.run(
                "MATCH (:Declaration {name:'StructEdgesFixture.D2'})-[:HAS_CONSTRUCTOR]->"
                "(:Declaration {name:'StructEdgesFixture.D2.mk'}) RETURN count(*)"
            ).single()[0] == 1
            # HAS_CONSTRUCTOR: Foo -> Foo.c1 / Foo.c2（inductive 多构造子）
            assert s.run(
                "MATCH (:Declaration {name:'StructEdgesFixture.Foo'})-[:HAS_CONSTRUCTOR]->"
                "(:Declaration {name:'StructEdgesFixture.Foo.c1'}) RETURN count(*)"
            ).single()[0] == 1
            assert s.run(
                "MATCH (:Declaration {name:'StructEdgesFixture.Foo'})-[:HAS_CONSTRUCTOR]->"
                "(:Declaration {name:'StructEdgesFixture.Foo.c2'}) RETURN count(*)"
            ).single()[0] == 1
            # 扶正：D2.d2 是 Field 节点，isExternal=false, kind='field', typeSig 非空
            f = s.run(
                "MATCH (n:Field {name:'StructEdgesFixture.D2.d2'}) "
                "RETURN n.isExternal, n.kind, n.typeSignature"
            ).single()
            assert f is not None and f[0] is False and f[1] == "field" and f[2]
    finally:
        subprocess.run(["python", "-m", "mathlib_kg.cli", "drop"], cwd=REPO, check=True)
        driver.close()

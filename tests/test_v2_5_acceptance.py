"""v2.5 end-to-end: parse → extract → load on StructEdgesFixture, asserting
HAS_FIELD/HAS_CONSTRUCTOR.

Skipped by default (needs Lean build + Neo4j). Enable:
  export MATHLIB_KG_NEO4J_USER=neo4j MATHLIB_KG_NEO4J_PASSWORD=REDACTED MATHLIB_KG_NEO4J_DB=neo4j
  export MATHLIB_KG_RUN_V2_5_ACCEPTANCE=1
  pytest tests/test_v2_5_acceptance.py -v -s
"""
import os
import subprocess
from pathlib import Path

import pytest
from neo4j import GraphDatabase

from leanatlas.config import get_config
from leanatlas.models import module_to_json
from leanatlas.parse_source import parse_file

pytestmark = pytest.mark.skipif(
    os.environ.get("MATHLIB_KG_RUN_V2_5_ACCEPTANCE") != "1"
    or not os.environ.get("MATHLIB_KG_NEO4J_PASSWORD"),
    reason="requires MATHLIB_KG_RUN_V2_5_ACCEPTANCE=1 and Neo4j credentials",
)

REPO = Path(__file__).resolve().parents[1]
EXTRACT_DIR = REPO / "extract"
FIXTURE = EXTRACT_DIR / "StructEdgesFixture.lean"


def test_v2_5_fields_constructors_on_fixture(tmp_path):
    # 1) Build + extract the fixture
    subprocess.run(["lake", "build", "StructEdgesFixture"], cwd=EXTRACT_DIR, check=True,
                   capture_output=True, text=True)
    extract = tmp_path / "e.jsonl"
    with extract.open("w") as f:
        subprocess.run(["lake", "exe", "extract", "StructEdgesFixture"],
                       cwd=EXTRACT_DIR, stdout=f, check=True)

    # 2) Parse the fixture source (Declaration nodes: D2/Foo are mathlib
    #    types → they enter type_names)
    rec, warnings = parse_file(str(FIXTURE), root=str(EXTRACT_DIR))
    assert warnings == []
    struct = tmp_path / "s.jsonl"
    struct.write_text(module_to_json(rec) + "\n", encoding="utf-8")

    # 3) Full load (drop first; the single load path carries v2.5 edges)
    subprocess.run(["python", "-m", "leanatlas.cli", "drop"], cwd=REPO, check=True)
    subprocess.run(
        ["python", "-m", "leanatlas.cli", "load",
         "--structure", str(struct), "--extract", str(extract)],
        cwd=REPO, check=True,
    )

    # 4) Assert HAS_FIELD / HAS_CONSTRUCTOR + node promotion
    cfg = get_config()
    driver = GraphDatabase.driver(cfg.neo4j_uri, auth=(cfg.neo4j_user, cfg.neo4j_password))
    try:
        with driver.session(database=cfg.neo4j_db) as s:
            # HAS_FIELD: D2 -> D2.d2 (own field, hard assertion)
            assert s.run(
                "MATCH (:Declaration {name:'StructEdgesFixture.D2'})-[:HAS_FIELD]->"
                "(:Declaration {name:'StructEdgesFixture.D2.d2'}) RETURN count(*)"
            ).single()[0] == 1
            # HAS_FIELD includes the inherited field D1.d1 (hard assertion —
            # established in T2: an inherited field's projection is the parent
            # structure's projection, i.e. D1.d1, not a child-synthesized
            # D2.d1; this is the flat-inheritance proof)
            assert s.run(
                "MATCH (:Declaration {name:'StructEdgesFixture.D2'})-[:HAS_FIELD]->"
                "(:Declaration {name:'StructEdgesFixture.D1.d1'}) RETURN count(*)"
            ).single()[0] == 1
            # HAS_CONSTRUCTOR: D2 -> D2.mk (structure constructor)
            assert s.run(
                "MATCH (:Declaration {name:'StructEdgesFixture.D2'})-[:HAS_CONSTRUCTOR]->"
                "(:Declaration {name:'StructEdgesFixture.D2.mk'}) RETURN count(*)"
            ).single()[0] == 1
            # HAS_CONSTRUCTOR: Foo -> Foo.c1 / Foo.c2 (inductive multiple constructors)
            assert s.run(
                "MATCH (:Declaration {name:'StructEdgesFixture.Foo'})-[:HAS_CONSTRUCTOR]->"
                "(:Declaration {name:'StructEdgesFixture.Foo.c1'}) RETURN count(*)"
            ).single()[0] == 1
            assert s.run(
                "MATCH (:Declaration {name:'StructEdgesFixture.Foo'})-[:HAS_CONSTRUCTOR]->"
                "(:Declaration {name:'StructEdgesFixture.Foo.c2'}) RETURN count(*)"
            ).single()[0] == 1
            # Promotion: D2.d2 is a Field node, isExternal=false, kind='field',
            # typeSig non-empty
            f = s.run(
                "MATCH (n:Field {name:'StructEdgesFixture.D2.d2'}) "
                "RETURN n.isExternal, n.kind, n.typeSignature"
            ).single()
            assert f is not None and f[0] is False and f[1] == "field" and f[2]
    finally:
        subprocess.run(["python", "-m", "leanatlas.cli", "drop"], cwd=REPO, check=True)
        driver.close()

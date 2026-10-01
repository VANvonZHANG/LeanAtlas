"""End-to-end acceptance test: parse → extract → load → query on
Init.Data.Nat.Basic.

Skipped by default (needs Lean extraction + Neo4j). Enable:
  export MATHLIB_KG_NEO4J_USER=neo4j MATHLIB_KG_NEO4J_PASSWORD=... MATHLIB_KG_NEO4J_DB=neo4j
  export MATHLIB_KG_RUN_ACCEPTANCE=1
  pytest tests/test_acceptance.py -v -s
"""
import json
import os
import subprocess
from pathlib import Path

import pytest
from neo4j import GraphDatabase

from mathlib_kg.config import get_config
from mathlib_kg.models import module_to_json
from mathlib_kg.parse_source import parse_file

pytestmark = pytest.mark.skipif(
    os.environ.get("MATHLIB_KG_RUN_ACCEPTANCE") != "1"
    or not os.environ.get("MATHLIB_KG_NEO4J_PASSWORD"),
    reason="requires MATHLIB_KG_RUN_ACCEPTANCE=1 and Neo4j credentials",
)

REPO = Path(__file__).resolve().parents[1]
EXTRACT_DIR = REPO / "extract"
TOOLCHAIN = "~/.elan/toolchains/leanprover--lean4---v4.30.0/src/lean"
MODULE_SRC = f"{TOOLCHAIN}/Init/Data/Nat/Basic.lean"


def test_init_end_to_end(tmp_path):
    struct = tmp_path / "s.jsonl"
    extract = tmp_path / "e.jsonl"

    # 1) parse
    rec, warnings = parse_file(MODULE_SRC, root=TOOLCHAIN)
    assert warnings == []
    assert len(rec.declarations) >= 3
    struct.write_text(module_to_json(rec) + "\n", encoding="utf-8")

    # 2) extract (real Lean extraction)
    with extract.open("w") as f:
        subprocess.run(
            ["lake", "exe", "extract", "Init.Data.Nat.Basic"],
            cwd=EXTRACT_DIR, stdout=f, check=True,
        )
    recs = [json.loads(ln) for ln in extract.read_text().splitlines() if ln.strip()]
    assert len(recs) > 1000  # full closure

    # 3) load
    subprocess.run(["python", "-m", "mathlib_kg.cli", "drop"], cwd=REPO, check=True)
    subprocess.run(
        ["python", "-m", "mathlib_kg.cli", "load",
         "--structure", str(struct), "--extract", str(extract)],
        cwd=REPO, check=True,
    )

    # 4) Acceptance queries
    cfg = get_config()
    driver = GraphDatabase.driver(cfg.neo4j_uri, auth=(cfg.neo4j_user, cfg.neo4j_password))
    try:
        with driver.session(database=cfg.neo4j_db) as s:
            assert s.run("MATCH ()-[r:DEPENDS_ON]->() RETURN count(r)").single()[0] > 0
            # Parsed declarations got the extract typeSignature via name-merge
            matched = s.run(
                "MATCH (d:Declaration) WHERE d.name='Nat.recCompiled' "
                "AND d.typeSignature IS NOT NULL RETURN count(d)"
            ).single()[0]
            assert matched == 1
            # Reverse dependency closure
            rev = s.run(
                "MATCH (:Declaration {name:'Nat'})<-[:DEPENDS_ON*1..4]-(d) "
                "RETURN count(DISTINCT d)"
            ).single()[0]
            assert rev > 0
    finally:
        subprocess.run(["python", "-m", "mathlib_kg.cli", "drop"], cwd=REPO, check=True)
        driver.close()

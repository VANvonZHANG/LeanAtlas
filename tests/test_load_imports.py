import os

import pytest

from mathlib_kg.config import get_config
from mathlib_kg.load_neo4j import connect, load_imports, load_modules
from mathlib_kg.models import Import, ModuleRecord
from mathlib_kg.neo4j_schema import apply_schema, drop_kg

pytestmark = pytest.mark.skipif(
    not os.environ.get("MATHLIB_KG_NEO4J_PASSWORD"), reason="requires Neo4j credentials"
)


def test_load_imports():
    cfg = get_config()
    driver = connect()
    with driver.session(database=cfg.neo4j_db) as s:
        s.execute_write(drop_kg)
        s.execute_write(apply_schema)
        recs = [
            ModuleRecord(
                module="Mathlib.A",
                path="A.lean",
                imports=[Import(name="Mathlib.B", isPublic=True)],
            ),
            ModuleRecord(module="Mathlib.B", path="B.lean"),
        ]
        s.execute_write(load_modules, recs)
        s.execute_write(load_imports, recs)
        row = s.run(
            "MATCH (:Module {name:'Mathlib.A'})-[r:IMPORTS]->(:Module {name:'Mathlib.B'}) "
            "RETURN r.isPublic"
        ).single()
        assert row is not None and row[0] is True
    driver.close()

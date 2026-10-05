import os

import pytest

from leanatlas.config import get_config
from leanatlas.load_neo4j import connect, load_declarations, load_modules, load_namespaces
from leanatlas.models import Declaration, Import, ModuleRecord
from leanatlas.neo4j_schema import apply_schema, drop_kg

pytestmark = pytest.mark.skipif(
    not os.environ.get("LEANATLAS_NEO4J_PASSWORD"), reason="requires Neo4j credentials"
)


def _rec() -> ModuleRecord:
    return ModuleRecord(
        module="Mathlib.A",
        path="A.lean",
        tags=["t"],
        authors=["X"],
        imports=[Import(name="Mathlib.B")],
        namespaces=["NS"],
        declarations=[
            Declaration(
                name="NS.foo",
                shortName="foo",
                kind="theorem",
                namespace="NS",
                sourceFile="A.lean",
                startLine=1,
                endLine=2,
                sourceText="theorem foo := rfl",
            )
        ],
    )


def test_load_nodes():
    cfg = get_config()
    driver = connect()
    with driver.session(database=cfg.neo4j_db) as s:
        s.execute_write(drop_kg)
        s.execute_write(apply_schema)
        rec = _rec()
        s.execute_write(load_modules, [rec])
        s.execute_write(load_namespaces, [rec])
        s.execute_write(load_declarations, [rec])
        assert s.run("MATCH (m:Module) RETURN count(m)").single()[0] == 1
        assert s.run("MATCH (n:Namespace) RETURN count(n)").single()[0] == 1
        assert s.run("MATCH (d:Declaration) RETURN count(d)").single()[0] == 1
        assert s.run("MATCH (d:Theorem) RETURN count(d)").single()[0] == 1
        assert (
            s.run(
                "MATCH (d:Declaration)-[:IN_NAMESPACE]->(:Namespace {name:'NS'}) "
                "RETURN count(d)"
            ).single()[0]
            == 1
        )
        assert (
            s.run(
                "MATCH (d:Declaration)-[:DEFINED_IN]->(:Module {name:'Mathlib.A'}) "
                "RETURN count(d)"
            ).single()[0]
            == 1
        )
        # SUBNAMESPACE_OF: NS itself has no parent; there is only 1 namespace here
        assert s.run("MATCH ()-[:SUBNAMESPACE_OF]->() RETURN count(*)").single()[0] == 0
    driver.close()

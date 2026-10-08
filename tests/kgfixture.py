"""Shared gated-test fixture graph (spec-level minimal): two modules, one
extract-only declaration, one cross-module dependency, one external dep.
Each gated test file calls load_fixture() itself; it wipes the configured DB."""
import os

import pytest

from leanatlas.config import get_config
from leanatlas.load_neo4j import (
    connect,
    load_declarations,
    load_dependencies_chunked,
    load_imports,
    load_modules,
)
from leanatlas.models import (
    CtorItem,
    Declaration,
    Dep,
    ExtractRecord,
    Import,
    ModuleRecord,
)
from leanatlas.neo4j_schema import apply_schema, drop_kg_batched

requires_neo4j = pytest.mark.skipif(
    not os.environ.get("LEANATLAS_NEO4J_PASSWORD"), reason="requires Neo4j credentials"
)


def fixture_records() -> tuple[list[ModuleRecord], list[ExtractRecord]]:
    recs = [
        ModuleRecord(
            module="Mathlib.B", path="Mathlib/B.lean", docstring="B module", title="B",
            declarations=[Declaration(
                name="Mathlib.B.base", shortName="base", kind="def",
                namespace="Mathlib.B", sourceFile="Mathlib/B.lean", startLine=3,
                endLine=4, sourceText="def base := 1", docstring="the base",
            )],
        ),
        ModuleRecord(
            module="Mathlib.A", path="Mathlib/A.lean", docstring="A module", title="A",
            imports=[Import(name="Mathlib.B")],
            declarations=[Declaration(
                name="Mathlib.A.user", shortName="user", kind="theorem",
                namespace="Mathlib.A", sourceFile="Mathlib/A.lean", startLine=5,
                endLine=6, sourceText="theorem user : 1 = 1 := rfl",
                docstring="uses base",
            )],
        ),
    ]
    ext = [
        ExtractRecord(name="Mathlib.B.base", typeSignature="Nat", module="Mathlib.B",
                      deps=[Dep(name="Nat", inValue=True)]),
        ExtractRecord(name="Mathlib.A.user", typeSignature="B.base → True",
                      module="Mathlib.A",
                      deps=[Dep(name="Mathlib.B.base", inValue=True),
                            Dep(name="_private.A.0.gen", inType=True)]),
        ExtractRecord(name="_private.A.0.gen", typeSignature="Gen", module="Mathlib.A",
                      constructors=[CtorItem(name="mk", position=0)]),
    ]
    return recs, ext


def load_fixture() -> None:
    cfg = get_config()
    driver = connect()
    recs, ext = fixture_records()
    with driver.session(database=cfg.neo4j_db) as s:
        s.execute_write(drop_kg_batched)
        s.execute_write(apply_schema)
        s.execute_write(load_modules, recs)
        s.execute_write(load_declarations, recs)
        s.execute_write(load_imports, recs)
        load_dependencies_chunked(s, ext)
    driver.close()

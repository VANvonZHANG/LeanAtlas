"""Gated: v3 module attribution in load_dependencies. Wipes the configured DB."""
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

pytestmark = pytest.mark.skipif(
    not os.environ.get("LEANATLAS_NEO4J_PASSWORD"), reason="requires Neo4j credentials"
)


def test_module_attribution_backfills_extract_only_decls():
    cfg = get_config()
    driver = connect()
    with driver.session(database=cfg.neo4j_db) as s:
        s.execute_write(drop_kg_batched)
        s.execute_write(apply_schema)
        rec = ModuleRecord(
            module="Mathlib.A",
            path="A.lean",
            imports=[Import(name="Mathlib.B")],
            declarations=[
                Declaration(
                    name="Mathlib.A.src", shortName="src", kind="def",
                    namespace="Mathlib.A", sourceFile="A.lean", startLine=3,
                    endLine=4, sourceText="def src := 1",
                )
            ],
        )
        s.execute_write(load_modules, [rec])
        s.execute_write(load_declarations, [rec])
        s.execute_write(load_imports, [rec])
        ext = [
            # source-visible: structure kind 'def' must survive the record's
            # instance-shaped fallback (coalesce keeps parsed kinds)
            ExtractRecord(name="Mathlib.A.src", typeSignature="S",
                          instantiates="Foo", module="Mathlib.A"),
            # extract-only (auto-generated): placeholder becomes attributed,
            # kind falls back to the record shape (constructors → inductive)
            ExtractRecord(name="_private.Mathlib.A.0.autogen", typeSignature="G",
                          constructors=[CtorItem(name="c", position=0)],
                          module="Mathlib.A"),
            # dependency without its own record stays an unattributed placeholder
            ExtractRecord(name="Mathlib.A.src", typeSignature="S",
                          deps=[Dep(name="Nat.zero", inValue=True)], module="Mathlib.A"),
        ]
        load_dependencies_chunked(s, ext)
        rows = s.run(
            "MATCH (d:Declaration) WHERE d.name IN "
            "['Mathlib.A.src', '_private.Mathlib.A.0.autogen', 'Nat.zero'] "
            "RETURN d.name AS name, d.module AS module, d.kind AS kind, "
            "d.typeSignature AS sig, d.isExternal AS ext ORDER BY name"
        ).data()
    driver.close()
    by = {r["name"]: r for r in rows}
    assert by["Mathlib.A.src"] == {
        "name": "Mathlib.A.src", "module": "Mathlib.A", "kind": "def",
        "sig": "S", "ext": False,
    }
    assert by["_private.Mathlib.A.0.autogen"] == {
        "name": "_private.Mathlib.A.0.autogen", "module": "Mathlib.A",
        "kind": "inductive", "sig": "G", "ext": True,
    }
    assert by["Nat.zero"]["module"] is None
    assert by["Nat.zero"]["ext"] is True

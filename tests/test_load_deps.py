import os

import pytest

from mathlib_kg.config import get_config
from mathlib_kg.load_neo4j import connect, load_declarations, load_dependencies
from mathlib_kg.models import Declaration, Dep, ExtractRecord, ModuleRecord
from mathlib_kg.neo4j_schema import apply_schema, drop_kg

pytestmark = pytest.mark.skipif(
    not os.environ.get("MATHLIB_KG_NEO4J_PASSWORD"), reason="需要 Neo4j 凭据"
)


def test_load_dependencies_with_external_placeholder():
    cfg = get_config()
    driver = connect()
    with driver.session(database=cfg.neo4j_db) as s:
        s.execute_write(drop_kg)
        s.execute_write(apply_schema)
        rec = ModuleRecord(
            module="Mathlib.A",
            path="A.lean",
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
        s.execute_write(load_declarations, [rec])
        ext = [
            ExtractRecord(
                name="NS.foo",
                typeSignature="P",
                deps=[
                    Dep(name="NS.bar", inValue=True),
                    Dep(name="Nat", inValue=True),
                ],
            )
        ]
        s.execute_write(load_dependencies, ext)
        # 外部占位 Nat
        nat = s.run("MATCH (d:Declaration {name:'Nat'}) RETURN d.isExternal").single()
        assert nat is not None and nat[0] is True
        # NS.bar 也是占位（未在 structure 中）
        bar = s.run("MATCH (d:Declaration {name:'NS.bar'}) RETURN d.isExternal").single()
        assert bar is not None and bar[0] is True
        # 真实声明 NS.foo 不是外部，且 typeSignature 已写入
        foo = s.run(
            "MATCH (d:Declaration {name:'NS.foo'}) RETURN d.isExternal, d.typeSignature"
        ).single()
        assert foo[0] is False and foo[1] == "P"
        # DEPENDS_ON 边 context=value
        edge = s.run(
            "MATCH (:Declaration {name:'NS.foo'})-[r:DEPENDS_ON]->(:Declaration {name:'NS.bar'}) "
            "RETURN r.context"
        ).single()
        assert edge is not None and edge[0] == "value"
    driver.close()

import os

import pytest

from mathlib_kg.config import get_config
from mathlib_kg.load_neo4j import connect, load_declarations, load_dependencies, load_relationships
from mathlib_kg.models import Declaration, Dep, DeprecatedBy, ExtractRecord, ExtendsItem, ModuleRecord
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


def test_load_relationships_four_edge_types():
    cfg = get_config()
    driver = connect()
    with driver.session(database=cfg.neo4j_db) as s:
        s.execute_write(drop_kg)
        s.execute_write(apply_schema)
        # 真实声明：B、instB、oldB、newB、A、foo（占位由 loader 自动补：MyClass 外部父类、ext 占位）
        rec = ModuleRecord(
            module="M",
            path="M.lean",
            declarations=[
                Declaration(name="B", shortName="B", kind="class", namespace="",
                            sourceFile="M.lean", startLine=1, endLine=2, sourceText=""),
                Declaration(name="instB", shortName="instB", kind="instance", namespace="",
                            sourceFile="M.lean", startLine=1, endLine=2, sourceText=""),
                Declaration(name="oldB", shortName="oldB", kind="def", namespace="",
                            sourceFile="M.lean", startLine=1, endLine=2, sourceText=""),
                Declaration(name="newB", shortName="newB", kind="def", namespace="",
                            sourceFile="M.lean", startLine=1, endLine=2, sourceText=""),
                Declaration(name="A", shortName="A", kind="class", namespace="",
                            sourceFile="M.lean", startLine=1, endLine=2, sourceText=""),
                Declaration(name="foo", shortName="foo", kind="def", namespace="",
                            sourceFile="M.lean", startLine=1, endLine=2, sourceText=""),
            ],
        )
        s.execute_write(load_declarations, [rec])
        ext = [
            ExtractRecord(name="B", typeSignature="T",
                          extends=[ExtendsItem(parent="A", position=0)]),
            ExtractRecord(name="instB", typeSignature="B",
                          instantiates="B", instancePriority=100),
            ExtractRecord(name="oldB", typeSignature="Nat",
                          deprecatedBy=DeprecatedBy(replacement="newB", since="2024-01-01")),
            # 外部父类 + 外部加法版本目标（测占位）
            ExtractRecord(name="C", typeSignature="T",
                          extends=[ExtendsItem(parent="Ext.FunLike", position=0)]),
            ExtractRecord(name="foo", typeSignature="...",
                          additiveVersion="foo_add"),
        ]
        s.execute_write(load_relationships, ext)

        # EXTENDS：B -[:EXTENDS {position:0}]-> A
        e = s.run("MATCH (:Declaration {name:'B'})-[r:EXTENDS]->(:Declaration {name:'A'}) "
                  "RETURN r.position").single()
        assert e is not None and e[0] == 0
        # 外部父类建了占位
        ext_p = s.run("MATCH (d:Declaration {name:'Ext.FunLike'}) RETURN d.isExternal").single()
        assert ext_p is not None and ext_p[0] is True

        # INSTANTIATES：instB -[:INSTANTIATES {priority:100}]-> B
        i = s.run("MATCH (:Declaration {name:'instB'})-[r:INSTANTIATES]->(:Declaration {name:'B'}) "
                  "RETURN r.priority").single()
        assert i is not None and i[0] == 100

        # DEPRECATED_BY：oldB -[:DEPRECATED_BY {since}]-> newB
        d = s.run("MATCH (:Declaration {name:'oldB'})-[r:DEPRECATED_BY]->(:Declaration {name:'newB'}) "
                  "RETURN r.since").single()
        assert d is not None and d[0] == "2024-01-01"

        # HAS_ADDITIVE_VERSION：foo -> foo_add（占位）
        av = s.run("MATCH (:Declaration {name:'foo'})-[:HAS_ADDITIVE_VERSION]->"
                   "(t:Declaration) RETURN t.name, t.isExternal").single()
        assert av is not None and av[0] == "foo_add" and av[1] is True

        # CREATE 语义：单次装载内同 (src,dst,type) 唯一，不翻倍（fixture 每对唯一）。
        # 注：CREATE 非幂等；全量重建的幂等性来自 drop-then-load（见 Global Constraints），
        # 故此处只验单次装载不重，不重复调用 load_relationships。
        ext_cnt = s.run("MATCH (:Declaration {name:'B'})-[r:EXTENDS]->(:Declaration {name:'A'}) "
                        "RETURN count(r)").single()[0]
        assert ext_cnt == 1
    driver.close()

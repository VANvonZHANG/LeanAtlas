import os

import pytest

from mathlib_kg.config import get_config
from mathlib_kg.load_neo4j import connect, load_declarations, load_dependencies, load_fields_constructors, load_relationships
from mathlib_kg.models import CtorItem, Declaration, Dep, DeprecatedBy, ExtractRecord, ExtendsItem, FieldItem, ModuleRecord
from mathlib_kg.neo4j_schema import apply_schema, drop_kg, drop_kg_batched

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


def test_load_fields_constructors():
    cfg = get_config()
    driver = connect()
    with driver.session(database=cfg.neo4j_db) as s:
        s.execute_write(drop_kg)
        s.execute_write(apply_schema)
        # mathlib 类型 D2（在 type_names）；外部类型 Nat（不在）
        rec = ModuleRecord(
            module="M", path="M.lean",
            declarations=[
                Declaration(name="StructEdgesFixture.D2", shortName="D2", kind="class",
                            namespace="", sourceFile="M.lean", startLine=1, endLine=2, sourceText=""),
            ],
        )
        s.execute_write(load_declarations, [rec])
        type_names = {"StructEdgesFixture.D2"}
        ext = [
            # D2：扁平字段（含继承）+ 构造子
            ExtractRecord(
                name="StructEdgesFixture.D2", typeSignature="Type",
                fields=[FieldItem(name="StructEdgesFixture.D2.d1", position=0),
                        FieldItem(name="StructEdgesFixture.D2.d2", position=1)],
                constructors=[CtorItem(name="StructEdgesFixture.D2.mk", position=0)]),
            # 字段/构造子常量自己的记录（带 typeSig，测补写）
            ExtractRecord(name="StructEdgesFixture.D2.d1", typeSignature="D2 → Nat"),
            ExtractRecord(name="StructEdgesFixture.D2.d2", typeSignature="D2 → Nat"),
            ExtractRecord(name="StructEdgesFixture.D2.mk", typeSignature="..."),
            # 外部类型 Nat：有 fields/constructors 但不在 type_names → 不展开
            ExtractRecord(
                name="Nat", typeSignature="Type",
                fields=[FieldItem(name="Nat.foo", position=0)],
                constructors=[CtorItem(name="Nat.zero", position=0)]),
        ]
        s.execute_write(load_fields_constructors, ext, type_names)

        # HAS_FIELD: D2 -> D2.d1 {position:0}
        hf = s.run("MATCH (:Declaration {name:'StructEdgesFixture.D2'})-[r:HAS_FIELD]->"
                   "(:Field {name:'StructEdgesFixture.D2.d1'}) RETURN r.position").single()
        assert hf is not None and hf[0] == 0
        # HAS_CONSTRUCTOR: D2 -> D2.mk {position:0}
        hc = s.run("MATCH (:Declaration {name:'StructEdgesFixture.D2'})-[r:HAS_CONSTRUCTOR]->"
                   "(:Constructor {name:'StructEdgesFixture.D2.mk'}) RETURN r.position").single()
        assert hc is not None and hc[0] == 0
        # 扶正：D2.d1 是 Field 节点，isExternal=false, kind='field', typeSig 补写成功
        f = s.run("MATCH (n:Field {name:'StructEdgesFixture.D2.d1'}) "
                  "RETURN n.isExternal, n.kind, n.typeSignature").single()
        assert f is not None and f[0] is False and f[1] == "field" and f[2] == "D2 → Nat"
        # 构造子扶正
        c = s.run("MATCH (n:Constructor {name:'StructEdgesFixture.D2.mk'}) "
                  "RETURN n.isExternal, n.kind").single()
        assert c is not None and c[0] is False and c[1] == "constructor"
        # 外部不展开：Nat 无 HAS_FIELD/HAS_CONSTRUCTOR，Nat.foo 不被建为 Field
        assert s.run("MATCH (:Declaration {name:'Nat'})-[:HAS_FIELD]->() RETURN count(*)").single()[0] == 0
        assert s.run("MATCH (:Declaration {name:'Nat'})-[:HAS_CONSTRUCTOR]->() RETURN count(*)").single()[0] == 0
        assert s.run("MATCH (n:Field {name:'Nat.foo'}) RETURN count(n)").single()[0] == 0
    driver.close()


def test_drop_kg_batched_clears_field_ctor_edges():
    """v2 教训：drop_kg_batched 清理元组漏边类型 → 删节点时 ConstraintValidationFailed。
    本测试先造 HAS_FIELD/HAS_CONSTRUCTOR 边，再 batched drop，断言边与节点清零。"""
    cfg = get_config()
    driver = connect()
    with driver.session(database=cfg.neo4j_db) as s:
        s.execute_write(drop_kg)
        s.execute_write(apply_schema)
        rec = ModuleRecord(
            module="M", path="M.lean",
            declarations=[Declaration(name="T", shortName="T", kind="class",
                                      namespace="", sourceFile="M.lean",
                                      startLine=1, endLine=2, sourceText="")],
        )
        s.execute_write(load_declarations, [rec])
        ext = [
            ExtractRecord(name="T", typeSignature="Type",
                          fields=[FieldItem(name="T.f", position=0)],
                          constructors=[CtorItem(name="T.mk", position=0)]),
            ExtractRecord(name="T.f", typeSignature="T → Nat"),
            ExtractRecord(name="T.mk", typeSignature="..."),
        ]
        s.execute_write(load_fields_constructors, ext, {"T"})
        # 此时图有 HAS_FIELD/HAS_CONSTRUCTOR 边 + Field/Constructor 节点
        assert s.run("MATCH ()-[r:HAS_FIELD]->() RETURN count(r)").single()[0] >= 1
        # batched drop（生产路径用的清理）必须不抛异常且清零
        drop_kg_batched(s)
        assert s.run("MATCH ()-[r:HAS_FIELD]->() RETURN count(r)").single()[0] == 0
        assert s.run("MATCH ()-[r:HAS_CONSTRUCTOR]->() RETURN count(r)").single()[0] == 0
        assert s.run("MATCH (n:Declaration) RETURN count(n)").single()[0] == 0
    driver.close()

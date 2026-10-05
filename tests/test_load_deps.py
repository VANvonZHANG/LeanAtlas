import os

import pytest

from leanatlas.config import get_config
from leanatlas.load_neo4j import connect, load_declarations, load_dependencies, load_fields_constructors, load_relationships
from leanatlas.models import CtorItem, Declaration, Dep, DeprecatedBy, ExtractRecord, ExtendsItem, FieldItem, ModuleRecord
from leanatlas.neo4j_schema import apply_schema, drop_kg, drop_kg_batched

pytestmark = pytest.mark.skipif(
    not os.environ.get("LEANATLAS_NEO4J_PASSWORD"), reason="requires Neo4j credentials"
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
        # External placeholder Nat
        nat = s.run("MATCH (d:Declaration {name:'Nat'}) RETURN d.isExternal").single()
        assert nat is not None and nat[0] is True
        # NS.bar is also a placeholder (absent from structure)
        bar = s.run("MATCH (d:Declaration {name:'NS.bar'}) RETURN d.isExternal").single()
        assert bar is not None and bar[0] is True
        # The real declaration NS.foo is not external, and its typeSignature was written
        foo = s.run(
            "MATCH (d:Declaration {name:'NS.foo'}) RETURN d.isExternal, d.typeSignature"
        ).single()
        assert foo[0] is False and foo[1] == "P"
        # DEPENDS_ON edge context=value
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
        # Real declarations: B, instB, oldB, newB, A, foo (placeholders are
        # auto-added by the loader: MyClass external parent, ext placeholder)
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
            # External parent class + external additive-version target (tests placeholders)
            ExtractRecord(name="C", typeSignature="T",
                          extends=[ExtendsItem(parent="Ext.FunLike", position=0)]),
            ExtractRecord(name="foo", typeSignature="...",
                          additiveVersion="foo_add"),
        ]
        s.execute_write(load_relationships, ext)

        # EXTENDS: B -[:EXTENDS {position:0}]-> A
        e = s.run("MATCH (:Declaration {name:'B'})-[r:EXTENDS]->(:Declaration {name:'A'}) "
                  "RETURN r.position").single()
        assert e is not None and e[0] == 0
        # The external parent class got a placeholder
        ext_p = s.run("MATCH (d:Declaration {name:'Ext.FunLike'}) RETURN d.isExternal").single()
        assert ext_p is not None and ext_p[0] is True

        # INSTANTIATES: instB -[:INSTANTIATES {priority:100}]-> B
        i = s.run("MATCH (:Declaration {name:'instB'})-[r:INSTANTIATES]->(:Declaration {name:'B'}) "
                  "RETURN r.priority").single()
        assert i is not None and i[0] == 100

        # DEPRECATED_BY: oldB -[:DEPRECATED_BY {since}]-> newB
        d = s.run("MATCH (:Declaration {name:'oldB'})-[r:DEPRECATED_BY]->(:Declaration {name:'newB'}) "
                  "RETURN r.since").single()
        assert d is not None and d[0] == "2024-01-01"

        # HAS_ADDITIVE_VERSION: foo -> foo_add (placeholder)
        av = s.run("MATCH (:Declaration {name:'foo'})-[:HAS_ADDITIVE_VERSION]->"
                   "(t:Declaration) RETURN t.name, t.isExternal").single()
        assert av is not None and av[0] == "foo_add" and av[1] is True

        # CREATE semantics: within a single load, the same (src,dst,type) is
        # unique and does not double (each fixture pair is unique).
        # Note: CREATE is not idempotent; full-rebuild idempotence comes from
        # drop-then-load (see Global Constraints), so here we only verify a
        # single load does not duplicate — we do not call load_relationships twice.
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
        # mathlib type D2 (in type_names); external type Nat (not in it)
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
            # D2: flattened fields (including inherited) + constructors
            ExtractRecord(
                name="StructEdgesFixture.D2", typeSignature="Type",
                fields=[FieldItem(name="StructEdgesFixture.D2.d1", position=0),
                        FieldItem(name="StructEdgesFixture.D2.d2", position=1)],
                constructors=[CtorItem(name="StructEdgesFixture.D2.mk", position=0)]),
            # The field/constructor constants' own records (carrying typeSig;
            # tests the backfill)
            ExtractRecord(name="StructEdgesFixture.D2.d1", typeSignature="D2 → Nat"),
            ExtractRecord(name="StructEdgesFixture.D2.d2", typeSignature="D2 → Nat"),
            ExtractRecord(name="StructEdgesFixture.D2.mk", typeSignature="..."),
            # External type Nat: has fields/constructors but is not in
            # type_names → not expanded
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
        # Promotion: D2.d1 is a Field node, isExternal=false, kind='field',
        # typeSig backfilled successfully
        f = s.run("MATCH (n:Field {name:'StructEdgesFixture.D2.d1'}) "
                  "RETURN n.isExternal, n.kind, n.typeSignature").single()
        assert f is not None and f[0] is False and f[1] == "field" and f[2] == "D2 → Nat"
        # Constructor promotion
        c = s.run("MATCH (n:Constructor {name:'StructEdgesFixture.D2.mk'}) "
                  "RETURN n.isExternal, n.kind").single()
        assert c is not None and c[0] is False and c[1] == "constructor"
        # Externals not expanded: Nat has no HAS_FIELD/HAS_CONSTRUCTOR, and
        # Nat.foo is not created as a Field
        assert s.run("MATCH (:Declaration {name:'Nat'})-[:HAS_FIELD]->() RETURN count(*)").single()[0] == 0
        assert s.run("MATCH (:Declaration {name:'Nat'})-[:HAS_CONSTRUCTOR]->() RETURN count(*)").single()[0] == 0
        assert s.run("MATCH (n:Field {name:'Nat.foo'}) RETURN count(n)").single()[0] == 0
    driver.close()


def test_drop_kg_batched_clears_field_ctor_edges():
    """v2 lesson learned: drop_kg_batched's cleanup tuple missed edge types →
    ConstraintValidationFailed when deleting nodes. This test first creates
    HAS_FIELD/HAS_CONSTRUCTOR edges, then batched-drops, asserting edges and
    nodes are cleared to zero."""
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
        # The graph now has HAS_FIELD/HAS_CONSTRUCTOR edges + Field/Constructor nodes
        assert s.run("MATCH ()-[r:HAS_FIELD]->() RETURN count(r)").single()[0] >= 1
        # Batched drop (the cleanup used by the production path) must not raise
        # and must clear everything
        drop_kg_batched(s)
        assert s.run("MATCH ()-[r:HAS_FIELD]->() RETURN count(r)").single()[0] == 0
        assert s.run("MATCH ()-[r:HAS_CONSTRUCTOR]->() RETURN count(r)").single()[0] == 0
        assert s.run("MATCH (n:Declaration) RETURN count(n)").single()[0] == 0
    driver.close()

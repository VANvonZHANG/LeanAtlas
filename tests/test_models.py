from datetime import date

from leanatlas.models import (
    Declaration,
    Dep,
    ExtractRecord,
    Import,
    ModuleRecord,
    extract_from_json,
    extract_to_json,
    module_from_json,
    module_to_json,
)


def test_module_roundtrip():
    m = ModuleRecord(
        module="Mathlib.Algebra.Quandle",
        path="Mathlib/Algebra/Quandle.lean",
        docstring="doc",
        title="Racks",
        tags=["rack"],
        authors=["Kyle Miller"],
        isDeprecated=False,
        imports=[Import(name="Mathlib.Data.Set.Basic", isPublic=True)],
        namespaces=["Quandles"],
        declarations=[
            Declaration(
                name="Shelf",
                shortName="Shelf",
                kind="class",
                namespace="",
                docstring="act",
                sourceFile="f.lean",
                startLine=97,
                endLine=101,
                sourceText="class Shelf ...",
                attrs=["ext"],
                isProtected=False,
                isDeprecated=False,
                deprecatedSince=date(2025, 12, 1),
            )
        ],
    )
    s = module_to_json(m)
    assert module_from_json(s) == m


def test_extract_roundtrip():
    e = ExtractRecord(
        name="Shelf",
        typeSignature="Type u → Sort u",
        deps=[Dep(name="Nat", inType=False, inValue=True)],
    )
    s = extract_to_json(e)
    assert extract_from_json(s) == e


from leanatlas.models import ExtendsItem, DeprecatedBy


def test_extract_record_extends_roundtrip():
    e = ExtractRecord(
        name="StructEdgesFixture.B",
        typeSignature="Type",
        extends=[ExtendsItem(parent="StructEdgesFixture.A", position=0)],
    )
    s = extract_to_json(e)
    back = extract_from_json(s)
    assert back == e
    assert back.extends[0].parent == "StructEdgesFixture.A"
    assert back.extends[0].position == 0


def test_extract_record_instantiates_roundtrip():
    e = ExtractRecord(
        name="StructEdgesFixture.instB",
        typeSignature="B",
        instantiates="StructEdgesFixture.B",
        instancePriority=100,
    )
    back = extract_from_json(extract_to_json(e))
    assert back.instantiates == "StructEdgesFixture.B"
    assert back.instancePriority == 100


def test_extract_record_deprecated_by_roundtrip():
    e = ExtractRecord(
        name="StructEdgesFixture.oldB",
        typeSignature="Nat",
        deprecatedBy=DeprecatedBy(
            replacement="StructEdgesFixture.newB",
            message="use newB instead",
            since="2024-01-01",
        ),
    )
    back = extract_from_json(extract_to_json(e))
    assert back.deprecatedBy.replacement == "StructEdgesFixture.newB"
    assert back.deprecatedBy.message == "use newB instead"
    assert back.deprecatedBy.since == "2024-01-01"


def test_extract_record_additive_version_roundtrip():
    e = ExtractRecord(
        name="StructEdgesFixture.foo",
        typeSignature="...",
        additiveVersion="StructEdgesFixture.addFoo",
    )
    back = extract_from_json(extract_to_json(e))
    assert back.additiveVersion == "StructEdgesFixture.addFoo"


def test_extract_record_new_fields_default_when_absent():
    # Old-format JSON (without the new fields) still decodes; new fields take defaults
    legacy = '{"name":"X","typeSignature":"T","deps":[]}'
    back = extract_from_json(legacy)
    assert back.extends == []
    assert back.instantiates is None
    assert back.instancePriority is None
    assert back.deprecatedBy is None
    assert back.additiveVersion is None


from leanatlas.models import FieldItem, CtorItem


def test_extract_record_fields_roundtrip():
    e = ExtractRecord(
        name="StructEdgesFixture.D2",
        typeSignature="Type",
        fields=[
            FieldItem(name="StructEdgesFixture.D2.d1", position=0),
            FieldItem(name="StructEdgesFixture.D2.d2", position=1),
        ],
    )
    back = extract_from_json(extract_to_json(e))
    assert back == e
    assert [f.name for f in back.fields] == ["StructEdgesFixture.D2.d1", "StructEdgesFixture.D2.d2"]
    assert [f.position for f in back.fields] == [0, 1]


def test_extract_record_constructors_roundtrip():
    e = ExtractRecord(
        name="StructEdgesFixture.Foo",
        typeSignature="Type",
        constructors=[
            CtorItem(name="StructEdgesFixture.Foo.c1", position=0),
            CtorItem(name="StructEdgesFixture.Foo.c2", position=1),
        ],
    )
    back = extract_from_json(extract_to_json(e))
    assert [c.name for c in back.constructors] == ["StructEdgesFixture.Foo.c1", "StructEdgesFixture.Foo.c2"]
    assert [c.position for c in back.constructors] == [0, 1]


def test_extract_record_fields_ctors_default_when_absent():
    # Old-format JSON (without fields/constructors) still decodes; new fields
    # default to empty lists
    legacy = '{"name":"X","typeSignature":"T","deps":[]}'
    back = extract_from_json(legacy)
    assert back.fields == []
    assert back.constructors == []

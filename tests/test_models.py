from datetime import date

from mathlib_kg.models import (
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

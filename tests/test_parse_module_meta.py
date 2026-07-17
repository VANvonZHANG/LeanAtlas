from pathlib import Path

from mathlib_kg.parse_source import parse_module_meta

FIXTURE = Path(__file__).parent / "fixtures" / "sample.lean"


def test_parse_module_meta():
    text = FIXTURE.read_text(encoding="utf-8")
    meta = parse_module_meta(text, str(FIXTURE))
    assert meta.module == "sample"
    assert meta.authors == ["Kyle Miller", "Mario Carneiro"]
    assert meta.title == "Racks and Quandles"
    assert meta.tags == ["rack", "quandle"]
    assert meta.isDeprecated is False
    assert meta.docstring is not None and "racks and quandles" in meta.docstring.lower()
    names = [i.name for i in meta.imports]
    assert names == ["Mathlib.Data.Set.Basic", "Mathlib.Algebra.Group.Basic"]
    assert meta.imports[0].isPublic is True
    assert meta.imports[1].isPublic is False

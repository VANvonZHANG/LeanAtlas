from mathlib_kg.models import module_from_json
from mathlib_kg.parse_source import parse_file, write_structure_jsonl


def test_parse_file(tmp_path):
    src = tmp_path / "Quandle.lean"
    src.write_text(
        "/-\nAuthors: A\n-/\nmodule\nimport Mathlib.Data.Set.Basic\n"
        "/-!\n# Title\n## Tags\nrack\n-/\n"
        "namespace Quandles\ndef x := 1\nend Quandles\n",
        encoding="utf-8",
    )
    rec, warnings = parse_file(str(src))
    assert rec.module == "Quandle"
    assert rec.authors == ["A"]
    assert rec.tags == ["rack"]
    assert rec.imports[0].name == "Mathlib.Data.Set.Basic"
    assert len(rec.declarations) == 1
    assert rec.declarations[0].namespace == "Quandles"
    assert warnings == []


def test_write_structure_jsonl(tmp_path):
    src = tmp_path / "A.lean"
    src.write_text("module\ndef y := 2\n", encoding="utf-8")
    out = tmp_path / "structure.jsonl"
    n = write_structure_jsonl([str(src)], str(out), root=None)
    assert n == 1
    line = out.read_text(encoding="utf-8").strip()
    rec = module_from_json(line)
    assert rec.module == "A"


def test_module_name_with_root(tmp_path):
    root = tmp_path / "Mathlib"
    (root / "Algebra").mkdir(parents=True)
    src = root / "Algebra" / "Quandle.lean"
    src.write_text("module\ndef z := 3\n", encoding="utf-8")
    rec, _ = parse_file(str(src), root=str(root))
    assert rec.module == "Algebra.Quandle"

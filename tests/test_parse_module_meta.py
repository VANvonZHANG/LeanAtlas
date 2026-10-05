from pathlib import Path

from leanatlas.parse_source import parse_module_meta

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


def test_docstring_example_imports_not_captured():
    # MinImports-style bug: example import lines inside a module docstring
    # (or a fenced code block) must not become fake import edges.
    text = "\n".join([
        "/-",
        "Copyright (c) 2024 Example Author. All rights reserved.",
        "Released under Apache 2.0 license as described in the file LICENSE.",
        "Authors: Example Author",
        "-/",
        "module",
        "",
        "public import Mathlib.Tactic.Common",
        "",
        "/-!",
        "# `#min_imports in`",
        "",
        "To use the command, first add",
        "",
        "```lean",
        "import Mathlib.Data.Sym.Sym2.Init",
        "```",
        "",
        "to the top of your file.",
        "-/",
        "",
        "open Lean Elab Command Meta in Mathlib",
        "",
        "elab_rules : command",
        '  | "(#min_imports in " stx ")" => do',
        "    -- see also: import Mathlib.Order.Basic",
        "    return",
    ])
    meta = parse_module_meta(text, "MinImports.lean")
    names = [i.name for i in meta.imports]
    assert names == ["Mathlib.Tactic.Common"]


def test_header_imports_captured():
    text = "\n".join([
        "/-",
        "Copyright (c) 2020 Example Author. All rights reserved.",
        "Released under Apache 2.0 license as described in the file LICENSE.",
        "Authors: Example Author",
        "-/",
        "",
        "import Mathlib.Data.Set.Basic",
        "import Mathlib.Algebra.Group.Basic",
        "",
        "def foo : Nat := 0",
    ])
    meta = parse_module_meta(text, "Plain.lean")
    names = [i.name for i in meta.imports]
    assert names == ["Mathlib.Data.Set.Basic", "Mathlib.Algebra.Group.Basic"]
    assert all(i.isPublic is False for i in meta.imports)


def test_public_meta_all_modifiers():
    text = "\n".join([
        "module",
        "",
        "public import A",
        "meta import B",
        "public meta import C",
        "import all D",
        "",
        "def foo : Nat := 0",
    ])
    meta = parse_module_meta(text, "Modifiers.lean")
    names = [i.name for i in meta.imports]
    assert names == ["A", "B", "C", "D"]
    assert [i.isPublic for i in meta.imports] == [True, False, True, False]


def test_inline_comment_import():
    text = "\n".join([
        "module",
        "",
        "import /- hi -/ Mathlib.X",
        "",
        "def foo : Nat := 0",
    ])
    meta = parse_module_meta(text, "InlineComment.lean")
    assert [i.name for i in meta.imports] == ["Mathlib.X"]


def test_prelude_and_multiline_block_comment_header():
    text = "\n".join([
        "/-",
        "Copyright (c) 2024 Example Author. All rights reserved.",
        "Released under Apache 2.0 license as described in the file LICENSE.",
        "-/",
        "prelude",
        "",
        "import Lean.Init",
        "import Mathlib.Data.Nat.Basic",
        "",
        "def foo : Nat := 0",
    ])
    meta = parse_module_meta(text, "Prelude.lean")
    names = [i.name for i in meta.imports]
    assert names == ["Lean.Init", "Mathlib.Data.Nat.Basic"]


def test_stops_at_first_command():
    text = "\n".join([
        "module",
        "",
        "import Mathlib.Data.Set.Basic",
        "",
        "open Foo",
        "",
        "import Mathlib.Mid.File.ShouldNotBeCaptured",
        "",
        "def foo : Nat := 0",
    ])
    meta = parse_module_meta(text, "Stops.lean")
    names = [i.name for i in meta.imports]
    assert names == ["Mathlib.Data.Set.Basic"]


def test_line_comments_between_imports():
    text = "\n".join([
        "module",
        "",
        "import Mathlib.Data.Set.Basic",
        "-- keep this linter import explicit",
        "-- (multi-line explanation)",
        "import Mathlib.Tactic.Linter.Header",
        "",
        "def foo : Nat := 0",
    ])
    meta = parse_module_meta(text, "LineComments.lean")
    names = [i.name for i in meta.imports]
    assert names == ["Mathlib.Data.Set.Basic", "Mathlib.Tactic.Linter.Header"]


def test_multi_line_module_docstring_before_imports():
    text = "\n".join([
        "/-!",
        "# Title",
        "",
        "This file does things.",
        "-/",
        "module",
        "",
        "import Mathlib.Data.Set.Basic",
        "",
        "def foo : Nat := 0",
    ])
    meta = parse_module_meta(text, "DocFirst.lean")
    assert [i.name for i in meta.imports] == ["Mathlib.Data.Set.Basic"]


def test_module_keyword_with_trailing_comment():
    # Real-data regression (Mathlib.lean, Mathlib/Tactic/Common.lean): the
    # `module` line can carry a `--` comment with variable whitespace before it.
    text = "\n".join([
        "module  -- shake: keep-all, shake: keep-downstream",
        "",
        "public import Mathlib.Tactic.Common",
        "",
        "def foo : Nat := 0",
    ])
    meta = parse_module_meta(text, "ModuleComment.lean")
    assert [(i.name, i.isPublic) for i in meta.imports] == [
        ("Mathlib.Tactic.Common", True)
    ]

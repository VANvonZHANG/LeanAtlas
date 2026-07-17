from mathlib_kg.parse_source import parse_declarations

TEXT = (
    "namespace Quandles\n"
    "\n"
    "/-- doc -/\n"
    "@[simp]\n"
    "theorem foo (n : ℕ) : n = n := by rfl\n"
    "\n"
    "def bar := 1\n"
    "\n"
    "end Quandles\n"
)


def test_parse_declarations_basic():
    warnings: list[str] = []
    decls = parse_declarations(TEXT, "f.lean", warnings)
    assert warnings == []
    kinds = [d.kind for d in decls]
    assert kinds == ["theorem", "def"]
    foo = decls[0]
    assert foo.name == "foo"
    assert foo.shortName == "foo"
    assert foo.namespace == "Quandles"
    assert "simp" in foo.attrs
    assert foo.docstring == "doc"
    assert foo.startLine == 5
    assert foo.endLine == 7  # def 行（排他上界）
    assert "theorem foo" in foo.sourceText
    bar = decls[1]
    assert bar.name == "bar"
    assert bar.namespace == "Quandles"
    assert bar.sourceText.strip().startswith("def bar")


MULTILINE_DOC = (
    "/--\n"
    "A *unital shelf* is a shelf with a `1`.\n"
    "It satisfies both laws.\n"
    "-/\n"
    "class UnitalShelf (α : Type u) where\n"
    "  one : α\n"
)


def test_parse_declarations_multiline_doc():
    warnings: list[str] = []
    decls = parse_declarations(MULTILINE_DOC, "g.lean", warnings)
    assert warnings == []
    assert len(decls) == 1
    assert decls[0].name == "UnitalShelf"
    assert decls[0].docstring is not None
    assert "unital shelf" in decls[0].docstring.lower()
    assert "both laws" in decls[0].docstring


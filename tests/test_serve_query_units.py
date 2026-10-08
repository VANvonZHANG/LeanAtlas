from leanatlas.serve_query import fulltext_terms, group_deps, group_strip, source_url


def test_fulltext_terms_prefix_stars_each_token():
    assert fulltext_terms("le_iff") == "le_iff*"
    assert fulltext_terms("Nat.add_succ") == "Nat* add_succ*"
    assert fulltext_terms("  foo.bar  ") == "foo* bar*"
    assert fulltext_terms("...") == ""


def test_source_url_maps_module_to_mathlib_blob():
    assert source_url("Mathlib.Order.Basic", 42) == (
        "https://github.com/leanprover-community/mathlib4/blob/master/"
        "Mathlib/Order/Basic.lean#L42"
    )
    assert source_url(None, 42) is None
    assert source_url("Mathlib.Order.Basic", None) is None


def test_group_deps_groups_by_other_module():
    rows = [
        {"other": "Mathlib.A.user", "otherKind": "theorem",
         "otherModule": "Mathlib.A"},
        {"other": "Mathlib.A.helper", "otherKind": "def",
         "otherModule": "Mathlib.A"},
        {"other": "Std.foo", "otherKind": None, "otherModule": "(external)"},
    ]
    out = group_deps("Mathlib.B.base", "in", "def", rows)
    assert out["dir"] == "in" and out["total"] == 3
    assert [g["module"] for g in out["groups"]] == ["(external)", "Mathlib.A"]
    a = out["groups"][1]
    assert a["count"] == 2
    assert a["edges"][0] == {"from": "Mathlib.A.user", "fromKind": "theorem",
                             "to": "Mathlib.B.base", "toKind": "def"}


def test_group_deps_out_reverses_edge_direction():
    rows = [{"other": "Mathlib.B.base", "otherKind": "def",
             "otherModule": "Mathlib.B"}]
    out = group_deps("Mathlib.A.user", "out", "theorem", rows)
    assert out["groups"][0]["edges"][0] == {
        "from": "Mathlib.A.user", "fromKind": "theorem",
        "to": "Mathlib.B.base", "toKind": "def",
    }


def test_group_strip_groups_by_source_decl():
    rows = [
        {"src": "Mathlib.A.user", "srcKind": "theorem",
         "dst": "Mathlib.B.base", "dstKind": "def"},
        {"src": "Mathlib.A.user", "srcKind": "theorem",
         "dst": "Mathlib.B.other", "dstKind": "def"},
    ]
    out = group_strip(rows)
    assert out["total"] == 2
    assert out["groups"] == [{
        "from": "Mathlib.A.user", "kind": "theorem", "count": 2,
        "edges": [{"to": "Mathlib.B.base", "kind": "def"},
                  {"to": "Mathlib.B.other", "kind": "def"}],
    }]

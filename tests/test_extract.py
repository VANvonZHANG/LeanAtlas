"""Golden test for the Extract.lean lake exe (skipped by default: LEAN
extraction is slow).

Enable: export LEANATLAS_SKIP_LEAN=0
"""
import json
import os
import subprocess
from pathlib import Path

import pytest

EXTRACT_DIR = Path(__file__).resolve().parents[1] / "extract"

pytestmark = pytest.mark.skipif(
    os.environ.get("LEANATLAS_SKIP_LEAN", "1") == "1",
    reason="LEAN extraction is slow, skipped by default; set LEANATLAS_SKIP_LEAN=0 to enable",
)


def _run_extract(module: str) -> list[dict]:
    out = subprocess.run(
        ["lake", "exe", "extract", module],
        cwd=EXTRACT_DIR,
        capture_output=True,
        text=True,
        check=True,
    )
    return [json.loads(ln) for ln in out.stdout.splitlines() if ln.strip()]


def test_extract_init_nat_basic():
    recs = _run_extract("Init.Data.Nat.Basic")
    # Structural completeness
    for r in recs[:30]:
        assert "name" in r
        assert "typeSignature" in r
        assert "deps" in r
        for d in r["deps"]:
            assert {"name", "inType", "inValue"} <= set(d.keys())
    # Every record has a non-empty typeSignature
    assert all(r["typeSignature"] for r in recs[:30])
    # At least some declarations carry dependencies
    assert sum(1 for r in recs if r["deps"]) > 0


def test_extract_struct_edges_fixture():
    """v2: EXTENDS/INSTANTIATES are hard assertions;
    DEPRECATED_BY/HAS_ADDITIVE_VERSION are soft assertions (skipped when the
    attr tables are unreadable on v4.30.0, see spec D12).
    """
    # Build the fixture module first (mathlib is already built; building one
    # tiny module takes tens of seconds)
    subprocess.run(["lake", "build", "StructEdgesFixture"], cwd=EXTRACT_DIR, check=True,
                   capture_output=True, text=True)
    recs = _run_extract("StructEdgesFixture")
    by_name = {r["name"]: r for r in recs}

    # EXTENDS: B extends A (hard assertion)
    b = by_name["StructEdgesFixture.B"]
    assert {"parent": "StructEdgesFixture.A", "position": 0} in b["extends"]

    # INSTANTIATES: instB's type head is B (hard assertion)
    inst = by_name["StructEdgesFixture.instB"]
    assert inst["instantiates"] == "StructEdgesFixture.B"

    # INSTANTIATES regression: the parameterized instance instC has type
    # `∀ (α : Type), C α`; the old getAppFn did not descend past forallE, so the
    # head was unreachable → instantiates:null (edge dropped). Here we hard-
    # assert C is reachable after stripping Pi binders (spec: INSTANTIATES
    # Pi-binder bug regression).
    inst_c = by_name["StructEdgesFixture.instC"]
    assert inst_c["instantiates"] == "StructEdgesFixture.C"

    # DEPRECATED_BY: oldB → newB (soft assertion: strictly assert the target
    # name when the attr tables are readable)
    oldb = by_name["StructEdgesFixture.oldB"]
    if oldb.get("deprecatedBy"):
        assert oldb["deprecatedBy"]["replacement"] == "StructEdgesFixture.newB"
        assert oldb["deprecatedBy"]["since"] == "2024-01-01"

    # HAS_ADDITIVE_VERSION: foo → addFoo (soft assertion: strictly assert the
    # target name when the attr tables are readable)
    foo = by_name["StructEdgesFixture.foo"]
    if foo.get("additiveVersion"):
        assert foo["additiveVersion"] == "StructEdgesFixture.addFoo"


def test_extract_fields_constructors_fixture():
    """v2.5: HAS_FIELD (flattened, including inherited) + HAS_CONSTRUCTOR
    (multiple constructors + position)."""
    # Build the fixture first (includes the new D1/D2/Foo; incremental build
    # takes tens of seconds)
    subprocess.run(["lake", "build", "StructEdgesFixture"], cwd=EXTRACT_DIR, check=True,
                   capture_output=True, text=True)
    recs = _run_extract("StructEdgesFixture")
    by_name = {r["name"]: r for r in recs}
    all_names = set(by_name.keys())

    # --- HAS_FIELD (flattened, including inherited) ---
    d2 = by_name["StructEdgesFixture.D2"]
    field_names = {f["name"] for f in d2["fields"]}
    # Hard assertions (established in Step 2):
    #   - own field d2 → projection StructEdgesFixture.D2.d2
    #   - inherited field d1 → Lean reuses the parent structure projection
    #     StructEdgesFixture.D1.d1 (not a child-synthesized D2.d1)
    #   - subobject coercion → StructEdgesFixture.D2.toD1
    #     (getStructureFieldsFlattened defaults to includeSubobjectFields)
    assert "StructEdgesFixture.D2.d2" in field_names
    assert "StructEdgesFixture.D1.d1" in field_names, \
        f"inherited field missing, actual fields={field_names}"
    assert "StructEdgesFixture.D2.toD1" in field_names
    # Cross-check (guards against name-splicing errors): every field name must
    # be a real constant in the env (present among all extract records)
    missing = field_names - all_names
    assert missing == set(), (
        f"fields names not in the env constant set: {missing} "
        "(go back to Step 2 and check getStructureFieldsFlattened's return format)"
    )
    # position is monotone (0..n-1, no duplicates)
    positions = [f["position"] for f in d2["fields"]]
    assert positions == list(range(len(positions)))

    # --- HAS_CONSTRUCTOR (structure mk + inductive multiple constructors) ---
    d2c = by_name["StructEdgesFixture.D2"]
    assert [c["name"] for c in d2c["constructors"]] == ["StructEdgesFixture.D2.mk"]
    assert [c["position"] for c in d2c["constructors"]] == [0]

    foo = by_name["StructEdgesFixture.Foo"]
    ctor_names = {c["name"] for c in foo["constructors"]}
    assert ctor_names == {"StructEdgesFixture.Foo.c1", "StructEdgesFixture.Foo.c2"}
    assert sorted(c["position"] for c in foo["constructors"]) == [0, 1]
    # Non-type constants (e.g. instB) must not have fields/constructors
    inst = by_name["StructEdgesFixture.instB"]
    assert inst["fields"] == [] and inst["constructors"] == []

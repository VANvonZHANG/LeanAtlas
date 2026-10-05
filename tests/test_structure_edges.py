"""Unit tests for module-layer structure-edge resolution (P1.5)."""
from mathlib_kg.structure_edges import (
    REL_TYPES,
    build_module_map,
    resolve_structure_edges,
)

ALIVE = {"Mathlib.A", "Mathlib.B", "Mathlib.C", "Mathlib.Core"}


def rec(name, module, extends=None, instantiates=None, fields=None):
    return {"name": name, "module": module,
            "extends": extends or [], "instantiates": instantiates,
            "fields": fields or []}


def test_module_map_skips_null_and_maps_all():
    records = [rec("X", "Mathlib.A"), rec("Y", None), rec("Z", "Mathlib.B")]
    assert build_module_map(records) == {"X": "Mathlib.A", "Z": "Mathlib.B"}


def test_resolves_extends_instantiates_fields():
    records = [
        rec("Child", "Mathlib.A", extends=[{"parent": "Parent", "position": 0}]),
        rec("Parent", "Mathlib.B"),
        rec("inst", "Mathlib.C", instantiates="Parent"),
        rec("S", "Mathlib.A", fields=[{"name": "Parent.f", "position": 0}]),
    ]
    m = build_module_map(records)
    out = resolve_structure_edges(records, m, ALIVE)
    assert set(out) == set(REL_TYPES)
    assert out["extends"] == [("Mathlib.A", "Mathlib.B")]
    assert out["instantiates"] == [("Mathlib.C", "Mathlib.B")]
    assert out["fields"] == [("Mathlib.A", "Mathlib.B")]


def test_external_target_and_alive_filter_dropped():
    records = [
        rec("C1", "Mathlib.A",
            extends=[{"parent": "Lean.Core", "position": 0}]),  # target unresolvable
        rec("C2", "Mathlib.External", instantiates="Parent"),  # source module not alive
        rec("Parent", "Mathlib.B"),
    ]
    m = build_module_map(records)
    out = resolve_structure_edges(records, m, ALIVE)
    assert out == {"extends": [], "instantiates": [], "fields": []}


def test_selfloop_and_null_source_module_dropped():
    records = [
        rec("Same", "Mathlib.A", instantiates="AlsoSame"),        # same module
        rec("AlsoSame", "Mathlib.A"),
        rec("NoMod", None, instantiates="Parent"),                # null source module
        rec("Parent", "Mathlib.B"),
    ]
    out = resolve_structure_edges(records, build_module_map(records), ALIVE)
    assert out["instantiates"] == []


def test_multi_parent_dedup_and_sorted_output():
    records = [
        rec("Kid", "Mathlib.C",
            extends=[{"parent": "P2", "position": 0}, {"parent": "P1", "position": 1}]),
        rec("P1", "Mathlib.B"), rec("P2", "Mathlib.A"),
        rec("Kid2", "Mathlib.C", extends=[{"parent": "P1", "position": 0}]),
    ]
    out = resolve_structure_edges(records, build_module_map(records), ALIVE)
    # Kid contributes (C,A) and (C,B); Kid2's (C,B) dedups with Kid's
    assert out["extends"] == [("Mathlib.C", "Mathlib.A"), ("Mathlib.C", "Mathlib.B")]


def test_deterministic_sorted_by_name_pair():
    records = [
        rec("Z", "Mathlib.C", instantiates="T1"),
        rec("Y", "Mathlib.A", instantiates="T2"),
        rec("T1", "Mathlib.B"), rec("T2", "Mathlib.Core"),
    ]
    out = resolve_structure_edges(records, build_module_map(records), ALIVE)
    assert out["instantiates"] == [("Mathlib.A", "Mathlib.Core"), ("Mathlib.C", "Mathlib.B")]

"""Module-layer structure edges (EXTENDS / INSTANTIATES / HAS_FIELD) for the
visualization data contract.

Consumes extract.jsonl as emitted by Extract.lean v3, where every record
carries its defining ``module`` (compiler truth via the module index — this
covers auto-generated and ``_private`` declarations that regex source parsing
cannot see). Both endpoints of every relation are resolved to modules with
exact-name lookups; cross-module pairs whose modules are both in the alive
layout set survive, deduped and sorted for byte-identical output.
"""
from __future__ import annotations

import json
from collections.abc import Iterable, Iterator
from pathlib import Path

REL_TYPES = ("extends", "instantiates", "fields")

StructureEdges = dict[str, list[tuple[str, str]]]


def iter_extract_records(path: Path) -> Iterator[dict]:
    """Stream extract.jsonl; skip blank/undecodable lines (they were already
    counted and reported by the Neo4j loader historically; the overlay is
    tolerant of the same loss)."""
    with open(path, encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                continue


def build_module_map(records: Iterable[dict]) -> dict[str, str]:
    """name -> defining module, for records that carry one."""
    out: dict[str, str] = {}
    for r in records:
        m = r.get("module")
        if m:
            out[r["name"]] = m
    return out


def _targets(rel: str, value) -> list[str]:
    """Record field shapes (verified empirically): extends is a list of
    {parent, position}; instantiates is a string; fields is a list of
    {name, position}."""
    if isinstance(value, str):
        return [value]
    return [e["parent"] if rel == "extends" else e["name"] for e in value]


def resolve_structure_edges(
    records: Iterable[dict],
    name_to_module: dict[str, str],
    alive: set[str],
) -> StructureEdges:
    """Collect cross-module relation pairs among alive modules.

    Direction: src = the extending/instantiating/defining module, dst = the
    parent class / instantiated class / field-projection-home module (points
    at the more foundational thing). Self-loops and unresolvable endpoints
    are dropped; each section is deduped and sorted.
    """
    pairs: dict[str, set[tuple[str, str]]] = {t: set() for t in REL_TYPES}
    for r in records:
        src = r.get("module")
        if not src or src not in alive:
            continue
        for rel in REL_TYPES:
            value = r.get(rel)
            if not value:
                continue
            for tgt in _targets(rel, value):
                dst = name_to_module.get(tgt)
                if dst is None and rel == "fields" and "." in tgt:
                    # Fields targets are projection constants (``D1.d1``);
                    # Extract.lean builds them via findField?/getProjFnForField?,
                    # so the owning structure is the name before the final dot.
                    # Exact lookup stays primary (projections are themselves
                    # recorded constants); this fallback only recovers owners
                    # whose projection record is absent from the map.
                    dst = name_to_module.get(tgt.rsplit(".", 1)[0])
                if not dst or dst not in alive or dst == src:
                    continue
                pairs[rel].add((src, dst))
    return {t: sorted(pairs[t]) for t in REL_TYPES}

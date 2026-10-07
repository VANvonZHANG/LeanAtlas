"""Declaration-level drill-down pack for the visualization layer (P2).

Builds declpack.bin: one binary file holding a compact JSON block per module
(the declarations defined in that module plus the dependency edges that stay
inside it), addressed by byte ranges so the web client lazy-loads a single
module's block with an HTTP Range request. File layout:

    [8 bytes little-endian uint64: byte length of the header JSON]
    [header JSON, UTF-8]
    [module blocks concatenated, in sorted module-name order]

Header module offsets are relative to the END of the header (so growing the
header never shifts block offsets). Same inputs -> byte-identical output
(generatedAt comes in via the caller, normalized like layout.write_document).

Truth sources:
- extract.jsonl (Extract.lean v3): per-declaration compiler truth — name,
  defining ``module``, deps[]. Every v3 record carries ``module``.
- structure.jsonl: source-parsed per-module declarations carrying ``kind``;
  joined by (module, name). Declarations the source parse cannot see
  (auto-generated / _private) fall back to a shape-based inference.
- data.json: the alive module set — blocks exist only for modules present as
  nodes (drill targets are exactly the module-layer nodes).

Scope decisions (see plan 2026-10-07): intra-module edges only (cross-module
stays at the module layer); typeSignature omitted (dominant payload); layout
precomputed here so the browser does no graph algorithms at load time.
"""
from __future__ import annotations

import json
import os
import struct
from collections import deque
from collections.abc import Iterable, Iterator
from pathlib import Path

from .layout import _zig  # same-package reuse: tested deterministic zigzag

PREFIX = struct.Struct("<Q")


def iter_jsonl(path: Path) -> Iterator[dict]:
    """Stream a .jsonl file; skip blank/undecodable lines (same tolerance as
    structure_edges.iter_extract_records — one bad line must not abort a
    1.6GB build)."""
    with open(path, encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                continue


def infer_kind(rec: dict) -> str:
    """Kind fallback from the record's own shape, for declarations the source
    parse cannot see. Order matters: instances are their own record kind in
    extract; constructors mark inductives; extends marks classes."""
    if rec.get("instantiates") is not None:
        return "instance"
    if rec.get("constructors"):
        return "inductive"
    if rec.get("extends"):
        return "class"
    return "def"


def collect_kinds(structure_records: Iterable[dict]) -> dict[tuple[str, str], str]:
    """(module, name) -> kind from structure.jsonl parsed declarations."""
    out: dict[tuple[str, str], str] = {}
    for r in structure_records:
        m = r.get("module")
        for d in r.get("declarations") or []:
            k = d.get("kind")
            if m and k:
                out[(m, d["name"])] = k
    return out


def assign_columns(n: int, edges: list[tuple[int, int]]) -> list[tuple[float, float]]:
    """Per-node (x, y): x = longest-path depth on the intra-dep DAG with
    dependencies on the LEFT (matching the module layer's foundation-left
    axis); y = deterministic zigzag slot within the column. edges are
    (src, dst) = src depends on dst. Kahn-style: a node's column is settled
    only after all its deps are placed, so depth(src) = 1 + max(depth(deps)).
    Cycle members (mutual recursion) never settle — they share one overflow
    column past the deepest settled depth, ordered by first appearance."""
    dep_count = [0] * n
    best = [0] * n  # running 1 + max placed-dep depth
    users: list[list[int]] = [[] for _ in range(n)]
    for s, d in edges:
        dep_count[s] += 1
        users[d].append(s)
    depth = [0] * n
    placed = [False] * n
    q = deque(i for i in range(n) if dep_count[i] == 0)
    while q:
        v = q.popleft()
        placed[v] = True
        depth[v] = best[v]
        for u in users[v]:
            best[u] = max(best[u], depth[v] + 1)
            dep_count[u] -= 1
            if dep_count[u] == 0:
                q.append(u)
    overflow = (max(depth) + 1) if n else 0
    cols: list[list[int]] = [[] for _ in range(overflow + 1)]
    for i in range(n):
        cols[depth[i] if placed[i] else overflow].append(i)
    xy = [(0.0, 0.0)] * n
    for c, members in enumerate(cols):
        if not members:
            continue
        members.sort()  # first-appearance order = deterministic
        for slot, i in enumerate(members):
            xy[i] = (float(c), float(_zig(slot)) * 1.5)
    return xy


def node_size(deg: int) -> float:
    """sigma node size from total intra-module degree, clamped like the
    module layer's radii (area-ish scaling, capped so hubs do not swallow
    their column)."""
    return round(1.5 + min(3.0, deg**0.5), 2)


def build_module_block(module: str, decls: list[dict], edges: list[tuple[int, int]]) -> bytes:
    """One module's block: compact JSON, decls array index = node id,
    e pairs [srcIdx, dstIdx] = src depends on dst (points at the more
    foundational declaration — the structureEdges convention, NOT the
    module-layer edges [dep, importer] order). Edge pairs are deduped and
    sorted HERE — this function is the bytes boundary, so a duplicated input
    pair can never reach the emitted block."""
    edges = sorted(set(edges))
    xy = assign_columns(len(decls), edges)
    deg = [0] * len(decls)
    for s, d in edges:
        deg[s] += 1
        deg[d] += 1
    doc = {
        "schemaVersion": 1,
        "module": module,
        "decls": [
            {"name": d["name"], "k": d["k"], "x": xy[i][0], "y": xy[i][1],
             "s": node_size(deg[i])}
            for i, d in enumerate(decls)
        ],
        "e": sorted(edges),
    }
    return json.dumps(doc, separators=(",", ":"), ensure_ascii=True).encode("utf-8")


def build_header(blocks: dict[str, bytes], stats: dict, *, version: str, now: str) -> dict:
    """Pack index. Block offsets are relative to the end of the header so
    they are independent of the header's own serialized length."""
    modules_idx: dict[str, dict[str, int]] = {}
    off = 0
    for m in sorted(blocks):
        modules_idx[m] = {"o": off, "l": len(blocks[m])}
        off += len(blocks[m])
    return {
        "schemaVersion": 1,
        "meta": {"version": version, "generatedAt": now, "scope": "mathlib",
                 "stats": stats},
        "modules": modules_idx,
    }


def write_pack(header: dict, blocks: dict[str, bytes], out: Path) -> None:
    """Atomic write (tmp + os.replace), block order = sorted module names."""
    hb = json.dumps(header, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    tmp = out.with_name(out.name + ".tmp")
    with open(tmp, "wb") as f:
        f.write(PREFIX.pack(len(hb)))
        f.write(hb)
        for m in sorted(blocks):
            f.write(blocks[m])
    os.replace(tmp, out)


def run_declpack(extract_path: Path, structure_path: Path, alive: list[str], *,
                 version: str, now: str) -> tuple[dict, dict[str, bytes]]:
    """Two streaming passes over extract.jsonl (1.6GB — never materialized):
    pass 1 builds name -> module for names defined in alive modules (only
    those can ever be intra-edge targets); pass 2 groups declarations per
    module and records name-pair edges (targets may appear after their users,
    so pairs resolve to indices only after the pass). Decls keep extract-file
    first-appearance order — deterministic for a given mathlib build."""
    alive_set = set(alive)
    kinds = collect_kinds(iter_jsonl(structure_path))

    name2module: dict[str, str] = {}
    for r in iter_jsonl(extract_path):
        m = r.get("module")
        if m in alive_set:
            name2module[r["name"]] = m

    modules: dict[str, dict] = {}
    inferred = 0
    duplicates = 0
    for r in iter_jsonl(extract_path):
        m = r.get("module")
        if m not in alive_set:
            continue
        entry = modules.setdefault(m, {"decls": [], "idx": {}, "raw": []})
        idx = entry["idx"]
        name = r["name"]
        if name in idx:  # duplicate declaration names are a data smell; keep first
            duplicates += 1
            continue
        idx[name] = len(entry["decls"])
        if (m, name) in kinds:
            kind = kinds[(m, name)]
        else:
            kind = infer_kind(r)
            inferred += 1
        entry["decls"].append({"name": name, "k": kind})
        for d in r.get("deps") or []:
            dn = d["name"]
            if dn != name and name2module.get(dn) == m:  # skip self-loops, keep intra
                entry["raw"].append((name, dn))

    blocks: dict[str, bytes] = {}
    total_decls = 0
    total_edges = 0
    for m, entry in modules.items():
        idx = entry["idx"]
        edges = sorted({(idx[s], idx[t]) for s, t in entry["raw"]
                        if s in idx and t in idx})
        blocks[m] = build_module_block(m, entry["decls"], edges)
        total_decls += len(entry["decls"])
        total_edges += len(edges)
    stats = {
        "modules": len(blocks),
        "decls": total_decls,
        "edges": total_edges,
        "kindsInferred": inferred,
        "duplicateNames": duplicates,
    }
    return build_header(blocks, stats, version=version, now=now), blocks

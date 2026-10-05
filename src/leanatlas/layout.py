"""Pure-function core of the layout engine: structure.jsonl records → layout data
consumable by the frontend.

Pipeline: load/filter → topo → bitmask closures → PageRank → swimlane coordinates →
transitive reduction → export. All functions are free of file IO (except
read_structure/describe_mathlib/write_document at the end). Determinism rule:
never iterate sets/dicts on order-sensitive paths; every ordering is either
topological order or name-sorted order.
"""
import os
import subprocess
import sys
import tomllib
from collections import Counter, deque
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import msgspec

from .models import ModuleRecord
from .structure_edges import (
    REL_TYPES,
    build_module_map,
    iter_extract_records,
    resolve_structure_edges,
)

__all__ = [
    "Topic", "DEFAULT_TOPICS", "load_topics", "assign_topic", "assign_topics",
    "Modules", "filter_and_build", "topological_order", "LayoutError", "LayoutCycleError",
    "compute_closures", "transitively_reduce", "pagerank_scores", "radii",
    "assign_positions", "build_document", "write_document", "run_layout",
    "read_structure", "describe_mathlib",
]


class LayoutError(Exception):
    """Expected layout-pipeline failure (empty filter result, bad-line overflow, etc.)."""


class LayoutCycleError(LayoutError):
    """Import cycle detected (Lean theories are acyclic; a data-quality sentinel for the parse)."""

    def __init__(self, sample: list[str]):
        super().__init__("import cycle detected: " + ", ".join(sample))
        self.sample = sample


@dataclass(frozen=True)
class Topic:
    id: str
    label: str
    y: float
    color: str


_FALLBACK_TOPIC = Topic(id="_default", label="Other", y=140.0, color="#202020")

# Built-in fallback table (initially identical to web/topics.toml, 27+1 entries;
# y/color adapted from MathlibExplorer gen_graph.py)
DEFAULT_TOPICS: tuple[Topic, ...] = (
    Topic("Tactic", "Tactic", 40.0, "#404080"),
    Topic("InformationTheory", "InformationTheory", 132.0, "#8000ff"),
    Topic("Combinatorics", "Combinatorics", 130.0, "#800000"),
    Topic("GroupTheory", "GroupTheory", 120.0, "#ff2040"),
    Topic("FieldTheory", "FieldTheory", 125.0, "#ffff80"),
    Topic("RingTheory", "RingTheory", 115.0, "#ff8000"),
    Topic("RepresentationTheory", "RepresentationTheory", 107.0, "#ff0000"),
    Topic("Algebra", "Algebra", 100.0, "#ffff00"),
    Topic("Init", "Init", 90.0, "#008040"),
    Topic("NumberTheory", "NumberTheory", 90.0, "#800000"),
    Topic("LinearAlgebra", "LinearAlgebra", 82.0, "#00ff00"),
    Topic("Order", "Order", 85.0, "#804000"),
    Topic("Logic", "Logic", 75.0, "#0080ff"),
    Topic("SetTheory", "SetTheory", 80.0, "#ff8080"),
    Topic("Data", "Data", 80.0, "#404040"),
    Topic("AlgebraicGeometry", "AlgebraicGeometry", 80.0, "#6040ff"),
    Topic("Computability", "Computability", 75.0, "#bfff00"),
    Topic("ModelTheory", "ModelTheory", 72.0, "#6040ff"),
    Topic("Geometry", "Geometry", 70.0, "#ff80ff"),
    Topic("CategoryTheory", "CategoryTheory", 62.0, "#80a0ff"),
    Topic("Analysis", "Analysis", 57.0, "#00ffff"),
    Topic("AlgebraicTopology", "AlgebraicTopology", 48.0, "#6040ff"),
    Topic("Condensed", "Condensed", 48.0, "#ff0000"),
    Topic("Topology", "Topology", 40.0, "#ff00ff"),
    Topic("MeasureTheory", "MeasureTheory", 30.0, "#8000ff"),
    Topic("Dynamics", "Dynamics", 25.0, "#008040"),
    Topic("Probability", "Probability", 20.0, "#0000ff"),
    _FALLBACK_TOPIC,
)


def load_topics(path: Path | None) -> list[Topic]:
    """Read topics.toml; missing/unparseable/no _default → built-in table + stderr warning."""
    if path is None or not Path(path).exists():
        if path is not None:
            print(f"warn: topics file not found: {path}; using built-in table", file=sys.stderr)
        return list(DEFAULT_TOPICS)
    try:
        raw = tomllib.loads(Path(path).read_text(encoding="utf-8"))
        topics = [Topic(**item) for item in raw["topic"]]
    except Exception as exc:  # noqa: BLE001 — any parse failure falls back
        print(f"warn: cannot parse {path} ({exc}); using built-in table", file=sys.stderr)
        return list(DEFAULT_TOPICS)
    if not any(t.id == "_default" for t in topics):
        print("warn: topics file lacks _default; appending built-in default", file=sys.stderr)
        topics.append(_FALLBACK_TOPIC)
    return topics


def assign_topic(module_name: str, topics: list[Topic]) -> Topic:
    """Table-order priority + trailing-dot prefix matching; unmatched → _default."""
    for t in topics:
        if module_name.startswith(f"Mathlib.{t.id}."):
            return t
    return next((t for t in topics if t.id == "_default"), _FALLBACK_TOPIC)


def assign_topics(names: list[str], topics: list[Topic]) -> list[Topic]:
    return [assign_topic(nm, topics) for nm in names]


@dataclass
class Modules:
    names: list[str]
    index: dict[str, int]
    deps: list[list[int]]
    importers: list[list[int]]
    skipped_external: int
    records: list[ModuleRecord]


def filter_and_build(records: list[ModuleRecord]) -> Modules:
    """Filter to Mathlib.* (drop umbrellas) + build adjacency lists. 0 survivors → LayoutError."""
    kept = sorted(
        (r for r in records
         if r.module != "Mathlib" and r.module.startswith("Mathlib.")),
        key=lambda r: r.module,
    )
    if not kept:
        raise LayoutError("no Mathlib.* modules survived filtering (filter sentinel)")
    index = {r.module: i for i, r in enumerate(kept)}
    deps: list[list[int]] = [[] for _ in kept]
    importers: list[list[int]] = [[] for _ in kept]
    skipped_external = 0
    for i, r in enumerate(kept):
        seen: set[int] = set()
        for imp in r.imports:
            j = index.get(imp.name)
            if j is None:            # external: Lean core / Std / Batteries etc.
                skipped_external += 1
                continue
            if j == i or j in seen:  # self-loop / duplicate import
                continue
            seen.add(j)
            deps[i].append(j)        # i imports j: edge j→i (dep→importer)
            importers[j].append(i)
    return Modules(
        names=[r.module for r in kept], index=index, deps=deps, importers=importers,
        skipped_external=skipped_external, records=kept,
    )


def topological_order(mod: Modules) -> list[int]:
    """Kahn topological sort (dependencies first). Deterministic: the initial queue and
    out-edges are both in ascending index order (= name order)."""
    n = len(mod.names)
    indeg = [len(mod.deps[i]) for i in range(n)]   # dep→importer: indegree = dependency count
    queue = deque(i for i in range(n) if indeg[i] == 0)
    order: list[int] = []
    while queue:
        v = queue.popleft()
        order.append(v)
        for u in mod.importers[v]:                 # already in name order; no re-sort needed
            indeg[u] -= 1
            if indeg[u] == 0:
                queue.append(u)
    if len(order) != n:
        placed = set(order)
        sample = sorted(mod.names[i] for i in range(n) if i not in placed)[:10]
        raise LayoutCycleError(sample)
    return order


def compute_closures(mod: Modules, topo: list[int]) -> list[int]:
    """Transitive-closure bitmaps (a Python big int is a bitset; isomorphic to
    Lean Shake's Bitset).

    Bit j of closure[i] is 1 ⟺ i transitively depends on j (i itself excluded).
    ~8.8k bits × 8.8k nodes ≈ 10MB.
    """
    closures = [0] * len(mod.names)
    for v in topo:                      # v (the dependency) is processed before all its importers
        cv = closures[v] | (1 << v)
        for u in mod.importers[v]:
            closures[u] |= cv
    return closures


def transitively_reduce(mod: Modules, closures: list[int]) -> list[list[int]]:
    """Transitive reduction: drop edges derivable via another direct dependency;
    reachability strictly unchanged."""
    reduced: list[list[int]] = []
    for b in range(len(mod.names)):
        deps_b = mod.deps[b]
        keep: list[int] = []
        for a in deps_b:
            redundant = False
            for d in deps_b:
                if d == a:
                    continue
                if (closures[d] >> a) & 1:   # d transitively depends on a ⟹ b reaches a via d
                    redundant = True
                    break
            if not redundant:
                keep.append(a)
        reduced.append(sorted(keep))
    return reduced


def pagerank_scores(mod: Modules, alpha: float = 0.85, max_iter: int = 30,
                    tol: float = 1e-6) -> list[float]:
    """Foundationality PageRank: each importer splits its rank evenly among the
    modules it imports (= nx.pagerank(G.reverse()) semantics)."""
    n = len(mod.names)
    if n == 0:
        return []
    rank = [1.0 / n] * n
    for _ in range(max_iter):
        nxt = [(1.0 - alpha) / n] * n
        dangling = sum(rank[i] for i in range(n) if not mod.deps[i])
        if dangling:
            share = alpha * dangling / n
            nxt = [x + share for x in nxt]
        for i in range(n):
            di = mod.deps[i]
            if not di:
                continue
            give = alpha * rank[i] / len(di)
            for d in di:
                nxt[d] += give
        delta = sum(abs(nxt[i] - rank[i]) for i in range(n))
        rank = nxt
        if delta < tol:
            break
    return rank


def radii(scores: list[float]) -> list[float]:
    """r = 0.2 + 3·√t (area-aware: area ∝ PageRank)."""
    if not scores:
        return []
    lo, hi = min(scores), max(scores)
    rng = (hi - lo) or 1.0
    return [0.2 + 3.0 * ((s - lo) / rng) ** 0.5 for s in scores]


def _zig(slot: int) -> int:
    """Zigzag offset sequence: 0, +1, -1, +2, -2, ..."""
    if slot == 0:
        return 0
    d = (slot + 1) // 2
    return d if slot % 2 == 1 else -d


def assign_positions(mod: Modules, topo: list[int], closures: list[int],
                     node_topics: list[Topic]) -> tuple[list[float], list[float]]:
    """x = |closure|^0.72 (zero-closure modules spread cyclically over -0..-9 in
    topo order); y = band value → mean of same-topic direct deps within the column
    → deterministic zigzag slot."""
    n = len(mod.names)
    xs = [float(closures[i].bit_count()) ** 0.72 for i in range(n)]
    k = 0
    for v in topo:                          # assigned in topo order (deterministic)
        if closures[v].bit_count() == 0:
            xs[v] = float(-(k % 10))
            k += 1
    ys = [float(t.y) for t in node_topics]
    columns: dict[int, list[int]] = {}
    for v in topo:                          # column members enter in topo order
        columns.setdefault(int(xs[v]), []).append(v)
    for col in sorted(columns):             # process columns in ascending order (deterministic)
        used: dict[int, bool] = {}
        for b in columns[col]:
            tb_id = node_topics[b].id
            vals = [ys[b]] + [ys[d] for d in mod.deps[b] if node_topics[d].id == tb_id]
            avg = sum(vals) / len(vals)
            base = int(avg)
            slot = 0
            probe = base + _zig(slot)
            while used.get(probe, False):
                slot += 1
                probe = base + _zig(slot)
                if slot > 20000:            # safety valve: continue above the highest occupied slot
                    probe = (max(used) + 1) if used else base
                    while used.get(probe, False):
                        probe += 1
                    break
            ys[b] = avg + (probe - base)
            used[probe] = True
    return xs, ys


def build_document(mod: Modules, topo: list[int], topics: list[Topic],
                   node_topics: list[Topic], xs: list[float], ys: list[float],
                   rs: list[float], reduced: list[list[int]], closures: list[int], *,
                   version: str, generated_at: str, scope: str = "mathlib",
                   skipped_bad_lines: int = 0,
                   structure_edges: dict[str, list[tuple[str, str]]] | None = None) -> dict:
    n = len(mod.names)
    pos_of = [0] * n
    for p, v in enumerate(topo):
        pos_of[v] = p
    unmatched = sum(1 for t in node_topics if t.id == "_default")
    nodes = []
    for v in topo:
        t = node_topics[v]
        rec_m = mod.records[v]
        nodes.append({
            "name": mod.names[v],
            "topic": t.id,
            "x": xs[v],
            "y": ys[v],
            "r": rs[v],
            "color": t.color,
            "declCount": len(rec_m.declarations),
            "closureSize": closures[v].bit_count(),
            "isDeprecated": rec_m.isDeprecated,
            "title": rec_m.title,
            "docstring": (rec_m.docstring[:1000] if rec_m.docstring is not None else None),
        })
    edges = [[pos_of[a], pos_of[b]]
             for b in range(n) for a in reduced[b]]      # [dep, importer] in topo-order coordinates
    se_in = structure_edges or {t: [] for t in REL_TYPES}
    # pos_of is index-keyed; structure pairs are module names → look up via mod.index
    structure = {t: sorted([pos_of[mod.index[a]], pos_of[mod.index[b]]] for a, b in se_in[t])
                 for t in REL_TYPES}
    return {
        "schemaVersion": 2,
        "meta": {
            "version": version,
            "generatedAt": generated_at,
            "scope": scope,
            "stats": {
                "modules": n,
                "edgesDirect": sum(len(d) for d in mod.deps),
                "edgesReduced": len(edges),
                "skippedExternalImports": mod.skipped_external,
                "skippedBadLines": skipped_bad_lines,
                "unmatchedTopicModules": unmatched,
                "extendsEdges": len(structure["extends"]),
                "instantiatesEdges": len(structure["instantiates"]),
                "fieldsEdges": len(structure["fields"]),
            },
        },
        "topics": [
            {"id": t.id, "label": t.label, "y": t.y, "color": t.color}
            for t in topics
        ],
        "nodes": nodes,
        "edges": edges,
        "structureEdges": structure,
    }


def write_document(doc: dict, out: Path, *, now: str | None = None) -> None:
    """Atomic write (tmp + os.replace); now overrides generatedAt (for deterministic tests)."""
    if now is not None:
        doc = {**doc, "meta": {**doc["meta"], "generatedAt": now}}
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(out.suffix + ".tmp")
    tmp.write_bytes(msgspec.json.encode(doc))
    os.replace(tmp, out)


def read_structure(path: Path) -> tuple[list[ModuleRecord], int]:
    """Decode ModuleRecord lines (bytes); skip/count corrupted lines, abort at ≥100."""
    decoder = msgspec.json.Decoder(ModuleRecord)
    records: list[ModuleRecord] = []
    bad = 0
    with Path(path).open("rb") as f:   # iterate raw byte lines; splitlines is a known pitfall
        for raw in f:
            line = raw.strip()
            if not line:
                continue
            try:
                records.append(decoder.decode(line))
            except msgspec.DecodeError:
                bad += 1
                if bad >= 100:
                    raise LayoutError(f"structure.jsonl: {bad}+ bad lines, aborting")
    return records, bad


def describe_mathlib(path: Path) -> str:
    """git describe of the mathlib checkout; on failure → "unknown" (non-blocking)."""
    try:
        out = subprocess.run(
            ["git", "-C", str(Path(path)), "describe", "--tags", "--always", "--dirty"],
            capture_output=True, text=True, timeout=10, check=True,
        )
        return out.stdout.strip()
    except Exception:  # noqa: BLE001
        return "unknown"


def run_layout(records: list[ModuleRecord], topics: list[Topic], *, version: str,
               now: str | None = None, skipped_bad_lines: int = 0,
               extract_path: Path | None = None,
               structure_edges: dict[str, list[tuple[str, str]]] | None = None) -> dict:
    """Orchestrate all pure functions; report unmatched topics to stderr.
    Determinism: identical inputs → byte-identical output (inject ``now`` for
    reproducible timestamps; structure_edges overrides extract_path when both given)."""
    mod = filter_and_build(records)
    topo = topological_order(mod)
    closures = compute_closures(mod, topo)
    node_topics = assign_topics(mod.names, topics)
    xs, ys = assign_positions(mod, topo, closures, node_topics)
    rs = radii(pagerank_scores(mod))
    reduced = transitively_reduce(mod, closures)

    structure_pairs = structure_edges
    if structure_pairs is None and extract_path is not None:
        if not Path(extract_path).exists():
            print(f"layout: --extract {extract_path} not found; emitting empty structureEdges",
                  file=sys.stderr)
            structure_pairs = {t: [] for t in REL_TYPES}
        else:
            # two streaming passes: the 1.6 GB extract cannot be held in memory
            m2 = build_module_map(iter_extract_records(Path(extract_path)))
            structure_pairs = resolve_structure_edges(
                iter_extract_records(Path(extract_path)), m2, set(mod.names))

    # Unmatched-topic report: count gray-band modules per second-level prefix
    # (to guide manual topics.toml additions)
    prefixes = Counter()
    for v, t in enumerate(node_topics):
        if t.id == "_default":
            parts = mod.names[v].split(".")
            prefixes[parts[1] if len(parts) > 2 else "(root)"] += 1
    for prefix, cnt in prefixes.most_common():
        print(f"unmatched topic: Mathlib.{prefix}.* × {cnt} → _default", file=sys.stderr)

    generated_at = now or datetime.now(UTC).isoformat(timespec="seconds")
    return build_document(
        mod, topo, topics, node_topics, xs, ys, rs, reduced, closures,
        version=version, generated_at=generated_at, skipped_bad_lines=skipped_bad_lines,
        structure_edges=structure_pairs,
    )

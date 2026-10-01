"""布局引擎纯函数核心：structure.jsonl 记录 → 前端可消费的布局数据。

分层：load/filter → topo → 位图闭包 → PageRank → 泳道坐标 → 传递约简 → export。
全部函数无文件 IO（read_structure/describe_mathlib/write_document 例外，见文末）；确定性总纲：
顺序敏感路径禁用 set/dict 迭代，一切顺序 = 拓扑序或名字排序。
"""
import os
import sys
import tomllib
from collections import deque
from dataclasses import dataclass
from pathlib import Path

import msgspec

from .models import ModuleRecord

__all__ = [
    "Topic", "DEFAULT_TOPICS", "load_topics", "assign_topic", "assign_topics",
    "Modules", "filter_and_build", "topological_order", "LayoutError", "LayoutCycleError",
    "compute_closures", "transitively_reduce", "pagerank_scores", "radii",
    "assign_positions", "build_document", "write_document", "run_layout",
    "read_structure", "describe_mathlib",
]


class LayoutError(Exception):
    """布局管线可预期的失败（过滤器全灭、损坏行超限等）。"""


class LayoutCycleError(LayoutError):
    """检测到 import 环（Lean 理论无环，这是句法解析数据的质量哨兵）。"""

    def __init__(self, sample: list[str]):
        super().__init__("import cycle detected: " + ", ".join(sample))
        self.sample = sample


@dataclass(frozen=True)
class Topic:
    id: str
    label: str
    labelZh: str
    y: float
    color: str


_FALLBACK_TOPIC = Topic(id="_default", label="Other", labelZh="其他", y=140.0, color="#202020")

# 内建 fallback 表（初始 = web/topics.toml 同款，27+1 条；y/color 改编自 MathlibExplorer gen_graph.py）
DEFAULT_TOPICS: tuple[Topic, ...] = (
    Topic("Tactic", "Tactic", "战术", 40.0, "#404080"),
    Topic("InformationTheory", "InformationTheory", "信息论", 132.0, "#8000ff"),
    Topic("Combinatorics", "Combinatorics", "组合数学", 130.0, "#800000"),
    Topic("GroupTheory", "GroupTheory", "群论", 120.0, "#ff2040"),
    Topic("FieldTheory", "FieldTheory", "域论", 125.0, "#ffff80"),
    Topic("RingTheory", "RingTheory", "环论", 115.0, "#ff8000"),
    Topic("RepresentationTheory", "RepresentationTheory", "表示论", 107.0, "#ff0000"),
    Topic("Algebra", "Algebra", "代数", 100.0, "#ffff00"),
    Topic("Init", "Init", "基础", 90.0, "#008040"),
    Topic("NumberTheory", "NumberTheory", "数论", 90.0, "#800000"),
    Topic("LinearAlgebra", "LinearAlgebra", "线性代数", 82.0, "#00ff00"),
    Topic("Order", "Order", "序理论", 85.0, "#804000"),
    Topic("Logic", "Logic", "逻辑", 75.0, "#0080ff"),
    Topic("SetTheory", "SetTheory", "集合论", 80.0, "#ff8080"),
    Topic("Data", "Data", "数据结构", 80.0, "#404040"),
    Topic("AlgebraicGeometry", "AlgebraicGeometry", "代数几何", 80.0, "#6040ff"),
    Topic("Computability", "Computability", "可计算性", 75.0, "#bfff00"),
    Topic("ModelTheory", "ModelTheory", "模型论", 72.0, "#6040ff"),
    Topic("Geometry", "Geometry", "几何", 70.0, "#ff80ff"),
    Topic("CategoryTheory", "CategoryTheory", "范畴论", 62.0, "#80a0ff"),
    Topic("Analysis", "Analysis", "分析", 57.0, "#00ffff"),
    Topic("AlgebraicTopology", "AlgebraicTopology", "代数拓扑", 48.0, "#6040ff"),
    Topic("Condensed", "Condensed", "凝聚数学", 48.0, "#ff0000"),
    Topic("Topology", "Topology", "拓扑", 40.0, "#ff00ff"),
    Topic("MeasureTheory", "MeasureTheory", "测度论", 30.0, "#8000ff"),
    Topic("Dynamics", "Dynamics", "动力系统", 25.0, "#008040"),
    Topic("Probability", "Probability", "概率论", 20.0, "#0000ff"),
    _FALLBACK_TOPIC,
)


def load_topics(path: Path | None) -> list[Topic]:
    """读 topics.toml；缺失/解析失败/无 _default → 内建表 + stderr warn。"""
    if path is None or not Path(path).exists():
        if path is not None:
            print(f"warn: topics file not found: {path}; using built-in table", file=sys.stderr)
        return list(DEFAULT_TOPICS)
    try:
        raw = tomllib.loads(Path(path).read_text(encoding="utf-8"))
        topics = [Topic(**item) for item in raw["topic"]]
    except Exception as exc:  # noqa: BLE001 — 任何解析失败都回退
        print(f"warn: cannot parse {path} ({exc}); using built-in table", file=sys.stderr)
        return list(DEFAULT_TOPICS)
    if not any(t.id == "_default" for t in topics):
        print("warn: topics file lacks _default; appending built-in default", file=sys.stderr)
        topics.append(_FALLBACK_TOPIC)
    return topics


def assign_topic(module_name: str, topics: list[Topic]) -> Topic:
    """表序优先 + 带尾点前缀匹配；未匹配 → _default。"""
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
    """过滤（只 Mathlib.*、删根伞）+ 构建内部邻接表。0 存活 → LayoutError。"""
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
            if j is None:            # Lean core / Std / Batteries 等外部
                skipped_external += 1
                continue
            if j == i or j in seen:  # 自环 / 重复 import
                continue
            seen.add(j)
            deps[i].append(j)        # i import j：边 j→i（dep→importer）
            importers[j].append(i)
    return Modules(
        names=[r.module for r in kept], index=index, deps=deps, importers=importers,
        skipped_external=skipped_external, records=kept,
    )


def topological_order(mod: Modules) -> list[int]:
    """Kahn 拓扑排序（依赖在前）。确定性：初始队列与出边均按索引升序（=名字序）。"""
    n = len(mod.names)
    indeg = [len(mod.deps[i]) for i in range(n)]   # 图向 dep→importer：入度=依赖数
    queue = deque(i for i in range(n) if indeg[i] == 0)
    order: list[int] = []
    while queue:
        v = queue.popleft()
        order.append(v)
        for u in mod.importers[v]:                 # 构建时已按名字序追加，无需再排
            indeg[u] -= 1
            if indeg[u] == 0:
                queue.append(u)
    if len(order) != n:
        placed = set(order)
        sample = sorted(mod.names[i] for i in range(n) if i not in placed)[:10]
        raise LayoutCycleError(sample)
    return order


def compute_closures(mod: Modules, topo: list[int]) -> list[int]:
    """传递闭包位图（Python 大整数即位集；与 Lean Shake 的 Bitset 同构）。

    closure[i] 第 j 位=1 ⟺ i 传递依赖 j（不含 i 自身）。~8.8k 位 × 8.8k 节点 ≈ 10MB。
    """
    closures = [0] * len(mod.names)
    for v in topo:                      # v（依赖）先于所有 importers 处理
        cv = closures[v] | (1 << v)
        for u in mod.importers[v]:
            closures[u] |= cv
    return closures


def transitively_reduce(mod: Modules, closures: list[int]) -> list[list[int]]:
    """传递约简：删除可经其他直接依赖推导的边；可达性严格不变。"""
    reduced: list[list[int]] = []
    for b in range(len(mod.names)):
        deps_b = mod.deps[b]
        keep: list[int] = []
        for a in deps_b:
            redundant = False
            for d in deps_b:
                if d == a:
                    continue
                if (closures[d] >> a) & 1:   # d 传递依赖 a ⟹ b 经 d 可达 a
                    redundant = True
                    break
            if not redundant:
                keep.append(a)
        reduced.append(sorted(keep))
    return reduced


def pagerank_scores(mod: Modules, alpha: float = 0.85, max_iter: int = 30,
                    tol: float = 1e-6) -> list[float]:
    """地基性 PageRank：importer 把 rank 均分给它 import 的模块（= nx.pagerank(G.reverse()) 语义）。"""
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
    """r = 0.2 + 3·√t（面积感知：面积 ∝ PageRank）。"""
    if not scores:
        return []
    lo, hi = min(scores), max(scores)
    rng = (hi - lo) or 1.0
    return [0.2 + 3.0 * ((s - lo) / rng) ** 0.5 for s in scores]


def _zig(slot: int) -> int:
    """锯齿位移序列：0, +1, -1, +2, -2, …"""
    if slot == 0:
        return 0
    d = (slot + 1) // 2
    return d if slot % 2 == 1 else -d


def assign_positions(mod: Modules, topo: list[int], closures: list[int],
                     node_topics: list[Topic]) -> tuple[list[float], list[float]]:
    """x = |closure|^0.72（零闭包按拓扑序散布 -0..-9 循环）；
    y = 带值 → 列内同 topic 直接依赖平均 → 确定性锯齿槽位。"""
    n = len(mod.names)
    xs = [float(closures[i].bit_count()) ** 0.72 for i in range(n)]
    k = 0
    for v in topo:                          # 拓扑序分配（确定性）
        if closures[v].bit_count() == 0:
            xs[v] = float(-(k % 10))
            k += 1
    ys = [float(t.y) for t in node_topics]
    columns: dict[int, list[int]] = {}
    for v in topo:                          # 列内元素按拓扑序进入
        columns.setdefault(int(xs[v]), []).append(v)
    for col in sorted(columns):             # 列处理顺序 = 列值升序（确定性）
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
                if slot > 20000:            # 安全阀：顺延到最高占用槽之上
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
                   skipped_bad_lines: int = 0) -> dict:
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
             for b in range(n) for a in reduced[b]]      # [dep, importer]，拓扑序坐标
    return {
        "schemaVersion": 1,
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
            },
        },
        "topics": [
            {"id": t.id, "label": t.label, "labelZh": t.labelZh, "y": t.y, "color": t.color}
            for t in topics
        ],
        "nodes": nodes,
        "edges": edges,
    }


def write_document(doc: dict, out: Path, *, now: str | None = None) -> None:
    """原子写出（tmp + os.replace）；now 覆盖 generatedAt（确定性测试用）。"""
    if now is not None:
        doc = {**doc, "meta": {**doc["meta"], "generatedAt": now}}
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(out.suffix + ".tmp")
    tmp.write_bytes(msgspec.json.encode(doc))
    os.replace(tmp, out)

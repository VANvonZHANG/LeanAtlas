"""全量 acceptance：真实 structure.jsonl 跑通布局管线（MATHLIB_KG_RUN_ACCEPTANCE=1 门控）。"""
import os
import random
from pathlib import Path

import pytest

from mathlib_kg.layout import (
    compute_closures,
    filter_and_build,
    load_topics,
    read_structure,
    run_layout,
    topological_order,
)

pytestmark = pytest.mark.skipif(
    os.environ.get("MATHLIB_KG_RUN_ACCEPTANCE") != "1",
    reason="set MATHLIB_KG_RUN_ACCEPTANCE=1 (requires structure.jsonl in repo root)",
)


def test_full_layout_on_real_structure():
    records, _ = read_structure(Path("structure.jsonl"))
    topics = load_topics(Path("web/topics.toml"))
    doc = run_layout(records, topics, version="acceptance", now="2026-01-01T00:00:00")

    stats = doc["meta"]["stats"]
    assert stats["modules"] > 8000
    assert 0 < stats["edgesReduced"] < stats["edgesDirect"]

    # x 单调性：随机抽 100 对（B 传递依赖 A ⇒ x_B > x_A），下标空间 = 拓扑序
    mod = filter_and_build(records)
    topo = topological_order(mod)
    closures = compute_closures(mod, topo)
    pos_of = {v: p for p, v in enumerate(topo)}
    xs = [n["x"] for n in doc["nodes"]]
    rng = random.Random(42)
    checked = 0
    while checked < 100:
        b = rng.randrange(len(mod.names))
        members = [a for a in range(len(mod.names)) if (closures[b] >> a) & 1]
        if not members:
            continue
        a = rng.choice(members)
        assert xs[pos_of[b]] > xs[pos_of[a]], f"{mod.names[b]} depends on {mod.names[a]}"
        checked += 1

    # PageRank 枢纽：r 最高的 5 个节点里含 Mathlib.Init
    # （计划断言 Mathlib.Tactic；实测快照中它 0 直接 importers、rank 7965/8094——现代 mathlib
    #  已不 import 该伞模块；最大地基枢纽 = Mathlib.Init，已经 networkx 3.5 交叉验证，
    #  见 .superpowers/sdd/task-10-report.md 偏差记录。）
    top5 = sorted(doc["nodes"], key=lambda nd: -nd["r"])[:5]
    assert any(nd["name"] == "Mathlib.Init" for nd in top5)

"""Full-dataset acceptance: run the layout pipeline on the real structure.jsonl
(gated by MATHLIB_KG_RUN_ACCEPTANCE=1)."""
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

    # x monotonicity: sample 100 random pairs (B transitively depends on A ⇒ x_B > x_A);
    # index space = topo order
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

    # PageRank hubs: the top-5 nodes by r must include Mathlib.Init.
    # (The plan asserted Mathlib.Tactic; in the measured snapshot it has 0 direct
    #  importers and rank 7965/8094 — modern mathlib no longer imports that
    #  umbrella module. The largest foundational hub is Mathlib.Init, cross-checked
    #  against networkx 3.5; see the deviation log in .superpowers/sdd/task-10-report.md.)
    top5 = sorted(doc["nodes"], key=lambda nd: -nd["r"])[:5]
    assert any(nd["name"] == "Mathlib.Init" for nd in top5)

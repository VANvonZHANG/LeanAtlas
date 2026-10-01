"""layout 纯函数核心的单元测试（无 IO、无 Neo4j/Lean）。"""
from pathlib import Path

import pytest

from mathlib_kg.layout import (
    DEFAULT_TOPICS,
    LayoutCycleError,
    LayoutError,
    Topic,
    assign_topic,
    compute_closures,
    filter_and_build,
    load_topics,
    pagerank_scores,
    radii,
    topological_order,
    transitively_reduce,
)
from mathlib_kg.models import Import


class TestBands:
    def test_default_table_has_28_entries_and_default(self):
        ids = [t.id for t in DEFAULT_TOPICS]
        assert len(ids) == 28
        assert "_default" in ids

    def test_prefix_match_with_trailing_dot(self):
        topics = list(DEFAULT_TOPICS)
        # Algebra 在表序上先于 AlgebraicGeometry：尾点防止 Algebra 吞掉 AlgebraicGeometry
        got = assign_topic("Mathlib.AlgebraicGeometry.Scheme", topics)
        assert got.id == "AlgebraicGeometry"
        got2 = assign_topic("Mathlib.Algebra.Group.Defs", topics)
        assert got2.id == "Algebra"

    def test_table_order_priority(self):
        # 表序优先：手工构造两条都匹配的表，第一条胜出
        custom = [
            Topic(id="Alpha", label="Alpha", labelZh="甲", y=10.0, color="#111111"),
            Topic(id="Alpha.Sub", label="AlphaSub", labelZh="子", y=11.0, color="#222222"),
            Topic(id="_default", label="Other", labelZh="其他", y=140.0, color="#202020"),
        ]
        assert assign_topic("Mathlib.Alpha.Sub.X", custom).id == "Alpha"

    def test_unmatched_falls_to_default(self):
        got = assign_topic("Mathlib.Util.Foo", list(DEFAULT_TOPICS))
        assert got.id == "_default"
        assert got.color == "#202020"

    def test_load_topics_reads_toml(self, tmp_path):
        p = tmp_path / "t.toml"
        p.write_text(
            '[[topic]]\nid = "Tactic"\nlabel = "Tactic"\nlabelZh = "战术"\ny = 40.0\ncolor = "#404080"\n'
            '[[topic]]\nid = "_default"\nlabel = "Other"\nlabelZh = "其他"\ny = 140.0\ncolor = "#202020"\n',
            encoding="utf-8",
        )
        got = load_topics(p)
        assert [t.id for t in got] == ["Tactic", "_default"]
        assert got[0].labelZh == "战术"

    def test_load_topics_missing_or_broken_falls_back(self, tmp_path, capsys):
        assert load_topics(None) == list(DEFAULT_TOPICS)
        bad = tmp_path / "bad.toml"
        bad.write_text("this is not = valid toml [[", encoding="utf-8")
        got = load_topics(bad)
        assert got == list(DEFAULT_TOPICS)
        assert any("warn" in line.lower() for line in capsys.readouterr().err.splitlines())


def _decl(k: int, ns: str):
    from mathlib_kg.models import Declaration

    return Declaration(
        name=f"{ns}.d{k}", shortName=f"d{k}", kind="def", namespace=ns,
        sourceFile="x.lean", startLine=1, endLine=2, sourceText="def x := 1",
    )


def rec(name: str, imports: tuple[str, ...] = (), decl_count: int = 0,
        deprecated: bool = False, title=None, doc=None):
    from mathlib_kg.models import ModuleRecord

    return ModuleRecord(
        module=name, path=f"/fake/{name}.lean", title=title, docstring=doc,
        isDeprecated=deprecated, imports=[Import(i) for i in imports],
        declarations=[_decl(k, name) for k in range(decl_count)],
    )


class TestFilterAndBuild:
    def test_drops_umbrella_and_non_mathlib(self):
        mods = filter_and_build([
            rec("Mathlib"),                      # 根伞
            rec("Archive"),                      # Archive 根伞
            rec("Archive.Examples.Foo", ("Mathlib.Order.Basic",)),
            rec("Counterexamples.X", ("Mathlib.Data.Nat.Basic",)),
            rec("Mathlib.Order.Basic"),
            rec("Mathlib.Algebra.Group.Defs", ("Mathlib.Order.Basic", "Lean.Core", "Mathlib.Order.Basic")),
        ])
        assert mods.names == ["Mathlib.Algebra.Group.Defs", "Mathlib.Order.Basic"]  # 名字序
        assert mods.index["Mathlib.Order.Basic"] == 1
        assert mods.deps[0] == [1]               # 外部 Lean.Core 跳过、重复 import 去重
        assert mods.importers[1] == [0]
        assert mods.skipped_external == 1

    def test_self_loop_skipped(self):
        mods = filter_and_build([rec("Mathlib.A", ("Mathlib.A",))])
        assert mods.deps[0] == []

    def test_zero_alive_raises(self):
        with pytest.raises(LayoutError, match="no Mathlib"):
            filter_and_build([rec("Archive"), rec("Mathlib")])


class TestTopo:
    def test_topological_order(self):
        mods = filter_and_build([
            rec("Mathlib.C", ("Mathlib.B",)),
            rec("Mathlib.B", ("Mathlib.A",)),
            rec("Mathlib.A"),
        ])
        order = topological_order(mods)
        assert order.index(mods.index["Mathlib.A"]) < order.index(mods.index["Mathlib.B"])
        assert order.index(mods.index["Mathlib.B"]) < order.index(mods.index["Mathlib.C"])

    def test_cycle_raises_with_names(self):
        mods = filter_and_build([
            rec("Mathlib.X", ("Mathlib.Y",)),
            rec("Mathlib.Y", ("Mathlib.X",)),
        ])
        with pytest.raises(LayoutCycleError) as ei:
            topological_order(mods)
        assert "Mathlib.X" in str(ei.value) and "Mathlib.Y" in str(ei.value)


class TestClosures:
    def test_closure_golden(self):
        mods = filter_and_build([
            rec("Mathlib.D", ("Mathlib.A", "Mathlib.B", "Mathlib.C")),
            rec("Mathlib.C", ("Mathlib.B",)),
            rec("Mathlib.B", ("Mathlib.A",)),
            rec("Mathlib.A"),
        ])
        i = mods.index
        closures = compute_closures(mods, topological_order(mods))
        # 手算：cl(A)=∅ cl(B)={A} cl(C)={A,B} cl(D)={A,B,C}
        assert closures[i["Mathlib.A"]] == 0
        assert closures[i["Mathlib.B"]].bit_count() == 1
        assert (closures[i["Mathlib.C"]] >> i["Mathlib.A"]) & 1 == 1
        assert (closures[i["Mathlib.C"]] >> i["Mathlib.B"]) & 1 == 1
        assert closures[i["Mathlib.D"]].bit_count() == 3
        # 不含自身
        assert (closures[i["Mathlib.D"]] >> i["Mathlib.D"]) & 1 == 0


class TestReduction:
    def test_diamond_redundant_edge_removed(self):
        mods = filter_and_build([
            rec("Mathlib.D", ("Mathlib.A", "Mathlib.B", "Mathlib.C")),
            rec("Mathlib.C", ("Mathlib.A",)),
            rec("Mathlib.B", ("Mathlib.A",)),
            rec("Mathlib.A"),
        ])
        i = mods.index
        reduced = transitively_reduce(mods, compute_closures(mods, topological_order(mods)))
        assert sorted(reduced[i["Mathlib.D"]]) == sorted([i["Mathlib.B"], i["Mathlib.C"]])
        assert reduced[i["Mathlib.C"]] == [i["Mathlib.A"]]
        assert reduced[i["Mathlib.A"]] == []

    def test_reachability_preserved(self):
        mods = filter_and_build([
            rec("Mathlib.D", ("Mathlib.A", "Mathlib.B", "Mathlib.C")),
            rec("Mathlib.C", ("Mathlib.B", "Mathlib.A")),
            rec("Mathlib.B", ("Mathlib.A",)),
            rec("Mathlib.E", ("Mathlib.D",)),
            rec("Mathlib.A"),
        ])
        closures = compute_closures(mods, topological_order(mods))
        reduced = transitively_reduce(mods, closures)
        # 从 reduced 邻接重建闭包（DFS），断言与原闭包一致
        seen_closures = []
        for start in range(len(mods.names)):
            stack, seen = list(reduced[start]), set()
            while stack:
                v = stack.pop()
                if v in seen:
                    continue
                seen.add(v)
                stack.extend(reduced[v])
            seen_closures.append(seen)
        for v in range(len(mods.names)):
            assert seen_closures[v] == {
                u for u in range(len(mods.names)) if (closures[v] >> u) & 1
            }


class TestPageRank:
    def test_hub_ranks_above_leaves(self):
        # A 被 B 依赖，B 被 C 依赖：A > B > C（排序性质，不断言精确值）
        mods = filter_and_build([
            rec("Mathlib.C", ("Mathlib.B",)),
            rec("Mathlib.B", ("Mathlib.A",)),
            rec("Mathlib.A"),
        ])
        i = mods.index
        scores = pagerank_scores(mods)
        assert scores[i["Mathlib.A"]] > scores[i["Mathlib.B"]] > scores[i["Mathlib.C"]]

    def test_radii_bounds_and_shape(self):
        rs = radii([0.0, 0.25, 1.0])
        assert rs[0] == pytest.approx(0.2)
        assert rs[1] == pytest.approx(0.2 + 3 * 0.5)
        assert rs[2] == pytest.approx(3.2)

    def test_radii_single_node(self):
        # min==max 时归一化分母回退为 1.0，半径 = 0.2
        assert radii([0.5]) == [pytest.approx(0.2)]

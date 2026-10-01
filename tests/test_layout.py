"""layout 纯函数核心的单元测试（无 IO、无 Neo4j/Lean）。"""
from pathlib import Path

import pytest

from mathlib_kg.layout import (
    DEFAULT_TOPICS,
    LayoutError,
    Topic,
    assign_topic,
    filter_and_build,
    load_topics,
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

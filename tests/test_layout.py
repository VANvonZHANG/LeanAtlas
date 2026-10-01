"""layout 纯函数核心的单元测试（无 IO、无 Neo4j/Lean）。"""
import json as _json
from pathlib import Path

import pytest

from mathlib_kg.layout import (
    DEFAULT_TOPICS,
    LayoutCycleError,
    LayoutError,
    Topic,
    assign_positions,
    assign_topic,
    assign_topics,
    build_document,
    compute_closures,
    filter_and_build,
    load_topics,
    pagerank_scores,
    radii,
    topological_order,
    transitively_reduce,
    write_document,
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


class TestPositions:
    def _setup(self, specs: dict[str, tuple[str, ...]], topics=None):
        mods = filter_and_build([rec(n, imps) for n, imps in specs.items()])
        topo = topological_order(mods)
        closures = compute_closures(mods, topo)
        node_topics = assign_topics(mods.names, list(topics or DEFAULT_TOPICS))
        return mods, topo, closures, node_topics

    def test_x_monotone_along_dependency(self):
        specs = {
            "Mathlib.A": (),
            "Mathlib.B": ("Mathlib.A",),
            "Mathlib.C": ("Mathlib.A", "Mathlib.B"),
            "Mathlib.D": ("Mathlib.C",),
        }
        mods, topo, closures, nt = self._setup(specs)
        xs, _ = assign_positions(mods, topo, closures, nt)
        i = mods.index
        assert xs[i["Mathlib.D"]] > xs[i["Mathlib.C"]] > xs[i["Mathlib.B"]] > xs[i["Mathlib.A"]] >= 0

    def test_zero_closure_spread_neg_columns(self):
        specs = {f"Mathlib.Util.K{k}": () for k in range(12)}
        mods, topo, closures, nt = self._setup(specs)
        xs, ys = assign_positions(mods, topo, closures, nt)
        zeros = [xs[i] for i in range(len(mods.names)) if closures[i].bit_count() == 0]
        assert zeros == [0.0, -1.0, -2.0, -3.0, -4.0, -5.0, -6.0, -7.0, -8.0, -9.0, 0.0, -1.0]

    def test_same_column_nodes_get_distinct_slots(self):
        # 同列同 topic 的多个节点：锯齿槽位保证整数槽互不重叠。
        # 注：零闭包节点被散布到不同 x 列，故须用等大闭包（B/C/D 闭包=1，
        # D 闭包=2→int(2^0.72)=1）构造真正的同列；A 独占 col 0 作对照。
        specs = {
            "Mathlib.Data.A": (),
            "Mathlib.Order.B": ("Mathlib.Data.A",),
            "Mathlib.Order.C": ("Mathlib.Data.A",),
            "Mathlib.Order.D": ("Mathlib.Data.A", "Mathlib.Order.B"),
        }
        mods, topo, closures, nt = self._setup(specs)
        xs, ys = assign_positions(mods, topo, closures, nt)
        slots = sorted(int(y) for y in ys)
        assert len(set(slots)) == 4

    def test_deterministic(self):
        specs = {
            "Mathlib.Order.A": (),
            "Mathlib.Order.B": ("Mathlib.Order.A",),
            "Mathlib.Algebra.C": ("Mathlib.Order.A",),
        }
        r1 = assign_positions(*self._setup(specs))
        r2 = assign_positions(*self._setup(specs))
        assert r1 == r2


class TestDocument:
    def _full(self):
        specs = {
            "Mathlib.A": (),
            "Mathlib.B": ("Mathlib.A",),
            "Mathlib.C": ("Mathlib.A", "Mathlib.B"),
        }
        mods = filter_and_build([rec(n, imps, decl_count=k, title=f"T{k}")
                                 for k, (n, imps) in enumerate(specs.items())])
        topo = topological_order(mods)
        closures = compute_closures(mods, topo)
        node_topics = assign_topics(mods.names, list(DEFAULT_TOPICS))
        xs, ys = assign_positions(mods, topo, closures, node_topics)
        rs = radii(pagerank_scores(mods))
        reduced = transitively_reduce(mods, closures)
        doc = build_document(mods, topo, list(DEFAULT_TOPICS), node_topics, xs, ys, rs, reduced, closures,
                             version="v0-test", generated_at="2026-01-01T00:00:00")
        return mods, doc

    def test_contract_fields(self):
        mods, doc = self._full()
        assert doc["schemaVersion"] == 1
        for key in ("version", "generatedAt", "scope", "stats"):
            assert key in doc["meta"]
        for key in ("modules", "edgesDirect", "edgesReduced", "skippedExternalImports",
                    "skippedBadLines", "unmatchedTopicModules"):
            assert key in doc["meta"]["stats"]
        # 节点 = 拓扑序；A（无依赖）必须在首位
        assert doc["nodes"][0]["name"] == "Mathlib.A"
        node0 = doc["nodes"][0]
        for key in ("name", "topic", "x", "y", "r", "color", "declCount",
                    "closureSize", "isDeprecated", "title", "docstring"):
            assert key in node0
        # 边下标合法且方向 = [dep, importer]
        for a, b in doc["edges"]:
            assert 0 <= a < len(doc["nodes"]) and 0 <= b < len(doc["nodes"])
        assert doc["meta"]["stats"]["edgesReduced"] == len(doc["edges"])

    def test_docstring_truncated_to_1000(self):
        specs = {"Mathlib.A": ()}
        mods = filter_and_build([rec("Mathlib.A", (), doc="x" * 5000)])
        topo = topological_order(mods)
        closures = compute_closures(mods, topo)
        node_topics = assign_topics(mods.names, list(DEFAULT_TOPICS))
        xs, ys = assign_positions(mods, topo, closures, node_topics)
        rs = radii(pagerank_scores(mods))
        reduced = transitively_reduce(mods, closures)
        doc = build_document(mods, topo, list(DEFAULT_TOPICS), node_topics, xs, ys, rs, reduced, closures,
                             version="v", generated_at="t")
        assert len(doc["nodes"][0]["docstring"]) == 1000

    def test_write_document_atomic_and_now_override(self, tmp_path):
        import json as _json

        _, doc = self._full()
        out = tmp_path / "data.json"
        write_document(doc, out, now="2000-01-01T00:00:00")
        on_disk = _json.loads(out.read_text(encoding="utf-8"))
        assert on_disk["meta"]["generatedAt"] == "2000-01-01T00:00:00"
        assert not list(tmp_path.glob("*.tmp"))          # 无残留临时文件

    def test_same_input_byte_identical(self, tmp_path):
        import msgspec as _msgspec

        _, doc1 = self._full()
        _, doc2 = self._full()
        b1 = _msgspec.json.encode(doc1)
        b2 = _msgspec.json.encode(doc2)
        assert b1 == b2


class TestRunAndRead:
    def test_read_structure_counts_bad_lines(self, tmp_path):
        from mathlib_kg.layout import read_structure
        p = tmp_path / "s.jsonl"
        good = rec("Mathlib.A")
        lines = [_json.dumps(_json.loads(__import__("msgspec").json.encode(good).decode()))]
        p.write_text("\n".join(lines + ["{broken", "{also-broken"]) + "\n", encoding="utf-8")
        records, bad = read_structure(p)
        assert len(records) == 1 and bad == 2

    def test_read_structure_aborts_at_100_bad_lines(self, tmp_path):
        from mathlib_kg.layout import LayoutError, read_structure
        p = tmp_path / "s.jsonl"
        p.write_text("\n".join(["{bad"] * 100) + "\n", encoding="utf-8")
        with pytest.raises(LayoutError, match="100"):
            read_structure(p)

    def test_run_layout_end_to_end_deterministic(self, capsys):
        from mathlib_kg.layout import run_layout
        records = [
            rec("Mathlib.Order.Basic"),
            rec("Mathlib.Algebra.Group.Defs", ("Mathlib.Order.Basic",), decl_count=5),
            rec("Archive.Old", ("Mathlib.Order.Basic",)),
        ]
        d1 = run_layout(records, list(DEFAULT_TOPICS), version="v1", now="2026-01-01T00:00:00")
        d2 = run_layout(records, list(DEFAULT_TOPICS), version="v1", now="2026-01-01T00:00:00")
        assert __import__("msgspec").json.encode(d1) == __import__("msgspec").json.encode(d2)
        assert d1["meta"]["stats"]["modules"] == 2          # Archive 被滤掉
        names = [nd["name"] for nd in d1["nodes"]]
        assert names[0] == "Mathlib.Order.Basic"            # 拓扑序首位
        # 未匹配 topic 报告出现在 stderr（Order/Algebra 均在表内 → 构造一个落灰带的）
        recs2 = [rec("Mathlib.Experiment.Foo", ("Mathlib.Order.Basic",))]
        run_layout(recs2, list(DEFAULT_TOPICS), version="v1", now="t")
        err = capsys.readouterr().err
        assert "Experiment" in err

    def test_cli_layout_reports_skipped_bad_lines(self, tmp_path):
        import msgspec as _m
        from typer.testing import CliRunner

        from mathlib_kg.cli import app

        p = tmp_path / "s.jsonl"
        p.write_bytes(_m.json.encode(rec("Mathlib.A")) + b"\n{broken\n")  # 1 好 + 1 坏
        out = tmp_path / "data.json"
        topics_f = tmp_path / "t.toml"
        topics_f.write_text(
            '[[topic]]\nid="_default"\nlabel="Other"\nlabelZh="其他"\n'
            'y=140.0\ncolor="#202020"\n',
            encoding="utf-8",
        )
        runner = CliRunner()
        result = runner.invoke(app, [
            "layout", "--structure", str(p), "--out", str(out), "--topics", str(topics_f),
        ])
        assert result.exit_code == 0, result.output
        data = _json.loads(out.read_text(encoding="utf-8"))
        assert data["meta"]["stats"]["skippedBadLines"] == 1

    def test_cli_layout_command(self, tmp_path, monkeypatch):
        from typer.testing import CliRunner

        from mathlib_kg.cli import app
        p = tmp_path / "s.jsonl"
        import msgspec as _m
        p.write_bytes(_m.json.encode(rec("Mathlib.A")).replace(b"}", b"}\n"))
        out = tmp_path / "data.json"
        topics_f = tmp_path / "t.toml"
        topics_f.write_text('[[topic]]\nid="_default"\nlabel="Other"\nlabelZh="其他"\ny=140.0\ncolor="#202020"\n', encoding="utf-8")
        runner = CliRunner()
        result = runner.invoke(app, [
            "layout", "--structure", str(p), "--out", str(out), "--topics", str(topics_f),
        ])
        assert result.exit_code == 0, result.output
        assert out.exists()

    def test_cli_layout_rejects_unknown_scope(self, tmp_path):
        from typer.testing import CliRunner

        from mathlib_kg.cli import app
        runner = CliRunner()
        result = runner.invoke(app, ["layout", "--scope", "all"])
        assert result.exit_code == 2

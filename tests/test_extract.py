"""Golden test for Extract.lean lake exe（默认跳过：LEAN 抽取较慢）。

启用：export MATHLIB_KG_SKIP_LEAN=0
"""
import json
import os
import subprocess
from pathlib import Path

import pytest

EXTRACT_DIR = Path(__file__).resolve().parents[1] / "extract"

pytestmark = pytest.mark.skipif(
    os.environ.get("MATHLIB_KG_SKIP_LEAN", "1") == "1",
    reason="LEAN 抽取较慢，默认跳过；设 MATHLIB_KG_SKIP_LEAN=0 启用",
)


def _run_extract(module: str) -> list[dict]:
    out = subprocess.run(
        ["lake", "exe", "extract", module],
        cwd=EXTRACT_DIR,
        capture_output=True,
        text=True,
        check=True,
    )
    return [json.loads(ln) for ln in out.stdout.splitlines() if ln.strip()]


def test_extract_init_nat_basic():
    recs = _run_extract("Init.Data.Nat.Basic")
    by_name = {r["name"]: r for r in recs}
    # 结构完整
    for r in recs[:30]:
        assert "name" in r
        assert "typeSignature" in r
        assert "deps" in r
        for d in r["deps"]:
            assert {"name", "inType", "inValue"} <= set(d.keys())
    # 每条有非空 typeSignature
    assert all(r["typeSignature"] for r in recs[:30])
    # 至少有一些声明带有依赖
    assert sum(1 for r in recs if r["deps"]) > 0


def test_extract_struct_edges_fixture():
    """v2: EXTENDS/INSTANTIATES 是硬断言；
    DEPRECATED_BY/HAS_ADDITIVE_VERSION 是软断言（attr 表若 v4.30.0 不可读则跳过，见 spec D12）。
    """
    # 先构建 fixture 模块（mathlib 已构建，构建一个 tiny 模块约数十秒）
    subprocess.run(["lake", "build", "StructEdgesFixture"], cwd=EXTRACT_DIR, check=True,
                   capture_output=True, text=True)
    recs = _run_extract("StructEdgesFixture")
    by_name = {r["name"]: r for r in recs}

    # EXTENDS：B extends A（硬断言）
    b = by_name["StructEdgesFixture.B"]
    assert {"parent": "StructEdgesFixture.A", "position": 0} in b["extends"]

    # INSTANTIATES：instB 的类型头是 B（硬断言）
    inst = by_name["StructEdgesFixture.instB"]
    assert inst["instantiates"] == "StructEdgesFixture.B"

    # INSTANTIATES 回归：参数化 instance instC 的类型是 `∀ (α : Type), C α`，
    # 旧代码 getAppFn 不下穿 forallE，head 取不到 → instantiates:null（边被丢）。
    # 这里硬断言剥 Pi 后能拿到 C（spec: INSTANTIATES Pi-binder bug 回归）。
    inst_c = by_name["StructEdgesFixture.instC"]
    assert inst_c["instantiates"] == "StructEdgesFixture.C"

    # DEPRECATED_BY：oldB → newB（软断言：attr 表可读时严格断言目标名）
    oldb = by_name["StructEdgesFixture.oldB"]
    if oldb.get("deprecatedBy"):
        assert oldb["deprecatedBy"]["replacement"] == "StructEdgesFixture.newB"
        assert oldb["deprecatedBy"]["since"] == "2024-01-01"

    # HAS_ADDITIVE_VERSION：foo → addFoo（软断言：attr 表可读时严格断言目标名）
    foo = by_name["StructEdgesFixture.foo"]
    if foo.get("additiveVersion"):
        assert foo["additiveVersion"] == "StructEdgesFixture.addFoo"


def test_extract_fields_constructors_fixture():
    """v2.5: HAS_FIELD（扁平含继承）+ HAS_CONSTRUCTOR（多构造子 + position）。"""
    # 先构建 fixture（含新增 D1/D2/Foo，增量构建数十秒）
    subprocess.run(["lake", "build", "StructEdgesFixture"], cwd=EXTRACT_DIR, check=True,
                   capture_output=True, text=True)
    recs = _run_extract("StructEdgesFixture")
    by_name = {r["name"]: r for r in recs}
    all_names = set(by_name.keys())

    # --- HAS_FIELD（扁平，含继承）---
    d2 = by_name["StructEdgesFixture.D2"]
    field_names = {f["name"] for f in d2["fields"]}
    # 硬断言（Step 2 实证）：
    #   - 自有字段 d2 → 投影 StructEdgesFixture.D2.d2
    #   - 继承字段 d1 → Lean 复用父结构投影 StructEdgesFixture.D1.d1（非子合成 D2.d1）
    #   - 子对象强转 → StructEdgesFixture.D2.toD1（getStructureFieldsFlattened 默认 includeSubobjectFields）
    assert "StructEdgesFixture.D2.d2" in field_names
    assert "StructEdgesFixture.D1.d1" in field_names, f"继承字段缺失，实际 fields={field_names}"
    assert "StructEdgesFixture.D2.toD1" in field_names
    # 交叉验证（防拼名错误）：每个 field 名都必须是 env 里真实存在的常量（出现在 extract 全部记录里）
    missing = field_names - all_names
    assert missing == set(), f"fields 拼出名不在 env 常量集：{missing}（回 Step 2 核对 getStructureFieldsFlattened 返回格式）"
    # position 单调（0..n-1，无重复）
    positions = [f["position"] for f in d2["fields"]]
    assert positions == list(range(len(positions)))

    # --- HAS_CONSTRUCTOR（structure 的 mk + inductive 多构造子）---
    d2c = by_name["StructEdgesFixture.D2"]
    assert [c["name"] for c in d2c["constructors"]] == ["StructEdgesFixture.D2.mk"]
    assert [c["position"] for c in d2c["constructors"]] == [0]

    foo = by_name["StructEdgesFixture.Foo"]
    ctor_names = {c["name"] for c in foo["constructors"]}
    assert ctor_names == {"StructEdgesFixture.Foo.c1", "StructEdgesFixture.Foo.c2"}
    assert sorted(c["position"] for c in foo["constructors"]) == [0, 1]
    # 非类型常量（如 instB）不应有 fields/constructors
    inst = by_name["StructEdgesFixture.instB"]
    assert inst["fields"] == [] and inst["constructors"] == []

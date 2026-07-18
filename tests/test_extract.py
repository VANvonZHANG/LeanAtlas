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

    # DEPRECATED_BY：oldB → newB（软断言：attr 表可读时严格断言目标名）
    oldb = by_name["StructEdgesFixture.oldB"]
    if oldb.get("deprecatedBy"):
        assert oldb["deprecatedBy"]["replacement"] == "StructEdgesFixture.newB"
        assert oldb["deprecatedBy"]["since"] == "2024-01-01"

    # HAS_ADDITIVE_VERSION：foo → addFoo（软断言：attr 表可读时严格断言目标名）
    foo = by_name["StructEdgesFixture.foo"]
    if foo.get("additiveVersion"):
        assert foo["additiveVersion"] == "StructEdgesFixture.addFoo"

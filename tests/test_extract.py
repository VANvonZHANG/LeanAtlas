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

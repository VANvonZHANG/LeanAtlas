import os

import pytest
from typer.testing import CliRunner

from mathlib_kg.cli import app

runner = CliRunner()
pytestmark = pytest.mark.skipif(
    not os.environ.get("MATHLIB_KG_NEO4J_PASSWORD"), reason="requires Neo4j credentials"
)


def test_parse_subcommand(tmp_path):
    src = tmp_path / "A.lean"
    src.write_text("module\ndef z := 3\n", encoding="utf-8")
    out = tmp_path / "structure.jsonl"
    result = runner.invoke(
        app,
        ["parse", "--mathlib-path", str(tmp_path), "--out", str(out), "--glob", "A.lean"],
    )
    assert result.exit_code == 0, result.output
    assert out.exists()
    assert "def z" in out.read_text(encoding="utf-8")


def test_query_and_drop():
    res_q = runner.invoke(app, ["query", "MATCH (n:Declaration) RETURN count(n)"])
    assert res_q.exit_code == 0, res_q.output
    res_d = runner.invoke(app, ["drop"])
    assert res_d.exit_code == 0, res_d.output

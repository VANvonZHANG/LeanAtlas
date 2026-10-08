"""serve app: static hosting + Range (ungated), healthz shape (gated).

Static/Range tests need no database: create_app never connects at startup
(lazy driver). Gated tests follow the test_cli.py convention and may wipe the
configured database.
"""
import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from leanatlas.serve import create_app


def _blob() -> bytes:
    return bytes(range(256)) * 64  # 16 KiB, non-trivial content


def _dist_client(tmp_path: Path) -> TestClient:
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text("<html>leanatlas</html>", encoding="utf-8")
    (dist / "declpack.bin").write_bytes(_blob())
    return TestClient(create_app(dist))


def test_static_index_served(tmp_path):
    client = _dist_client(tmp_path)
    res = client.get("/")
    assert res.status_code == 200
    assert "leanatlas" in res.text


def test_static_files_honor_range(tmp_path):
    # Spec §13.1: the pack's per-block Range drill must survive StaticFiles.
    client = _dist_client(tmp_path)
    res = client.get("/declpack.bin", headers={"Range": "bytes=100-199"})
    assert res.status_code == 206
    assert len(res.content) == 100
    assert res.content == _blob()[100:200]


def test_healthz_never_crashes_without_db():
    # API-only app, no credentials / no listener: a clean 503, never a traceback.
    client = TestClient(create_app(None))
    res = client.get("/api/healthz")
    assert res.status_code in (200, 503)


pytestmark_gate = pytest.mark.skipif(
    not os.environ.get("LEANATLAS_NEO4J_PASSWORD"), reason="requires Neo4j credentials"
)


@pytestmark_gate
def test_healthz_reports_shape():
    client = TestClient(create_app(None))
    res = client.get("/api/healthz")
    assert res.status_code == 200, res.text
    d = res.json()["data"]
    assert isinstance(d["modules"], int) and d["modules"] >= 0
    assert isinstance(d["decls"], int) and d["decls"] >= 0
    assert isinstance(d["layoutPresent"], bool)
    assert d["kgVersion"] is None or isinstance(d["kgVersion"], int)

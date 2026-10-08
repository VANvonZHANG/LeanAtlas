"""Gated query-endpoint tests over the shared fixture graph."""
from fastapi.testclient import TestClient

from leanatlas.serve import create_app
from tests.kgfixture import load_fixture, requires_neo4j


@requires_neo4j
def test_search_finds_attributed_declarations():
    load_fixture()
    client = TestClient(create_app(None))
    res = client.get("/api/search", params={"q": "base"})
    assert res.status_code == 200, res.text
    data = res.json()["data"]
    names = [r["name"] for r in data]
    assert "Mathlib.B.base" in names
    # unattributed placeholders (Nat) never surface
    assert all(r["module"].startswith("Mathlib.") for r in data)


@requires_neo4j
def test_decl_detail_and_source_url():
    load_fixture()
    client = TestClient(create_app(None))
    res = client.get("/api/decl/Mathlib.A.user")
    assert res.status_code == 200, res.text
    d = res.json()["data"]
    assert d["kind"] == "theorem"
    assert d["module"] == "Mathlib.A"
    assert d["sourceUrl"] == (
        "https://github.com/leanprover-community/mathlib4/blob/master/"
        "Mathlib/A.lean#L5"
    )
    assert client.get("/api/decl/nope").status_code == 404


@requires_neo4j
def test_decl_deps_directions_and_external_group():
    load_fixture()
    client = TestClient(create_app(None))
    # who depends on Mathlib.B.base (cross-module): Mathlib.A.user
    res = client.get("/api/decl/Mathlib.B.base/deps", params={"dir": "in"})
    assert res.status_code == 200, res.text
    d = res.json()["data"]
    assert d["total"] == 1
    assert d["groups"] == [{"module": "Mathlib.A", "count": 1, "edges": [
        {"from": "Mathlib.A.user", "fromKind": "theorem",
         "to": "Mathlib.B.base", "toKind": "def"},
    ]}]
    # what Mathlib.B.base depends on: only external Nat (no attribution)
    res = client.get("/api/decl/Mathlib.B.base/deps", params={"dir": "out"})
    d = res.json()["data"]
    assert d["groups"] == [{"module": "(external)", "count": 1, "edges": [
        {"from": "Mathlib.B.base", "fromKind": "def", "to": "Nat", "toKind": None},
    ]}]
    # intra-module deps are excluded by design (the block carries them)
    res = client.get("/api/decl/Mathlib.A.user/deps", params={"dir": "out"})
    d = res.json()["data"]
    assert d["total"] == 1  # only Mathlib.B.base (cross)
    assert [g["module"] for g in d["groups"]] == ["Mathlib.B"]
    assert client.get("/api/decl/zzz/deps").status_code == 404


@requires_neo4j
def test_depstrip_between_modules():
    load_fixture()
    client = TestClient(create_app(None))
    res = client.get("/api/depstrip", params={"a": "Mathlib.A", "b": "Mathlib.B"})
    assert res.status_code == 200, res.text
    assert res.json()["data"] == {
        "total": 1,
        "groups": [{"from": "Mathlib.A.user", "kind": "theorem", "count": 1,
                    "edges": [{"to": "Mathlib.B.base", "kind": "def"}]}],
    }
    empty = client.get("/api/depstrip", params={"a": "Mathlib.B", "b": "Mathlib.A"})
    assert empty.json()["data"]["total"] == 0


@requires_neo4j
def test_batch_details():
    load_fixture()
    client = TestClient(create_app(None))
    res = client.post("/api/decls/batch",
                      json={"names": ["Mathlib.B.base", "missing"],
                            "fields": ["name", "kind"]})
    assert res.status_code == 200, res.text
    assert res.json()["data"] == [{"name": "Mathlib.B.base", "kind": "def"}]
    assert client.post("/api/decls/batch",
                       json={"names": ["x"], "fields": ["nope"]}).status_code == 422
    too_many = {"names": ["x"] * 501}
    assert client.post("/api/decls/batch", json=too_many).status_code == 422

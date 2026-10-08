"""serve_graph: pure assemblers (ungated) + endpoint behavior (gated)."""
from fastapi.testclient import TestClient

from leanatlas.serve import create_app

# module-level: the @requires_neo4j decorators need the names at import time,
# and importing kgfixture itself never touches the database
from tests.kgfixture import fixture_records, load_fixture, requires_neo4j

# --- pure: block builder parity with the pack builder on identical inputs ---

DECLS = [{"name": "Mathlib.A.b", "kind": "def"},
         {"name": "Mathlib.A.c", "kind": "theorem"}]
EDGES = [(1, 0)]  # c depends on b


def test_build_block_doc_matches_pack_builder():
    import json as _json

    from leanatlas.declpack import build_module_block
    from leanatlas.serve_graph import build_block_doc

    # the pack builder's input convention is {"name", "k"} (run_declpack);
    # build_block_doc takes DB rows keyed "kind" (_DECLS_Q) — same content
    pack_decls = [{"name": d["name"], "k": d["kind"]} for d in DECLS]
    from_pack = _json.loads(build_module_block("Mathlib.A", pack_decls, EDGES))
    from_db = build_block_doc("Mathlib.A", DECLS, EDGES)
    assert from_db == from_pack  # same algorithms, same inputs → same document


# --- pure: graph doc assembly from canned DB rows ---

NODE_ROWS = [
    {"name": "Mathlib.B", "topic": "Algebra", "x": 0.0, "y": 100.0, "r": 0.2,
     "color": "#ffff00", "declCount": 1, "closureSize": 0, "isDeprecated": False,
     "title": "B", "docstring": "long " * 300},
    {"name": "Mathlib.A", "topic": "Algebra", "x": 1.0, "y": 100.0, "r": 0.5,
     "color": "#ffff00", "declCount": 1, "closureSize": 1, "isDeprecated": False,
     "title": None, "docstring": None},
]


def test_assemble_graph_doc_truncates_docstring():
    from leanatlas.serve_graph import assemble_graph_doc

    doc = assemble_graph_doc(
        NODE_ROWS,
        [{"a": 0, "b": 1}],
        [{"rel": "extends", "a": 0, "b": 1}],
        {"meta": {"version": "v"}, "topics": [{"id": "Algebra"}]},
    )
    assert doc["schemaVersion"] == 2
    assert doc["nodes"][0]["docstring"] == ("long " * 300)[:1000]  # build_document parity
    assert doc["edges"] == [[0, 1]]
    assert doc["structureEdges"] == {"extends": [[0, 1]], "instantiates": [], "fields": []}


@requires_neo4j
def test_graph_endpoint_reassembles_stored_document():
    import leanatlas.serve_graph as sg
    from leanatlas.layout import run_layout
    from leanatlas.layout_store import build_store_rows, store_layout

    recs, _ext = fixture_records()
    doc1 = run_layout(recs, [], version="v-test",
                      now="2026-10-07T00:00:00+00:00")
    load_fixture()
    from leanatlas.config import get_config
    from leanatlas.load_neo4j import connect
    driver = connect()
    with driver.session(database=get_config().neo4j_db) as s:
        s.execute_write(store_layout, build_store_rows(doc1))
    driver.close()
    sg._doc_cache.update(kgVersion=None, doc=None)  # cold cache
    client = TestClient(create_app(None))
    res = client.get("/api/graph")
    assert res.status_code == 200, res.text
    assert res.json()["data"] == doc1  # THE parity test: file doc == API doc


@requires_neo4j
def test_graph_503_without_stored_layout():
    load_fixture()  # wipes Meta (drop_kg_batched now clears it)
    import leanatlas.serve_graph as sg
    sg._doc_cache.update(kgVersion=None, doc=None)
    client = TestClient(create_app(None))
    assert client.get("/api/graph").status_code == 503


@requires_neo4j
def test_module_decls_endpoint_serves_attributed_block():
    load_fixture()
    import leanatlas.serve_graph as sg
    sg._block_cache.clear()
    client = TestClient(create_app(None))
    res = client.get("/api/module/Mathlib.A/decls")
    assert res.status_code == 200, res.text
    block = res.json()["data"]
    assert block["schemaVersion"] == 1
    # name-sorted (code-point: 'M' U+004D < '_' U+005F): user before the
    # underscore-private name — same order as the pack's extract first-appearance
    assert [d["name"] for d in block["decls"]] == ["Mathlib.A.user", "_private.A.0.gen"]
    assert block["decls"][0]["k"] == "theorem"    # source-parsed kind wins
    assert block["decls"][1]["k"] == "inductive"  # extract fallback kind
    # user depends on _private.A.0.gen (intra); cross-module dep to
    # Mathlib.B.base is NOT in the block (module layer owns cross edges)
    idx = {d["name"]: i for i, d in enumerate(block["decls"])}
    assert block["e"] == sorted([[idx["Mathlib.A.user"], idx["_private.A.0.gen"]]])


@requires_neo4j
def test_module_decls_404s():
    load_fixture()
    import leanatlas.serve_graph as sg
    sg._block_cache.clear()
    client = TestClient(create_app(None))
    assert client.get("/api/module/Mathlib.ZZZ/decls").status_code == 404

"""serve_graph: pure assemblers (ungated) + endpoint behavior (gated)."""
from fastapi.testclient import TestClient

from leanatlas.models import Declaration, Import, ModuleRecord
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


def _viz_order_records() -> list[ModuleRecord]:
    """The parity test's OWN fixture (kgfixture stays untouched for Task 5):
    4 modules / 3 direct (= 3 reduced) edges where NAME order ≠ TOPO order —
    Mathlib.A.deep is name-first but topo-LAST, so any importer-topo-major
    edge enumeration orders the document's edge array differently than
    build_document's name-index-major one. (A 3-module diamond like
    Z.base←A.mid←M.top collapses to 2 edges whose orderings coincide.)"""

    def rec(module: str, imports: list[Import]) -> ModuleRecord:
        path = module.replace(".", "/") + ".lean"
        short = module.rsplit(".", 1)[1]
        return ModuleRecord(
            module=module, path=path, imports=imports,
            declarations=[Declaration(
                name=f"{module}.{short}", shortName=short, kind="def",
                namespace=module, sourceFile=path, startLine=1, endLine=2,
                sourceText=f"def {short} := 1",
            )],
        )

    return [
        rec("Mathlib.A.deep", [Import(name="Mathlib.N.mid")]),
        rec("Mathlib.M.leaf", []),
        rec("Mathlib.N.mid", [Import(name="Mathlib.M.leaf")]),
        rec("Mathlib.Z.shallow", [Import(name="Mathlib.M.leaf")]),
    ]


@requires_neo4j
def test_graph_endpoint_reassembles_stored_document():
    import leanatlas.serve_graph as sg
    from leanatlas.config import get_config
    from leanatlas.layout import run_layout
    from leanatlas.layout_store import build_store_rows, store_layout
    from leanatlas.load_neo4j import (
        connect,
        load_declarations,
        load_imports,
        load_modules,
    )
    from leanatlas.neo4j_schema import apply_schema, drop_kg_batched

    recs = _viz_order_records()
    doc1 = run_layout(recs, [], version="v-test",
                      now="2026-10-07T00:00:00+00:00")
    # pin the topology parity hinges on: nodes topo-ordered (A.deep last
    # despite being name-first), edges name-index-major (A.deep's edge first)
    assert [n["name"] for n in doc1["nodes"]] == [
        "Mathlib.M.leaf", "Mathlib.N.mid", "Mathlib.Z.shallow", "Mathlib.A.deep"]
    assert doc1["edges"] == [[1, 3], [0, 1], [0, 2]]

    driver = connect()
    with driver.session(database=get_config().neo4j_db) as s:
        s.execute_write(drop_kg_batched)
        s.execute_write(apply_schema)
        s.execute_write(load_modules, recs)
        s.execute_write(load_declarations, recs)
        s.execute_write(load_imports, recs)
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
def test_graph_503_clears_caches():
    """I1 regression: a wiped graph (no :Meta) must empty BOTH caches — a
    long-lived process must not outlive its cached generation."""
    import leanatlas.serve_graph as sg
    from leanatlas.config import get_config
    from leanatlas.load_neo4j import connect

    load_fixture()
    sg._doc_cache.update(kgVersion=1, doc={"sentinel": True})
    sg._block_cache["Mathlib.A"] = {"sentinel": True}
    driver = connect()
    with driver.session(database=get_config().neo4j_db) as s:
        s.run("MATCH (m:Meta) DETACH DELETE m")  # direct wipe of :Meta
    driver.close()
    client = TestClient(create_app(None))
    assert client.get("/api/graph").status_code == 503
    assert sg._doc_cache == {"kgVersion": None, "doc": None}
    assert len(sg._block_cache) == 0


@requires_neo4j
def test_rebuild_invalidates_cached_doc():
    """I1 regression: after Meta is dropped and a CHANGED document re-stored,
    a surviving process (holding the old doc in _doc_cache) must serve the
    NEW document. Both generations' first store hits the kgVersion-IS-NULL
    arm; the wall-clock seed keeps the two versions apart (the sleep makes
    the differing seconds deterministic — the seed is second-granular)."""
    import time as _time

    import leanatlas.serve_graph as sg
    from leanatlas.config import get_config
    from leanatlas.layout import run_layout
    from leanatlas.layout_store import build_store_rows, store_layout
    from leanatlas.load_neo4j import connect

    load_fixture()  # fresh generation-0 graph: Modules A/B, no layout yet
    recs, _ = fixture_records()
    doc1 = run_layout(recs, [], version="v-gen1",
                      now="2026-10-07T00:00:00+00:00")
    driver = connect()
    with driver.session(database=get_config().neo4j_db) as s:
        s.execute_write(store_layout, build_store_rows(doc1))
    driver.close()
    sg._doc_cache.update(kgVersion=None, doc=None)
    client = TestClient(create_app(None))
    res = client.get("/api/graph")
    assert res.status_code == 200, res.text
    assert res.json()["data"] == doc1  # gen-1 doc now cached in-process

    _time.sleep(1.1)  # second-granularity seeds need different seconds
    # a CHANGED generation: one module fewer
    doc2 = run_layout(recs[:1], [], version="v-gen2",
                      now="2026-10-08T00:00:00+00:00")
    driver = connect()
    with driver.session(database=get_config().neo4j_db) as s:
        # simulate the drop of a reload: Meta + layout props + viz edges gone
        s.run("MATCH (m:Meta) DETACH DELETE m")
        s.run(
            "MATCH (m:Module) REMOVE m.x, m.y, m.r, m.topic, m.color, "
            "m.declCount, m.closureSize, m.topo"
        )
        s.run("MATCH ()-[r:VIZ]->() DELETE r")
        s.run("MATCH ()-[r:STRUCTURE]->() DELETE r")
        s.execute_write(store_layout, build_store_rows(doc2))
    driver.close()
    # same process, gen-1 doc still in _doc_cache — must NOT be served
    res = client.get("/api/graph")
    assert res.status_code == 200, res.text
    assert res.json()["data"] == doc2
    assert [n["name"] for n in res.json()["data"]["nodes"]] == ["Mathlib.B"]


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

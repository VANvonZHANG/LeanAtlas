"""layout_store: row building (ungated) and store round-trip (gated)."""
import json
import os

import pytest

DOC = {
    "schemaVersion": 2,
    "meta": {"version": "v4.30.0", "generatedAt": "2026-10-07T00:00:00+00:00",
             "scope": "mathlib", "stats": {"modules": 2}},
    "topics": [{"id": "Algebra", "label": "Algebra", "y": 100.0, "color": "#ffff00"}],
    "nodes": [
        {"name": "Mathlib.B", "topic": "Algebra", "x": 0.0, "y": 100.0, "r": 0.2,
         "color": "#ffff00", "declCount": 1, "closureSize": 0,
         "isDeprecated": False, "title": None, "docstring": None},
        {"name": "Mathlib.A", "topic": "Algebra", "x": 1.0, "y": 100.0, "r": 0.5,
         "color": "#ffff00", "declCount": 1, "closureSize": 1,
         "isDeprecated": False, "title": None, "docstring": None},
    ],
    "edges": [[0, 1]],  # [dep B, importer A]
    "structureEdges": {"extends": [[0, 1]], "instantiates": [], "fields": []},
}


def test_build_store_rows_maps_document_to_batches():
    from leanatlas.layout_store import build_store_rows

    rows = build_store_rows(DOC)
    assert rows["nodes"][0] == {
        "name": "Mathlib.B", "x": 0.0, "y": 100.0, "r": 0.2, "topic": "Algebra",
        "color": "#ffff00", "declCount": 1, "closureSize": 0, "topo": 0,
    }
    assert rows["viz"] == [{"a": "Mathlib.B", "b": "Mathlib.A"}]
    assert rows["struct"] == [{"rel": "extends", "a": "Mathlib.B", "b": "Mathlib.A"}]
    assert json.loads(rows["topicsJson"]) == DOC["topics"]
    assert json.loads(rows["metaJson"]) == DOC["meta"]


def test_topo_avoids_cypher_reserved_word():
    # `order` is reserved in Cypher; the stored property is `topo`
    from leanatlas.layout_store import build_store_rows

    assert all("topo" in n and "order" not in n for n in build_store_rows(DOC)["nodes"])


@pytest.mark.skipif(
    not os.environ.get("LEANATLAS_NEO4J_PASSWORD"), reason="requires Neo4j credentials"
)
def test_store_layout_roundtrip():
    from leanatlas.config import get_config
    from leanatlas.layout_store import build_store_rows, store_layout
    from leanatlas.load_neo4j import (
        connect,
        load_declarations,
        load_imports,
        load_modules,
    )
    from leanatlas.models import Declaration, Import, ModuleRecord
    from leanatlas.neo4j_schema import apply_schema, drop_kg_batched

    recs = [
        ModuleRecord(
            module="Mathlib.B", path="Mathlib/B.lean", docstring="B module", title="B",
            declarations=[Declaration(
                name="Mathlib.B.base", shortName="base", kind="def",
                namespace="Mathlib.B", sourceFile="Mathlib/B.lean", startLine=3,
                endLine=4, sourceText="def base := 1", docstring="the base",
            )],
        ),
        ModuleRecord(
            module="Mathlib.A", path="Mathlib/A.lean", docstring="A module", title="A",
            imports=[Import(name="Mathlib.B")],
            declarations=[Declaration(
                name="Mathlib.A.user", shortName="user", kind="theorem",
                namespace="Mathlib.A", sourceFile="Mathlib/A.lean", startLine=5,
                endLine=6, sourceText="theorem user : 1 = 1 := rfl", docstring="uses base",
            )],
        ),
    ]
    cfg = get_config()
    driver = connect()
    with driver.session(database=cfg.neo4j_db) as s:
        s.execute_write(drop_kg_batched)
        s.execute_write(apply_schema)
        s.execute_write(load_modules, recs)
        s.execute_write(load_declarations, recs)
        s.execute_write(load_imports, recs)
        s.execute_write(store_layout, build_store_rows(DOC))
        props = s.run(
            "MATCH (m:Module {name:'Mathlib.A'}) RETURN m.x AS x, m.topo AS topo, "
            "m.color AS color, m.topic AS topic"
        ).single()
        viz = s.run(
            "MATCH (a:Module)-[:VIZ]->(b:Module) RETURN a.name AS a, b.name AS b"
        ).single()
        meta = s.run(
            "MATCH (m:Meta {id:'kg'}) RETURN m.kgVersion AS v, "
            "m.topicsJson IS NOT NULL AS p"
        ).single()
        # leave the DB clean for the next gated test
        s.run("MATCH (m:Meta {id:'kg'}) DETACH DELETE m")
    driver.close()
    assert props == {"x": 1.0, "topo": 1, "color": "#ffff00", "topic": "Algebra"}
    assert viz == {"a": "Mathlib.B", "b": "Mathlib.A"}
    assert meta["v"] == 1 and meta["p"] is True

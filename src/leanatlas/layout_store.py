"""layout --store: persist the module-map document into Neo4j (P3).

Writes exactly what serve_graph.assemble_graph_doc reassembles: per-Module
layout props + topo position (`topo`; `order` is a Cypher reserved word),
the transitively-reduced import edges as VIZ, module-level structure edges as
STRUCTURE {rel}, and the document's meta/topics JSON on :Meta. kgVersion
increments on every store so /api/graph's cache invalidates; drop_kg_batched
clears Meta/VIZ/STRUCTURE, so a wiped graph reads layoutPresent=false and can
never serve a stale cached document (spec §7). The first store after a wipe
seeds kgVersion from wall-clock (see store_layout) so versions never repeat
across rebuilds either.
"""
from __future__ import annotations

import json
import time

from .structure_edges import REL_TYPES

META_ID = "kg"


def build_store_rows(doc: dict) -> dict:
    """data.json document -> Cypher row batches. Pure (ungated tests).

    VIZ pair order [a, b] is the document's [dep, importer]; /api/graph emits
    the pairs back verbatim, so the document's edge array round-trips.
    """
    name_at = [n["name"] for n in doc["nodes"]]
    nodes = [
        {
            "name": n["name"], "x": n["x"], "y": n["y"], "r": n["r"],
            "topic": n["topic"], "color": n["color"],
            "declCount": n["declCount"], "closureSize": n["closureSize"],
            "topo": i,
        }
        for i, n in enumerate(doc["nodes"])
    ]
    viz = [{"a": name_at[a], "b": name_at[b]} for a, b in doc["edges"]]
    struct = [
        {"rel": rel, "a": name_at[a], "b": name_at[b]}
        for rel in REL_TYPES
        for a, b in doc["structureEdges"][rel]
    ]
    return {
        "nodes": nodes,
        "viz": viz,
        "struct": struct,
        "metaJson": json.dumps(doc["meta"], separators=(",", ":")),
        "topicsJson": json.dumps(doc["topics"], separators=(",", ":")),
    }


def store_layout(tx, rows: dict) -> None:
    """One transaction: clear previous layout artifacts, write the new ones."""
    tx.run("MATCH ()-[r:VIZ]->() DELETE r")
    tx.run("MATCH ()-[r:STRUCTURE]->() DELETE r")
    for i in range(0, len(rows["nodes"]), 1000):
        tx.run(
            "UNWIND $batch AS n MATCH (m:Module {name:n.name}) "
            "SET m.x=n.x, m.y=n.y, m.r=n.r, m.topic=n.topic, m.color=n.color, "
            "m.declCount=n.declCount, m.closureSize=n.closureSize, m.topo=n.topo",
            batch=rows["nodes"][i : i + 1000],
        )
    for i in range(0, len(rows["viz"]), 1000):
        tx.run(
            "UNWIND $batch AS e MATCH (a:Module {name:e.a}), (b:Module {name:e.b}) "
            "CREATE (a)-[:VIZ]->(b)",
            batch=rows["viz"][i : i + 1000],
        )
    for i in range(0, len(rows["struct"]), 1000):
        tx.run(
            "UNWIND $batch AS e MATCH (a:Module {name:e.a}), (b:Module {name:e.b}) "
            "CREATE (a)-[:STRUCTURE {rel:e.rel}]->(b)",
            batch=rows["struct"][i : i + 1000],
        )
    # A wiped database restarts kgVersion numbering, so the first store of
    # each generation is seeded from wall-clock — a long-lived serve process
    # can never see a repeated version across rebuilds (its cached document
    # from the previous generation always mismatches and reloads).
    tx.run(
        "MERGE (m:Meta {id:$id}) SET m.topicsJson=$topics, m.metaJson=$meta, "
        "m.kgVersion = CASE WHEN m.kgVersion IS NULL THEN $seed "
        "ELSE m.kgVersion + 1 END",
        id=META_ID, topics=rows["topicsJson"], meta=rows["metaJson"],
        seed=int(time.time()),
    )

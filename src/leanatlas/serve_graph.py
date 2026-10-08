"""/api/graph and /api/module/{name}/decls (P3 serve).

/api/graph reassembles the data.json document (schemaVersion 2) from what
`layout --store` persisted — byte-shape parity with the static file is the
schema-parity contract (spec §3): the frontend's one parser handles both.
One cached payload, invalidated by :Meta.kgVersion (spec §7).

/api/module/{name}/decls builds one DeclBlock (schemaVersion 1) live from the
database, reusing the pack's deterministic layout functions — same algorithms
as the pack builder; declaration order is name-sorted (the pack preserves
extract first-appearance order: content-equivalent, not byte-identical, spec §3).
"""
from __future__ import annotations

import json
import threading
from collections import OrderedDict
from typing import Any

from fastapi import APIRouter, HTTPException

from .declpack import assign_columns, node_size
from .serve_core import db_unavailable, ok, session

graph_router = APIRouter()
module_router = APIRouter()

_META_Q = (
    "MATCH (m:Meta {id:'kg'}) "
    "RETURN m.kgVersion AS kgVersion, m.metaJson AS metaJson, m.topicsJson AS topicsJson"
)
_NODES_Q = (
    "MATCH (m:Module) WHERE m.x IS NOT NULL "
    "RETURN m.name AS name, m.topic AS topic, m.x AS x, m.y AS y, m.r AS r, "
    "m.color AS color, m.declCount AS declCount, m.closureSize AS closureSize, "
    "m.isDeprecated AS isDeprecated, m.title AS title, m.docstring AS docstring "
    "ORDER BY m.topo"
)
# pair order [a, b] = [dep, importer]. build_document enumerates the edge
# array name-index-major (`for b in range(n) for a in reduced[b]` — the
# indices are filter_and_build's NAME-sorted order, reduced[b] name-index
# sorted), NOT importer-topo-major: topo and name orderings are unrelated
# permutations. Module names are unique, so ORDER BY b.name, a.name (ASCII
# codepoint order = Python sorted) reproduces the document's array verbatim;
# the RETURNed values stay the topo positions (node-array indices).
_VIZ_Q = (
    "MATCH (dep:Module)-[:VIZ]->(imp:Module) "
    "RETURN dep.topo AS a, imp.topo AS b ORDER BY imp.name, dep.name"
)
# build_document sorts each structureEdges list lexicographically on the
# (min, max)-normalized pair — ORDER BY a.topo, b.topo reproduces it.
_STRUCT_Q = (
    "MATCH (a:Module)-[r:STRUCTURE]->(b:Module) "
    "RETURN r.rel AS rel, a.topo AS a, b.topo AS b ORDER BY a.topo, b.topo"
)

_doc_cache: dict[str, Any] = {"kgVersion": None, "doc": None}


def assemble_graph_doc(
    node_rows: list[dict], viz_rows: list[dict], struct_rows: list[dict], meta: dict
) -> dict:
    """DB rows -> data.json-shaped document. Pure (ungated tests). docstring is
    re-truncated to 1000 like build_document (the DB stores the full text)."""
    nodes = [
        {
            "name": r["name"], "topic": r["topic"], "x": r["x"], "y": r["y"],
            "r": r["r"], "color": r["color"], "declCount": r["declCount"],
            "closureSize": r["closureSize"], "isDeprecated": r["isDeprecated"],
            "title": r["title"],
            "docstring": r["docstring"][:1000] if r["docstring"] is not None else None,
        }
        for r in node_rows
    ]
    return {
        "schemaVersion": 2,
        "meta": meta["meta"],
        "topics": meta["topics"],
        "nodes": nodes,
        "edges": [[e["a"], e["b"]] for e in viz_rows],
        "structureEdges": {
            rel: [[e["a"], e["b"]] for e in struct_rows if e["rel"] == rel]
            for rel in ("extends", "instantiates", "fields")
        },
    }


@graph_router.get("/api/graph")
def get_graph() -> dict:
    meta_row = None
    try:
        with session() as s:
            meta_row = s.run(_META_Q).single()
            if meta_row is None or meta_row["topicsJson"] is None:
                # A wiped graph invalidates everything; a surviving process
                # must not outlive its caches (I1: without this, a 503 would
                # leave generation-N doc/blocks cached to be served again
                # should numbering ever restart from a stale value).
                _doc_cache.update(kgVersion=None, doc=None)
                with _block_cache_lock:
                    _block_cache.clear()
                raise HTTPException(
                    status_code=503,
                    detail="layout not stored — run `leanatlas layout --store`",
                )
            if _doc_cache["kgVersion"] == meta_row["kgVersion"] and _doc_cache["doc"]:
                return ok(_doc_cache["doc"])
            nodes = [dict(r) for r in s.run(_NODES_Q)]
            viz = [dict(r) for r in s.run(_VIZ_Q)]
            struct = [dict(r) for r in s.run(_STRUCT_Q)]
    except HTTPException:
        raise
    except Exception as exc:
        raise db_unavailable(exc) from exc
    doc = assemble_graph_doc(
        nodes, viz, struct,
        {"meta": json.loads(meta_row["metaJson"]),
         "topics": json.loads(meta_row["topicsJson"])},
    )
    _doc_cache["kgVersion"] = meta_row["kgVersion"]
    _doc_cache["doc"] = doc
    return ok(doc)


_DECLS_Q = (
    "MATCH (d:Declaration {module:$mod}) "
    "RETURN d.name AS name, d.kind AS kind ORDER BY d.name"
)
_INTRA_Q = (
    "MATCH (a:Declaration {module:$mod})-[:DEPENDS_ON]->(b:Declaration {module:$mod}) "
    "RETURN DISTINCT a.name AS src, b.name AS dst ORDER BY a.name, b.name"
)

_block_cache: OrderedDict[str, dict] = OrderedDict()
# Sync FastAPI endpoints run in uvicorn's thread pool, so the LRU can be hit
# from several threads at once — every mutation (and the 503 clear above)
# takes the lock.
_block_cache_lock = threading.Lock()
_BLOCK_CACHE_MAX = 128


def build_block_doc(module: str, decls: list[dict], edges: list[tuple[int, int]]) -> dict:
    """DB rows -> DeclBlock document, reusing the pack's deterministic layout
    functions (assign_columns/node_size). Pure — the ungated test asserts
    document parity with declpack.build_module_block on identical inputs."""
    xy = assign_columns(len(decls), edges)
    deg = [0] * len(decls)
    for src, dst in edges:
        deg[src] += 1
        deg[dst] += 1
    return {
        "schemaVersion": 1,
        "module": module,
        "decls": [
            {"name": d["name"], "k": d["kind"], "x": xy[i][0], "y": xy[i][1],
             "s": node_size(deg[i])}
            for i, d in enumerate(decls)
        ],
        "e": [list(e) for e in edges],
    }


@module_router.get("/api/module/{name}/decls")
def module_decls(name: str) -> dict:
    with _block_cache_lock:
        cached = _block_cache.get(name)
        if cached:
            _block_cache.move_to_end(name)
    if cached:
        return ok(cached)
    try:
        with session() as s:
            decls = [dict(r) for r in s.run(_DECLS_Q, mod=name)]
            if not decls:
                known = s.run(
                    "MATCH (m:Module {name:$mod}) RETURN count(m) AS n", mod=name
                ).single()["n"]
                if not known:
                    raise HTTPException(404, f"unknown module: {name}")
                raise HTTPException(404, f"no declaration data for {name}")
            pairs = [dict(r) for r in s.run(_INTRA_Q, mod=name)]
    except HTTPException:
        raise
    except Exception as exc:
        raise db_unavailable(exc) from exc
    idx = {d["name"]: i for i, d in enumerate(decls)}
    edges = sorted({
        (idx[r["src"]], idx[r["dst"]])
        for r in pairs
        if r["src"] != r["dst"] and r["src"] in idx and r["dst"] in idx
    })
    doc = build_block_doc(name, decls, edges)
    with _block_cache_lock:
        _block_cache[name] = doc  # OrderedDict assignment moves it to the end
        while len(_block_cache) > _BLOCK_CACHE_MAX:
            _block_cache.popitem(last=False)
    return ok(doc)

"""`leanatlas serve`: FastAPI app over the live KG + static explorer (P3).

Mounts /api/* (graph/block endpoints in serve_graph.py, query endpoints in
serve_query.py) and the built web/dist, so one command serves the whole
explorer from one origin (spec §2: static-only serving survives a missing
database — no lifespan, the driver connects lazily per request).
"""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, FastAPI
from fastapi.staticfiles import StaticFiles

from .serve_core import db_unavailable, ok, session
from .serve_graph import graph_router, module_router
from .serve_query import query_router

health_router = APIRouter()


@health_router.get("/api/healthz")
def healthz() -> dict:
    try:
        with session() as s:
            decls = s.run(
                "MATCH (d:Declaration) WHERE d.module IS NOT NULL RETURN count(d) AS n"
            ).single()["n"]
            modules = s.run("MATCH (m:Module) RETURN count(m) AS n").single()["n"]
            meta = s.run(
                "MATCH (m:Meta {id:'kg'}) "
                "RETURN m.kgVersion AS v, m.topicsJson IS NOT NULL AS p"
            ).single()
    except Exception as exc:
        raise db_unavailable(exc) from exc
    return ok({
        "decls": decls,
        "modules": modules,
        "kgVersion": meta["v"] if meta else None,
        "layoutPresent": bool(meta and meta["p"]),
    })


def create_app(dist: Path | None = None) -> FastAPI:
    """dist: built web assets to host at / (API-only when None or missing)."""
    app = FastAPI(title="LeanAtlas serve", version="0.1.0")
    app.include_router(health_router)
    app.include_router(graph_router)
    app.include_router(module_router)
    app.include_router(query_router)
    if dist is not None and Path(dist).is_dir():
        # mounted last: routes registered above win, everything else is static
        app.mount("/", StaticFiles(directory=dist, html=True), name="dist")
    return app

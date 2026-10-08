"""Shared serve plumbing: lazy Neo4j driver, session context, response
helpers. Kept free of any router/app imports so serve_graph / serve_query can
import it without cycles. No lifespan events: the driver is a lazy module
singleton, so a dist-only serve never connects, and every database-touching
endpoint degrades to 503 on connection failure (spec §2 degradation ladder)."""
from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from fastapi import HTTPException

from . import load_neo4j as ldb
from .config import get_config

_DRIVER = None


def get_driver():
    """Lazy singleton — connecting at import/startup would break dist-only serving."""
    global _DRIVER
    if _DRIVER is None:
        _DRIVER = ldb.connect()
    return _DRIVER


def close_driver() -> None:
    """Test seam: drop the singleton between TestClient runs."""
    global _DRIVER
    if _DRIVER is not None:
        _DRIVER.close()
        _DRIVER = None


@contextmanager
def session() -> Iterator[Any]:
    s = get_driver().session(database=get_config().neo4j_db)
    try:
        yield s
    finally:
        s.close()


def ok(data: Any) -> dict:
    return {"ok": True, "data": data}


def db_unavailable(exc: Exception) -> HTTPException:
    return HTTPException(status_code=503, detail=f"neo4j unavailable: {exc}")

"""/api/search, /api/decl/{name}, /api/decls/batch, /api/decl/{name}/deps,
/api/depstrip (P3 serve). All read-only; payloads are the anti-N+1 shapes the
panels render from in one request (spec §4)."""
from __future__ import annotations

import re

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from .serve_core import db_unavailable, ok, session

query_router = APIRouter()

_ft_ready = False


def ensure_fulltext(s) -> None:
    """Idempotent, once per process. Created lazily on the first search — a
    dist-only serve never touches the index."""
    global _ft_ready
    if not _ft_ready:
        s.run(
            "CREATE FULLTEXT INDEX declSearch IF NOT EXISTS "
            "FOR (d:Declaration) ON EACH [d.name, d.shortName]"
        )
        _ft_ready = True


def fulltext_terms(q: str) -> str:
    """Query -> Lucene OR-of-prefixes: split on non-word chars, star each token
    ('le_iff' -> 'le_iff*'). Pure (ungated tests)."""
    toks = [t for t in re.split(r"[^\w]+", q) if t]
    return " ".join(t + "*" for t in toks)


_SEARCH_Q = (
    "CALL db.index.fulltext.queryNodes('declSearch', $q) YIELD node, score "
    "WHERE node.module IS NOT NULL "
    "RETURN node.name AS name, node.kind AS kind, node.module AS module, score "
    "ORDER BY score DESC, name LIMIT $limit"
)


@query_router.get("/api/search")
def search(q: str, limit: int = 20) -> dict:
    q = q.strip()
    if not q:
        return ok([])
    limit = max(1, min(limit, 100))
    terms = fulltext_terms(q)
    if not terms:
        return ok([])
    try:
        with session() as s:
            ensure_fulltext(s)
            rows = [
                {"name": r["name"], "kind": r["kind"], "module": r["module"]}
                for r in s.run(_SEARCH_Q, q=terms, limit=limit)
            ]
    except Exception as exc:
        raise db_unavailable(exc) from exc
    return ok(rows)


_DECL_Q = (
    "MATCH (d:Declaration {name:$name}) "
    "RETURN d.name AS name, d.shortName AS shortName, d.kind AS kind, "
    "d.module AS module, d.typeSignature AS typeSignature, "
    "d.docstring AS docstring, d.sourceFile AS sourceFile, "
    "d.startLine AS startLine, d.endLine AS endLine, "
    "d.sourceText AS sourceText, d.attrs AS attrs, "
    "d.isDeprecated AS isDeprecated, d.isExternal AS isExternal"
)

_SOURCE_BASE = "https://github.com/leanprover-community/mathlib4/blob/master/"


def source_url(module: str | None, start_line: int | None) -> str | None:
    """mathlib4 GitHub deep link. The module name maps 1:1 to its file path
    (Mathlib.Order.Basic -> Mathlib/Order/Basic.lean) — sidesteps the absolute
    sourceFile paths the parser records. Pure (ungated tests)."""
    if not module or not start_line:
        return None
    return f"{_SOURCE_BASE}{module.replace('.', '/')}.lean#L{start_line}"


@query_router.get("/api/decl/{name}")
def decl_detail(name: str) -> dict:
    try:
        with session() as s:
            row = s.run(_DECL_Q, name=name).single()
    except Exception as exc:
        raise db_unavailable(exc) from exc
    if row is None:
        raise HTTPException(404, f"unknown declaration: {name}")
    d = dict(row)
    d["sourceUrl"] = source_url(d["module"], d["startLine"])
    return ok(d)


_ALLOWED_FIELDS = ("name", "kind", "module", "typeSignature", "docstring",
                   "startLine", "endLine", "sourceText", "sourceUrl")


class BatchBody(BaseModel):
    names: list[str] = Field(min_length=1, max_length=500)
    fields: list[str] | None = None


_BATCH_Q = (
    "UNWIND $names AS nm MATCH (d:Declaration {name:nm}) "
    "RETURN d.name AS name, d.kind AS kind, d.module AS module, "
    "d.typeSignature AS typeSignature, d.docstring AS docstring, "
    "d.startLine AS startLine, d.endLine AS endLine, d.sourceText AS sourceText"
)


@query_router.post("/api/decls/batch")
def decls_batch(body: BatchBody) -> dict:
    fields = body.fields or ["name", "kind", "module", "typeSignature",
                             "docstring", "startLine"]
    bad = [f for f in fields if f not in _ALLOWED_FIELDS]
    if bad:
        raise HTTPException(422, f"unknown fields: {bad}")
    try:
        with session() as s:
            rows = [dict(r) for r in s.run(_BATCH_Q, names=body.names)]
    except Exception as exc:
        raise db_unavailable(exc) from exc
    for r in rows:
        r["sourceUrl"] = source_url(r["module"], r["startLine"])
    return ok([{f: r.get(f) for f in fields} for r in rows])


def _deps_q(direction: str) -> str:
    pattern = (
        "MATCH (d:Declaration {name:$name})<-[:DEPENDS_ON]-(other:Declaration)"
        if direction == "in" else
        "MATCH (d:Declaration {name:$name})-[:DEPENDS_ON]->(other:Declaration)"
    )
    return (
        f"{pattern} "
        "RETURN other.name AS other, other.kind AS otherKind, "
        "coalesce(other.module, '(external)') AS otherModule, d.kind AS selfKind "
        "ORDER BY otherModule, other LIMIT $limit"
    )


def group_deps(name: str, direction: str, self_kind: str | None,
               rows: list[dict]) -> dict:
    """Rows -> grouped payload (spec §4: one request, zero follow-ups). Edges
    carry both endpoints with kinds; the group key is the other side's module
    ('(external)' for deps into core/std names — they carry no attribution).
    Pure (ungated tests)."""
    groups: dict[str, list[dict]] = {}
    for r in rows:
        if direction == "in":
            edge = {"from": r["other"], "fromKind": r["otherKind"],
                    "to": name, "toKind": self_kind}
        else:
            edge = {"from": name, "fromKind": self_kind,
                    "to": r["other"], "toKind": r["otherKind"]}
        groups.setdefault(r["otherModule"], []).append(edge)
    return {
        "dir": direction,
        "total": len(rows),
        "groups": [
            {"module": m, "count": len(es), "edges": es}
            for m, es in sorted(groups.items())
        ],
    }


@query_router.get("/api/decl/{name}/deps")
def decl_deps(name: str, dir: str = "in", limit: int = 200) -> dict:
    if dir not in ("in", "out"):
        raise HTTPException(422, "dir must be 'in' or 'out'")
    limit = max(1, min(limit, 1000))
    try:
        with session() as s:
            row = s.run(
                "MATCH (d:Declaration {name:$name}) RETURN d.kind AS k", name=name
            ).single()
            if row is None:
                raise HTTPException(404, f"unknown declaration: {name}")
            rows = [dict(r) for r in s.run(_deps_q(dir), name=name, limit=limit)]
    except HTTPException:
        raise
    except Exception as exc:
        raise db_unavailable(exc) from exc
    return ok(group_deps(name, dir, row["k"], rows))


_STRIP_Q = (
    "MATCH (a:Declaration {module:$a})-[:DEPENDS_ON]->(b:Declaration {module:$b}) "
    "RETURN DISTINCT a.name AS src, a.kind AS srcKind, b.name AS dst, b.kind AS dstKind "
    "ORDER BY src, dst LIMIT $limit"
)


def group_strip(rows: list[dict]) -> dict:
    """Group the A->B dependency strip by source declaration. Pure."""
    groups: dict[str, dict] = {}
    for r in rows:
        g = groups.setdefault(r["src"], {"kind": r["srcKind"], "edges": []})
        g["edges"].append({"to": r["dst"], "kind": r["dstKind"]})
    return {
        "total": len(rows),
        "groups": [
            {"from": s, "kind": g["kind"], "count": len(g["edges"]),
             "edges": g["edges"]}
            for s, g in sorted(groups.items())
        ],
    }


@query_router.get("/api/depstrip")
def depstrip(a: str, b: str, limit: int = 500) -> dict:
    if a == b:
        raise HTTPException(422, "a and b must differ")
    limit = max(1, min(limit, 2000))
    try:
        with session() as s:
            rows = [dict(r) for r in s.run(_STRIP_Q, a=a, b=b, limit=limit)]
    except Exception as exc:
        raise db_unavailable(exc) from exc
    return ok(group_strip(rows))

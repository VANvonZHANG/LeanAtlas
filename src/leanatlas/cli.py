"""leanatlas CLI: parse / load / query / drop / layout."""
import json
import os
from datetime import UTC, datetime
from pathlib import Path

import typer
from rich import print as rprint

from . import declpack as declpack_mod
from . import layout as layout_mod
from . import load_neo4j as ldb
from . import parse_source
from .config import get_config
from .models import extract_from_json, module_from_json
from .neo4j_schema import apply_schema, drop_kg_batched

app = typer.Typer(add_completion=False, help="Build a Neo4j knowledge graph from mathlib.")

# Upper bound for typeSignature length: a few declarations' repr fallbacks can
# reach hundreds of MB and must be truncated
MAX_TYPE_SIGNATURE = 10000


@app.command()
def parse(
    root: str = typer.Option(
        ..., "--mathlib-path",
        help="mathlib root directory (module names are computed relative to it)",
    ),
    out: str = typer.Option("structure.jsonl", "--out"),
    glob: str = typer.Option("*.lean", "--glob"),
) -> None:
    """Scan .lean files and produce structure.jsonl."""
    files = [str(p) for p in Path(root).rglob(glob) if ".lake" not in p.parts]
    n = parse_source.write_structure_jsonl(files, out, root=root)
    rprint(f"[green]Parsed {n} modules -> {out}[/green]")


@app.command()
def load(
    structure: str = typer.Option("structure.jsonl", "--structure"),
    extract: str = typer.Option(None, "--extract"),
) -> None:
    """Load structure.jsonl (+ optional extract.jsonl) into the configured database."""
    cfg = get_config()
    driver = ldb.connect()
    recs = [
        module_from_json(ln)
        for ln in Path(structure).read_text(encoding="utf-8").split("\n")
        if ln.strip()
    ]
    with driver.session(database=cfg.neo4j_db) as s:
        s.execute_write(apply_schema)
        s.execute_write(ldb.load_modules, recs)
        s.execute_write(ldb.load_namespaces, recs)
        s.execute_write(ldb.load_declarations, recs)
        s.execute_write(ldb.load_imports, recs)
        if extract:
            erecs = []
            skipped = 0
            truncated = 0
            # Split on \n only (not splitlines — it also splits at \f/\v/ and
            # other Unicode line boundaries, which the Lean Json.str does not
            # escape, so one record would be shredded into fragments)
            for ln in Path(extract).read_text(encoding="utf-8").split("\n"):
                if not ln.strip():
                    continue
                try:
                    rec = extract_from_json(ln)
                except Exception:
                    # A few extract records contain content msgspec cannot strictly
                    # decode; skip them instead of aborting
                    skipped += 1
                    continue
                # Truncate pathological typeSignatures (a few repr fallbacks reach
                # hundreds of MB and would time out bolt writes)
                if len(rec.typeSignature) > MAX_TYPE_SIGNATURE:
                    rec.typeSignature = (
                        rec.typeSignature[:MAX_TYPE_SIGNATURE] + "...<truncated>"
                    )
                    truncated += 1
                erecs.append(rec)
            if skipped:
                rprint(f"[yellow]Skipped {skipped} undecodable extract records[/yellow]")
            if truncated:
                rprint(
                    f"[yellow]Truncated {truncated} overlong typeSignatures "
                    f"(>{MAX_TYPE_SIGNATURE} chars)[/yellow]"
                )
            ldb.load_dependencies_chunked(s, erecs)
            ldb.load_relationships_chunked(s, erecs)
            # v2.5: derive the mathlib type set from structure.jsonl and attach
            # HAS_FIELD/HAS_CONSTRUCTOR
            mathlib_type_names = {
                d.name for r in recs for d in r.declarations
                if d.kind in ("structure", "class", "inductive")
            }
            if mathlib_type_names and erecs:
                ldb.load_fields_constructors_chunked(s, erecs, mathlib_type_names)
    driver.close()
    rprint(f"[green]Load complete: {len(recs)} modules -> {cfg.neo4j_db}[/green]")


@app.command()
def query(cypher: str = typer.Argument(...)) -> None:
    """Run a read-only Cypher query against the configured database and print results."""
    cfg = get_config()
    driver = ldb.connect()
    with driver.session(database=cfg.neo4j_db) as s:
        for row in s.run(cypher):
            rprint(dict(row))
    driver.close()


@app.command()
def drop() -> None:
    """Drop KG nodes (Declaration/Module/Namespace) and relationships, keep other data."""
    cfg = get_config()
    driver = ldb.connect()
    with driver.session(database=cfg.neo4j_db) as s:
        drop_kg_batched(s)
    driver.close()
    rprint(f"[yellow]KG nodes dropped ({cfg.neo4j_db})[/yellow]")


@app.command()
def layout(
    structure: Path = typer.Option(Path("structure.jsonl"), "--structure",
                                   help="path to structure.jsonl"),
    out: Path = typer.Option(Path("web/public/data.json"), "--out", help="output data.json path"),
    topics: Path = typer.Option(Path("web/topics.toml"), "--topics", help="topic table path"),
    scope: str = typer.Option("mathlib", "--scope", help="P0 supports mathlib only"),
    extract: Path = typer.Option(Path("extract.jsonl"), "--extract",
                                 help="extract.jsonl (v3, module field) for structure edges"),
    mathlib_path_arg: Path = typer.Option(None, "--mathlib-path",
                                          help="local mathlib checkout (with built .lake)"),
    store: bool = typer.Option(False, "--store",
                               help="also persist the layout into the configured "
                                    "database (live-serve mode)"),
) -> None:
    """Compute the module-level layout and export data.json (visualization layer P0)."""
    if scope != "mathlib":
        typer.echo(f"error: --scope {scope} not implemented (P0 supports mathlib only)", err=True)
        raise typer.Exit(code=2)
    records, bad = layout_mod.read_structure(structure)
    topic_list = layout_mod.load_topics(topics)
    env_path = os.environ.get("LEANATLAS_MATHLIB_PATH")
    provided = mathlib_path_arg or env_path
    if not provided or not Path(provided).exists():
        typer.echo(
            "error: mathlib checkout not found. Pass --mathlib-path or set LEANATLAS_MATHLIB_PATH",
            err=True,
        )
        raise typer.Exit(code=2)
    mathlib_path = Path(provided)
    version = layout_mod.describe_mathlib(mathlib_path)
    doc = layout_mod.run_layout(records, topic_list, version=version,
                                skipped_bad_lines=bad, extract_path=extract)
    layout_mod.write_document(doc, out)
    if store:
        from . import layout_store
        cfg = get_config()
        driver = ldb.connect()
        rows = layout_store.build_store_rows(doc)
        with driver.session(database=cfg.neo4j_db) as s:
            s.execute_write(layout_store.store_layout, rows)
            stored = s.run(
                "MATCH (m:Module) WHERE m.x IS NOT NULL RETURN count(m) AS n"
            ).single()["n"]
        driver.close()
        if stored != doc["meta"]["stats"]["modules"]:
            typer.echo(
                f"warn: stored {stored} of {doc['meta']['stats']['modules']} modules — "
                "database was loaded from a different structure.jsonl?",
                err=True,
            )
        typer.echo(f"layout --store: {stored} modules persisted -> {cfg.neo4j_db}")
    stats = doc["meta"]["stats"]
    typer.echo(
        f"layout: modules={stats['modules']} edgesDirect={stats['edgesDirect']} "
        f"edgesReduced={stats['edgesReduced']} "
        f"structure(E/I/F)={stats['extendsEdges']}/{stats['instantiatesEdges']}/"
        f"{stats['fieldsEdges']} "
        f"badLines={bad} → {out}"
    )


@app.command()
def declpack(
    extract: Path = typer.Option(Path("extract.jsonl"), "--extract",
                                 help="extract.jsonl (v3, module field)"),
    structure: Path = typer.Option(Path("structure.jsonl"), "--structure"),
    data: Path = typer.Option(Path("web/public/data.json"), "--data",
                              help="data.json — alive modules come from its nodes"),
    out: Path = typer.Option(Path("web/public/declpack.bin"), "--out"),
    mathlib_path_arg: Path = typer.Option(None, "--mathlib-path",
                                          help="local mathlib checkout (with built .lake)"),
) -> None:
    """Build the declaration-level drill-down pack declpack.bin (P2)."""
    env_path = os.environ.get("LEANATLAS_MATHLIB_PATH")
    provided = mathlib_path_arg or env_path
    if not provided or not Path(provided).exists():
        typer.echo(
            "error: mathlib checkout not found. Pass --mathlib-path or set LEANATLAS_MATHLIB_PATH",
            err=True,
        )
        raise typer.Exit(code=2)
    data_doc = json.loads(Path(data).read_text(encoding="utf-8"))
    alive = [n["name"] for n in data_doc["nodes"]]
    version = layout_mod.describe_mathlib(Path(provided))
    now = datetime.now(UTC).isoformat(timespec="seconds")
    header, blocks = declpack_mod.run_declpack(
        extract, structure, alive, version=version, now=now)
    declpack_mod.write_pack(header, blocks, out)
    stats = header["meta"]["stats"]
    typer.echo(
        f"declpack: modules={stats['modules']} decls={stats['decls']} "
        f"edges={stats['edges']} kindsInferred={stats['kindsInferred']} "
        f"duplicates={stats['duplicateNames']} "
        f"size={out.stat().st_size / 1e6:.1f}MB -> {out}"
    )


@app.command()
def serve(
    host: str = typer.Option("127.0.0.1", "--host", help="bind address (0.0.0.0 opens LAN)"),
    port: int = typer.Option(8000, "--port"),
    dist: Path = typer.Option(Path("web/dist"), "--dist",
                              help="built web assets; API-only mode if missing"),
) -> None:
    """Serve the explorer (static) + query API (live Neo4j) from one origin (P3)."""
    import uvicorn

    from .serve import create_app

    if not dist.is_dir():
        typer.echo(f"serve: {dist} not found — serving API only", err=True)
        uvicorn.run(create_app(None), host=host, port=port)
    else:
        uvicorn.run(create_app(dist), host=host, port=port)


if __name__ == "__main__":
    app()

"""mathlib-kg CLI: parse / load / query / drop / layout."""
import os
from pathlib import Path

import typer
from rich import print as rprint

from . import layout as layout_mod
from . import load_neo4j as ldb
from . import parse_source
from .config import get_config
from .models import extract_from_json, module_from_json
from .neo4j_schema import apply_schema, drop_kg, drop_kg_batched

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
) -> None:
    """Compute the module-level layout and export data.json (visualization layer P0)."""
    if scope != "mathlib":
        typer.echo(f"error: --scope {scope} not implemented (P0 supports mathlib only)", err=True)
        raise typer.Exit(code=2)
    records, bad = layout_mod.read_structure(structure)
    topic_list = layout_mod.load_topics(topics)
    mathlib_path = Path(os.environ.get("MATHLIB_KG_MATHLIB_PATH", "/path/to/mathlib4"))
    version = layout_mod.describe_mathlib(mathlib_path)
    doc = layout_mod.run_layout(records, topic_list, version=version,
                                skipped_bad_lines=bad, extract_path=extract)
    layout_mod.write_document(doc, out)
    stats = doc["meta"]["stats"]
    typer.echo(
        f"layout: modules={stats['modules']} edgesDirect={stats['edgesDirect']} "
        f"edgesReduced={stats['edgesReduced']} "
        f"structure(E/I/F)={stats['extendsEdges']}/{stats['instantiatesEdges']}/{stats['fieldsEdges']} "
        f"badLines={bad} → {out}"
    )


if __name__ == "__main__":
    app()

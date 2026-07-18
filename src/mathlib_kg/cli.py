"""mathlib-kg CLI: parse / load / query / drop."""
from pathlib import Path

import typer
from rich import print as rprint

from . import load_neo4j as ldb
from . import parse_source
from .config import get_config
from .models import extract_from_json, module_from_json
from .neo4j_schema import apply_schema, drop_kg, drop_kg_batched

app = typer.Typer(add_completion=False, help="Build a Neo4j knowledge graph from mathlib.")

# typeSignature 长度上限：个别声明的 repr 兜底可达数百 MB，必须截断
MAX_TYPE_SIGNATURE = 10000


@app.command()
def parse(
    root: str = typer.Option(..., "--mathlib-path", help="mathlib 根目录（模块名据此相对计算）"),
    out: str = typer.Option("structure.jsonl", "--out"),
    glob: str = typer.Option("*.lean", "--glob"),
) -> None:
    """扫 .lean 产出 structure.jsonl。"""
    files = [str(p) for p in Path(root).rglob(glob) if ".lake" not in p.parts]
    n = parse_source.write_structure_jsonl(files, out, root=root)
    rprint(f"[green]解析 {n} 个模块 -> {out}[/green]")


@app.command()
def load(
    structure: str = typer.Option("structure.jsonl", "--structure"),
    extract: str = typer.Option(None, "--extract"),
) -> None:
    """把 structure.jsonl（+可选 extract.jsonl）装载进配置库。"""
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
            # 只按 \n 切行（不用 splitlines——它会在 \f/\v/  等 Unicode 行边界上误切，
            # 而 Lean 的 Json.str 未转义这些字符，会把一条记录切成碎片）
            for ln in Path(extract).read_text(encoding="utf-8").split("\n"):
                if not ln.strip():
                    continue
                try:
                    rec = extract_from_json(ln)
                except Exception:
                    # 极少数 extract 记录含 msgspec 无法严格解码的内容，跳过不中断
                    skipped += 1
                    continue
                # 截断病态 typeSignature（个别 repr 兜底可达数百 MB，会令 bolt 写超时）
                if len(rec.typeSignature) > MAX_TYPE_SIGNATURE:
                    rec.typeSignature = (
                        rec.typeSignature[:MAX_TYPE_SIGNATURE] + "...<truncated>"
                    )
                    truncated += 1
                erecs.append(rec)
            if skipped:
                rprint(f"[yellow]跳过 {skipped} 条无法解码的 extract 记录[/yellow]")
            if truncated:
                rprint(f"[yellow]截断 {truncated} 条超长 typeSignature (>{MAX_TYPE_SIGNATURE} 字符)[/yellow]")
            ldb.load_dependencies_chunked(s, erecs)
            ldb.load_relationships_chunked(s, erecs)
    driver.close()
    rprint(f"[green]装载完成: {len(recs)} 模块 -> {cfg.neo4j_db}[/green]")


@app.command()
def query(cypher: str = typer.Argument(...)) -> None:
    """对配置库执行只读 Cypher 并打印结果。"""
    cfg = get_config()
    driver = ldb.connect()
    with driver.session(database=cfg.neo4j_db) as s:
        for row in s.run(cypher):
            rprint(dict(row))
    driver.close()


@app.command()
def drop() -> None:
    """清空 KG 节点（Declaration/Module/Namespace）及关系，保留库内其它数据。"""
    cfg = get_config()
    driver = ldb.connect()
    with driver.session(database=cfg.neo4j_db) as s:
        drop_kg_batched(s)
    driver.close()
    rprint(f"[yellow]已清空 KG 节点 ({cfg.neo4j_db})[/yellow]")


if __name__ == "__main__":
    app()

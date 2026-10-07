"""declpack builder: grouping, kinds, intra edges, layout, pack bytes, CLI."""
import json

from typer.testing import CliRunner

from leanatlas.cli import app
from leanatlas.declpack import (
    assign_columns,
    build_header,
    build_module_block,
    collect_kinds,
    infer_kind,
    node_size,
    run_declpack,
    write_pack,
)

runner = CliRunner()


def _extract_line(name, module, deps=(), **extra):
    rec = {
        "additiveVersion": None, "constructors": [], "deprecatedBy": None,
        "deps": [{"name": d, "inType": False, "inValue": True} for d in deps],
        "extends": [], "fields": [], "instancePriority": None,
        "instantiates": None, "module": module, "name": name,
        "typeSignature": "sig",
    }
    rec.update(extra)
    return json.dumps(rec)


def _structure_line(module, decls):
    return json.dumps({
        "module": module, "path": f"/x/{module}.lean", "docstring": None,
        "title": None, "tags": [], "authors": [], "isDeprecated": False,
        "imports": [], "namespaces": [],
        "declarations": [{"name": n, "kind": k, "shortName": n, "namespace": module,
                          "sourceFile": "/x", "startLine": 1, "endLine": 2,
                          "sourceText": "", "docstring": None, "attrs": [],
                          "isProtected": False, "isExternal": False,
                          "isDeprecated": False, "deprecatedSince": None}
                         for n, k in decls],
    })


def test_infer_kind_fallbacks():
    assert infer_kind({"instantiates": "Foo", "constructors": [], "extends": []}) == "instance"
    assert infer_kind({"instantiates": None, "constructors": [{"parent": "X"}], "extends": []}) == "inductive"
    assert infer_kind({"instantiates": None, "constructors": [], "extends": [{"parent": "X"}]}) == "class"
    assert infer_kind({"instantiates": None, "constructors": [], "extends": []}) == "def"


def test_collect_kinds_join_wins():
    recs = [json.loads(_structure_line("M.A", [("M.A.f", "def"), ("M.A.thm", "theorem")]))]
    kinds = collect_kinds(recs)
    assert kinds == {("M.A", "M.A.f"): "def", ("M.A", "M.A.thm"): "theorem"}


def test_run_declpack_groups_skips_and_keeps_intra_edges(tmp_path):
    extract = tmp_path / "extract.jsonl"
    extract.write_text("\n".join([
        _extract_line("M.A.f", "M.A", deps=["M.A.thm", "M.B.g", "M.A.f"]),  # cross + self dep
        _extract_line("M.A.thm", "M.A", deps=[]),
        _extract_line("M.B.g", "M.B", deps=["M.A.thm"]),  # cross-module both ways
        _extract_line("M.C.h", "M.C", deps=[]),  # module not alive -> dropped
    ]) + "\n")
    structure = tmp_path / "structure.jsonl"
    structure.write_text(_structure_line("M.A", [("M.A.thm", "theorem")]) + "\n")
    header, blocks = run_declpack(extract, structure, ["M.A", "M.B"],
                                  version="v4.30.0", now="2026-10-07T00:00:00Z")
    assert sorted(blocks) == ["M.A", "M.B"]
    a = json.loads(blocks["M.A"])
    assert [d["name"] for d in a["decls"]] == ["M.A.f", "M.A.thm"]
    assert a["decls"][0]["k"] == "def"        # not in structure.jsonl -> inferred
    assert a["decls"][1]["k"] == "theorem"    # joined from structure.jsonl
    assert a["e"] == [[0, 1]]                 # self-loop and cross-module dropped
    assert header["meta"]["stats"]["modules"] == 2
    assert header["meta"]["stats"]["decls"] == 3


def test_assign_columns_dag_depth_and_cycle_overflow():
    # 0 depends on nothing; 1 depends on 0; 2 depends on 1; 3<->4 form a cycle
    xy = assign_columns(5, [(1, 0), (2, 1), (3, 4), (4, 3)])
    assert xy[0][0] == 0.0
    assert xy[1][0] == 1.0
    assert xy[2][0] == 2.0
    assert xy[3][0] == xy[4][0] == 3.0  # overflow column past max depth
    # column 0 has one member -> y 0; deterministic zigzag for the cycle pair
    assert xy[0][1] == 0.0
    assert xy[3][1] == 0.0 and xy[4][1] == 1.5


def test_node_size_clamps():
    assert node_size(0) == 1.5
    assert node_size(4) == 3.5
    assert node_size(999) == 4.5  # sqrt clamp at 3.0


def test_build_module_block_exact_json():
    decls = [{"name": "M.A.f", "k": "def"}, {"name": "M.A.thm", "k": "theorem"}]
    block = build_module_block("M.A", decls, [(0, 1), (0, 1)])
    doc = json.loads(block)
    assert doc["module"] == "M.A" and doc["schemaVersion"] == 1
    assert doc["e"] == [[0, 1]]  # deduped + sorted at the bytes boundary
    assert [d["s"] for d in doc["decls"]] == [2.5, 2.5]  # deg 1 each, after dedupe


def test_write_pack_roundtrip_and_determinism(tmp_path):
    blocks = {"M.A": build_module_block("M.A", [{"name": "M.A.f", "k": "def"}], []),
              "M.B": build_module_block("M.B", [{"name": "M.B.g", "k": "def"}], [])}
    header = build_header(blocks, {"modules": 2, "decls": 2, "edges": 0},
                          version="v4.30.0", now="T")
    out1, out2 = tmp_path / "p1.bin", tmp_path / "p2.bin"
    write_pack(header, blocks, out1)
    write_pack(header, blocks, out2)
    b1, b2 = out1.read_bytes(), out2.read_bytes()
    assert b1 == b2  # byte-identical
    import struct as _s
    (hlen,) = _s.unpack("<Q", b1[:8])
    h = json.loads(b1[8 : 8 + hlen])
    base = 8 + hlen
    for name, hit in h["modules"].items():
        got = json.loads(b1[base + hit["o"] : base + hit["o"] + hit["l"]])
        assert got == json.loads(blocks[name])  # offsets land exactly on blocks


def test_cli_declpack_smoke(tmp_path):
    extract = tmp_path / "extract.jsonl"
    extract.write_text(_extract_line("M.A.f", "M.A", deps=["M.A.thm"]) + "\n" +
                       _extract_line("M.A.thm", "M.A") + "\n")
    structure = tmp_path / "structure.jsonl"
    structure.write_text(_structure_line("M.A", []) + "\n")
    data = tmp_path / "data.json"
    data.write_text(json.dumps({"schemaVersion": 2, "nodes": [{"name": "M.A"}]}))
    out = tmp_path / "declpack.bin"
    result = runner.invoke(app, [
        "declpack", "--extract", str(extract), "--structure", str(structure),
        "--data", str(data), "--out", str(out), "--mathlib-path", str(tmp_path),
    ])
    assert result.exit_code == 0, result.output
    assert out.exists() and out.stat().st_size > 0
    assert "modules=1" in result.output

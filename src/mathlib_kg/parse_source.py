"""Parse mathlib .lean files into structure.jsonl records."""
import re
from pathlib import Path
from typing import Optional

import msgspec

from .models import Declaration, Import, ModuleRecord, module_to_json

# ---- Module-level regexes ----
AUTHORS_RE = re.compile(r"Authors:\s*(.+)")
MODULE_DOC_RE = re.compile(r"/-!(.*?)-/", re.DOTALL)
IMPORT_RE = re.compile(r"^\s*(public\s+)?import\s+([A-Za-z_][\w.]*)", re.MULTILINE)
DEPRECATED_MODULE_RE = re.compile(r"^\s*deprecated_module\b", re.MULTILINE)

# ---- Declaration-level regexes ----
DECL_RE = re.compile(
    r"^(?P<attrs>(?:@\[[^\]]*\]\s*)*)"
    r"(?P<mods>(?:(?:protected|private|noncomputable|partial)\s+)*)"
    r"(?P<kind>theorem|lemma|def|instance|class|structure|inductive|axiom|abbrev)\b"
    r"(?:\s+(?P<name>[A-Za-z_][A-Za-z0-9_'.]*))?"
)
NS_OPEN_RE = re.compile(r"^\s*namespace\s+(\S+)")
DOC_LINE_RE = re.compile(r"/--\s*(.*?)\s*-/")
ATTR_RE = re.compile(r"@\[([^\]]*)\]")


class ModuleMeta(msgspec.Struct):
    module: str
    path: str
    docstring: Optional[str] = None
    title: Optional[str] = None
    tags: list[str] = msgspec.field(default_factory=list)
    authors: list[str] = msgspec.field(default_factory=list)
    isDeprecated: bool = False
    imports: list[Import] = msgspec.field(default_factory=list)


def _parse_tags(doc: str) -> list[str]:
    lines = doc.splitlines()
    for i, ln in enumerate(lines):
        if ln.strip().lower().startswith("## tags"):
            for nxt in lines[i + 1:]:
                if nxt.strip():
                    return [t.strip() for t in nxt.split(",") if t.strip()]
            break
    return []


def _parse_title(doc: str) -> Optional[str]:
    for ln in doc.splitlines():
        s = ln.strip()
        if s.startswith("# "):
            return s[2:].strip()
    return None


def parse_module_meta(text: str, path: str) -> ModuleMeta:
    am = AUTHORS_RE.search(text)
    authors = [a.strip() for a in am.group(1).split(",") if a.strip()] if am else []
    docstring = title = None
    tags: list[str] = []
    if mdoc := MODULE_DOC_RE.search(text):
        docstring = mdoc.group(1).strip()
        title = _parse_title(docstring)
        tags = _parse_tags(docstring)
    imports = [
        Import(name=m.group(2), isPublic=bool(m.group(1)))
        for m in IMPORT_RE.finditer(text)
    ]
    return ModuleMeta(
        module=Path(path).stem,
        path=path,
        docstring=docstring,
        title=title,
        tags=tags,
        authors=authors,
        isDeprecated=bool(DEPRECATED_MODULE_RE.search(text)),
        imports=imports,
    )


def _split_attrs(attrs_block: str) -> list[str]:
    out: list[str] = []
    for m in ATTR_RE.finditer(attrs_block):
        out.extend(p.strip() for p in m.group(1).split() if p.strip())
    return out


def parse_declarations(
    text: str, source_file: str, warnings: list[str]
) -> list[Declaration]:
    lines = text.splitlines()
    # Top-level declaration headers (no indentation at line start)
    decl_starts: list[tuple[int, re.Match]] = []
    for i, ln in enumerate(lines):
        if ln[:1].isspace():
            continue
        m = DECL_RE.match(ln)
        if m and m.group("kind"):
            decl_starts.append((i, m))

    ns_stack: list[str] = []
    pending_doc: Optional[str] = None
    pending_attrs: list[str] = []
    results: list[Declaration] = []
    di = 0
    collecting_doc = False
    doc_buf: list[str] = []

    for i, ln in enumerate(lines):
        stripped = ln.strip()
        if collecting_doc:
            # Multi-line docstring: keep collecting until a line containing `-/`
            if "-/" in stripped:
                doc_buf.append(stripped.split("-/", 1)[0])
                pending_doc = "\n".join(p for p in doc_buf if p).strip()
                doc_buf = []
                collecting_doc = False
            else:
                doc_buf.append(stripped)
            continue
        if m := NS_OPEN_RE.match(ln):
            ns_stack.append(m.group(1))
            pending_doc = None
            continue
        if re.match(r"^end(?:\s+\S+)?\s*$", ln):
            if ns_stack:
                ns_stack.pop()
            pending_doc = None
            continue
        if stripped.startswith("/--"):
            dm = DOC_LINE_RE.match(stripped)
            if dm:
                pending_doc = dm.group(1)
            else:
                after = stripped[3:].strip()
                if "-/" in after:
                    pending_doc = after.split("-/", 1)[0].strip()
                else:
                    doc_buf = [after] if after else []
                    collecting_doc = True
            continue
        if stripped.startswith("@["):
            pending_attrs.extend(_split_attrs(ln))
            continue
        if di < len(decl_starts) and decl_starts[di][0] == i:
            _, m = decl_starts[di]
            di += 1
            kind = m.group("kind")
            name_raw = m.group("name") or ""
            ns = ".".join(ns_stack)
            start_idx = i
            end_idx = decl_starts[di][0] if di < len(decl_starts) else len(lines)
            src = "\n".join(lines[start_idx:end_idx])
            if not name_raw and kind != "instance":
                warnings.append(f"{source_file}:{start_idx + 1}: cannot parse {kind} name")
                pending_doc = None
                pending_attrs = []
                continue
            mods = m.group("mods") or ""
            # Fully qualified name = namespace + short name (matches Lean constant
            # names, so it aligns with extract)
            qualified = (ns + "." + name_raw) if (ns and name_raw) else name_raw
            results.append(
                Declaration(
                    name=qualified,
                    shortName=name_raw.rsplit(".", 1)[-1] if name_raw else "",
                    kind=kind,
                    namespace=ns,
                    docstring=pending_doc,
                    sourceFile=source_file,
                    startLine=start_idx + 1,
                    endLine=end_idx + 1,
                    sourceText=src,
                    attrs=list(pending_attrs),
                    isProtected="protected" in mods,
                )
            )
            pending_doc = None
            pending_attrs = []
    return results


def _module_name(path: str, root: Optional[str] = None) -> str:
    p = Path(path)
    if root:
        try:
            rel = p.relative_to(root)
            return ".".join(rel.with_suffix("").parts)
        except ValueError:
            pass
    return p.stem


def parse_file(path: str, root: Optional[str] = None) -> tuple[ModuleRecord, list[str]]:
    text = Path(path).read_text(encoding="utf-8")
    warnings: list[str] = []
    meta = parse_module_meta(text, path)
    module_name = _module_name(path, root) or meta.module
    decls = parse_declarations(text, path, warnings)
    ns_seen: set[str] = set()
    ns_list: list[str] = []
    for d in decls:
        if d.namespace and d.namespace not in ns_seen:
            ns_seen.add(d.namespace)
            ns_list.append(d.namespace)
    rec = ModuleRecord(
        module=module_name,
        path=path,
        docstring=meta.docstring,
        title=meta.title,
        tags=meta.tags,
        authors=meta.authors,
        isDeprecated=meta.isDeprecated,
        imports=meta.imports,
        namespaces=ns_list,
        declarations=decls,
    )
    return rec, warnings


def write_structure_jsonl(
    paths: list[str], out_path: str, root: Optional[str] = None
) -> int:
    n = 0
    with open(out_path, "w", encoding="utf-8") as f:
        for p in paths:
            rec, _ = parse_file(p, root)
            f.write(module_to_json(rec) + "\n")
            n += 1
    return n

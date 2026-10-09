# Changelog

## v0.4.0 (2026-10-09)

### Added
- `leanatlas serve`: a local FastAPI over the live Neo4j graph — declaration
  search across all ~766k attributed declarations, on-demand declaration
  details (type signature, docstring, mathlib4 source deep links — source
  links and docstrings currently appear only on declarations the source
  parser captured, ~15% of attributed declarations; a known parser bug,
  fix planned next release), cross-module dependency queries
  (per-declaration in/out, module-to-module strips), and DB-served
  overview/declaration graphs via `leanatlas layout --store`. The static
  explorer degrades gracefully when the server is absent.
- Loader v3 module attribution: extract records now backfill each
  declaration's defining module, type signature, and fallback kind in the
  database (existing databases need one re-run of `leanatlas load`).

## v0.3.0 (2026-10-07)

### Added
- Declaration-level drill-down: pin a module and hit "explore declarations"
  to open its internal declaration graph (kinds color-coded, intra-module
  dependency edges), lazy-loaded per module from a single `declpack.bin` pack
  via HTTP Range requests. Deep-linkable with `#mod=…`; PNG export works in
  both views. Build the pack with `leanatlas declpack` (see web/DECLPACK.md).

## v0.2.0 (2026-10-07)

- Topic label styling in the explorer: show/hide, size, color, opacity, and
  zoom-following labels (adjustable in the new topics panel; session-local).

## v0.1.0 (2026-10-06)

First public release.

- Knowledge-graph pipeline: parse → extract (kernel truth incl. defining
  module, structural relations) → Neo4j load (declarations, modules,
  namespaces, 11 edge kinds).
- Deterministic module-map layout engine (`leanatlas layout`).
- Interactive explorer: search/fly-to, pin closure highlighting, topic
  filters, structure-edge overlay (extends/instantiates/fields) with live
  color & curvature controls, URL deep links, PNG export.

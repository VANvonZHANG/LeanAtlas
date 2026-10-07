# Changelog

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

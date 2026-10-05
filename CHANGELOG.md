# Changelog

## v0.1.0 (unreleased)

First public release.

- Knowledge-graph pipeline: parse → extract (kernel truth incl. defining
  module, structural relations) → Neo4j load (declarations, modules,
  namespaces, 11 edge kinds).
- Deterministic module-map layout engine (`leanatlas layout`).
- Interactive explorer: search/fly-to, pin closure highlighting, topic
  filters, structure-edge overlay (extends/instantiates/fields) with live
  color & curvature controls, URL deep links, PNG export.

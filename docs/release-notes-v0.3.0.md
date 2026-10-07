# LeanAtlas v0.3.0

Declaration-level drill-down.

- **Explore inside a module**: pin a module and hit "explore declarations"
  to open its internal declaration graph — every theorem, def, instance,
  class and structure defined there, color-coded by kind, laid out
  left-to-right from foundations to dependents, with the module's internal
  dependency edges. The familiar interactions carry over: pin a declaration
  to highlight its transitive closure, drive edge density, hover to trace
  direct dependencies, export the view as PNG.
- **One file, loaded per module**: all declaration data lives in a single
  `declpack.bin` pack (65 MB for mathlib v4.30: 7,950 module blocks,
  549,683 declarations, 1.47 M intra-module edges) that the browser reads
  with HTTP Range requests — each drill downloads exactly one small block,
  never the whole file.
- **Deep links**: declaration views are shareable — `#mod=Mathlib.Order.Basic`
  opens the module's graph directly, `#mod=…&node=le_iff_eq_or_lt` pins a
  declaration inside it, and the camera round-trips with the view.
- Hardened URL restore: a hand-mangled hash can no longer crash the app, and
  stale pins/hovers/topic filters never leak across the view switch.

The declaration pack is **not** shipped as a release asset in v0.3.0 — build
it locally with `leanatlas declpack` (one command, needs the extract/structure
files; see web/DECLPACK.md). Without the pack the drill button degrades to an
explanatory error panel; every other feature works unchanged.

Full changelog: https://github.com/VANvonZHANG/LeanAtlas/compare/v0.2.0...v0.3.0

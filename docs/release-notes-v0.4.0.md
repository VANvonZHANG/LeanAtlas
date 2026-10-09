# LeanAtlas v0.4.0

Live queries: `leanatlas serve`.

- **One command, whole explorer**: `leanatlas serve` starts a local FastAPI
  over the live Neo4j graph and serves the built web app from the same
  origin — no CORS, loopback by default. Without the server (or the
  database) the static explorer keeps working exactly as before; the app
  degrades gracefully through three levels.
- **Search every declaration**: the search box now reaches all ~766k
  attributed declarations (not just the 8k module names) when the API is
  up. Pick a declaration to fly to its module, drill in, and pin it.
- **Declaration details on demand**: selecting a declaration shows its type
  signature, docstring, and — where the source parser captured line
  numbers — a deep link into the mathlib4 source on GitHub. Coverage of
  source links/docstrings is currently limited (~15% of declarations) by a
  known parser bug; the fix is planned for the next release.
- **Who uses this?**: a new dependency panel answers per-declaration
  cross-module reverse/forward dependencies grouped by module, plus
  module-to-module dependency strips.
- **Database-served rendering**: with `leanatlas layout --store` the
  overview map and per-module declaration graphs are served live from the
  database (byte-shape identical to the static files, pinned by parity
  tests) — `data.json`/`declpack.bin` become optional static-deployment
  artifacts.
- Loader upgrade: extract records now attribute every declaration's
  defining module, type signature, and fallback kind in the database.
  **Upgrading**: existing databases need one re-run of `leanatlas load`
  (~30 min) to gain attribution; the release notes' `data.json` below works
  unchanged either way.

Full changelog: https://github.com/VANvonZHANG/LeanAtlas/compare/v0.3.0...v0.4.0

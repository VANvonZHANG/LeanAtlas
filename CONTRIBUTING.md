# Contributing

Thanks for your interest in LeanAtlas!

## Setup

```bash
git clone https://github.com/<you>/leanatlas && cd leanatlas
uv sync --extra dev
cd web && pnpm install
```

## Before submitting

- `ruff check src tests` and `pytest -q` must pass (Python side).
- `pnpm vitest run` and `pnpm build` must pass (web side).
- Keep commits small and in English; code and comments are English-only.

## Notes

- The Neo4j-backed tests are skipped automatically when no `LEANATLAS_NEO4J_*`
  environment is configured.
- `extract/` is a self-contained Lake project pinned to the same Lean
  toolchain as the mathlib checkout you test against.

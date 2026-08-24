# Contributing

Thanks for considering a contribution to this template. It exists to
demonstrate a specific, opinionated take on Modular Monolith architecture in
FastAPI — contributions are welcome, but should reinforce that shape rather
than work around it.

## Before you start

Read [`docs/README.md`](docs/README.md) first, especially
[`docs/architecture.md`](docs/architecture.md). The module boundaries
(`public_api.py` as the only cross-module surface, `.importlinter`'s
contracts, the `api → facades → modules → shared` layering) aren't
conventions to keep in mind — they're enforced by the test suite, and a PR
that violates one will fail CI regardless of how the surrounding code looks.

If you're adding a new module, [`docs/adding-a-module.md`](docs/adding-a-module.md)
is a checklist written from actually adding one — follow it rather than
improvising the wiring.

## Development setup

```bash
python -m venv .venv
source .venv/bin/activate   # .venv\Scripts\activate on Windows
pip install -r requirements.txt
cp .env.example .env
pre-commit install
```

`pre-commit install` is not optional in practice: it runs `ruff`, `mypy`, and
`lint-imports` on `git commit`, which is the same three checks CI runs first.
Catching a boundary violation locally is a lot faster than catching it in CI.

## Before opening a pull request

```bash
ruff check .
mypy
lint-imports
pytest
```

All four must pass — this is exactly what `.github/workflows/ci.yml`'s
`lint-and-test` job runs. If your change touches anything under
`app/shared/database.py`, a module's `models.py`, or `alembic/`, also verify
against a real PostgreSQL instance before opening the PR — SQLite silently
skips the schema-per-module path entirely (see
[`docs/database.md`](docs/database.md#schema-per-module-isolation-postgresql)),
so a change that only looks correct against SQLite is not verified:

```bash
docker compose up -d db
DATABASE_URL=postgresql+asyncpg://app:app_password@localhost:5432/app_db alembic upgrade head
```

## What a good PR looks like here

- **Tests live with what they test.** Single-module changes get tests in
  `app/modules/<name>/tests/`; anything that genuinely spans modules or is
  cross-cutting infrastructure goes in `tests/` — see
  [`docs/testing.md`](docs/testing.md#where-tests-live). Don't add a new file
  to `tests/` for something that only touches one module.
- **A boundary change updates its `.importlinter` contract and its doc in the
  same PR**, not as a follow-up. `docs/architecture.md`'s "Enforcing
  boundaries" section explains why each contract exists — if your change
  needs a new one, explain it there the same way.
- **No `# type: ignore` or `# noqa` without a comment on the same or
  preceding line saying why.** A handful already exist in this codebase for
  genuine, documented tool limitations (see `app/shared/registry.py`'s
  docstring for one example) — that's the bar: a specific, checkable reason,
  not a way to silence an inconvenient error.
- **Comments explain the non-obvious "why," not the "what."** If a comment
  just restates what the next line of code does, delete it; well-named
  functions and variables should already say what. Deep rationale belongs in
  `docs/*.md`, not a multi-line comment block.

## Commit messages and PRs

Keep commit messages short and focused on *why*, not a line-by-line diff
summary — skim `git log` for the tone this repo already uses. Squash
work-in-progress commits before opening a PR; a reviewer shouldn't have to
reconstruct your debugging process.

## Reporting bugs vs. proposing changes

For a bug in the template itself (not a security issue — see
[`SECURITY.md`](SECURITY.md) for that), open a GitHub issue with enough detail
to reproduce it: what you ran, what you expected, what actually happened.
For anything that changes the architecture itself (a new cross-module
communication pattern, a different testing strategy), open an issue to
discuss it before writing the code — the shape of the change matters more
than the diff.

## Questions

Da-Wei Lin — daweilin7689@gmail.com

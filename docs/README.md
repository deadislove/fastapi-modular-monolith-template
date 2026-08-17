# Technical Documentation

Deep-dive reference for this template's Modular Monolith architecture. The root
[`README.md`](../README.md) covers setup and day-to-day commands (Quick Start,
Docker, API endpoint list); these docs cover the *why* behind the design.

| Doc | Covers |
|-----|--------|
| [architecture.md](architecture.md) | Module boundaries, layering, what's public vs. private, how it's enforced |
| [cross-module-communication.md](cross-module-communication.md) | The three ways modules talk to each other, and when to use which |
| [database.md](database.md) | Session lifecycle, `UnitOfWork`, schema-per-module, migrations |
| [testing.md](testing.md) | Test suite map, strategy, and the gotchas the suite already ran into |
| [quality-and-tooling.md](quality-and-tooling.md) | `ruff`/`mypy`/`lint-imports`/`pre-commit`/CI, and the production-readiness guards (JWT secret, rate limiter) |
| [adding-a-module.md](adding-a-module.md) | Checklist for adding a new module, written from actually adding `orders` |

Each module also documents its own contract next to its code — start there for a
single module's specifics:
[`app/modules/users/README.md`](../app/modules/users/README.md),
[`app/modules/products/README.md`](../app/modules/products/README.md),
[`app/modules/orders/README.md`](../app/modules/orders/README.md).

## Reading order

If you're new to this codebase, read in this order:

1. **architecture.md** — the shape of the system and the rule everything else follows.
2. **cross-module-communication.md** — how modules actually talk to each other in
   practice, since "no direct imports" alone doesn't tell you what to do instead.
3. **database.md**, **testing.md**, and **quality-and-tooling.md** as needed —
   reference material for when you're touching persistence, writing tests, or
   setting up your toolchain.
4. **adding-a-module.md** — when you're ready to add your own.

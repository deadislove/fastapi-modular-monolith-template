# Architecture

## The shape of the system

This is a **Modular Monolith**: one deployable process, split into bounded-context
modules that are as decoupled from each other as if they were separate services —
minus the network hop. The payoff is refactor-ability: if `products` ever needs to
become its own service, the seams are already where they'd need to be.

```
┌─────────────────────────────────────────────────────────┐
│                        app/api/v1/                       │  presentation
│              (routers, request/response mapping)         │
└───────────────────────┬───────────────────────────────────┘
                         │ depends on
┌───────────────────────▼───────────────────────────────────┐
│                      app/facades/                         │  orchestration
│      (the only code allowed to call two modules'          │
│       public_api in one operation)                        │
└───────────────────────┬───────────────────────────────────┘
                         │ depends on
┌───────────────────────▼───────────────────────────────────┐
│                     app/modules/*/                        │  domain
│   users/                          products/                │
│   ├── public_api.py  ◄─────────── only this is importable  │
│   ├── events.py          from outside the module           │
│   ├── schemas.py                                            │
│   ├── errors.py                                             │
│   ├── models.py       (entity types public_api returns —    │
│   │                    read-only outside the module)        │
│   ├── service.py      (private)                             │
│   └── repository.py   (private)                             │
└───────────────────────┬───────────────────────────────────┘
                         │ depends on
┌───────────────────────▼───────────────────────────────────┐
│                      app/shared/                           │  infrastructure
│   config, database (engine/session/UnitOfWork), events bus,│
│   security, generic errors, exception handler, rate limiter │
└───────────────────────────────────────────────────────────┘
```

Dependencies only point downward. `app/shared` never imports from `app/modules`;
`app/modules` never imports from `app/facades` or `app/api`. This is the
`api → facades → modules → shared` **layering rule**, and it's not just a
convention — see [Enforcing boundaries](#enforcing-boundaries).

## Module public/private surface

A module's public surface — what code outside the module is allowed to import — is:

- **`public_api.py`** — the sanctioned entry point. Every method is async, returns
  `Result[T, DomainError]`, and never raises for expected failure modes (see
  [Result pattern](#result-pattern-over-exceptions) below).
- **`schemas.py`** — Pydantic request/response DTOs.
- **`errors.py`** — the module's domain error types (the `Err` side of its `Result`s).
- **`models.py`** — the SQLAlchemy entity type(s) `public_api.py` returns. These
  cross the boundary as **read-only value objects**: callers may read fields off
  them, but only the owning module's `service.py`/`repository.py` may write to the
  database through them.

Everything else — **`service.py`** (business logic) and **`repository.py`**
(persistence/query construction) — is a private implementation detail. Nothing
outside the module, not even another module's `public_api.py`, may import them.

Each module also has its own README with the exact list of what it publishes and
depends on: [`app/modules/users/README.md`](../app/modules/users/README.md),
[`app/modules/products/README.md`](../app/modules/products/README.md).

## Result pattern over exceptions

Every `public_api.py` method returns `Result[T, DomainError]` (from the `result`
library) instead of raising for expected failures — "user not found", "email
already taken", "not the product owner" are all values, not exceptions. Only truly
unexpected failures (a DB connection dropping, a bug) should raise, and those are
caught by the global exception handler (`app/shared/exception_handler.py`), which
turns them into a generic 500 rather than leaking internals.

The presentation layer (`app/api/v1/*.py`) is the only place that converts a
`Result`'s `Err` into an HTTP status code — see each router's `_map_*_error`
function. Domain code never encodes HTTP concerns.

This choice has one sharp edge worth knowing about explicitly: because failure is a
return value, not a raised exception, "no exception was raised" does **not** mean
"this operation succeeded" or "it's safe to commit." See
[database.md's `UnitOfWork` section](database.md#unitofwork) for where this matters
concretely.

## Protocol-based module contracts

`app/facades/user_product_facade.py` depends on `UserPublicApiProtocol` /
`ProductPublicApiProtocol` (`typing.Protocol`, defined in each module's
`public_api.py`) rather than the concrete `UserPublicApi` / `ProductPublicApi`
classes. Two reasons:

1. It makes the contract a facade relies on explicit and reviewable in one place,
   separate from the implementation.
2. It lets a facade test substitute a fake implementation of a module's public API
   without touching the database or monkeypatching a session factory — useful for
   fast, dependency-free unit tests of orchestration logic (this template doesn't
   currently have such a fake-based test, since `tests/test_facade.py` exercises
   the real modules end-to-end over HTTP, but the seam is there when you need it).

## Enforcing boundaries

Everything above is a rule that's easy to violate by accident — an IDE will happily
autocomplete `from app.modules.products.repository import ProductRepository` from
inside `app/api/v1/users.py`, and nothing about Python itself will stop you.

[`import-linter`](https://import-linter.readthedocs.io/) closes that gap. Contracts
live in `.importlinter` at the repo root:

```bash
lint-imports
```

Three contracts run:

1. **Layering** (`api → facades → modules → shared`) — a `type = layers` contract.
   A lower layer can never import from a higher one.
2. **`users` internals are private** — a `type = forbidden` contract blocking any
   import of `app.modules.users.repository` or `app.modules.users.service` from
   outside the module.
3. **`products` internals are private** — the same, for `products`.

One subtlety in contracts 2 and 3: `forbidden` contracts check reachability
*transitively*, so without `ignore_imports` in `.importlinter`, the legitimate
`public_api.py → service.py → repository.py` chain *inside* the module would itself
trip the contract (since `public_api.py` is externally reachable and it imports
`service.py`). The `ignore_imports` entries exclude exactly those two internal
edges, so what's left flagged is a genuine outside-in shortcut.

This also runs as part of the test suite (`tests/test_architecture.py`), so a
boundary violation shows up as a normal failing test, not a separate step someone
has to remember to run — see [testing.md](testing.md).

## Physical separation goes one layer deeper on PostgreSQL

Everything above is code-level (import) separation. On PostgreSQL, each module also
gets its own database schema — see
[database.md's schema-per-module section](database.md#schema-per-module-isolation-postgresql).

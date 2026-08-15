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
│      (the only code allowed to call more than one          │
│       module's public_api in one operation)                │
└───────────────────────┬───────────────────────────────────┘
                         │ depends on
┌───────────────────────▼───────────────────────────────────┐
│                     app/modules/*/                        │  domain
│   users/          products/          orders/                │
│   ├── public_api.py  ◄─────────── only this is importable  │
│   ├── events.py          from outside the module           │
│   ├── schemas.py                                            │
│   ├── errors.py                                             │
│   ├── models.py       (entity types public_api returns —    │
│   │                    read-only outside the module)        │
│   ├── subscribers.py  (private — self-registered reactions  │
│   │                    to this module's own events)          │
│   ├── service.py      (private)                             │
│   ├── repository.py   (private)                             │
│   └── tests/          (this module's own test suite)         │
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
  them, but only the owning module's `service.py`/`repository.py` may write to —
  or *query* — the database through them. A `Product` returned by
  `ProductPublicApi` may be type-hinted and read from `app.facades`; a different
  module's `service.py`/`repository.py` importing `products.models` to build its
  own `select(Product)...` instead of calling `ProductPublicApi` is the
  cross-module coupling `.importlinter`'s fifth contract exists to catch — see
  [Enforcing boundaries](#enforcing-boundaries).

Everything else — **`service.py`** (business logic), **`repository.py`**
(persistence/query construction), and **`subscribers.py`** (this module's own
reactions to its own events, see
[cross-module-communication.md](cross-module-communication.md#where-subscriptions-are-wired-up))
— is a private implementation detail. Nothing outside the module, not even
another module's `public_api.py`, may import them; `subscribers.py` has one
narrow exception, `app/main.py`, the composition root.

Each module also has its own README with the exact list of what it publishes and
depends on: [`app/modules/users/README.md`](../app/modules/users/README.md),
[`app/modules/products/README.md`](../app/modules/products/README.md),
[`app/modules/orders/README.md`](../app/modules/orders/README.md). Adding a new
module yourself? [`docs/adding-a-module.md`](adding-a-module.md) is a checklist,
written from actually adding `orders`.

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

Every `DomainError` has an `as_detail()` method (`{"code": ..., "message": ...}`)
that routers pass as `HTTPException(detail=...)`. A shared `HTTPException` handler
in `app/shared/exception_handler.py` — plus matching handlers for FastAPI's
`RequestValidationError` (422) and slowapi's `RateLimitExceeded` (429) — wraps
every one of these into the same top-level envelope:
`{"error": {"code": ..., "message": ...}}`. Without this, a domain 404 and an
unhandled 500 would come back in two different shapes (they used to: `{"detail":
...}` vs `{"error": ..., "message": ...}`), which pushes every API client into
writing two error-parsing paths instead of one.

This choice has one sharp edge worth knowing about explicitly: because failure is a
return value, not a raised exception, "no exception was raised" does **not** mean
"this operation succeeded" or "it's safe to commit." See
[database.md's `UnitOfWork` section](database.md#unitofwork) for where this matters
concretely.

## Protocol-based module contracts

Every facade — `UserProductFacade`, `OrderFacade` — depends on each module's
`*PublicApiProtocol` (`typing.Protocol`, defined in that module's `public_api.py`)
rather than its concrete `*PublicApi` class. Two reasons:

1. It makes the contract a facade relies on explicit and reviewable in one place,
   separate from the implementation.
2. It lets a facade test substitute a fake implementation of a module's public API
   without touching the database or monkeypatching a session factory — useful for
   fast, dependency-free unit tests of orchestration logic. `tests/test_facade.py`
   exercises the real modules end-to-end over HTTP; `tests/test_facade_fakes.py`
   is the fake-based counterpart, covering `UserProductFacade.get_user_with_products`
   — the one facade method with no `UnitOfWork`, so the only one a fake can drive
   without also needing a real database session. Methods that open a `UnitOfWork`
   (`create_product_for_user`, `OrderFacade.place_order`) still need `test_facade.py`'s
   HTTP-level coverage for that reason.

## Enforcing boundaries

Everything above is a rule that's easy to violate by accident — an IDE will happily
autocomplete `from app.modules.products.repository import ProductRepository` from
inside `app/api/v1/users.py`, and nothing about Python itself will stop you.

[`import-linter`](https://import-linter.readthedocs.io/) closes that gap. Contracts
live in `.importlinter` at the repo root:

```bash
lint-imports
```

Six contracts run:

1. **Layering** (`api → facades → modules → shared`) — a `type = layers` contract.
   A lower layer can never import from a higher one.
2. **`users` internals are private**, 3. **`products` internals are private**,
   4. **`orders` internals are private** — one `type = forbidden` contract per
   module, blocking any import of that module's `repository.py`/`service.py`
   (and `subscribers.py`, if it has one) from outside it. Every other module's
   name is listed in `source_modules` (so `orders` importing `users.repository`
   is caught exactly like `app.api` doing the same).
5. **No cross-module model queries** — `models.py` *is* part of a module's
   public surface (see above), so contracts 2–4 deliberately don't block
   `app.facades`/`app.main` from importing it. What this fifth contract blocks
   instead is a different module's `service.py`/`repository.py` importing it —
   the shape that would let, say, `orders`' repository build a query directly
   against `products`' table instead of going through `ProductPublicApi`. Its
   `source_modules` are every module's `service.py`/`repository.py`, and its
   `forbidden_modules` are every module's `models.py`.
6. **Facades don't import each other** — a `type = independence` contract over
   every file in `app/facades/`. A Facade is meant to be the *only* code
   allowed to call more than one module's `public_api` in one operation (see
   [cross-module-communication.md](cross-module-communication.md#2-facade--unitofwork--when-you-need-an-atomic-result));
   nothing stops one facade calling another instead of calling `public_api`
   directly, which would grow an undocumented second layer of orchestration on
   top of the first. `independence` simply asserts none of the listed modules
   import each other, in either direction.

One subtlety in contracts 2–5: `forbidden` contracts check reachability
*transitively*, so without `ignore_imports` in `.importlinter`, legitimate internal
chains would trip them too — the `public_api.py → service.py → repository.py`
chain *inside* a module (contracts 2–4), and every module's `service.py`/
`repository.py` importing its *own*, required `models.py` (contract 5). The
`ignore_imports` entries exclude exactly those edges, so what's left flagged is
a genuine outside-in shortcut. Adding a new module means adding a new `forbidden`
contract for it, its name to the other modules' `source_modules`, and its
`service.py`/`repository.py` → `models.py` edges to contract 5; adding a new
facade means adding its module path to contract 6's `modules` list — see
[`docs/adding-a-module.md`](adding-a-module.md).

This also runs as part of the test suite (`tests/test_architecture.py`), so a
boundary violation shows up as a normal failing test, not a separate step someone
has to remember to run — see [testing.md](testing.md).

## Physical separation goes one layer deeper on PostgreSQL

Everything above is code-level (import) separation. On PostgreSQL, each module also
gets its own database schema — see
[database.md's schema-per-module section](database.md#schema-per-module-isolation-postgresql).

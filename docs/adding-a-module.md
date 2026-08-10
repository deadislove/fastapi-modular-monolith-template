# Adding a new module

A checklist, not a tutorial — written from actually adding the `orders` module
(the third one in this template, after `users` and `products`). Skim
`app/modules/orders/` alongside this; it's the reference implementation for
every step below.

## 1. The module's own files (`app/modules/<name>/`)

| File | Purpose |
|------|---------|
| `models.py` | SQLAlchemy entity. `__table_args__ = {"schema": module_schema("<name>")}` — see [database.md](database.md#schema-per-module-isolation-postgresql). Decide now whether a field referencing another module's row gets a real `ForeignKey` (rare — see [database.md](database.md#the-one-deliberate-cross-module-foreign-key)) or a plain indexed column (the default). |
| `schemas.py` | Pydantic request/response DTOs. |
| `errors.py` | Domain error dataclasses + a `<Name>Error` union type (`SomeError \| DomainError`). |
| `events.py` | Optional. Only if the module needs to notify other code without returning a result — see [cross-module-communication.md](cross-module-communication.md#3-domain-events--fire-and-forget-side-effects). |
| `repository.py` | Persistence. Extend `BaseRepository[Model]`, add query methods `get_all`/`get_by_id` don't cover. **Private** — never imported outside the module. |
| `service.py` | Business logic, returns `Result[T, <Name>Error]`. **Private**. |
| `public_api.py` | The module's only public surface. See step 2. |
| `README.md` | Owned table, public surface, published events, dependencies on other modules — copy the structure of `app/modules/orders/README.md`. |

## 2. `public_api.py` shape

Copy this from any existing module — the shape is identical every time:

- A `<Name>PublicApiProtocol(Protocol)` listing every method's signature. Facades
  depend on this, not the concrete class — see
  [architecture.md](architecture.md#protocol-based-module-contracts).
- A `<Name>PublicApi` class:
  - `__init__(self, session_factory: async_sessionmaker[AsyncSession] | None = None)`
    storing `self._session_factory`.
  - Every method takes an optional `session: AsyncSession | None = None`, uses
    `resolve_session(session, self._session_factory)`, and only commits (and only
    publishes any event) when it owns the session — see
    [database.md](database.md#unitofwork) and
    [cross-module-communication.md](cross-module-communication.md#who-publishes-the-event-when-a-facade-drives-the-unitofwork).
- A module-level singleton at the bottom: `<name>_public_api = <Name>PublicApi()`.

## 3. Wire the model into table creation

Three places import every module's `models.py` so its table ends up in
`Base.metadata` before anything tries to create tables — add the new import to
all three, or `create_all_tables()`/Alembic/tests silently won't know the table
exists:

- `app/main.py`
- `alembic/env.py`
- `tests/conftest.py`

## 4. `.importlinter` — two kinds of changes

- Add a new `forbidden` contract for the module, blocking its `repository.py`
  and `service.py` from outside import, with `source_modules` listing every
  *other* module plus `app.api` and `app.facades`, and `ignore_imports`
  excluding its own `public_api → service` / `public_api → repository` edges
  (required — `forbidden` contracts check reachability transitively, so without
  this the module's own internal chain trips its own contract). Copy the
  `orders-internals` contract and rename.
- Add the new module's name to every *existing* module's `forbidden` contract
  `source_modules` list — otherwise the new module could import an older
  module's internals and nothing would catch it. Easy to forget; this is the
  step that's silent until you specifically test for it.

Run `lint-imports` after — it'll tell you immediately if a contract is missing
or misconfigured.

## 5. If it needs another module's data: a Facade, not a direct import

If the new module only needs its own data, skip this — routers can call its
`public_api` directly. If placing/creating a `<name>` needs to check or write
another module's data too (like `orders` needs `users` to exist and `products`
to have stock), that coordination goes in a **new facade**
(`app/facades/<name>_facade.py`), never in the module's own `service.py`. See
[cross-module-communication.md](cross-module-communication.md#2-facade--unitofwork--when-you-need-an-atomic-result)
for the full pattern, including the `UnitOfWork` shape for atomic multi-module
writes.

## 6. API layer

- `app/api/v1/<name>.py`: router with a `_map_<name>_error` function translating
  the module's (and any module it depends on's) errors to HTTP status codes.
  Copy an existing router's error-mapping style.
- Register it in `app/api/v1/router.py`:
  `api_v1_router.include_router(<name>_router)`.
- List endpoints: add `limit`/`offset` `Query` params (default 50, max 100) —
  see the root README's API table for the convention.

## 7. Migration

```bash
DATABASE_URL=postgresql+asyncpg://... alembic revision --autogenerate -m "add <name>"
```

Then, by hand, in the generated file's `upgrade()`:
`op.execute('CREATE SCHEMA IF NOT EXISTS <name>')` before `op.create_table(...)` —
autogenerate never emits this. Mirror it in `downgrade()`:
`op.execute('DROP SCHEMA IF EXISTS <name>')` after the table drop. See
[database.md's Migrations section](database.md#migrations) — this exact step is
demonstrated by `alembic/versions/..._add_orders.py`.

Verify the migration against a real PostgreSQL instance before trusting it —
autogenerating/applying against SQLite won't exercise the schema path at all
(`module_schema()` resolves to `None` there). `docker compose up -d db` (or a
throwaway `docker run postgres:16-alpine ...`), then `alembic upgrade head` /
`alembic downgrade -1` against it.

## 8. Tests

At minimum, mirror `tests/test_orders.py`'s shape: one HTTP test per
success/error path the router exposes, plus one test that specifically proves
any `UnitOfWork` atomicity claim the module's facade makes (e.g. "a rejected
write leaves nothing behind" — assert row counts/field values are unchanged
after the failed call, not just that it returned an error). See
[testing.md](testing.md#why-test_place_order_rolls_back_stock_on_insufficient_stock-exists)
for why that class of test matters more than it looks.

`.importlinter`'s contracts run as part of the suite automatically
(`tests/test_architecture.py`) — no test to add there, just don't forget step 4.

## 9. Docs

- This module's own `README.md` (step 1).
- If the new module changes how an existing pattern applies (a new kind of
  cross-module reference, a new event, a facade shape not seen before), update
  the relevant `docs/*.md` rather than only explaining it in a code comment —
  see [`docs/README.md`](README.md) for where each kind of reasoning belongs.

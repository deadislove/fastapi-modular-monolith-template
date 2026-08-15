# Database

## Engine and sessions

`app/shared/database.py` owns a single async engine (`engine`) and session factory
(`AsyncSessionFactory`), built from `settings.DATABASE_URL`. Swap the URL —
`sqlite+aiosqlite:///./app.db` for local dev, `postgresql+asyncpg://...` for
anything else — and every module picks it up without code changes.

`get_db_session()` is the plain FastAPI-dependency session-per-request pattern:

```python
async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionFactory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
```

Every `public_api.py` method uses the same factory internally by default, but
through a shared helper — `resolve_session()` — rather than opening a session
inline, because a caller sometimes needs to supply its *own* session instead. See
[cross-module-communication.md](cross-module-communication.md#2-facade--unitofwork--when-you-need-an-atomic-result)
for the full `UnitOfWork` / `session_factory` story; the short version:

- No `session` passed → the method opens and commits its own, exactly like a plain
  request-scoped session.
- A `session` passed (from a facade's `UnitOfWork`) → the method reuses it and
  leaves commit/rollback to the caller, which is what makes an atomic write across
  two modules possible at all.

## `UnitOfWork`

`app/shared/database.py`'s `UnitOfWork` is a transaction boundary for facades that
must write to more than one module atomically:

```python
async with UnitOfWork() as session:
    ...
    if result.is_ok():
        await session.commit()
    return result
```

It **always rolls back on exit unless the caller explicitly committed** — this is
not the usual "commit unless an exception propagated" pattern, and the reason is
specific to this codebase's [Result-based error handling](architecture.md#result-pattern-over-exceptions):
see [cross-module-communication.md](cross-module-communication.md#why-unitofwork-defaults-to-rollback-not-commit)
for why "no exception raised" can't be trusted as "safe to commit" here.

## Schema-per-module isolation (PostgreSQL)

Import boundaries (see [architecture.md](architecture.md#enforcing-boundaries)) are
code-level separation. On PostgreSQL, each module also gets its own database
**schema** — `users.users`, `products.products`, `orders.orders` — so the
separation is physical, not just a convention `import-linter` enforces at commit
time.

```python
# app/shared/database.py
IS_POSTGRES = settings.DATABASE_URL.startswith("postgresql")

def module_schema(name: str) -> str | None:
    return name if IS_POSTGRES else None
```

```python
# app/modules/products/models.py
class Product(Base):
    __tablename__ = "products"
    __table_args__ = {"schema": module_schema("products")}
```

`module_schema()` resolves to `None` whenever `DATABASE_URL` isn't PostgreSQL — no
schema, SQLite's single default namespace — so **SQLite dev and the entire test
suite are completely unaffected**. This was verified, not assumed: the full test
suite (which runs against an in-memory SQLite database) passes unchanged with this
code active, and separately, a real PostgreSQL container was spun up to confirm the
schema path — see [Verifying against real PostgreSQL](#verifying-against-real-postgresql-what-was-actually-checked)
below.

### Bootstrapping schemas

`Base.metadata.create_all()` creates tables but **never the schemas that contain
them** — that's a gap in what SQLAlchemy's `create_all` does, not this project.
`create_all_tables()` (used for local dev bootstrapping and in tests) works around
it by creating each schema first, derived from the tables actually registered
rather than a hand-maintained list:

```python
async def create_all_tables() -> None:
    async with engine.begin() as conn:
        if IS_POSTGRES:
            schemas = {table.schema for table in Base.metadata.tables.values() if table.schema}
            for schema in schemas:
                await conn.execute(CreateSchema(schema, if_not_exists=True))
        await conn.run_sync(Base.metadata.create_all)
```

### Migrations

`alembic/env.py` passes `include_schemas=True` to `context.configure(...)`, which is
required for autogenerate to even *see* tables outside the default schema. But
autogenerate still only diffs tables — it does **not** emit `CREATE SCHEMA`
statements for a newly-introduced schema. Both checked-in migrations add that line
by hand: `alembic/versions/111c01eef9d1_initial_schema.py` (`users`, `products`) and
`alembic/versions/orders/8b1c06fb2131_add_orders.py`, generated later when the
`orders` module was added:

```python
def upgrade() -> None:
    op.execute('CREATE SCHEMA IF NOT EXISTS orders')
    op.create_table('orders', ..., schema='orders')
```

Any future migration that introduces a *new* module's first table needs the same
one-line addition — autogenerate won't remind you. The `orders` migration is a
real example of exactly this: `alembic revision --autogenerate` correctly detected
only `orders.orders` as new (no FK, since `orders` doesn't take the same shortcut
`products` does — see below), and the `CREATE SCHEMA` line still had to be added
by hand same as the first time.

#### Per-module migration directories

`alembic/versions/` (flat, root) holds `111c01eef9d1_initial_schema.py` — history
that predates the per-module convention, bundling `users` and `products`' original
tables into one revision. It's left exactly where it is, unmoved and unsplit:
rewriting it into two revisions would change revision IDs already recorded in any
real database's `alembic_version` table, breaking `alembic upgrade`/`downgrade` for
every existing deployment for a purely cosmetic gain.

Every module's migrations *since* get their own directory instead —
`alembic/versions/users/`, `alembic/versions/products/`, `alembic/versions/orders/`
— configured via `alembic.ini`'s `version_locations`:

```ini
path_separator = newline
version_locations =
    %(here)s/alembic/versions
    %(here)s/alembic/versions/users
    %(here)s/alembic/versions/products
    %(here)s/alembic/versions/orders
```

`8b1c06fb2131_add_orders.py` was moved into `alembic/versions/orders/` as part of
this split — a pure file relocation, not a revision-ID change (Alembic links
revisions by the `revision`/`down_revision` strings inside each file, not by path,
so moving a file across `version_locations` doesn't affect any already-applied
migration's tracking).

One easy way to lose the split: `path_separator` (not the deprecated
`version_path_separator`) must be `newline`, matching the one-location-per-line
format above. Set it to `os` (or leave the old `version_path_separator = os` from
before this split) and Alembic silently splits `version_locations` on
`os.pathsep` (`:` on Linux/macOS) instead — since none of these paths contain a
`:`, the whole multi-line value collapses into one bogus, nonexistent directory,
and Alembic finds *zero* revisions without raising an error. `alembic heads`
returning nothing is the tell.

Target a specific module's directory with `--version-path` when generating a new
migration — autogenerate still diffs the *whole* schema, `--version-path` only
controls where the resulting file is written:

```bash
DATABASE_URL=postgresql+asyncpg://... alembic revision --autogenerate -m "message" \
    --version-path alembic/versions/products
```

Leaving off `--version-path` also still works (Alembic falls back to the first
entry in `version_locations`, i.e. the flat root directory) — it just won't sort
the new file into a module folder, so pass it explicitly for anything that isn't
a genuinely cross-module change.

Generate migrations against the actual target database, not whatever
`DATABASE_URL` happens to default to locally — the command above already shows
the pattern. Autogenerating against SQLite won't show any schema at all, since
`module_schema()` resolves to `None` for that dialect — that's correct, not a
bug, but it means "generate once, run everywhere" doesn't apply here the way it
might in a single-schema project. (SQLite can't run `alembic upgrade head` here
at all, for the same reason: the checked-in migrations execute a literal
`CREATE SCHEMA`, which is PostgreSQL-only syntax — always verify migrations
against real PostgreSQL, never SQLite; see below.)

### The one deliberate cross-module foreign key

`Product.created_by_user_id` is a real
`ForeignKey("users.users.id" if IS_POSTGRES else "users.id", ondelete="CASCADE")`.
On PostgreSQL this is a genuine **cross-schema** foreign key — `products.products`
pointing into `users.users` — which is the physical-separation mirror of the
cross-module coupling `import-linter` blocks at the code level.

It stays, on purpose, instead of being replaced with an event-driven cascade
(`UserDeleted` → `products` subscriber deletes the user's rows), for one concrete
reason: this template's `EventBus` deliberately swallows handler exceptions (see
[cross-module-communication.md](cross-module-communication.md#why-handler-exceptions-are-swallowed--and-what-that-rules-out)),
which makes it the wrong tool for an integrity guarantee. A DB-level FK with
`ON DELETE CASCADE` can't silently fail to cascade the way a swallowed event
handler exception could. The tradeoff — and it is a tradeoff, not a free lunch — is
that `products` now has one real, physical dependency on `users`'s schema. See
`app/modules/products/README.md` for the module-level writeup of the same
decision.

`orders` deliberately does **not** repeat this: `Order.user_id` and
`Order.product_id` are plain indexed columns, no FK. Business logic is the
reason (deleting a product shouldn't delete the historical orders that reference
it — an order is a receipt, not a cascade target), and referential integrity
instead comes from `OrderFacade` validating both ids inside the same `UnitOfWork`
that creates the order. See `app/modules/orders/README.md`.

### Verifying against real PostgreSQL: what was actually checked

When this was built, the schema-per-module path was verified end-to-end against a
real PostgreSQL container, not just read through:

1. `alembic revision --autogenerate` against Postgres correctly detected
   `users.users` and `products.products` as separate schemas, including the
   cross-schema FK.
2. `alembic upgrade head` created both schemas and both tables; `\dn` / `\dt` /
   `\d products.products` confirmed the layout matched the models exactly.
3. `alembic downgrade base` cleanly dropped both tables and both schemas.
4. A full app-level smoke test — register a user, create a product for them via
   `UserProductFacade`, then delete the user — confirmed the product row was gone
   afterward, proving the cross-schema `ON DELETE CASCADE` actually fires.

The same process repeated when the `orders` module was added: `alembic
revision --autogenerate` against the same Postgres instance correctly picked up
only `orders.orders` as new (confirming the no-FK design produces no cross-schema
constraint), `alembic upgrade head` / `downgrade -1` applied and reverted cleanly,
and an app-level smoke test placed a real order through `OrderFacade` — stock
dropped by the ordered quantity, then a second order for more than the remaining
stock failed with `InsufficientStockError` **and** left both the stock level and
the order count unchanged, proving the atomic rollback holds across two modules'
writes (`products`' stock, `orders`' row), not just one.

One environment-specific gotcha surfaced during that verification, worth knowing if
you hit the same thing: if you also run PostgreSQL natively on your machine (e.g.
via Homebrew), it likely already owns host port 5432, and `docker compose`'s
published port silently loses to it for `localhost` connections — you'll see
`role "app" does not exist` even though the container itself is healthy, because
you're actually talking to the native instance, not the container. Either stop the
native instance or remap the port (`"5433:5432"` in `docker-compose.yml`, with a
matching `DATABASE_URL`).

The per-module `version_locations` split (above) was verified the same way, against
a fresh real PostgreSQL container: `alembic heads`/`alembic history` correctly
resolved the full revision graph across all four configured directories;
`alembic upgrade head` created all three schemas and tables identically to the
pre-split layout, and `alembic downgrade base` cleanly reverted all of them;
`alembic_version` after `upgrade head` still read `8b1c06fb2131` — the same
revision ID as before the split, confirming the file move doesn't perturb a
database that already has migrations applied. `alembic revision --autogenerate
--version-path alembic/versions/products` (a temporary, reverted-after-verifying
`sku` column added to `Product`) correctly wrote the new file into
`alembic/versions/products/`, detected only that one column as new, and both
`alembic upgrade head`/`downgrade -1` applied and reverted it cleanly — proving
the per-module story actually works going forward, not just that the directories
exist.

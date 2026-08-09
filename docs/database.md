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
**schema** — `users.users`, `products.products` — so the separation is physical,
not just a convention `import-linter` enforces at commit time.

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
statements for a newly-introduced schema. The checked-in
`alembic/versions/..._initial_schema.py` adds those by hand:

```python
def upgrade() -> None:
    op.execute('CREATE SCHEMA IF NOT EXISTS users')
    op.execute('CREATE SCHEMA IF NOT EXISTS products')
    op.create_table('users', ..., schema='users')
    op.create_table('products', ..., schema='products')
```

Any future migration that introduces a *new* module's first table needs the same
one-line addition — autogenerate won't remind you.

Generate migrations against the actual target database, not whatever
`DATABASE_URL` happens to default to locally:

```bash
DATABASE_URL=postgresql+asyncpg://... alembic revision --autogenerate -m "message"
alembic upgrade head
```

Autogenerating against SQLite won't show any schema at all, since `module_schema()`
resolves to `None` for that dialect — that's correct, not a bug, but it means
"generate once, run everywhere" doesn't apply here the way it might in a
single-schema project.

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

One environment-specific gotcha surfaced during that verification, worth knowing if
you hit the same thing: if you also run PostgreSQL natively on your machine (e.g.
via Homebrew), it likely already owns host port 5432, and `docker compose`'s
published port silently loses to it for `localhost` connections — you'll see
`role "app" does not exist` even though the container itself is healthy, because
you're actually talking to the native instance, not the container. Either stop the
native instance or remap the port (`"5433:5432"` in `docker-compose.yml`, with a
matching `DATABASE_URL`).

# fastapi-modular-monolith-template

High-cohesion, low-coupling **Modular Monolith** built with:

- **FastAPI** + Swagger UI (OpenAPI)
- **SQLAlchemy v2 Async** (SQLite for dev, PostgreSQL for prod — schema-per-module on Postgres)
- **JWT Auth** (OAuth2 Bearer via PyJWT + passlib/bcrypt)
- **Result Pattern** (`result` library) for cross-module communication
- **Rate Limiting** (slowapi)
- **API Versioning** (`/api/v1/`)
- **Global Exception Handler**
- **Alembic** migrations
- **Multi-stage Dockerfile** + `docker-compose.yml`

---

## Project Structure

```
app/
├── main.py                        # FastAPI app entry point
├── api/v1/
│   ├── router.py                  # Aggregates all v1 routers
│   ├── users.py                   # /api/v1/users endpoints
│   └── products.py                # /api/v1/products endpoints
├── modules/
│   ├── users/                     # User bounded context
│   │   ├── models.py              # SQLAlchemy User entity
│   │   ├── schemas.py             # Pydantic request/response schemas
│   │   ├── errors.py              # Domain error types
│   │   ├── events.py              # Domain events this module publishes
│   │   ├── repository.py          # Persistence layer (private)
│   │   ├── service.py             # Business logic (private)
│   │   └── public_api.py          # ← Module boundary (only import this externally)
│   └── products/                  # Product bounded context
│       ├── models.py
│       ├── schemas.py
│       ├── errors.py
│       ├── repository.py          # (private)
│       ├── service.py             # (private)
│       └── public_api.py          # ← Module boundary
├── facades/
│   └── user_product_facade.py     # Cross-module orchestration (needs a result back)
└── shared/
    ├── config.py                  # Pydantic settings
    ├── database.py                # Async engine, session factory, UnitOfWork
    ├── events.py                  # In-process event bus (fire-and-forget side effects)
    ├── base_repository.py         # Generic CRUD base
    ├── security.py                # JWT + password hashing
    ├── errors.py                  # Shared base error types
    ├── exception_handler.py       # Global 500 handler
    └── rate_limiter.py            # slowapi setup
alembic/                           # DB migrations
tests/                             # pytest-asyncio test suite
```

---

## Quick Start

```bash
# 1. Create and activate virtual environment
python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate     # macOS/Linux

# 2. Install dependencies
pip install -r requirements.txt

# 3. Copy and configure environment
cp .env.example .env

# 4. Run the application (SQLite auto-created on startup)
uvicorn app.main:app --reload

# 5. Open Swagger UI
# http://localhost:8000/docs
```

---

## API Endpoints

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | `/api/v1/users/register` | — | Register a new user |
| POST | `/api/v1/users/login` | — | Login, receive JWT |
| GET | `/api/v1/users/me` | ✓ | Get current user |
| GET | `/api/v1/users/` | ✓ | List all users (`limit`, `offset`) |
| GET | `/api/v1/users/{id}` | ✓ | Get user by ID |
| PATCH | `/api/v1/users/{id}` | ✓ | Update user |
| DELETE | `/api/v1/users/{id}` | ✓ | Delete user |
| POST | `/api/v1/products/` | ✓ | Create product |
| GET | `/api/v1/products/` | — | List all products (`limit`, `offset`) |
| GET | `/api/v1/products/my` | ✓ | List my products (`limit`, `offset`) |
| GET | `/api/v1/products/{id}` | — | Get product by ID |
| PATCH | `/api/v1/products/{id}` | ✓ | Update product (owner) |
| DELETE | `/api/v1/products/{id}` | ✓ | Delete product (owner) |
| GET | `/health` | — | Health check |

List endpoints default to `limit=50` (max `100`) and are ordered by `id` for stable
paging — see `BaseRepository.get_all`.

---

## Testing

```bash
pytest
```

| File | Covers |
|------|--------|
| `test_users.py` / `test_products.py` | Per-module HTTP behavior |
| `test_facade.py` | Cross-module composition, and that `UnitOfWork` actually rolls back |
| `test_events.py` | `EventBus` semantics + the real `main.py` subscriber wiring |
| `test_public_api_di.py` | Constructing an isolated `public_api` instance via `session_factory` |
| `test_architecture.py` | Runs `.importlinter`'s contracts as part of the suite |

`tests/conftest.py` resets slowapi's rate limiter before every test (`_reset_rate_limiter`,
autouse) — its counters are process-wide, so without this, tests pass or fail
depending on how many HTTP requests earlier tests happened to make.

---

## Linting

```bash
ruff check . --fix
```

## Architecture Boundary Check

```bash
lint-imports
```

Fails the build if a module's internals (`repository.py`/`service.py`) are imported
from outside the module, or if the `api → facades → modules → shared` layering is
violated. See [Enforcing boundaries](#enforcing-boundaries).

---

## Database Migrations

```bash
# Generate a migration (point DATABASE_URL at the target DB — schemas only
# materialize on PostgreSQL, so autogenerating against SQLite won't show them)
alembic revision --autogenerate -m "message"

# Apply migrations
alembic upgrade head
```

The checked-in `alembic/versions/..._initial_schema.py` creates the `users` and
`products` PostgreSQL schemas by hand (`op.execute("CREATE SCHEMA ...")`) — autogenerate
detects tables inside a schema but never emits the `CREATE SCHEMA` itself, so any
future migration that introduces a new module's first table needs the same one-line
addition. See [Schema-per-module isolation](#schema-per-module-isolation-postgresql).

---

## Docker

```bash
docker compose up -d --build
# App: http://localhost:8000/docs
# PostgreSQL: localhost:5432
```

If you also run PostgreSQL natively on this machine (e.g. via Homebrew), it likely
already owns host port 5432, and `docker compose`'s published port silently loses to
it for `localhost` connections — you'll see `role "app" does not exist` even though
the container is healthy. Either stop the native instance or remap the port
(`"5433:5432"` in `docker-compose.yml`, and update `DATABASE_URL` to match).

---

## Architecture Rules

- **No direct cross-module DB joins** — cross-module data access goes through `public_api.py` interfaces
- **Result pattern** — all module public APIs return `Result[T, DomainError]`, never raise
- **Facades** — `UserProductFacade` is the only place that orchestrates multiple modules
- **Absolute imports** — always `from app.modules.users.public_api import ...`

### Module public/private surface

Each module's public surface is `public_api.py` + `schemas.py` + `errors.py` (and the
`models.py` entity types that `public_api.py` returns — treat them as read-only value
objects outside the module). `repository.py` and `service.py` are implementation
details and must never be imported from outside the module.

This is enforced, not just documented — see [Enforcing boundaries](#enforcing-boundaries).
Each module also has its own README with its exact contract and dependencies:
[`modules/users/README.md`](app/modules/users/README.md),
[`modules/products/README.md`](app/modules/products/README.md).

### Cross-module transactions (`UnitOfWork`)

Every `public_api.py` method accepts an optional `session` parameter. Called without
it (the normal case), the method opens and commits its own session, unchanged from
before. A facade that needs an atomic write across two modules instead opens a
`UnitOfWork`, passes the shared session into each call, and commits explicitly once
it has confirmed a successful `Result`:

```python
from app.shared.database import UnitOfWork

async with UnitOfWork() as session:
    user_result = await user_public_api.get_user_by_id(user_id, session=session)
    if user_result.is_err():
        return Err(user_result.err())

    result = await product_public_api.create_product(data, user_id, session=session)
    if result.is_ok():
        await session.commit()
    return result
```

`UnitOfWork` never commits on your behalf — it always rolls back on exit unless you
called `session.commit()` first. This matters because this codebase reports failure
via `Result.Err` rather than exceptions, so "no exception was raised" does not imply
"safe to commit"; defaulting to rollback means a forgotten commit fails safe instead
of persisting a partial cross-module write. See `UserProductFacade.create_product_for_user`
for a full example.

### Protocol-based module contracts

Facades depend on `UserPublicApiProtocol` / `ProductPublicApiProtocol`
(`typing.Protocol`) rather than the concrete `UserPublicApi` / `ProductPublicApi`
classes. This makes the public contract explicit and lets facade tests substitute a
fake implementation without patching the database session factory.

### Domain events — the alternative to a Facade

A **Facade** is for when the caller needs a result back (see `UnitOfWork` above). A
**domain event** is for when a module just needs to say "this happened" without
knowing or caring whether anyone reacts — logging, sending a welcome email, warming
a cache. `app/shared/events.py` provides an in-process `EventBus`; each module
defines the events it publishes next to itself (e.g. `app/modules/users/events.py`):

```python
# app/modules/users/events.py
@dataclass(frozen=True)
class UserRegistered(DomainEvent):
    user_id: int
    email: str
```

`UserPublicApi.register_user` publishes `UserRegistered` once its own transaction
commits. Subscribers are wired up at the composition root, `app/main.py`, which is
the one place allowed to know about both a module's event types and the
cross-cutting handlers that react to them — modules never import each other's
`events.py` directly:

```python
# app/main.py
event_bus.subscribe(UserRegistered, _log_user_registered)
```

Add a new side effect (e.g. "send a welcome email") by writing a handler and
subscribing it in `main.py` — the `users` module never needs to change.

### Session factory injection

Every `public_api.py` class also accepts an optional `session_factory` in its
constructor. The module singletons (`user_public_api`, `product_public_api`) leave
it unset, which means they resolve `app.shared.database.AsyncSessionFactory` lazily
on each call — this is what lets `tests/conftest.py` point the whole app at an
in-memory test database by patching that one attribute. For a unit test that wants
a fully isolated instance instead of touching that process-wide global, construct
your own: `UserPublicApi(session_factory=TestSessionFactory)` — see
`tests/test_public_api_di.py`.

### Schema-per-module isolation (PostgreSQL)

Module boundaries so far are all code-level (imports). On PostgreSQL, each module
also gets its own DB schema — `users.users`, `products.products` — via
`module_schema(name)` in `app/shared/database.py`:

```python
class Product(Base):
    __tablename__ = "products"
    __table_args__ = {"schema": module_schema("products")}
```

`module_schema` resolves to `None` (no schema — SQLite's `public`-only default)
whenever `DATABASE_URL` isn't PostgreSQL, so SQLite dev and the whole test suite are
completely unaffected — this only activates for `docker compose` / production.
`create_all_tables()` (used for quick local bootstrapping) creates each schema
before its tables; Alembic migrations do the same for anything applied with
`alembic upgrade`.

**The one deliberate exception**: `Product.created_by_user_id` is a real
`ForeignKey` into `users.users`, so on PostgreSQL it's a genuine cross-schema
foreign key — the physical-separation equivalent of the cross-module coupling
`.importlinter` blocks at the code level. It stays because it buys referential
integrity and an automatic `ON DELETE CASCADE` that would otherwise need
reimplementing by hand, and this template's `EventBus` (see
[Domain events](#domain-events--the-alternative-to-a-facade)) deliberately swallows
handler exceptions, which makes it the wrong tool for an integrity guarantee like
this one. Details and the tradeoff are in `app/modules/products/README.md`.

### Enforcing boundaries

Module boundaries are checked by [`import-linter`](https://import-linter.readthedocs.io/),
configured in `.importlinter`:

- `repository.py` / `service.py` may not be imported from outside their own module
- `app.api` → `app.facades` → `app.modules` → `app.shared` is a one-way layering —
  a lower layer (e.g. `app.shared`) can never import from a higher one

```bash
lint-imports
```

Run this alongside `ruff check` — a broken contract fails the same way a lint error does.

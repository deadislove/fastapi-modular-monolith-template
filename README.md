# fastapi-modular-monolith-template

High-cohesion, low-coupling **Modular Monolith** built with:

- **FastAPI** + Swagger UI (OpenAPI)
- **SQLAlchemy v2 Async** (SQLite for dev, PostgreSQL for prod — schema-per-module on Postgres)
- **JWT Auth** (OAuth2 Bearer via PyJWT + passlib/bcrypt)
- **Result Pattern** (`result` library) for cross-module communication
- **Rate Limiting** (slowapi)
- **API Versioning** (`/api/v1/`)
- **Unified error responses** — `{"error": {"code", "message"}}` for every 4xx/5xx, domain or otherwise
- **Liveness/readiness health checks** — `/health` vs `/health/ready` (DB ping)
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
│   ├── products.py                # /api/v1/products endpoints
│   └── orders.py                  # /api/v1/orders endpoints
├── modules/
│   ├── users/                     # User bounded context
│   │   ├── models.py              # SQLAlchemy User entity
│   │   ├── schemas.py             # Pydantic request/response schemas
│   │   ├── errors.py              # Domain error types
│   │   ├── events.py              # Domain events this module publishes
│   │   ├── subscribers.py         # Self-registered reactions to its own events (private)
│   │   ├── repository.py          # Persistence layer (private)
│   │   ├── service.py             # Business logic (private)
│   │   ├── public_api.py          # ← Module boundary (only import this externally)
│   │   └── tests/                 # This module's own test suite
│   ├── products/                  # Product bounded context
│   │   ├── models.py
│   │   ├── schemas.py
│   │   ├── errors.py
│   │   ├── repository.py          # (private)
│   │   ├── service.py             # (private)
│   │   ├── public_api.py          # ← Module boundary
│   │   └── tests/
│   └── orders/                    # Order bounded context — depends on both users and products
│       ├── models.py
│       ├── schemas.py
│       ├── errors.py
│       ├── events.py
│       ├── subscribers.py         # (private)
│       ├── repository.py          # (private)
│       ├── service.py             # (private)
│       ├── public_api.py          # ← Module boundary
│       └── tests/
├── facades/
│   ├── user_product_facade.py     # Coordinates users + products
│   └── order_facade.py            # Coordinates users + products + orders (3-module UnitOfWork)
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
tests/                             # Cross-module integration + architecture contract tests
conftest.py                        # Shared pytest fixtures (repo-wide, incl. app/modules/*/tests/)
```

📖 **For the architecture reasoning behind this structure — not just the file
list — see [`docs/`](docs/README.md).**

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
| POST | `/api/v1/orders/` | ✓ | Place an order (reserves stock atomically) |
| GET | `/api/v1/orders/my` | ✓ | List my orders (`limit`, `offset`) |
| GET | `/api/v1/orders/{id}` | ✓ | Get order by ID (owner only) |
| GET | `/health` | — | Liveness — always 200 if the process is up |
| GET | `/health/ready` | — | Readiness — 503 if the database is unreachable |

List endpoints default to `limit=50` (max `100`) and are ordered by `id` for stable
paging — see `BaseRepository.get_all`.

---

## Testing

```bash
pytest
```

Five test files cover per-module HTTP behavior, cross-module facade composition,
the event bus, isolated-instance DI, and architecture boundaries (`.importlinter`
run as a test). Full breakdown, plus the two test-suite gotchas already hit and
fixed (a process-wide rate limiter, and shared test data within a file):
**[`docs/testing.md`](docs/testing.md)**.

---

## Linting & Architecture Boundary Check

```bash
ruff check . --fix
lint-imports
```

`lint-imports` fails the build if a module's internals (`repository.py`/`service.py`)
are imported from outside the module, or if the `api → facades → modules → shared`
layering is violated. How the contracts work: **[`docs/architecture.md`](docs/architecture.md#enforcing-boundaries)**.

---

## Database Migrations

```bash
# Generate a migration (point DATABASE_URL at the target DB — schemas only
# materialize on PostgreSQL, so autogenerating against SQLite won't show them)
alembic revision --autogenerate -m "message"

# Apply migrations
alembic upgrade head
```

The checked-in initial migration creates the `users` and `products` PostgreSQL
schemas by hand — autogenerate detects tables inside a schema but never emits the
`CREATE SCHEMA` itself. Full migration workflow and the schema-per-module design
it depends on: **[`docs/database.md`](docs/database.md)**.

---

## Docker

```bash
docker compose up -d --build
# App: http://localhost:8000/docs
# PostgreSQL: localhost:5432
docker compose ps   # both services should report (healthy)
```

Both services define a `healthcheck`: `db` via `pg_isready`, `app` via
[`/health/ready`](#api-endpoints) — no `curl`/`wget` in the slim image, so the
Dockerfile's `HEALTHCHECK` and this healthcheck both call it with Python's stdlib
`urllib` instead. `app`'s `depends_on: db: condition: service_healthy` means it
won't even start until Postgres is actually ready, not just running.

Running PostgreSQL natively on the same machine (e.g. via Homebrew)? See the port
5432 conflict note in **[`docs/database.md`](docs/database.md#verifying-against-real-postgresql-what-was-actually-checked)**
— it looks like a broken container but isn't one.

---

## Architecture

- **No direct cross-module DB joins** — cross-module data access goes through `public_api.py` interfaces
- **Result pattern** — all module public APIs return `Result[T, DomainError]`, never raise
- **Facades** — the only code allowed to orchestrate more than one module in a single operation (`UserProductFacade`, `OrderFacade`)
- **Absolute imports** — always `from app.modules.users.public_api import ...`

These four rules are the summary; the reasoning, the enforcement mechanism, and the
patterns for satisfying them in practice are documented in **[`docs/`](docs/README.md)**:

| | |
|---|---|
| [`docs/architecture.md`](docs/architecture.md) | Module boundaries, layering, public/private surface, `import-linter` enforcement |
| [`docs/cross-module-communication.md`](docs/cross-module-communication.md) | Direct calls vs. Facade+`UnitOfWork` vs. domain events — and when to use which |
| [`docs/database.md`](docs/database.md) | Session lifecycle, `UnitOfWork`, schema-per-module, migrations |
| [`docs/adding-a-module.md`](docs/adding-a-module.md) | Checklist for adding a new module, written from actually adding `orders` |

Each module also documents its own contract next to its code:
[`app/modules/users/README.md`](app/modules/users/README.md),
[`app/modules/products/README.md`](app/modules/products/README.md),
[`app/modules/orders/README.md`](app/modules/orders/README.md).

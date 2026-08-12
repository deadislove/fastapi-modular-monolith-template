import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text

import app.modules.orders.models  # noqa: F401
import app.modules.products.models  # noqa: F401

# Import models so SQLAlchemy metadata is populated before create_all_tables runs
import app.modules.users.models  # noqa: F401
from app.api.v1.router import api_v1_router

# Composition root: aggregates each module's self-registered event subscribers.
# A subscription to *another* module's event (not the publisher's own) still
# belongs here, since only this file may import another module's events.py.
from app.modules.orders.subscribers import register_subscribers as register_orders_subscribers
from app.modules.users.subscribers import register_subscribers as register_users_subscribers
from app.shared.config import settings
from app.shared.database import create_all_tables, resolve_session
from app.shared.events import event_bus
from app.shared.exception_handler import register_exception_handlers
from app.shared.rate_limiter import register_rate_limiter

# Without this, app.* loggers propagate to a handler-less root and produce no
# output at all under `uvicorn app.main:app` — no-op if one already exists.
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

logger = logging.getLogger(__name__)


def register_event_subscribers() -> None:
    """Each module registers its own reactions to its own events. Adding a
    new module's subscribers means one import + one call here — not a new
    handler function and event-type import in this file."""
    register_users_subscribers(event_bus)
    register_orders_subscribers(event_bus)


register_event_subscribers()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Bootstrap DB tables on startup — safe for SQLite dev; use Alembic for production."""
    await create_all_tables()
    yield


app = FastAPI(
    title=settings.APP_NAME,
    description=(
        "High-cohesion, low-coupling Modular Monolith with FastAPI, SQLAlchemy v2 Async, "
        "JWT Auth, Rate Limiting, API Versioning, Result Pattern, and Swagger UI."
    ),
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    lifespan=lifespan,
)

# --- Middleware ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Cross-cutting concerns ---
register_rate_limiter(app)
register_exception_handlers(app)

# --- Versioned API routes ---
app.include_router(api_v1_router)


@app.get("/health", tags=["Health"], summary="Liveness check")
async def health_check() -> dict:
    """Process is up. Always 200 — does not touch the database, so it can't
    flap (and trigger a container restart) just because the DB is briefly
    unreachable. See /health/ready for that."""
    return {"status": "ok", "app": settings.APP_NAME}


@app.get("/health/ready", tags=["Health"], summary="Readiness check")
async def readiness_check() -> JSONResponse:
    """Process is up *and* can reach the database — what a load balancer
    should gate traffic on."""
    try:
        async with resolve_session(None) as (session, _owns):
            await session.execute(text("SELECT 1"))
    except Exception:
        logger.exception("Readiness check failed")
        return JSONResponse(status_code=503, content={"status": "unavailable", "database": "unreachable"})
    return JSONResponse(status_code=200, content={"status": "ok", "database": "ok"})

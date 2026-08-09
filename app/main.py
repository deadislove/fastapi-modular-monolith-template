import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

import app.modules.products.models  # noqa: F401

# Import models so SQLAlchemy metadata is populated before create_all_tables runs
import app.modules.users.models  # noqa: F401
from app.api.v1.router import api_v1_router

# main.py is the composition root: the one place allowed to know about both a
# module's published event types and its cross-cutting subscribers.
from app.modules.users.events import UserRegistered
from app.shared.config import settings
from app.shared.database import create_all_tables
from app.shared.events import event_bus
from app.shared.exception_handler import register_exception_handlers
from app.shared.rate_limiter import register_rate_limiter

logger = logging.getLogger(__name__)


async def _log_user_registered(event: UserRegistered) -> None:
    logger.info("User registered: id=%s email=%s", event.user_id, event.email)


def register_event_subscribers() -> None:
    """Wire cross-cutting subscribers to domain events published by modules — add
    new ones here (e.g. send a welcome email) without touching the publishing
    module. See app/shared/events.py for when to reach for an event vs a Facade."""
    event_bus.subscribe(UserRegistered, _log_user_registered)


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


@app.get("/health", tags=["Health"], summary="Health check")
async def health_check() -> dict:
    return {"status": "ok", "app": settings.APP_NAME}

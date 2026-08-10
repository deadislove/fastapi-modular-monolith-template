import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

import app.modules.orders.models  # noqa: F401
import app.modules.products.models  # noqa: F401

# Import models so SQLAlchemy metadata is populated before create_all_tables runs
import app.modules.users.models  # noqa: F401
from app.api.v1.router import api_v1_router

# Composition root: knows both a module's event types and its subscribers.
from app.modules.orders.events import OrderPlaced
from app.modules.users.events import UserRegistered
from app.shared.config import settings
from app.shared.database import create_all_tables
from app.shared.events import event_bus
from app.shared.exception_handler import register_exception_handlers
from app.shared.rate_limiter import register_rate_limiter

logger = logging.getLogger(__name__)


async def _log_user_registered(event: UserRegistered) -> None:
    logger.info("User registered: id=%s email=%s", event.user_id, event.email)


async def _log_order_placed(event: OrderPlaced) -> None:
    logger.info(
        "Order placed: id=%s user_id=%s product_id=%s qty=%s",
        event.order_id, event.user_id, event.product_id, event.quantity,
    )


def register_event_subscribers() -> None:
    """Add new subscribers here without touching the publishing module."""
    event_bus.subscribe(UserRegistered, _log_user_registered)
    event_bus.subscribe(OrderPlaced, _log_order_placed)


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

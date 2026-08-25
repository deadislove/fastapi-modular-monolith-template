import importlib
import logging
import pkgutil
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text

import app.modules as _app_modules  # aliased: this file reassigns `app` to the FastAPI instance below
from app.api.v1.router import api_v1_router, discover_routers
from app.shared.config import settings
from app.shared.database import create_all_tables, resolve_session
from app.shared.events import event_bus
from app.shared.exception_handler import register_exception_handlers
from app.shared.rate_limiter import register_rate_limiter
from app.shared.registry import module_registry
from app.shared.request_context import install_request_id_log_filter, register_request_context

# Without this, app.* loggers propagate to a handler-less root and produce no
# output at all under `uvicorn app.main:app` — no-op if one already exists.
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s [%(request_id)s]: %(message)s",
)
# Must run right after basicConfig, before anything below might log — see
# install_request_id_log_filter()'s own docstring for why.
install_request_id_log_filter()

logger = logging.getLogger(__name__)


def discover_modules() -> None:
    """Composition root only: imports every app/modules/<name>/ subpackage's
    models.py (populates SQLAlchemy metadata), public_api.py (self-registers
    its contract into module_registry), and subscribers.py if present
    (self-registers its event subscribers). Not in app/shared/ — shared must
    never import from modules, and this function does exactly that on
    purpose, so it belongs at the composition root instead."""
    for _, name, is_pkg in pkgutil.iter_modules(_app_modules.__path__):
        if not is_pkg:
            continue
        importlib.import_module(f"app.modules.{name}.models")
        importlib.import_module(f"app.modules.{name}.public_api")
        subscribers_module = f"app.modules.{name}.subscribers"
        try:
            importlib.import_module(subscribers_module)
        except ModuleNotFoundError as exc:
            if exc.name != subscribers_module:
                raise


# Order matters: modules must be discovered (populating module_registry)
# before discover_routers() imports the router files that resolve facades,
# which in turn resolve module contracts from the registry.
discover_modules()
module_registry.wire_event_subscribers(event_bus)
discover_routers()


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
register_request_context(app)

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

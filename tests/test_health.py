import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

import app.shared.database as db_module

pytestmark = pytest.mark.asyncio


async def test_health_liveness(client: AsyncClient) -> None:
    response = await client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


async def test_health_readiness_when_db_reachable(client: AsyncClient) -> None:
    response = await client.get("/health/ready")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": "ok"}


async def test_health_readiness_when_db_unreachable(client: AsyncClient) -> None:
    """Regression test: readiness must resolve AsyncSessionFactory late (via
    resolve_session), not via a top-level import — an early-bound import would
    silently keep using the real dev/test factory instead of picking this up."""
    original_factory = db_module.AsyncSessionFactory
    broken_engine = create_async_engine(
        "sqlite+aiosqlite:////nonexistent-dir-xyz/app.db", future=True
    )
    db_module.AsyncSessionFactory = async_sessionmaker(
        bind=broken_engine, class_=AsyncSession, expire_on_commit=False
    )
    try:
        response = await client.get("/health/ready")
    finally:
        db_module.AsyncSessionFactory = original_factory

    assert response.status_code == 503
    assert response.json() == {"status": "unavailable", "database": "unreachable"}

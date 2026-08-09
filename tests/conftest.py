import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

import app.modules.products.models  # noqa: F401

# Import models before Base.metadata is used so all tables are registered
import app.modules.users.models  # noqa: F401
import app.shared.database as db_module
from app.main import app
from app.shared.database import Base

# In-memory SQLite for tests — fast, isolated, no cleanup needed
TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"

test_engine = create_async_engine(TEST_DATABASE_URL, echo=False, future=True)
TestSessionFactory = async_sessionmaker(
    bind=test_engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
    autocommit=False,
)

# Patch the module-level factory immediately at import time so all singletons
# (user_public_api, product_public_api) pick up the test engine from the start.
db_module.AsyncSessionFactory = TestSessionFactory  # type: ignore[assignment]


@pytest_asyncio.fixture(scope="session", autouse=True)
async def setup_test_db():
    """Create all tables once per test session."""
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture(autouse=True)
def _reset_rate_limiter():
    """
    slowapi's Limiter keeps its counters in a process-wide in-memory store, shared
    by every test in the session regardless of which file or DB row they touch.
    Without this, tests pass or fail depending on how many requests earlier tests
    happened to make — exactly the kind of order-dependent flakiness a growing
    suite runs into. Reset before each test so every test starts its own budget.
    """
    from app.shared.rate_limiter import limiter

    limiter.reset()


@pytest_asyncio.fixture
async def client():
    """HTTP test client backed by the in-memory test database."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from types import TracebackType

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.schema import CreateSchema

from app.shared.config import settings

# Single engine instance — swap DATABASE_URL in .env to target any supported backend
engine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.DEBUG,
    future=True,
)

# SQLite has no real schema/namespace concept (ATTACHing extra files to fake one
# would complicate local dev for little benefit), so schema-per-module is a
# PostgreSQL-only concern: each module's models opt in via `module_schema(name)`,
# which resolves to None — no schema — everywhere else. Decided once, from the
# configured URL, rather than by inspecting the live engine, so model classes (which
# set their schema at class-definition time, before any connection exists) can use it.
IS_POSTGRES = settings.DATABASE_URL.startswith("postgresql")


def module_schema(name: str) -> str | None:
    """Schema name for a module's tables — only meaningful on PostgreSQL. Use this
    in every module's `models.py` (see app/modules/users/models.py) rather than
    hardcoding a schema string, so dropping to SQLite for a quick local run doesn't
    require touching every model."""
    return name if IS_POSTGRES else None

AsyncSessionFactory = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
    autocommit=False,
)


class Base(DeclarativeBase):
    """Shared declarative base for all module models."""
    pass


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency — yields a scoped async session per request."""
    async with AsyncSessionFactory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def create_all_tables() -> None:
    """
    Bootstrap all tables — used in tests and local dev runs (SQLite or Postgres).
    `Base.metadata.create_all` creates tables but never the schemas that contain
    them, so on Postgres we create each module's schema first, derived from the
    tables actually registered rather than a hand-maintained list. Production
    should still prefer Alembic migrations (which do the same schema creation —
    see alembic/versions); this just keeps `docker compose up` working standalone.
    """
    async with engine.begin() as conn:
        if IS_POSTGRES:
            schemas = {table.schema for table in Base.metadata.tables.values() if table.schema}
            for schema in schemas:
                await conn.execute(CreateSchema(schema, if_not_exists=True))
        await conn.run_sync(Base.metadata.create_all)


@asynccontextmanager
async def resolve_session(
    external_session: AsyncSession | None,
    session_factory: async_sessionmaker[AsyncSession] | None = None,
) -> AsyncGenerator[tuple[AsyncSession, bool], None]:
    """
    Session resolution shared by every module's public_api.

    Yields (session, owns_transaction). When a caller (typically a facade running
    inside a UnitOfWork) passes its own session, we reuse it and let that caller
    control commit/rollback — this is what makes atomic cross-module writes possible.
    Otherwise we open and own a new session from `session_factory`, falling back to
    the process-wide `AsyncSessionFactory` (read late, by name, so tests can still
    swap it by patching this module's attribute) when none is given explicitly.
    """
    if external_session is not None:
        yield external_session, False
        return
    factory = session_factory or AsyncSessionFactory
    async with factory() as session:
        yield session, True


class UnitOfWork:
    """
    Transaction boundary for facades that must write to more than one module
    atomically. Pass the yielded session into each public_api call so every
    module writes through the same connection.

    The caller must explicitly `await session.commit()` once it has confirmed a
    successful Result — UnitOfWork never commits on your behalf. Because this
    codebase reports failure via Result.Err rather than raising, "no exception"
    does not mean "safe to commit"; only rolling back by default (on success,
    an Err Result, or a raised exception alike) keeps a forgotten commit failing
    safe instead of persisting a partial cross-module write.

        async with UnitOfWork() as session:
            user = await user_public_api.get_user_by_id(user_id, session=session)
            if user.is_err():
                return Err(user.err())
            result = await product_public_api.create_product(data, user_id, session=session)
            if result.is_ok():
                await session.commit()
            return result

    Pass `session_factory` to target a different database (e.g. a test engine)
    without touching the process-wide `AsyncSessionFactory` global.
    """

    def __init__(self, session_factory: async_sessionmaker[AsyncSession] | None = None) -> None:
        self._session_factory = session_factory

    async def __aenter__(self) -> AsyncSession:
        factory = self._session_factory or AsyncSessionFactory
        self._session = factory()
        await self._session.__aenter__()
        return self._session

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        try:
            await self._session.rollback()
        finally:
            await self._session.__aexit__(exc_type, exc, tb)

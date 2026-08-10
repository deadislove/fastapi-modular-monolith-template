from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from types import TracebackType

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.schema import CreateSchema

from app.shared.config import settings

engine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.DEBUG,
    future=True,
)

# Decided once from the URL, not the live engine — models set their schema at
# class-definition time, before any connection exists.
IS_POSTGRES = settings.DATABASE_URL.startswith("postgresql")


def module_schema(name: str) -> str | None:
    """Only PostgreSQL has schemas; resolves to None (default namespace) otherwise."""
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
    """Bootstrap all tables for local/test runs. create_all() never creates the
    schemas that contain tables, so do that first on Postgres."""
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
    """Yields (session, owns_transaction). Reuses an external session (from
    UnitOfWork) when given one; otherwise opens its own."""
    if external_session is not None:
        yield external_session, False
        return
    factory = session_factory or AsyncSessionFactory
    async with factory() as session:
        yield session, True


class UnitOfWork:
    """Shared-session transaction boundary for atomic cross-module writes.

    Always rolls back on exit unless the caller explicitly commits — failures
    here are Result.Err, not exceptions, so "no exception raised" doesn't mean
    "safe to commit".

        async with UnitOfWork() as session:
            user = await user_public_api.get_user_by_id(user_id, session=session)
            if user.is_err():
                return Err(user.err())
            result = await product_public_api.create_product(data, user_id, session=session)
            if result.is_ok():
                await session.commit()
            return result
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

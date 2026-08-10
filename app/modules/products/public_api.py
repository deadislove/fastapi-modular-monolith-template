# Public contract for the Product module. Internal domain models must not leak beyond this boundary.
# All cross-module callers (Facades, other modules) MUST use this interface exclusively.

from typing import Protocol

from result import Result
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.modules.products.errors import ProductError
from app.modules.products.models import Product
from app.modules.products.repository import ProductRepository
from app.modules.products.schemas import ProductCreateRequest, ProductUpdateRequest
from app.modules.products.service import ProductService
from app.shared.database import resolve_session


class ProductPublicApiProtocol(Protocol):
    """Structural contract facades depend on instead of the concrete class, so
    tests can substitute a fake without touching the database."""

    async def create_product(
        self, data: ProductCreateRequest, user_id: int, session: AsyncSession | None = None
    ) -> Result[Product, ProductError]: ...

    async def get_product_by_id(
        self, product_id: int, session: AsyncSession | None = None
    ) -> Result[Product, ProductError]: ...

    async def get_all_products(
        self, limit: int | None = None, offset: int = 0, session: AsyncSession | None = None
    ) -> Result[list[Product], ProductError]: ...

    async def get_products_by_user(
        self,
        user_id: int,
        limit: int | None = None,
        offset: int = 0,
        session: AsyncSession | None = None,
    ) -> Result[list[Product], ProductError]: ...

    async def update_product(
        self,
        product_id: int,
        data: ProductUpdateRequest,
        requesting_user_id: int,
        session: AsyncSession | None = None,
    ) -> Result[Product, ProductError]: ...

    async def delete_product(
        self, product_id: int, requesting_user_id: int, session: AsyncSession | None = None
    ) -> Result[None, ProductError]: ...

    async def reserve_stock(
        self, product_id: int, quantity: int, session: AsyncSession | None = None
    ) -> Result[Product, ProductError]: ...


class ProductPublicApi:
    """The only sanctioned entry point for external callers. Every method takes
    an optional `session`; when a caller (typically a facade's UnitOfWork)
    passes one, that caller owns the commit/rollback."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession] | None = None) -> None:
        self._session_factory = session_factory

    async def create_product(
        self, data: ProductCreateRequest, user_id: int, session: AsyncSession | None = None
    ) -> Result[Product, ProductError]:
        async with resolve_session(session, self._session_factory) as (s, owns):
            service = ProductService(ProductRepository(s))
            result = await service.create(data, user_id)
            if result.is_ok() and owns:
                await s.commit()
            return result

    async def get_product_by_id(
        self, product_id: int, session: AsyncSession | None = None
    ) -> Result[Product, ProductError]:
        async with resolve_session(session, self._session_factory) as (s, _owns):
            service = ProductService(ProductRepository(s))
            return await service.get_by_id(product_id)

    async def get_all_products(
        self, limit: int | None = None, offset: int = 0, session: AsyncSession | None = None
    ) -> Result[list[Product], ProductError]:
        async with resolve_session(session, self._session_factory) as (s, _owns):
            service = ProductService(ProductRepository(s))
            return await service.get_all(limit=limit, offset=offset)

    async def get_products_by_user(
        self,
        user_id: int,
        limit: int | None = None,
        offset: int = 0,
        session: AsyncSession | None = None,
    ) -> Result[list[Product], ProductError]:
        async with resolve_session(session, self._session_factory) as (s, _owns):
            service = ProductService(ProductRepository(s))
            return await service.get_by_user(user_id, limit=limit, offset=offset)

    async def update_product(
        self,
        product_id: int,
        data: ProductUpdateRequest,
        requesting_user_id: int,
        session: AsyncSession | None = None,
    ) -> Result[Product, ProductError]:
        async with resolve_session(session, self._session_factory) as (s, owns):
            service = ProductService(ProductRepository(s))
            result = await service.update(product_id, data, requesting_user_id)
            if result.is_ok() and owns:
                await s.commit()
            return result

    async def delete_product(
        self, product_id: int, requesting_user_id: int, session: AsyncSession | None = None
    ) -> Result[None, ProductError]:
        async with resolve_session(session, self._session_factory) as (s, owns):
            service = ProductService(ProductRepository(s))
            result = await service.delete(product_id, requesting_user_id)
            if result.is_ok() and owns:
                await s.commit()
            return result

    async def reserve_stock(
        self, product_id: int, quantity: int, session: AsyncSession | None = None
    ) -> Result[Product, ProductError]:
        async with resolve_session(session, self._session_factory) as (s, owns):
            service = ProductService(ProductRepository(s))
            result = await service.reserve_stock(product_id, quantity)
            if result.is_ok() and owns:
                await s.commit()
            return result


# Module-level singleton — import this in facades and API routers
product_public_api = ProductPublicApi()

# Public contract for the Order module. Internal domain models must not leak beyond this boundary.
# All cross-module callers (Facades, other modules) MUST use this interface exclusively.

from decimal import Decimal
from typing import Protocol

from result import Result
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.modules.orders.errors import OrderError
from app.modules.orders.events import OrderPlaced
from app.modules.orders.models import Order
from app.modules.orders.repository import OrderRepository
from app.modules.orders.service import OrderService
from app.shared.database import resolve_session
from app.shared.events import event_bus


class OrderPublicApiProtocol(Protocol):
    """Structural contract facades depend on instead of the concrete class, so
    tests can substitute a fake without touching the database."""

    async def create_order(
        self,
        user_id: int,
        product_id: int,
        quantity: int,
        unit_price: Decimal,
        session: AsyncSession | None = None,
    ) -> Result[Order, OrderError]: ...

    async def get_order_by_id(
        self, order_id: int, session: AsyncSession | None = None
    ) -> Result[Order, OrderError]: ...

    async def get_orders_by_user(
        self,
        user_id: int,
        limit: int | None = None,
        offset: int = 0,
        session: AsyncSession | None = None,
    ) -> Result[list[Order], OrderError]: ...


class OrderPublicApi:
    """The only sanctioned entry point for external callers. Every method takes
    an optional `session`; when a caller (typically a facade's UnitOfWork)
    passes one, that caller owns the commit/rollback."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession] | None = None) -> None:
        self._session_factory = session_factory

    async def create_order(
        self,
        user_id: int,
        product_id: int,
        quantity: int,
        unit_price: Decimal,
        session: AsyncSession | None = None,
    ) -> Result[Order, OrderError]:
        async with resolve_session(session, self._session_factory) as (s, owns):
            service = OrderService(OrderRepository(s))
            result = await service.create(user_id, product_id, quantity, unit_price)
            if result.is_ok() and owns:
                await s.commit()
                order = result.ok()
                await event_bus.publish(
                    OrderPlaced(
                        order_id=order.id,
                        user_id=user_id,
                        product_id=product_id,
                        quantity=quantity,
                        total_price=order.total_price,
                    )
                )
            return result

    async def get_order_by_id(
        self, order_id: int, session: AsyncSession | None = None
    ) -> Result[Order, OrderError]:
        async with resolve_session(session, self._session_factory) as (s, _owns):
            service = OrderService(OrderRepository(s))
            return await service.get_by_id(order_id)

    async def get_orders_by_user(
        self,
        user_id: int,
        limit: int | None = None,
        offset: int = 0,
        session: AsyncSession | None = None,
    ) -> Result[list[Order], OrderError]:
        async with resolve_session(session, self._session_factory) as (s, _owns):
            service = OrderService(OrderRepository(s))
            return await service.get_by_user(user_id, limit=limit, offset=offset)


# Module-level singleton — import this in facades and API routers
order_public_api = OrderPublicApi()

from result import Err, Result

from app.modules.orders.errors import OrderError
from app.modules.orders.events import OrderPlaced
from app.modules.orders.models import Order
from app.modules.orders.public_api import OrderPublicApiProtocol, order_public_api
from app.modules.products.errors import ProductError
from app.modules.products.public_api import ProductPublicApiProtocol, product_public_api
from app.modules.users.errors import UserError
from app.modules.users.public_api import UserPublicApiProtocol, user_public_api
from app.shared.database import UnitOfWork
from app.shared.errors import DomainError
from app.shared.events import event_bus


class OrderFacade:
    """Coordinates users, products, and orders — the only place allowed to
    call all three in one operation."""

    def __init__(
        self,
        user_api: UserPublicApiProtocol,
        product_api: ProductPublicApiProtocol,
        order_api: OrderPublicApiProtocol,
    ) -> None:
        self._user_api = user_api
        self._product_api = product_api
        self._order_api = order_api

    async def place_order(
        self, user_id: int, product_id: int, quantity: int
    ) -> Result[Order, UserError | ProductError | OrderError | DomainError]:
        """Validates the user, reserves stock, and creates the order in one
        UnitOfWork — a stock reservation can never be left dangling without
        its order, or vice versa."""
        async with UnitOfWork() as session:
            user_result = await self._user_api.get_user_by_id(user_id, session=session)
            if user_result.is_err():
                return Err(user_result.err())  # type: ignore[arg-type]

            product_result = await self._product_api.get_product_by_id(product_id, session=session)
            if product_result.is_err():
                return Err(product_result.err())  # type: ignore[arg-type]
            unit_price = product_result.ok().price  # type: ignore[union-attr]

            reserve_result = await self._product_api.reserve_stock(
                product_id, quantity, session=session
            )
            if reserve_result.is_err():
                return Err(reserve_result.err())  # type: ignore[arg-type]

            order_result = await self._order_api.create_order(
                user_id, product_id, quantity, unit_price, session=session
            )
            if order_result.is_ok():
                await session.commit()
                order = order_result.ok()
                # create_order() doesn't publish here: with an external session,
                # it doesn't own the commit and can't know it's safe to. The
                # facade does, once its own commit above has actually succeeded.
                await event_bus.publish(
                    OrderPlaced(
                        order_id=order.id,
                        user_id=user_id,
                        product_id=product_id,
                        quantity=quantity,
                        total_price=order.total_price,
                    )
                )
            return order_result


# Module-level singleton — wire up via the module singletons
order_facade = OrderFacade(
    user_api=user_public_api,
    product_api=product_public_api,
    order_api=order_public_api,
)

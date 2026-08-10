from decimal import Decimal

from result import Err, Ok, Result

from app.modules.orders.errors import OrderError, OrderNotFoundError
from app.modules.orders.models import Order
from app.modules.orders.repository import OrderRepository


class OrderService:
    """Orchestrates order placement — stock reservation is the products
    module's job, called by the facade before this runs."""

    def __init__(self, repo: OrderRepository) -> None:
        self._repo = repo

    async def create(
        self, user_id: int, product_id: int, quantity: int, unit_price: Decimal
    ) -> Result[Order, OrderError]:
        order = Order(
            user_id=user_id,
            product_id=product_id,
            quantity=quantity,
            total_price=unit_price * quantity,
        )
        created = await self._repo.add(order)
        return Ok(created)

    async def get_by_id(self, order_id: int) -> Result[Order, OrderError]:
        order = await self._repo.get_by_id(order_id)
        if order is None:
            return Err(OrderNotFoundError())
        return Ok(order)

    async def get_by_user(
        self, user_id: int, limit: int | None = None, offset: int = 0
    ) -> Result[list[Order], OrderError]:
        orders = await self._repo.get_by_user(user_id, limit=limit, offset=offset)
        return Ok(orders)

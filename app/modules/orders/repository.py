from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.orders.models import Order
from app.shared.base_repository import BaseRepository


class OrderRepository(BaseRepository[Order]):
    """Persistence layer for the Order bounded context."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(Order, session)

    async def get_by_user(
        self, user_id: int, limit: int | None = None, offset: int = 0
    ) -> list[Order]:
        stmt = (
            select(Order)
            .where(Order.user_id == user_id)
            .order_by(Order.id)
            .offset(offset)
        )
        if limit is not None:
            stmt = stmt.limit(limit)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.products.models import Product
from app.shared.base_repository import BaseRepository


class ProductRepository(BaseRepository[Product]):
    """Persistence layer for the Product bounded context."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(Product, session)

    async def get_by_user(
        self, user_id: int, limit: int | None = None, offset: int = 0
    ) -> list[Product]:
        stmt = (
            select(Product)
            .where(Product.created_by_user_id == user_id)
            .order_by(Product.id)
            .offset(offset)
        )
        if limit is not None:
            stmt = stmt.limit(limit)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

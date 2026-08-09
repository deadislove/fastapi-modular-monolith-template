from result import Err, Ok, Result

from app.modules.products.errors import (
    ProductError,
    ProductForbiddenError,
    ProductNotFoundError,
)
from app.modules.products.models import Product
from app.modules.products.repository import ProductRepository
from app.modules.products.schemas import ProductCreateRequest, ProductUpdateRequest


class ProductService:
    """Orchestrates product catalog logic — enforces ownership invariants."""

    def __init__(self, repo: ProductRepository) -> None:
        self._repo = repo

    async def create(self, data: ProductCreateRequest, user_id: int) -> Result[Product, ProductError]:
        product = Product(
            name=data.name,
            description=data.description,
            price=data.price,
            stock=data.stock,
            created_by_user_id=user_id,
        )
        created = await self._repo.add(product)
        return Ok(created)

    async def get_by_id(self, product_id: int) -> Result[Product, ProductError]:
        product = await self._repo.get_by_id(product_id)
        if product is None:
            return Err(ProductNotFoundError())
        return Ok(product)

    async def get_all(
        self, limit: int | None = None, offset: int = 0
    ) -> Result[list[Product], ProductError]:
        products = await self._repo.get_all(limit=limit, offset=offset)
        return Ok(products)

    async def get_by_user(
        self, user_id: int, limit: int | None = None, offset: int = 0
    ) -> Result[list[Product], ProductError]:
        products = await self._repo.get_by_user(user_id, limit=limit, offset=offset)
        return Ok(products)

    async def update(
        self, product_id: int, data: ProductUpdateRequest, requesting_user_id: int
    ) -> Result[Product, ProductError]:
        product = await self._repo.get_by_id(product_id)
        if product is None:
            return Err(ProductNotFoundError())
        # Ownership check — only the creator may mutate the product
        if product.created_by_user_id != requesting_user_id:
            return Err(ProductForbiddenError())

        if data.name is not None:
            product.name = data.name
        if data.description is not None:
            product.description = data.description
        if data.price is not None:
            product.price = data.price
        if data.stock is not None:
            product.stock = data.stock

        await self._repo.session.flush()
        await self._repo.session.refresh(product)
        return Ok(product)

    async def delete(
        self, product_id: int, requesting_user_id: int
    ) -> Result[None, ProductError]:
        product = await self._repo.get_by_id(product_id)
        if product is None:
            return Err(ProductNotFoundError())
        if product.created_by_user_id != requesting_user_id:
            return Err(ProductForbiddenError())
        await self._repo.delete(product)
        return Ok(None)

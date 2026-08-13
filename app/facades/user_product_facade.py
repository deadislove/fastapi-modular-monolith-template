from dataclasses import dataclass
from decimal import Decimal

from result import Err, Ok, Result

from app.modules.products.errors import ProductError
from app.modules.products.models import Product
from app.modules.products.public_api import ProductPublicApiProtocol, product_public_api
from app.modules.products.schemas import ProductCreateRequest
from app.modules.users.errors import UserError
from app.modules.users.models import User
from app.modules.users.public_api import UserPublicApiProtocol, user_public_api
from app.shared.database import UnitOfWork
from app.shared.errors import DomainError


@dataclass
class UserWithProducts:
    """Composite read model — assembled by the facade, never by a cross-module JOIN."""
    user: User
    products: list[Product]


class UserProductFacade:
    """Coordinates users and products. Facades are the only code allowed to
    call more than one module's public_api in one operation — see also
    OrderFacade for a three-module example."""

    def __init__(
        self,
        user_api: UserPublicApiProtocol,
        product_api: ProductPublicApiProtocol,
    ) -> None:
        self._user_api = user_api
        self._product_api = product_api

    async def get_user_with_products(
        self, user_id: int
    ) -> Result[UserWithProducts, UserError | ProductError | DomainError]:
        """Fetch a user and all their products — two module calls, zero cross-module joins."""
        user_result = await self._user_api.get_user_by_id(user_id)
        if user_result.is_err():
            return Err(user_result.unwrap_err())

        products_result = await self._product_api.get_products_by_user(user_id)
        if products_result.is_err():
            return Err(products_result.unwrap_err())

        return Ok(UserWithProducts(user=user_result.unwrap(), products=products_result.unwrap()))

    async def create_product_for_user(
        self,
        user_id: int,
        name: str,
        price: Decimal,
        description: str | None = None,
        stock: int = 0,
    ) -> Result[Product, UserError | ProductError | DomainError]:
        """Validate user exists before creating a product on their behalf, in one
        UnitOfWork so a missing user can't leave a half-applied write behind."""
        async with UnitOfWork() as session:
            user_result = await self._user_api.get_user_by_id(user_id, session=session)
            if user_result.is_err():
                return Err(user_result.unwrap_err())

            create_data = ProductCreateRequest(
                name=name,
                description=description,
                price=price,
                stock=stock,
            )
            product_result = await self._product_api.create_product(
                create_data, user_id, session=session
            )
            if product_result.is_ok():
                await session.commit()
            return product_result


# Module-level singleton — wire up via the module singletons
user_product_facade = UserProductFacade(
    user_api=user_public_api,
    product_api=product_public_api,
)

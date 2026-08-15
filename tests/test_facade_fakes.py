"""Fake-based facade tests — no database, no HTTP, no session factory. See
docs/architecture.md#protocol-based-module-contracts for the seam these fakes
exercise: *PublicApiProtocol lets a facade test substitute a fake module
implementation.

Only UserProductFacade.get_user_with_products is covered here — it's the one
facade method with no UnitOfWork, so it's the one method a fake can drive
end-to-end without also needing a real (even if in-memory) database session.
create_product_for_user and OrderFacade.place_order both open a UnitOfWork
internally, so they stay covered by tests/test_facade.py's HTTP-level tests."""

from decimal import Decimal

import pytest
from result import Err, Ok, Result

from app.facades.user_product_facade import UserProductFacade
from app.modules.products.errors import ProductError
from app.modules.products.models import Product
from app.modules.users.errors import UserError, UserNotFoundError
from app.modules.users.models import User

pytestmark = pytest.mark.asyncio


class _FakeUserPublicApi:
    """Stands in for UserPublicApiProtocol. Only get_user_by_id is exercised
    by get_user_with_products; every other method is unused by this facade
    method and left unimplemented on purpose."""

    def __init__(self, get_user_by_id_result: Result[User, UserError]) -> None:
        self._get_user_by_id_result = get_user_by_id_result

    async def register_user(self, data, session=None):
        raise NotImplementedError

    async def authenticate_user(self, email, password, session=None):
        raise NotImplementedError

    async def get_user_by_id(self, user_id, session=None):
        return self._get_user_by_id_result

    async def get_all_users(self, limit=None, offset=0, session=None):
        raise NotImplementedError

    async def update_user(self, user_id, data, session=None):
        raise NotImplementedError

    async def delete_user(self, user_id, session=None):
        raise NotImplementedError


class _FakeProductPublicApi:
    """Stands in for ProductPublicApiProtocol. Only get_products_by_user is
    exercised by get_user_with_products; every other method is unused by this
    facade method and left unimplemented on purpose."""

    def __init__(
        self, get_products_by_user_result: Result[list[Product], ProductError] | None = None
    ) -> None:
        self._get_products_by_user_result = get_products_by_user_result

    async def create_product(self, data, user_id, session=None):
        raise NotImplementedError

    async def get_product_by_id(self, product_id, session=None):
        raise NotImplementedError

    async def get_all_products(self, limit=None, offset=0, session=None):
        raise NotImplementedError

    async def get_products_by_user(self, user_id, limit=None, offset=0, session=None):
        assert self._get_products_by_user_result is not None, (
            "get_products_by_user must not be called once the user lookup has failed"
        )
        return self._get_products_by_user_result

    async def update_product(self, product_id, data, requesting_user_id, session=None):
        raise NotImplementedError

    async def delete_product(self, product_id, requesting_user_id, session=None):
        raise NotImplementedError

    async def reserve_stock(self, product_id, quantity, session=None):
        raise NotImplementedError


async def test_get_user_with_products_assembles_both_from_fakes() -> None:
    user = User(id=1, email="fake@example.com", username="fake_user", hashed_password="x")
    product = Product(
        id=10, name="Fake Widget", price=Decimal("9.99"), stock=5, created_by_user_id=1
    )

    facade = UserProductFacade(
        user_api=_FakeUserPublicApi(Ok(user)),
        product_api=_FakeProductPublicApi(Ok([product])),
    )

    result = await facade.get_user_with_products(user_id=1)

    assert result.is_ok()
    composite = result.unwrap()
    assert composite.user.id == 1
    assert composite.products == [product]


async def test_get_user_with_products_short_circuits_when_user_missing() -> None:
    """Proven by a fake whose get_products_by_user asserts if it's ever called
    — not just by checking the returned Err, which a bug that called both APIs
    unconditionally could still satisfy by accident."""
    facade = UserProductFacade(
        user_api=_FakeUserPublicApi(Err(UserNotFoundError())),
        product_api=_FakeProductPublicApi(),  # no result configured — must not be called
    )

    result = await facade.get_user_with_products(user_id=999)

    assert result.is_err()
    assert isinstance(result.unwrap_err(), UserNotFoundError)

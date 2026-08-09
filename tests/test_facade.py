from decimal import Decimal

import pytest
from httpx import AsyncClient

from app.facades.user_product_facade import user_product_facade
from app.modules.products.public_api import product_public_api

pytestmark = pytest.mark.asyncio

PRODUCT_PAYLOAD = {
    "name": "Facade Widget",
    "description": "Created via HTTP so the facade has something to assemble",
    "price": "5.00",
    "stock": 10,
}


def _register_payload(username: str) -> dict:
    """Each test gets its own account — the in-memory test DB persists across
    tests in a session, so reusing one email/username would 409 on the 2nd use."""
    return {"email": f"{username}@example.com", "username": username, "password": "secret123"}


async def _register(client: AsyncClient, username: str) -> int:
    response = await client.post("/api/v1/users/register", json=_register_payload(username))
    return response.json()["id"]


async def _register_and_login(client: AsyncClient, username: str) -> tuple[int, str]:
    user_id = await _register(client, username)
    payload = _register_payload(username)
    login = await client.post(
        "/api/v1/users/login",
        data={"username": payload["email"], "password": payload["password"]},
    )
    return user_id, login.json()["access_token"]


async def test_get_user_with_products_assembles_both(client: AsyncClient) -> None:
    user_id, token = await _register_and_login(client, "facade_carol")
    await client.post(
        "/api/v1/products/",
        json=PRODUCT_PAYLOAD,
        headers={"Authorization": f"Bearer {token}"},
    )

    result = await user_product_facade.get_user_with_products(user_id)

    assert result.is_ok()
    composite = result.ok()
    assert composite.user.id == user_id
    assert len(composite.products) == 1
    assert composite.products[0].name == PRODUCT_PAYLOAD["name"]


async def test_get_user_with_products_user_not_found(client: AsyncClient) -> None:
    result = await user_product_facade.get_user_with_products(999_999)
    assert result.is_err()


async def test_create_product_for_user(client: AsyncClient) -> None:
    user_id = await _register(client, "facade_dave")

    result = await user_product_facade.create_product_for_user(
        user_id=user_id, name="Facade-created Gadget", price=Decimal("19.99")
    )

    assert result.is_ok()
    product = result.ok()
    assert product.created_by_user_id == user_id
    assert product.name == "Facade-created Gadget"

    # Confirm it's durably committed, not just visible on the in-transaction object.
    fetched = await product_public_api.get_product_by_id(product.id)
    assert fetched.is_ok()


async def test_create_product_for_user_rolls_back_when_user_missing(client: AsyncClient) -> None:
    """Proves UnitOfWork's default-rollback behavior: the existence check and the
    product write share one transaction, so a missing user leaves nothing behind."""
    before = (await product_public_api.get_all_products()).ok()

    result = await user_product_facade.create_product_for_user(
        user_id=999_999, name="Ghost Product", price=Decimal("1.00")
    )

    assert result.is_err()
    after = (await product_public_api.get_all_products()).ok()
    assert len(after) == len(before)

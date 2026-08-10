import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio


def _user_payload(username: str) -> dict:
    return {"email": f"{username}@example.com", "username": username, "password": "secret123"}


async def _register_and_login(client: AsyncClient, username: str) -> tuple[int, str]:
    payload = _user_payload(username)
    register = await client.post("/api/v1/users/register", json=payload)
    login = await client.post(
        "/api/v1/users/login",
        data={"username": payload["email"], "password": payload["password"]},
    )
    return register.json()["id"], login.json()["access_token"]


async def _create_product(client: AsyncClient, token: str, stock: int, price: str = "10.00") -> int:
    response = await client.post(
        "/api/v1/products/",
        json={"name": "Order Test Widget", "price": price, "stock": stock},
        headers={"Authorization": f"Bearer {token}"},
    )
    return response.json()["id"]


async def test_place_order_success(client: AsyncClient) -> None:
    _, token = await _register_and_login(client, "order_alice")
    product_id = await _create_product(client, token, stock=10, price="10.00")

    response = await client.post(
        "/api/v1/orders/",
        json={"product_id": product_id, "quantity": 3},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 201
    data = response.json()
    assert data["quantity"] == 3
    assert data["total_price"] == "30.00"

    product = await client.get(f"/api/v1/products/{product_id}")
    assert product.json()["stock"] == 7


async def test_place_order_insufficient_stock(client: AsyncClient) -> None:
    _, token = await _register_and_login(client, "order_bob")
    product_id = await _create_product(client, token, stock=2)

    response = await client.post(
        "/api/v1/orders/",
        json={"product_id": product_id, "quantity": 5},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 409


async def test_place_order_rolls_back_stock_on_insufficient_stock(client: AsyncClient) -> None:
    """UnitOfWork spans two modules' writes here (products' stock, orders' row) —
    a failed reservation must leave the already-decremented-in-memory stock untouched."""
    _, token = await _register_and_login(client, "order_carol")
    product_id = await _create_product(client, token, stock=2)

    await client.post(
        "/api/v1/orders/",
        json={"product_id": product_id, "quantity": 5},
        headers={"Authorization": f"Bearer {token}"},
    )

    product = await client.get(f"/api/v1/products/{product_id}")
    assert product.json()["stock"] == 2

    orders = await client.get(
        "/api/v1/orders/my", headers={"Authorization": f"Bearer {token}"}
    )
    assert orders.json() == []


async def test_place_order_product_not_found(client: AsyncClient) -> None:
    _, token = await _register_and_login(client, "order_dave")

    response = await client.post(
        "/api/v1/orders/",
        json={"product_id": 999_999, "quantity": 1},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 404


async def test_place_order_unauthenticated(client: AsyncClient) -> None:
    response = await client.post("/api/v1/orders/", json={"product_id": 1, "quantity": 1})
    assert response.status_code == 401


async def test_list_my_orders(client: AsyncClient) -> None:
    _, token = await _register_and_login(client, "order_erin")
    product_id = await _create_product(client, token, stock=10)
    await client.post(
        "/api/v1/orders/",
        json={"product_id": product_id, "quantity": 1},
        headers={"Authorization": f"Bearer {token}"},
    )

    response = await client.get("/api/v1/orders/my", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200
    assert len(response.json()) >= 1


async def test_get_order_by_id(client: AsyncClient) -> None:
    _, token = await _register_and_login(client, "order_frank")
    product_id = await _create_product(client, token, stock=10)
    create = await client.post(
        "/api/v1/orders/",
        json={"product_id": product_id, "quantity": 2},
        headers={"Authorization": f"Bearer {token}"},
    )
    order_id = create.json()["id"]

    response = await client.get(
        f"/api/v1/orders/{order_id}", headers={"Authorization": f"Bearer {token}"}
    )

    assert response.status_code == 200
    assert response.json()["id"] == order_id


async def test_get_order_not_found(client: AsyncClient) -> None:
    _, token = await _register_and_login(client, "order_grace")
    response = await client.get(
        "/api/v1/orders/999999", headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 404


async def test_get_order_forbidden_for_other_user(client: AsyncClient) -> None:
    _, owner_token = await _register_and_login(client, "order_heidi")
    product_id = await _create_product(client, owner_token, stock=10)
    create = await client.post(
        "/api/v1/orders/",
        json={"product_id": product_id, "quantity": 1},
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    order_id = create.json()["id"]

    _, other_token = await _register_and_login(client, "order_ivan")
    response = await client.get(
        f"/api/v1/orders/{order_id}", headers={"Authorization": f"Bearer {other_token}"}
    )

    assert response.status_code == 403

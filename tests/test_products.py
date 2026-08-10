import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio

USER_PAYLOAD = {
    "email": "bob@example.com",
    "username": "bob",
    "password": "secret123",
}

PRODUCT_PAYLOAD = {
    "name": "Widget",
    "description": "A fine widget",
    "price": "9.99",
    "stock": 100,
}


async def _register_and_login(client: AsyncClient) -> str:
    """Helper: register a user and return a valid JWT."""
    await client.post("/api/v1/users/register", json=USER_PAYLOAD)
    login = await client.post(
        "/api/v1/users/login",
        data={"username": USER_PAYLOAD["email"], "password": USER_PAYLOAD["password"]},
    )
    return login.json()["access_token"]


async def test_create_product(client: AsyncClient) -> None:
    token = await _register_and_login(client)
    response = await client.post(
        "/api/v1/products/",
        json=PRODUCT_PAYLOAD,
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == PRODUCT_PAYLOAD["name"]
    assert "id" in data


async def test_create_product_unauthenticated(client: AsyncClient) -> None:
    response = await client.post("/api/v1/products/", json=PRODUCT_PAYLOAD)
    assert response.status_code == 401


async def test_list_products(client: AsyncClient) -> None:
    token = await _register_and_login(client)
    await client.post(
        "/api/v1/products/",
        json=PRODUCT_PAYLOAD,
        headers={"Authorization": f"Bearer {token}"},
    )
    response = await client.get("/api/v1/products/")
    assert response.status_code == 200
    assert isinstance(response.json(), list)
    assert len(response.json()) >= 1


async def test_get_product_by_id(client: AsyncClient) -> None:
    token = await _register_and_login(client)
    create = await client.post(
        "/api/v1/products/",
        json=PRODUCT_PAYLOAD,
        headers={"Authorization": f"Bearer {token}"},
    )
    product_id = create.json()["id"]
    response = await client.get(f"/api/v1/products/{product_id}")
    assert response.status_code == 200
    assert response.json()["id"] == product_id


async def test_get_product_not_found(client: AsyncClient) -> None:
    response = await client.get("/api/v1/products/99999")
    assert response.status_code == 404


async def test_update_product(client: AsyncClient) -> None:
    token = await _register_and_login(client)
    create = await client.post(
        "/api/v1/products/",
        json=PRODUCT_PAYLOAD,
        headers={"Authorization": f"Bearer {token}"},
    )
    product_id = create.json()["id"]
    response = await client.patch(
        f"/api/v1/products/{product_id}",
        json={"name": "Updated Widget", "stock": 50},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    assert response.json()["name"] == "Updated Widget"
    assert response.json()["stock"] == 50


async def test_delete_product(client: AsyncClient) -> None:
    token = await _register_and_login(client)
    create = await client.post(
        "/api/v1/products/",
        json=PRODUCT_PAYLOAD,
        headers={"Authorization": f"Bearer {token}"},
    )
    product_id = create.json()["id"]
    response = await client.delete(
        f"/api/v1/products/{product_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 204

    # Confirm deletion
    get_response = await client.get(f"/api/v1/products/{product_id}")
    assert get_response.status_code == 404


async def test_list_my_products(client: AsyncClient) -> None:
    token = await _register_and_login(client)
    await client.post(
        "/api/v1/products/",
        json=PRODUCT_PAYLOAD,
        headers={"Authorization": f"Bearer {token}"},
    )
    response = await client.get(
        "/api/v1/products/my",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    assert len(response.json()) >= 1


async def test_list_my_products_respects_limit(client: AsyncClient) -> None:
    token = await _register_and_login(client)
    for i in range(3):
        await client.post(
            "/api/v1/products/",
            json={**PRODUCT_PAYLOAD, "name": f"Paginated Widget {i}"},
            headers={"Authorization": f"Bearer {token}"},
        )

    response = await client.get(
        "/api/v1/products/my?limit=1",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    assert len(response.json()) == 1


async def test_list_my_products_offset_skips_rows(client: AsyncClient) -> None:
    """Different offsets must return different rows, not the same page twice."""
    token = await _register_and_login(client)
    for i in range(3):
        await client.post(
            "/api/v1/products/",
            json={**PRODUCT_PAYLOAD, "name": f"Offset Widget {i}"},
            headers={"Authorization": f"Bearer {token}"},
        )

    page_one = await client.get(
        "/api/v1/products/my?limit=1&offset=0",
        headers={"Authorization": f"Bearer {token}"},
    )
    page_two = await client.get(
        "/api/v1/products/my?limit=1&offset=1",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert page_one.json()[0]["id"] != page_two.json()[0]["id"]

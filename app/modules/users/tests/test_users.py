import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio


REGISTER_PAYLOAD = {
    "email": "alice@example.com",
    "username": "alice",
    "password": "secret123",
}


async def test_register_user(client: AsyncClient) -> None:
    response = await client.post("/api/v1/users/register", json=REGISTER_PAYLOAD)
    assert response.status_code == 201
    data = response.json()
    assert data["email"] == REGISTER_PAYLOAD["email"]
    assert data["username"] == REGISTER_PAYLOAD["username"]
    assert "id" in data


async def test_register_duplicate_email(client: AsyncClient) -> None:
    await client.post("/api/v1/users/register", json=REGISTER_PAYLOAD)
    response = await client.post("/api/v1/users/register", json=REGISTER_PAYLOAD)
    assert response.status_code == 409


async def test_login_success(client: AsyncClient) -> None:
    await client.post("/api/v1/users/register", json=REGISTER_PAYLOAD)
    response = await client.post(
        "/api/v1/users/login",
        data={"username": REGISTER_PAYLOAD["email"], "password": REGISTER_PAYLOAD["password"]},
    )
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"


async def test_login_wrong_password(client: AsyncClient) -> None:
    await client.post("/api/v1/users/register", json=REGISTER_PAYLOAD)
    response = await client.post(
        "/api/v1/users/login",
        data={"username": REGISTER_PAYLOAD["email"], "password": "wrongpassword"},
    )
    assert response.status_code == 401


async def test_get_me(client: AsyncClient) -> None:
    await client.post("/api/v1/users/register", json=REGISTER_PAYLOAD)
    login = await client.post(
        "/api/v1/users/login",
        data={"username": REGISTER_PAYLOAD["email"], "password": REGISTER_PAYLOAD["password"]},
    )
    token = login.json()["access_token"]
    response = await client.get("/api/v1/users/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    assert response.json()["email"] == REGISTER_PAYLOAD["email"]


async def test_get_me_unauthenticated(client: AsyncClient) -> None:
    response = await client.get("/api/v1/users/me")
    assert response.status_code == 401


async def test_register_rejects_short_password(client: AsyncClient) -> None:
    response = await client.post(
        "/api/v1/users/register",
        json={"email": "shortpw@example.com", "username": "shortpw", "password": "short1"},
    )
    assert response.status_code == 422


async def test_register_rejects_password_over_bcrypt_byte_limit(client: AsyncClient) -> None:
    """73 single-byte chars is already over the limit; using a multi-byte
    character proves the check counts bytes, not Python string length —
    36 of these 3-byte characters (€, U+20AC) is 108 bytes but only 36
    characters."""
    response = await client.post(
        "/api/v1/users/register",
        json={
            "email": "longpw@example.com",
            "username": "longpw",
            "password": "€" * 36,
        },
    )
    assert response.status_code == 422


async def test_register_rejects_short_username(client: AsyncClient) -> None:
    response = await client.post(
        "/api/v1/users/register",
        json={"email": "shortname@example.com", "username": "ab", "password": "secret123"},
    )
    assert response.status_code == 422

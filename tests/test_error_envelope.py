import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio


async def test_domain_error_uses_unified_envelope(client: AsyncClient) -> None:
    response = await client.get("/api/v1/products/999999")
    assert response.status_code == 404
    assert response.json() == {"error": {"code": "PRODUCT_NOT_FOUND", "message": "Product not found"}}


async def test_validation_error_uses_unified_envelope(client: AsyncClient) -> None:
    response = await client.post("/api/v1/users/register", json={"email": "not-an-email"})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


async def test_unauthenticated_error_uses_unified_envelope(client: AsyncClient) -> None:
    """A garbage (not merely absent) token exercises get_current_user_id's own
    HTTPException, which is where the INVALID_TOKEN code comes from — a request
    with no Authorization header at all 401s earlier, via OAuth2PasswordBearer's
    own generic exception, and still gets the same envelope (just a generic code)."""
    response = await client.get(
        "/api/v1/users/me", headers={"Authorization": "Bearer garbage"}
    )
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "INVALID_TOKEN"


async def test_rate_limit_error_uses_unified_envelope(client: AsyncClient) -> None:
    """/register is 10/minute; the 11th call in the same (reset-per-test) budget
    must 429 with the same envelope as every other error."""
    last = None
    for i in range(11):
        last = await client.post(
            "/api/v1/users/register",
            json={"email": f"envelope{i}@example.com", "username": f"envelope{i}", "password": "secret123"},
        )
    assert last.status_code == 429
    assert last.json()["error"]["code"] == "RATE_LIMIT_EXCEEDED"

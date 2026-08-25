import logging

import pytest
from httpx import AsyncClient

from app.shared.request_context import REQUEST_ID_HEADER

pytestmark = pytest.mark.asyncio


async def test_response_includes_a_request_id_header(client: AsyncClient) -> None:
    response = await client.get("/health")
    assert REQUEST_ID_HEADER in response.headers
    assert response.headers[REQUEST_ID_HEADER]  # non-empty


async def test_two_requests_get_different_request_ids(client: AsyncClient) -> None:
    first = await client.get("/health")
    second = await client.get("/health")
    assert first.headers[REQUEST_ID_HEADER] != second.headers[REQUEST_ID_HEADER]


async def test_log_lines_from_within_a_request_carry_its_request_id(
    client: AsyncClient, caplog: pytest.LogCaptureFixture
) -> None:
    """The users subscriber's log line (app/modules/users/subscribers.py,
    triggered via the event bus from inside the request) must carry the same
    request_id as the response it belongs to — proving the ContextVar
    actually threads through the whole call chain, not just the router."""
    with caplog.at_level(logging.INFO):
        response = await client.post(
            "/api/v1/users/register",
            json={
                "email": "context-test@example.com",
                "username": "context_test",
                "password": "secret123",
            },
        )
    request_id = response.headers[REQUEST_ID_HEADER]

    subscriber_records = [r for r in caplog.records if "User registered" in r.message]
    assert subscriber_records, "expected the users subscriber's log line to fire"
    assert subscriber_records[0].request_id == request_id

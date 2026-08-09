from dataclasses import dataclass

import pytest
from httpx import AsyncClient

from app.modules.users.events import UserRegistered
from app.shared.events import DomainEvent, EventBus, event_bus

pytestmark = pytest.mark.asyncio


@dataclass(frozen=True)
class _PingEvent(DomainEvent):
    value: int


async def test_publish_calls_subscribed_handlers() -> None:
    bus = EventBus()
    received = []

    async def handler(event: _PingEvent) -> None:
        received.append(event.value)

    bus.subscribe(_PingEvent, handler)
    await bus.publish(_PingEvent(value=42))

    assert received == [42]


async def test_publish_with_no_subscribers_is_a_no_op() -> None:
    bus = EventBus()
    await bus.publish(_PingEvent(value=1))  # must not raise


async def test_a_failing_handler_does_not_stop_other_handlers() -> None:
    bus = EventBus()
    received = []

    async def bad_handler(event: _PingEvent) -> None:
        raise RuntimeError("boom")

    async def good_handler(event: _PingEvent) -> None:
        received.append(event.value)

    bus.subscribe(_PingEvent, bad_handler)
    bus.subscribe(_PingEvent, good_handler)

    await bus.publish(_PingEvent(value=7))  # must not raise, despite bad_handler

    assert received == [7]


async def test_unsubscribe_stops_future_events() -> None:
    bus = EventBus()
    received = []

    async def handler(event: _PingEvent) -> None:
        received.append(event.value)

    bus.subscribe(_PingEvent, handler)
    bus.unsubscribe(_PingEvent, handler)
    await bus.publish(_PingEvent(value=99))

    assert received == []


async def test_registering_a_user_publishes_user_registered(client: AsyncClient) -> None:
    """Proves the composition-root wiring in app/main.py, not just EventBus in
    isolation — registers a real handler on the process-wide event_bus singleton."""
    received: list[UserRegistered] = []

    async def handler(event: UserRegistered) -> None:
        received.append(event)

    event_bus.subscribe(UserRegistered, handler)
    try:
        response = await client.post(
            "/api/v1/users/register",
            json={"email": "events@example.com", "username": "events_user", "password": "secret123"},
        )
        assert response.status_code == 201
        assert len(received) == 1
        assert received[0].email == "events@example.com"
    finally:
        event_bus.unsubscribe(UserRegistered, handler)

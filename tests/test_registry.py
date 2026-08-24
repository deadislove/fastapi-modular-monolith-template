from typing import Protocol

import pytest

from app.shared.events import EventBus
from app.shared.registry import ModuleRegistry


class _SomeProtocol(Protocol):
    def ping(self) -> str: ...


class _SomeImplementation:
    def ping(self) -> str:
        return "pong"


def test_resolve_returns_the_registered_implementation() -> None:
    registry = ModuleRegistry()
    impl = _SomeImplementation()

    registry.register_contract(_SomeProtocol, impl)  # type: ignore[type-abstract]

    assert registry.resolve(_SomeProtocol) is impl  # type: ignore[type-abstract]


def test_resolve_fails_loudly_when_nothing_registered() -> None:
    registry = ModuleRegistry()

    with pytest.raises(LookupError, match="_SomeProtocol"):
        registry.resolve(_SomeProtocol)  # type: ignore[type-abstract]


def test_register_contract_rejects_double_registration() -> None:
    registry = ModuleRegistry()
    registry.register_contract(_SomeProtocol, _SomeImplementation())  # type: ignore[type-abstract]

    with pytest.raises(ValueError, match="_SomeProtocol"):
        registry.register_contract(_SomeProtocol, _SomeImplementation())  # type: ignore[type-abstract]


async def test_wire_event_subscribers_calls_every_registered_registrar() -> None:
    registry = ModuleRegistry()
    calls: list[EventBus] = []

    registry.register_subscribers(calls.append)
    registry.register_subscribers(calls.append)

    bus = EventBus()
    registry.wire_event_subscribers(bus)

    assert calls == [bus, bus]

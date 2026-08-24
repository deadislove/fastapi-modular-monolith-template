"""Passive contract registry — generic on purpose: must not import from
app.modules, same rule as events.py. Modules register what they provide
(from their own public_api.py/subscribers.py); the composition root
(app/main.py) is the only place allowed to know which modules exist and
import them to trigger that registration — see app/main.py's
discover_modules()."""

from collections.abc import Callable
from typing import TypeVar

from app.shared.events import EventBus

T = TypeVar("T")


class ModuleRegistry:
    """A module isn't usable by another module until it's registered here —
    resolve() fails loudly instead of returning None, so a module that
    forgot to register is a startup error, not a runtime surprise.

    Every register_contract()/resolve() call site passes a *PublicApiProtocol
    class, not a concrete class — mypy's type-abstract check assumes a
    `type[T]` argument might get instantiated inside the function and rejects
    passing a Protocol there, even though neither method here ever calls
    `protocol()`. There's no clean way to type around this (a known mypy
    limitation for exactly this registry-of-protocols shape), so every call
    site carries a narrow `# type: ignore[type-abstract]`."""

    def __init__(self) -> None:
        self._contracts: dict[type, object] = {}
        self._subscriber_registrars: list[Callable[[EventBus], None]] = []

    def register_contract(self, protocol: type[T], implementation: T) -> None:
        if protocol in self._contracts:
            raise ValueError(f"{protocol.__name__} is already registered")
        self._contracts[protocol] = implementation

    def resolve(self, protocol: type[T]) -> T:
        try:
            return self._contracts[protocol]  # type: ignore[return-value]
        except KeyError:
            raise LookupError(
                f"No module has registered a contract for {protocol.__name__}"
            ) from None

    def register_subscribers(self, register_fn: Callable[[EventBus], None]) -> None:
        self._subscriber_registrars.append(register_fn)

    def wire_event_subscribers(self, bus: EventBus) -> None:
        for register_fn in self._subscriber_registrars:
            register_fn(bus)


# Process-wide singleton — modules register into it; consumers resolve from it.
module_registry = ModuleRegistry()

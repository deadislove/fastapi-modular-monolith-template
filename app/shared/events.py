"""In-process pub/sub for fire-and-forget side effects (use a Facade instead
when the caller needs a result back). Generic on purpose: must not import from
app.modules. Concrete event types live in each module's events.py; subscribers
are wired up in app/main.py, the one place allowed to know about both."""

import logging
from collections import defaultdict
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import TypeVar

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class DomainEvent:
    """Base type for events a module publishes when something noteworthy happens."""


EventT = TypeVar("EventT", bound=DomainEvent)
Handler = Callable[[DomainEvent], Awaitable[None]]


class EventBus:
    """In-memory, single-process pub/sub. A handler's exception is logged and
    swallowed, not re-raised — an optional side effect can't fail the publisher's request."""

    def __init__(self) -> None:
        self._handlers: dict[type[DomainEvent], list[Handler]] = defaultdict(list)

    def subscribe(
        self, event_type: type[EventT], handler: Callable[[EventT], Awaitable[None]]
    ) -> None:
        self._handlers[event_type].append(handler)  # type: ignore[arg-type]

    def unsubscribe(
        self, event_type: type[EventT], handler: Callable[[EventT], Awaitable[None]]
    ) -> None:
        self._handlers[event_type].remove(handler)  # type: ignore[arg-type]

    async def publish(self, event: DomainEvent) -> None:
        for handler in self._handlers[type(event)]:
            try:
                await handler(event)
            except Exception:
                logger.exception("Event handler %r failed for %r", handler, event)


# Process-wide singleton — modules publish to it; subscribers register on startup.
event_bus = EventBus()

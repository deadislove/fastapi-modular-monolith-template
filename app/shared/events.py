"""
In-process pub/sub for decoupled cross-module side effects.

Use a Facade (see app/facades/) when the caller needs a result back — it calls
each module's public_api directly and can return errors. Use an event when a
module just needs to say "this happened" without knowing or caring whether
anyone reacts: e.g. logging, sending a welcome email, warming a cache. This
keeps optional side effects out of the core service logic that would
otherwise have to be threaded through it, and out of the publishing module's
knowledge of who consumes it.

This bus is generic and must not import from app.modules — concrete event
types live next to the module that publishes them (e.g.
app.modules.users.events), and subscribers are wired up at the composition
root (app/main.py), which is the one place allowed to know about both.
"""

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
    """
    In-memory, single-process pub/sub. Handlers run sequentially in subscription
    order; a handler's exception is logged and swallowed so one broken subscriber
    can't take down the publisher's request.
    """

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

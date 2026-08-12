import logging

from app.modules.users.events import UserRegistered
from app.shared.events import EventBus

logger = logging.getLogger(__name__)


async def _log_user_registered(event: UserRegistered) -> None:
    logger.info("User registered: id=%s email=%s", event.user_id, event.email)


def register_subscribers(bus: EventBus) -> None:
    """Self-registration for this module's reactions to its own events. A
    subscription to *another* module's event still belongs in app/main.py —
    only the composition root may import another module's events.py."""
    bus.subscribe(UserRegistered, _log_user_registered)

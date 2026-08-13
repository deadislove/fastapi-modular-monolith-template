import logging

from app.modules.users.events import UserRegistered
from app.shared.events import EventBus

logger = logging.getLogger(__name__)


async def _log_user_registered(event: UserRegistered) -> None:
    logger.info("User registered: id=%s email=%s", event.user_id, event.email)


def register_subscribers(bus: EventBus) -> None:
    """Only this module's own events — cross-module subscriptions stay in app/main.py."""
    bus.subscribe(UserRegistered, _log_user_registered)

import logging

from app.modules.orders.events import OrderPlaced
from app.shared.events import EventBus

logger = logging.getLogger(__name__)


async def _log_order_placed(event: OrderPlaced) -> None:
    logger.info(
        "Order placed: id=%s user_id=%s product_id=%s qty=%s",
        event.order_id, event.user_id, event.product_id, event.quantity,
    )


def register_subscribers(bus: EventBus) -> None:
    """Self-registration for this module's reactions to its own events. A
    subscription to *another* module's event still belongs in app/main.py —
    only the composition root may import another module's events.py."""
    bus.subscribe(OrderPlaced, _log_order_placed)

from dataclasses import dataclass
from decimal import Decimal

from app.shared.events import DomainEvent


@dataclass(frozen=True)
class OrderPlaced(DomainEvent):
    """Published after an order and its stock reservation both commit."""

    order_id: int
    user_id: int
    product_id: int
    quantity: int
    total_price: Decimal

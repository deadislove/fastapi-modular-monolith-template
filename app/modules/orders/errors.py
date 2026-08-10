from dataclasses import dataclass

from app.shared.errors import DomainError, NotFoundError


@dataclass(frozen=True)
class OrderNotFoundError(NotFoundError):
    message: str = "Order not found"
    code: str = "ORDER_NOT_FOUND"


# Union type alias — used as the Err side of Result[T, OrderError]
OrderError = OrderNotFoundError | DomainError

from dataclasses import dataclass

from app.shared.errors import DomainError, ForbiddenError, NotFoundError


@dataclass(frozen=True)
class OrderNotFoundError(NotFoundError):
    message: str = "Order not found"
    code: str = "ORDER_NOT_FOUND"


@dataclass(frozen=True)
class OrderForbiddenError(ForbiddenError):
    message: str = "Not your order"
    code: str = "ORDER_FORBIDDEN"


# Union type alias — used as the Err side of Result[T, OrderError]
OrderError = OrderNotFoundError | OrderForbiddenError | DomainError

from dataclasses import dataclass

from app.shared.errors import ConflictError, DomainError, ForbiddenError, NotFoundError


@dataclass(frozen=True)
class ProductNotFoundError(NotFoundError):
    message: str = "Product not found"
    code: str = "PRODUCT_NOT_FOUND"


@dataclass(frozen=True)
class ProductForbiddenError(ForbiddenError):
    message: str = "You do not have permission to modify this product"
    code: str = "PRODUCT_FORBIDDEN"


@dataclass(frozen=True)
class InsufficientStockError(ConflictError):
    message: str = "Not enough stock available"
    code: str = "INSUFFICIENT_STOCK"


# Union type alias — used as the Err side of Result[T, ProductError]
ProductError = ProductNotFoundError | ProductForbiddenError | InsufficientStockError | DomainError

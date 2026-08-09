from dataclasses import dataclass

from app.shared.errors import DomainError, ForbiddenError, NotFoundError


@dataclass(frozen=True)
class ProductNotFoundError(NotFoundError):
    message: str = "Product not found"
    code: str = "PRODUCT_NOT_FOUND"


@dataclass(frozen=True)
class ProductForbiddenError(ForbiddenError):
    message: str = "You do not have permission to modify this product"
    code: str = "PRODUCT_FORBIDDEN"


# Union type alias — used as the Err side of Result[T, ProductError]
ProductError = ProductNotFoundError | ProductForbiddenError | DomainError

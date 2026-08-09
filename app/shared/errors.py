from dataclasses import dataclass


@dataclass(frozen=True)
class DomainError:
    """Base error type for all module-level domain errors."""
    message: str
    code: str = "DOMAIN_ERROR"


@dataclass(frozen=True)
class NotFoundError(DomainError):
    code: str = "NOT_FOUND"


@dataclass(frozen=True)
class ConflictError(DomainError):
    code: str = "CONFLICT"


@dataclass(frozen=True)
class UnauthorizedError(DomainError):
    code: str = "UNAUTHORIZED"


@dataclass(frozen=True)
class ForbiddenError(DomainError):
    code: str = "FORBIDDEN"


@dataclass(frozen=True)
class ValidationError(DomainError):
    code: str = "VALIDATION_ERROR"

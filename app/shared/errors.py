from dataclasses import dataclass


@dataclass(frozen=True)
class DomainError:
    """Base error type for all module-level domain errors."""
    message: str
    code: str = "DOMAIN_ERROR"

    def as_detail(self) -> dict[str, str]:
        """HTTPException(detail=...) payload — see app/shared/exception_handler.py."""
        return {"code": self.code, "message": self.message}


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

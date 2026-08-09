from dataclasses import dataclass

from app.shared.errors import ConflictError, DomainError, NotFoundError, UnauthorizedError


@dataclass(frozen=True)
class UserNotFoundError(NotFoundError):
    message: str = "User not found"
    code: str = "USER_NOT_FOUND"


@dataclass(frozen=True)
class UserEmailConflictError(ConflictError):
    message: str = "A user with this email already exists"
    code: str = "USER_EMAIL_CONFLICT"


@dataclass(frozen=True)
class UserUsernameConflictError(ConflictError):
    message: str = "A user with this username already exists"
    code: str = "USER_USERNAME_CONFLICT"


@dataclass(frozen=True)
class InvalidCredentialsError(UnauthorizedError):
    message: str = "Invalid email or password"
    code: str = "INVALID_CREDENTIALS"


@dataclass(frozen=True)
class UserInactiveError(UnauthorizedError):
    message: str = "User account is inactive"
    code: str = "USER_INACTIVE"


# Union type alias — used as the Err side of Result[T, UserError]
UserError = (
    UserNotFoundError
    | UserEmailConflictError
    | UserUsernameConflictError
    | InvalidCredentialsError
    | UserInactiveError
    | DomainError
)

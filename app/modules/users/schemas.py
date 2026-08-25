from datetime import datetime

from pydantic import BaseModel, EmailStr, Field, field_validator

# bcrypt only hashes the first 72 bytes of a password (see
# app/shared/security.py); anything past that is silently ignored, not an
# error. Enforcing the limit here means a user finds out at registration, not
# after discovering their 100-character password logs in with any 72-byte
# prefix of it.
_MAX_PASSWORD_BCRYPT_BYTES = 72


def _check_password_fits_bcrypt(value: str) -> None:
    if len(value.encode("utf-8")) > _MAX_PASSWORD_BCRYPT_BYTES:
        raise ValueError(
            f"Password must be at most {_MAX_PASSWORD_BCRYPT_BYTES} bytes — "
            "bcrypt silently truncates anything longer"
        )


# --- Request schemas ---

class UserRegisterRequest(BaseModel):
    email: EmailStr = Field(max_length=255)
    username: str = Field(min_length=3, max_length=100)
    password: str = Field(min_length=8)

    @field_validator("password")
    @classmethod
    def _password_length(cls, value: str) -> str:
        _check_password_fits_bcrypt(value)
        return value


class UserLoginRequest(BaseModel):
    email: EmailStr
    password: str


class UserUpdateRequest(BaseModel):
    username: str | None = Field(default=None, min_length=3, max_length=100)
    password: str | None = Field(default=None, min_length=8)

    @field_validator("password")
    @classmethod
    def _password_length(cls, value: str | None) -> str | None:
        if value is not None:
            _check_password_fits_bcrypt(value)
        return value


# --- Response schemas ---

class UserResponse(BaseModel):
    id: int
    email: str
    username: str
    is_active: bool
    is_superuser: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"

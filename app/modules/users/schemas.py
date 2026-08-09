from datetime import datetime

from pydantic import BaseModel, EmailStr


# --- Request schemas ---

class UserRegisterRequest(BaseModel):
    email: EmailStr
    username: str
    password: str


class UserLoginRequest(BaseModel):
    email: EmailStr
    password: str


class UserUpdateRequest(BaseModel):
    username: str | None = None
    password: str | None = None


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

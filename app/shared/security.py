from datetime import UTC, datetime, timedelta

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from passlib.context import CryptContext

from app.shared.config import settings

# Use bcrypt with truncate_error disabled — bcrypt 4.x raises ValueError for passwords >72 bytes
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Token URL matches the login endpoint in the users router
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/users/login")


def hash_password(plain: str) -> str:
    return pwd_context.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def create_access_token(subject: str | int, extra_claims: dict | None = None) -> str:
    """Issue a signed JWT. `subject` is typically the user id."""
    expire = datetime.now(UTC) + timedelta(minutes=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES)
    payload: dict = {"sub": str(subject), "exp": expire}
    if extra_claims:
        payload.update(extra_claims)
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def decode_access_token(token: str) -> dict:
    """Decode and validate a JWT. Raises jwt.PyJWTError on failure."""
    return jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])


async def get_current_user_id(token: str = Depends(oauth2_scheme)) -> int:
    """FastAPI dependency — extracts and validates the caller's user id from Bearer token."""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail={"code": "INVALID_TOKEN", "message": "Could not validate credentials"},
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = decode_access_token(token)
        user_id_str: str | None = payload.get("sub")
        if user_id_str is None:
            raise credentials_exception
        return int(user_id_str)
    except (jwt.PyJWTError, ValueError) as err:
        raise credentials_exception from err

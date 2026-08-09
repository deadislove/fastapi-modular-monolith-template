from result import Err, Ok, Result

from app.modules.users.errors import (
    InvalidCredentialsError,
    UserEmailConflictError,
    UserError,
    UserInactiveError,
    UserNotFoundError,
    UserUsernameConflictError,
)
from app.modules.users.models import User
from app.modules.users.repository import UserRepository
from app.modules.users.schemas import UserRegisterRequest, UserUpdateRequest
from app.shared.security import create_access_token, hash_password, verify_password


class UserService:
    """Orchestrates user domain logic — repository is the only persistence boundary."""

    def __init__(self, repo: UserRepository) -> None:
        self._repo = repo

    async def register(self, data: UserRegisterRequest) -> Result[User, UserError]:
        if await self._repo.email_exists(data.email):
            return Err(UserEmailConflictError())
        if await self._repo.username_exists(data.username):
            return Err(UserUsernameConflictError())

        user = User(
            email=data.email,
            username=data.username,
            hashed_password=hash_password(data.password),
        )
        created = await self._repo.add(user)
        return Ok(created)

    async def authenticate(self, email: str, password: str) -> Result[str, UserError]:
        """Returns a signed JWT on success."""
        user = await self._repo.get_by_email(email)
        if user is None or not verify_password(password, user.hashed_password):
            return Err(InvalidCredentialsError())
        if not user.is_active:
            return Err(UserInactiveError())
        token = create_access_token(subject=user.id)
        return Ok(token)

    async def get_by_id(self, user_id: int) -> Result[User, UserError]:
        user = await self._repo.get_by_id(user_id)
        if user is None:
            return Err(UserNotFoundError())
        return Ok(user)

    async def get_all(self, limit: int | None = None, offset: int = 0) -> Result[list[User], UserError]:
        users = await self._repo.get_all(limit=limit, offset=offset)
        return Ok(users)

    async def update(self, user_id: int, data: UserUpdateRequest) -> Result[User, UserError]:
        user = await self._repo.get_by_id(user_id)
        if user is None:
            return Err(UserNotFoundError())

        if data.username is not None:
            if await self._repo.username_exists(data.username):
                return Err(UserUsernameConflictError())
            user.username = data.username

        if data.password is not None:
            user.hashed_password = hash_password(data.password)

        await self._repo.session.flush()
        await self._repo.session.refresh(user)
        return Ok(user)

    async def delete(self, user_id: int) -> Result[None, UserError]:
        user = await self._repo.get_by_id(user_id)
        if user is None:
            return Err(UserNotFoundError())
        await self._repo.delete(user)
        return Ok(None)

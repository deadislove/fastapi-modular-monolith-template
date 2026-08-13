# Public contract for the User module. Internal domain models must not leak beyond this boundary.
# All cross-module callers (Facades, other modules) MUST use this interface exclusively.

from typing import Protocol

from result import Result
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.modules.users.errors import UserError
from app.modules.users.events import UserRegistered
from app.modules.users.models import User
from app.modules.users.repository import UserRepository
from app.modules.users.schemas import UserRegisterRequest, UserUpdateRequest
from app.modules.users.service import UserService
from app.shared.database import resolve_session
from app.shared.events import event_bus


class UserPublicApiProtocol(Protocol):
    """Structural contract facades depend on instead of the concrete class, so
    tests can substitute a fake without touching the database."""

    async def register_user(
        self, data: UserRegisterRequest, session: AsyncSession | None = None
    ) -> Result[User, UserError]: ...

    async def authenticate_user(
        self, email: str, password: str, session: AsyncSession | None = None
    ) -> Result[str, UserError]: ...

    async def get_user_by_id(
        self, user_id: int, session: AsyncSession | None = None
    ) -> Result[User, UserError]: ...

    async def get_all_users(
        self, limit: int | None = None, offset: int = 0, session: AsyncSession | None = None
    ) -> Result[list[User], UserError]: ...

    async def update_user(
        self, user_id: int, data: UserUpdateRequest, session: AsyncSession | None = None
    ) -> Result[User, UserError]: ...

    async def delete_user(
        self, user_id: int, session: AsyncSession | None = None
    ) -> Result[None, UserError]: ...


class UserPublicApi:
    """The only sanctioned entry point for external callers. Every method takes
    an optional `session`; when a caller (typically a facade's UnitOfWork)
    passes one, that caller owns the commit/rollback."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession] | None = None) -> None:
        self._session_factory = session_factory

    async def register_user(
        self, data: UserRegisterRequest, session: AsyncSession | None = None
    ) -> Result[User, UserError]:
        async with resolve_session(session, self._session_factory) as (s, owns):
            service = UserService(UserRepository(s))
            result = await service.register(data)
            if result.is_ok() and owns:
                await s.commit()
                user = result.unwrap()
                await event_bus.publish(UserRegistered(user_id=user.id, email=user.email))
            return result

    async def authenticate_user(
        self, email: str, password: str, session: AsyncSession | None = None
    ) -> Result[str, UserError]:
        async with resolve_session(session, self._session_factory) as (s, _owns):
            service = UserService(UserRepository(s))
            return await service.authenticate(email, password)

    async def get_user_by_id(
        self, user_id: int, session: AsyncSession | None = None
    ) -> Result[User, UserError]:
        async with resolve_session(session, self._session_factory) as (s, _owns):
            service = UserService(UserRepository(s))
            return await service.get_by_id(user_id)

    async def get_all_users(
        self, limit: int | None = None, offset: int = 0, session: AsyncSession | None = None
    ) -> Result[list[User], UserError]:
        async with resolve_session(session, self._session_factory) as (s, _owns):
            service = UserService(UserRepository(s))
            return await service.get_all(limit=limit, offset=offset)

    async def update_user(
        self, user_id: int, data: UserUpdateRequest, session: AsyncSession | None = None
    ) -> Result[User, UserError]:
        async with resolve_session(session, self._session_factory) as (s, owns):
            service = UserService(UserRepository(s))
            result = await service.update(user_id, data)
            if result.is_ok() and owns:
                await s.commit()
            return result

    async def delete_user(
        self, user_id: int, session: AsyncSession | None = None
    ) -> Result[None, UserError]:
        async with resolve_session(session, self._session_factory) as (s, owns):
            service = UserService(UserRepository(s))
            result = await service.delete(user_id)
            if result.is_ok() and owns:
                await s.commit()
            return result


# Module-level singleton — import this in facades and API routers
user_public_api = UserPublicApi()

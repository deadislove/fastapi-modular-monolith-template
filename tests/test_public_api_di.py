import pytest

from app.modules.users.public_api import UserPublicApi
from app.modules.users.schemas import UserRegisterRequest
from tests.conftest import TestSessionFactory

pytestmark = pytest.mark.asyncio


async def test_user_public_api_accepts_an_explicit_session_factory() -> None:
    """
    A UserPublicApi built with its own session_factory never touches the
    process-wide app.shared.database.AsyncSessionFactory global — useful for unit
    tests that want an isolated instance instead of monkeypatching shared state.
    """
    isolated_api = UserPublicApi(session_factory=TestSessionFactory)

    result = await isolated_api.register_user(
        UserRegisterRequest(
            email="isolated@example.com", username="isolated_user", password="secret123"
        )
    )

    assert result.is_ok()
    assert result.ok().email == "isolated@example.com"

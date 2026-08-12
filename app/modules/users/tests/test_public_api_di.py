import pytest

from app.modules.users.public_api import UserPublicApi
from app.modules.users.schemas import UserRegisterRequest
from conftest import TestSessionFactory

pytestmark = pytest.mark.asyncio


async def test_user_public_api_accepts_an_explicit_session_factory() -> None:
    """Never touches the process-wide AsyncSessionFactory global."""
    isolated_api = UserPublicApi(session_factory=TestSessionFactory)

    result = await isolated_api.register_user(
        UserRegisterRequest(
            email="isolated@example.com", username="isolated_user", password="secret123"
        )
    )

    assert result.is_ok()
    assert result.ok().email == "isolated@example.com"

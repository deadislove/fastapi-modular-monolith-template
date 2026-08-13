import pytest
from pydantic import ValidationError

from app.shared.config import Settings


def test_production_rejects_default_jwt_secret() -> None:
    with pytest.raises(ValidationError, match="JWT_SECRET_KEY"):
        Settings(APP_ENV="production", JWT_SECRET_KEY="dev-secret-key-change-in-production")


def test_production_accepts_overridden_jwt_secret() -> None:
    Settings(APP_ENV="production", JWT_SECRET_KEY="a-real-random-secret")


def test_development_allows_default_jwt_secret() -> None:
    Settings(APP_ENV="development", JWT_SECRET_KEY="dev-secret-key-change-in-production")

from pydantic import model_validator
from pydantic_settings import BaseSettings

_DEFAULT_JWT_SECRET_KEY = "dev-secret-key-change-in-production"


class Settings(BaseSettings):
    APP_NAME: str = "fastapi-modular-monolith-template"
    APP_ENV: str = "development"
    DEBUG: bool = True

    DATABASE_URL: str = "sqlite+aiosqlite:///./app.db"

    JWT_SECRET_KEY: str = _DEFAULT_JWT_SECRET_KEY
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 30

    RATE_LIMIT_DEFAULT: str = "100/minute"

    # Explicit allow-list — browsers reject "*" combined with allow_credentials=True anyway.
    CORS_ORIGINS: list[str] = ["http://localhost:3000", "http://localhost:8000"]

    model_config = {"env_file": ".env", "case_sensitive": True}

    @model_validator(mode="after")
    def _forbid_default_jwt_secret_in_production(self) -> "Settings":
        if self.APP_ENV == "production" and self.JWT_SECRET_KEY == _DEFAULT_JWT_SECRET_KEY:
            raise ValueError(
                "JWT_SECRET_KEY is still the insecure default — set a real secret "
                "via the JWT_SECRET_KEY env var before running with APP_ENV=production."
            )
        return self


settings = Settings()

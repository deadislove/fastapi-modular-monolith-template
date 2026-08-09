from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    APP_NAME: str = "fastapi-modular-monolith-template"
    APP_ENV: str = "development"
    DEBUG: bool = True

    DATABASE_URL: str = "sqlite+aiosqlite:///./app.db"

    JWT_SECRET_KEY: str = "dev-secret-key-change-in-production"
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 30

    RATE_LIMIT_DEFAULT: str = "100/minute"

    # Explicit allow-list — `["*"]` combined with allow_credentials=True is rejected
    # by browsers anyway (the spec forbids a wildcard origin on credentialed
    # requests) and is an unsafe default even where it's silently accepted.
    CORS_ORIGINS: list[str] = ["http://localhost:3000", "http://localhost:8000"]

    model_config = {"env_file": ".env", "case_sensitive": True}


settings = Settings()

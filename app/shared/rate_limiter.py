from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from app.shared.config import settings

# Key function: fall back to IP when no token is present
limiter = Limiter(key_func=get_remote_address, default_limits=[settings.RATE_LIMIT_DEFAULT])


def _rate_limit_exceeded_handler(request: Request, exc: RateLimitExceeded) -> JSONResponse:
    """Same {"error": {"code", "message"}} envelope as app/shared/exception_handler.py
    — slowapi's default handler uses a different shape."""
    response = JSONResponse(
        status_code=429,
        content={
            "error": {"code": "RATE_LIMIT_EXCEEDED", "message": f"Rate limit exceeded: {exc.detail}"}
        },
    )
    return request.app.state.limiter._inject_headers(response, request.state.view_rate_limit)


def register_rate_limiter(app: FastAPI) -> None:
    """Wire slowapi limiter into the FastAPI app state and exception handler."""
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)  # type: ignore[arg-type]

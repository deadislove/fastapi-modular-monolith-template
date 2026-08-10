import logging

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)


def _error_response(status_code: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(status_code=status_code, content={"error": {"code": code, "message": message}})


def register_exception_handlers(app: FastAPI) -> None:
    """Every error response — domain errors, validation errors, unhandled
    exceptions — shares one shape: {"error": {"code": ..., "message": ...}}."""

    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
        # Routers raise HTTPException(detail=some_domain_error.as_detail()); anything
        # that instead raises with a plain string detail still gets the same shape.
        if isinstance(exc.detail, dict) and "code" in exc.detail and "message" in exc.detail:
            return _error_response(exc.status_code, exc.detail["code"], exc.detail["message"])
        return _error_response(exc.status_code, "HTTP_ERROR", str(exc.detail))

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        return _error_response(422, "VALIDATION_ERROR", "Request validation failed")

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("Unhandled exception on %s %s", request.method, request.url)
        return _error_response(
            500, "INTERNAL_SERVER_ERROR", "An unexpected error occurred. Please try again later."
        )

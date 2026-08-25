"""Per-request correlation ID — every log line produced while handling a
request (router, facade, subscriber, background task) carries the same
request_id, so concurrent requests' interleaved log output can be told apart.
Always generated server-side, never trusted from an incoming header — an
unauthenticated client could otherwise inject arbitrary values into every log
line for its own request."""

import logging
import uuid
from collections.abc import Awaitable, Callable
from contextvars import ContextVar

from fastapi import FastAPI, Request, Response

REQUEST_ID_HEADER = "X-Request-ID"

_request_id: ContextVar[str] = ContextVar("request_id", default="-")


class RequestIdLogFilter(logging.Filter):
    """Attaches the current request's ID to every LogRecord that reaches the
    handler this filter is installed on — including records from loggers
    this codebase doesn't own (e.g. sqlalchemy.engine) — so one
    %(request_id)s in the log format works everywhere without touching any
    individual logger.info(...) call site."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = _request_id.get()
        return True


async def _request_id_middleware(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    request_id = str(uuid.uuid4())
    token = _request_id.set(request_id)
    try:
        response = await call_next(request)
    finally:
        _request_id.reset(token)
    response.headers[REQUEST_ID_HEADER] = request_id
    return response


def install_request_id_log_filter() -> None:
    """Attaches the logging filter to every handler already on the root
    logger. Call this immediately after configuring logging (before
    discover_modules() or anything else that might log), not from
    register_request_context() below — that one only runs once the FastAPI
    app exists, which is later than the earliest point something could log."""
    for handler in logging.getLogger().handlers:
        handler.addFilter(RequestIdLogFilter())


def register_request_context(app: FastAPI) -> None:
    """Wires the correlation-ID middleware onto the FastAPI app."""
    app.middleware("http")(_request_id_middleware)

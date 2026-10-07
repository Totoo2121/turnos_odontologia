"""Base exception model + JSON handlers (no stack traces leaked to clients)."""

from collections.abc import Callable
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse


class AppError(Exception):
    """Base application error with explicit HTTP status."""

    def __init__(self, message: str, status_code: int = 500) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code


async def _app_error_handler(_request: Request, exc: AppError) -> JSONResponse:
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.message})


async def _unhandled_handler(_request: Request, _exc: Exception) -> JSONResponse:
    return JSONResponse(status_code=500, content={"detail": "internal error"})


def register_exception_handlers(app: FastAPI) -> None:
    """Register base handlers on the app (idempotent for tests)."""
    handler: Callable[..., Any] = _app_error_handler  # type: ignore[assignment]
    unhandled: Callable[..., Any] = _unhandled_handler  # type: ignore[assignment]
    app.exception_handler(AppError)(handler)
    app.exception_handler(Exception)(unhandled)

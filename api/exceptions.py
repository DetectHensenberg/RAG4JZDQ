"""Global exception handlers for FastAPI.

Registers structured JSON error responses for common exception types,
preventing stack traces from leaking to clients while still logging
full details server-side.
"""

from __future__ import annotations

import logging

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Custom exception hierarchy
# ---------------------------------------------------------------------------
class AppError(Exception):
    """Base exception for all application-level errors."""

    status_code: int = 500
    message: str = "服务器内部错误"

    def __init__(self, message: str | None = None, detail: str = "") -> None:
        self.message = message or self.__class__.message
        self.detail = detail
        super().__init__(self.message)


class ResourceNotFoundError(AppError):
    """Raised when a requested resource does not exist."""

    status_code = 404
    message = "资源未找到"


class LLMTimeoutError(AppError):
    """Raised when a language model call exceeds the configured timeout."""

    status_code = 504
    message = "大模型调用超时，请稍后重试"


class RateLimitExceededError(AppError):
    """Raised when a client exceeds the configured rate limit."""

    status_code = 429
    message = "请求过于频繁，请稍后重试"


class StorageError(AppError):
    """Raised when a database or vector store operation fails."""

    status_code = 500
    message = "数据存储操作失败"


class ValidationError(AppError):
    """Raised when request validation fails beyond Pydantic checks."""

    status_code = 422
    message = "参数校验失败"


# ---------------------------------------------------------------------------
# Handler registration
# ---------------------------------------------------------------------------
def register_exception_handlers(app: FastAPI) -> None:
    """Attach global exception handlers to the FastAPI app.

    Args:
        app: The FastAPI application instance.
    """

    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={"ok": False, "message": exc.detail},
        )

    @app.exception_handler(AppError)
    async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
        logger.warning(
            "%s on %s: %s (detail: %s)",
            type(exc).__name__,
            request.url.path,
            exc.message,
            exc.detail,
        )
        return JSONResponse(
            status_code=exc.status_code,
            content={"ok": False, "message": exc.message},
        )

    @app.exception_handler(ValueError)
    async def value_error_handler(request: Request, exc: ValueError) -> JSONResponse:
        logger.warning("ValueError on %s: %s", request.url.path, exc)
        return JSONResponse(
            status_code=400,
            content={"ok": False, "message": f"参数错误: {exc}"},
        )

    @app.exception_handler(FileNotFoundError)
    async def file_not_found_handler(request: Request, exc: FileNotFoundError) -> JSONResponse:
        logger.warning("FileNotFoundError on %s: %s", request.url.path, exc)
        return JSONResponse(
            status_code=404,
            content={"ok": False, "message": f"文件未找到: {exc}"},
        )

    @app.exception_handler(PermissionError)
    async def permission_error_handler(request: Request, exc: PermissionError) -> JSONResponse:
        logger.warning("PermissionError on %s: %s", request.url.path, exc)
        return JSONResponse(
            status_code=403,
            content={"ok": False, "message": "权限不足"},
        )

    @app.exception_handler(Exception)
    async def general_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("Unhandled exception on %s %s", request.method, request.url.path)
        return JSONResponse(
            status_code=500,
            content={"ok": False, "message": "服务器内部错误，请查看日志"},
        )

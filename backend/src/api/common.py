"""What the routers share: authentication and role checks, plus one uniform JSON error shape."""

from __future__ import annotations

from fastapi import Depends, FastAPI, Header
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException

from src.services import auth_service
from src.services.auth_service import AuthenticatedUser
from src.services.shared import ServiceError


def current_user(authorization: str | None = Header(default=None)) -> AuthenticatedUser:
    return auth_service.user_from_authorization(authorization)


def require_admin(user: AuthenticatedUser = Depends(current_user)) -> AuthenticatedUser:
    if not user.is_admin:
        raise ServiceError(403, "admin_required", "Only administrators can do this")
    return user


def require_manager(user: AuthenticatedUser = Depends(current_user)) -> AuthenticatedUser:
    if not user.is_manager:
        raise ServiceError(403, "manager_required", "Only managers can do this")
    return user


def require_marketer(user: AuthenticatedUser = Depends(current_user)) -> AuthenticatedUser:
    if not user.is_marketer:
        raise ServiceError(403, "marketer_required", "Only marketers can do this")
    return user


def require_idempotency_key(idempotency_key: str | None = Header(default=None, alias="Idempotency-Key")) -> str:
    """Required on costly operations: one pipeline run spends several LLM calls."""
    if not idempotency_key:
        raise ServiceError(
            400,
            "idempotency_key_required",
            "This operation requires an `Idempotency-Key` header. Reuse the same key when the user retries.",
        )
    return idempotency_key


def _error_payload(code: str, message: str, **details) -> dict:
    return {"error": {"code": code, "message": message, "details": details}}


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(ServiceError)
    async def _service_error(_, error: ServiceError):
        return JSONResponse(
            status_code=error.status_code,
            content=_error_payload(error.code, error.message, **error.details),
            headers=error.headers,
        )

    @app.exception_handler(HTTPException)
    async def _http_error(_, error: HTTPException):
        return JSONResponse(
            status_code=error.status_code,
            content=_error_payload(f"http_{error.status_code}", str(error.detail)),
            headers=error.headers,
        )

    @app.exception_handler(RequestValidationError)
    async def _validation_error(_, error: RequestValidationError):
        # Only location and message: the raw input may contain a password.
        fields = [{"field": ".".join(str(part) for part in item["loc"]), "reason": item["msg"]} for item in error.errors()]
        return JSONResponse(
            status_code=422,
            content=_error_payload("invalid_request", "The submitted data is not valid", errors=fields),
        )

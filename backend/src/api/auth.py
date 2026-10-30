from __future__ import annotations

from fastapi import APIRouter, Depends, Header, Request, status
from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from src.api.common import current_user
from src.services import auth_service
from src.services.auth_service import AuthenticatedUser
from src.utils import nfc

router = APIRouter(prefix="/auth", tags=["auth"])

MIN_PASSWORD_LENGTH = 8
# Supabase hashes with bcrypt, which only reads the first 72 bytes.
MAX_PASSWORD_LENGTH = 72
MAX_NAME_LENGTH = 200


def _clean_full_name(value: object) -> object:
    if not isinstance(value, str):
        return value
    normalized = nfc(value.strip())
    if not normalized:
        raise ValueError("full_name must not be empty")
    if len(normalized) > MAX_NAME_LENGTH:
        raise ValueError(f"full_name must not exceed {MAX_NAME_LENGTH} characters")
    return normalized


class RegisterRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: EmailStr
    password: str = Field(min_length=MIN_PASSWORD_LENGTH, max_length=MAX_PASSWORD_LENGTH)
    full_name: str

    _validate_full_name = field_validator("full_name", mode="before")(_clean_full_name)


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: EmailStr
    password: str = Field(min_length=1, max_length=MAX_PASSWORD_LENGTH)


class RefreshRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    refresh_token: str = Field(min_length=1)


class ProfileUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    full_name: str

    _validate_full_name = field_validator("full_name", mode="before")(_clean_full_name)


@router.post("/register", status_code=status.HTTP_201_CREATED)
def register(payload: RegisterRequest, request: Request):
    auth_service.enforce_rate_limit(auth_service.REGISTRATION_RATE_LIMIT, request)
    return auth_service.register(payload.email, payload.password, payload.full_name)


@router.post("/login")
def login(payload: LoginRequest, request: Request):
    auth_service.enforce_rate_limit(auth_service.LOGIN_RATE_LIMIT, request)
    return auth_service.login(payload.email, payload.password)


@router.post("/refresh")
def refresh(payload: RefreshRequest, request: Request):
    auth_service.enforce_rate_limit(auth_service.LOGIN_RATE_LIMIT, request)
    return auth_service.refresh(payload.refresh_token)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    _user: AuthenticatedUser = Depends(current_user),
    authorization: str = Header(),
) -> None:
    auth_service.logout(authorization.split(" ", 1)[-1].strip())


@router.get("/me")
def get_me(user: AuthenticatedUser = Depends(current_user)):
    return auth_service.get_profile(user.id)


@router.patch("/me")
def update_me(payload: ProfileUpdate, user: AuthenticatedUser = Depends(current_user)):
    return auth_service.update_profile(user.id, full_name=payload.full_name)

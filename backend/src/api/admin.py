from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field

from src.api.common import require_admin
from src.services import admin_service
from src.services.auth_service import AuthenticatedUser
from src.services.shared import ServiceError

router = APIRouter(prefix="/admin", tags=["admin"], dependencies=[Depends(require_admin)])

PlatformValue = Literal["facebook", "instagram", "tiktok", "zalo", "website", "email"]
StatusValue = Literal["active", "inactive"]
ContentChannelValue = Literal["facebook", "direct_message", "instagram", "tiktok"]


class RoleUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: Literal["manager", "marketer"]


class ChannelCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=120)
    platform: PlatformValue
    account_ref: str = Field(min_length=1, max_length=200)
    content_channel: ContentChannelValue | None = None
    status: StatusValue = "active"
    is_connected: bool = False
    note: str = Field(default="", max_length=500)


class ChannelUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=120)
    platform: PlatformValue | None = None
    account_ref: str | None = Field(default=None, min_length=1, max_length=200)
    content_channel: ContentChannelValue | None = None
    status: StatusValue | None = None
    is_connected: bool | None = None
    note: str | None = Field(default=None, max_length=500)


@router.get("/users")
def list_users():
    return {"items": admin_service.list_users()}


@router.patch("/users/{user_id}/role")
def update_role(user_id: str, payload: RoleUpdate, actor: AuthenticatedUser = Depends(require_admin)):
    return admin_service.change_role(actor, user_id, payload.role)


@router.get("/campaigns")
def list_campaigns():
    return {"items": admin_service.list_campaigns()}


@router.get("/channels")
def list_channels():
    return {"items": admin_service.list_channels()}


@router.get("/channels/options")
def channel_options():
    return admin_service.channel_options()


@router.post("/channels", status_code=201)
def create_channel(payload: ChannelCreate, actor: AuthenticatedUser = Depends(require_admin)):
    return admin_service.create_channel(actor_id=actor.id, **payload.model_dump())


@router.patch("/channels/{channel_id}")
def update_channel(channel_id: int, payload: ChannelUpdate):
    # exclude_unset keeps "not sent" apart from "sent as null".
    changes = payload.model_dump(exclude_unset=True)
    if not changes:
        raise ServiceError(422, "no_changes", "The payload has no fields to update")
    return admin_service.update_channel(channel_id, **changes)


@router.delete("/channels/{channel_id}")
def delete_channel(channel_id: int):
    return admin_service.delete_channel(channel_id)

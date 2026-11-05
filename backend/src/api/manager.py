from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from src.api.common import require_idempotency_key, require_manager
from src.services import manager_service
from src.services.auth_service import AuthenticatedUser

router = APIRouter(prefix="/manager", tags=["manager"], dependencies=[Depends(require_manager)])


class ReviewDecision(BaseModel):
    decision: Literal["approve", "reject"]
    reason: str = Field(default="", max_length=1000)


@router.get("/campaigns")
def list_campaigns():
    return manager_service.list_campaigns()


@router.get("/campaigns/{campaign_id}")
def get_campaign(campaign_id: int):
    return manager_service.get_campaign(campaign_id)


@router.post("/campaigns/{campaign_id}/review")
def review_campaign(
    campaign_id: int,
    payload: ReviewDecision,
    user: AuthenticatedUser = Depends(require_manager),
    key: str = Depends(require_idempotency_key),
):
    return manager_service.review_campaign(campaign_id, user, payload.decision, payload.reason, key)


@router.post("/campaigns/{campaign_id}/publish")
def publish_campaign(
    campaign_id: int,
    user: AuthenticatedUser = Depends(require_manager),
    key: str = Depends(require_idempotency_key),
):
    return manager_service.publish_campaign(campaign_id, user, key)


@router.get("/analytics")
def analytics_overview(campaign_id: int | None = None):
    return manager_service.analytics_overview(campaign_id)


@router.get("/audit-log")
def audit_history():
    return manager_service.audit_history()


@router.get("/schedules")
def list_schedules(date_from: str = Query(...), date_to: str = Query(...), channel: str | None = None):
    return manager_service.list_schedules(date_from, date_to, channel)


@router.get("/channels")
def list_channels():
    return {"items": manager_service.list_channels()}

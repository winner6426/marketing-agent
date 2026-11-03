from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, BackgroundTasks, Depends, Query
from pydantic import BaseModel, Field

from src.api.common import require_idempotency_key, require_marketer
from src.services import marketer_service
from src.services.auth_service import AuthenticatedUser

router = APIRouter(prefix="/marketer", tags=["marketer"], dependencies=[Depends(require_marketer)])


def owned_campaign(campaign_id: int, user: AuthenticatedUser = Depends(require_marketer)) -> AuthenticatedUser:
    """A dependency, so ownership is checked before the request body is validated."""
    marketer_service.ensure_owned_campaign(campaign_id, user)
    return user


def owned_draft(draft_id: int, user: AuthenticatedUser = Depends(require_marketer)) -> AuthenticatedUser:
    marketer_service.ensure_owned_campaign(draft_id, user)
    return user


class CreateCampaign(BaseModel):
    name: str = Field(default="", max_length=200)
    brief: dict


class CreateChatDraft(CreateCampaign):
    chat_session_id: str | None = None


class CampaignAnswer(BaseModel):
    brief_additions: dict


class SubmitChatDraft(BaseModel):
    selected_content_item_ids: list[int] = Field(default_factory=list)


class UpdateContentDraft(BaseModel):
    draft: dict
    scheduled_date: str
    scheduled_time: str


class AiEditRequest(BaseModel):
    instruction: str = Field(..., min_length=1, max_length=2000)
    target_text: str = Field(default="", max_length=5000)


class ManualSendRequest(BaseModel):
    content_item_id: int
    channel: Literal["zalo", "sms"]
    # Sent by the client on purpose: people can edit text between copying and sending it.
    sent_content: str = Field(min_length=1, max_length=20000)
    recipients: str = Field(default="", max_length=300)
    recipient_count: int = Field(default=0, ge=0, le=10000)


class CreateChatSession(BaseModel):
    title: str = Field(default=marketer_service.DEFAULT_CHAT_TITLE, min_length=1, max_length=200)


class UpdateChatSession(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)


class CreateChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(..., min_length=1)
    metadata: dict = Field(default_factory=dict)


class UpdateChatMessage(BaseModel):
    content: str = Field(..., min_length=1)
    metadata: dict = Field(default_factory=dict)


# --- Read models ----------------------------------------------------------------


@router.get("/products")
def list_products():
    return marketer_service.list_products()


@router.get("/channels")
def list_channels():
    return {"items": marketer_service.list_channels()}


@router.get("/schedules")
def list_schedules(
    date_from: str = Query(...),
    date_to: str = Query(...),
    channel: str | None = None,
    user: AuthenticatedUser = Depends(require_marketer),
):
    return marketer_service.list_schedules(user, date_from, date_to, channel)


@router.get("/audit-log")
def my_audit_log(user: AuthenticatedUser = Depends(require_marketer)):
    return marketer_service.my_audit_log(user)


# --- Campaigns ------------------------------------------------------------------


@router.post("/campaigns", status_code=201)
def create_campaign(payload: CreateCampaign, user: AuthenticatedUser = Depends(require_marketer)):
    return marketer_service.create_campaign(user, payload.brief, payload.name)


@router.get("/campaigns")
def list_campaigns(user: AuthenticatedUser = Depends(require_marketer)):
    return marketer_service.list_campaigns(user)


@router.get("/campaigns/{campaign_id}", dependencies=[Depends(owned_campaign)])
def get_campaign(campaign_id: int):
    return marketer_service.get_campaign(campaign_id)


@router.delete("/campaigns/{campaign_id}")
def delete_campaign(
    campaign_id: int,
    confirm_approved: bool = False,
    user: AuthenticatedUser = Depends(owned_campaign),
):
    return marketer_service.delete_campaign(campaign_id, user, confirm_approved=confirm_approved)


@router.post("/campaigns/{campaign_id}/run", status_code=202)
def run_campaign(
    campaign_id: int,
    background_tasks: BackgroundTasks,
    user: AuthenticatedUser = Depends(owned_campaign),
    key: str = Depends(require_idempotency_key),
):
    """An incomplete brief is a valid state, not an error: the questions appear in the campaign detail."""
    response = marketer_service.start_run(campaign_id, user)
    background_tasks.add_task(marketer_service.run_in_background, campaign_id, key)
    return response


@router.post("/campaigns/{campaign_id}/answer", status_code=202)
def answer_campaign(
    campaign_id: int,
    payload: CampaignAnswer,
    background_tasks: BackgroundTasks,
    user: AuthenticatedUser = Depends(owned_campaign),
    key: str = Depends(require_idempotency_key),
):
    response = marketer_service.start_answer(campaign_id, user)
    background_tasks.add_task(marketer_service.answer_in_background, campaign_id, key, payload.brief_additions)
    return response


@router.patch("/campaigns/{campaign_id}/content/{content_item_id}")
def update_content(
    campaign_id: int,
    content_item_id: int,
    payload: UpdateContentDraft,
    user: AuthenticatedUser = Depends(owned_campaign),
):
    return marketer_service.update_content(
        campaign_id,
        content_item_id,
        user,
        draft=payload.draft,
        scheduled_date=payload.scheduled_date,
        scheduled_time=payload.scheduled_time,
    )


@router.post("/campaigns/{campaign_id}/content/{content_item_id}/ai-edit")
def ai_edit_content(
    campaign_id: int,
    content_item_id: int,
    payload: AiEditRequest,
    user: AuthenticatedUser = Depends(owned_campaign),
):
    return marketer_service.ai_edit_content(
        campaign_id, content_item_id, user, instruction=payload.instruction, target_text=payload.target_text
    )


@router.post("/campaigns/{campaign_id}/manual-sends", status_code=201)
def record_manual_send(
    campaign_id: int,
    payload: ManualSendRequest,
    user: AuthenticatedUser = Depends(owned_campaign),
):
    return marketer_service.record_manual_send(campaign_id, user, **payload.model_dump())


@router.get("/campaigns/{campaign_id}/analytics", dependencies=[Depends(owned_campaign)])
def campaign_analytics(campaign_id: int):
    return marketer_service.campaign_analytics(campaign_id)


# --- Chat drafts ----------------------------------------------------------------


@router.post("/chat-drafts", status_code=202)
def create_chat_draft(
    payload: CreateChatDraft,
    background_tasks: BackgroundTasks,
    user: AuthenticatedUser = Depends(require_marketer),
    key: str = Depends(require_idempotency_key),
):
    response = marketer_service.start_chat_draft(
        user, payload.brief, key, name=payload.name, chat_session_id=payload.chat_session_id
    )
    background_tasks.add_task(marketer_service.run_chat_draft_in_background, response["draft_id"], key)
    return response


@router.post("/chat-drafts/{draft_id}/answer", status_code=202, dependencies=[Depends(owned_draft)])
def answer_chat_draft(
    draft_id: int,
    payload: CampaignAnswer,
    background_tasks: BackgroundTasks,
    key: str = Depends(require_idempotency_key),
):
    response = marketer_service.start_chat_draft_answer(draft_id)
    background_tasks.add_task(marketer_service.answer_chat_draft_in_background, draft_id, key, payload.brief_additions)
    return response


@router.post("/chat-drafts/{draft_id}/submit", status_code=201)
def submit_chat_draft(
    draft_id: int,
    payload: SubmitChatDraft,
    user: AuthenticatedUser = Depends(owned_draft),
    key: str = Depends(require_idempotency_key),
):
    return marketer_service.submit_chat_draft(draft_id, user, payload.selected_content_item_ids, key)


# --- Chat sessions --------------------------------------------------------------


@router.post("/chat-sessions", status_code=201)
def create_chat_session(payload: CreateChatSession, user: AuthenticatedUser = Depends(require_marketer)):
    return marketer_service.create_chat_session(user, payload.title)


@router.get("/chat-sessions")
def list_chat_sessions(user: AuthenticatedUser = Depends(require_marketer)):
    return marketer_service.list_chat_sessions(user)


@router.get("/chat-sessions/{chat_session_id}")
def get_chat_session(chat_session_id: str, user: AuthenticatedUser = Depends(require_marketer)):
    return marketer_service.get_chat_session(user, chat_session_id)


@router.patch("/chat-sessions/{chat_session_id}")
def update_chat_session(
    chat_session_id: str,
    payload: UpdateChatSession,
    user: AuthenticatedUser = Depends(require_marketer),
):
    return marketer_service.update_chat_session(user, chat_session_id, payload.title)


@router.delete("/chat-sessions/{chat_session_id}")
def delete_chat_session(chat_session_id: str, user: AuthenticatedUser = Depends(require_marketer)):
    return marketer_service.delete_chat_session(user, chat_session_id)


@router.post("/chat-sessions/{chat_session_id}/messages", status_code=201)
def create_chat_message(
    chat_session_id: str,
    payload: CreateChatMessage,
    user: AuthenticatedUser = Depends(require_marketer),
):
    return marketer_service.create_chat_message(user, chat_session_id, payload.role, payload.content, payload.metadata)


@router.patch("/chat-sessions/{chat_session_id}/messages/{message_id}")
def update_chat_message(
    chat_session_id: str,
    message_id: int,
    payload: UpdateChatMessage,
    user: AuthenticatedUser = Depends(require_marketer),
):
    return marketer_service.update_chat_message(user, chat_session_id, message_id, payload.content, payload.metadata)

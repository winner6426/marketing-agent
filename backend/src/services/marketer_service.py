"""Marketer operations: campaigns, chat sessions and drafts, content editing and manual sends.

Every function acts only on the caller's own data. Foreign ids return 404, so ids cannot be probed.
"""

from __future__ import annotations

import logging
from datetime import date

from src import utils
from src.agents import campaign_runner
from src.agents.campaign_runner import (
    ContentNotReadyForApprovalError,
    InvalidContentSelectionError,
    content_revision,
    get_runner,
)
from src.agents.nodes import writer
from src.models import catalog, db
from src.models.campaign_state import campaign_display_name, render_outbound_text
from src.services import shared
from src.services.auth_service import AuthenticatedUser
from src.services.shared import ServiceError, campaign_detail, campaign_list_item, not_found
from src.utils import current_timestamp

LOGGER = logging.getLogger(__name__)

# Regenerating these would overwrite content that a manager has already seen or signed.
NON_RUNNABLE_STATUSES = {"waiting_approval", "approval", "scheduled", "published"}
DELETE_CONFIRMATION_STATUSES = {"approval", "published"}
FAILED_STATUSES = {"failed", "generation_failed"}
DEFAULT_CHAT_TITLE = "New conversation"
MAX_ERROR_LENGTH = 500


# --- Access ---------------------------------------------------------------------


def ensure_owned_campaign(campaign_id: int, user: AuthenticatedUser) -> None:
    with db.get_session() as session:
        campaign = session.get(db.Campaign, campaign_id)
        if campaign is None or campaign.created_by_id != user.id:
            raise not_found(campaign_id)


def _owned_chat_session(session, chat_session_id: str, user: AuthenticatedUser) -> db.ChatSession:
    chat = session.get(db.ChatSession, chat_session_id)
    if chat is None or chat.marketer_id != user.id:
        raise ServiceError(404, "chat_session_not_found", "Chat session not found")
    return chat


def _set_campaign_status(campaign_id: int, status: str) -> None:
    with db.get_session() as session:
        campaign = session.get(db.Campaign, campaign_id)
        if campaign is not None:
            campaign.status = status
            session.commit()


def _running_payload(campaign_id: int, *, current_node: str = "brief_analyst") -> dict:
    return {
        "campaign_id": campaign_id,
        "status": "running",
        "current_node": current_node,
        "pending_human_action": None,
        "plan": None,
        "contents": [],
    }


def _endpoint(operation: str, scope: int | str) -> str:
    # Scoped so a reused Idempotency-Key can never return another campaign's or user's response.
    return f"marketer.{operation}:{scope}"


# --- Catalog and read models ----------------------------------------------------


def list_products() -> dict:
    with db.get_session() as session:
        return {"items": catalog.brief_catalog(session)}


def list_campaigns(user: AuthenticatedUser) -> list[dict]:
    with db.get_session() as session:
        rows = (
            session.query(db.Campaign)
            .filter(db.Campaign.created_by_id == user.id)
            .order_by(db.Campaign.updated_at.desc(), db.Campaign.id.desc())
            .all()
        )
        return [campaign_list_item(campaign) for campaign in rows]


def get_campaign(campaign_id: int) -> dict:
    return campaign_detail(campaign_id)


def campaign_analytics(campaign_id: int) -> dict:
    with db.get_session() as session:
        return {
            "campaign": shared.campaign_overview(session, campaign_id),
            "content": shared.variant_performance(session, campaign_id),
        }


def my_audit_log(user: AuthenticatedUser) -> dict:
    with db.get_session() as session:
        return {"user_id": user.id, "role": user.role, "entries": shared.user_history(session, user.id)}


def list_schedules(user: AuthenticatedUser, date_from: str, date_to: str, channel: str | None = None) -> dict:
    return shared.list_schedules(date_from, date_to, channel, owner_id=user.id)


def list_channels() -> list[dict]:
    return shared.list_channels(include_inactive=False)


# --- Campaign lifecycle ---------------------------------------------------------


def create_campaign(user: AuthenticatedUser, brief: dict, name: str = "") -> dict:
    campaign_id = get_runner().create(brief, created_by=user.email, created_by_id=user.id, name=name)
    shared.record_audit(user, "create_campaign", f"campaign:{campaign_id}")
    return {"campaign_id": campaign_id, "status": "draft"}


def delete_campaign(campaign_id: int, user: AuthenticatedUser, *, confirm_approved: bool) -> dict:
    with db.get_session() as session:
        campaign = session.get(db.Campaign, campaign_id)
        if campaign is None:
            raise not_found(campaign_id)
        requires_confirmation = campaign.status in DELETE_CONFIRMATION_STATUSES
    if requires_confirmation and not confirm_approved:
        raise ServiceError(
            409,
            "delete_confirmation_required",
            "This campaign was approved or published; confirm explicitly before deleting it",
        )
    result = get_runner().delete(campaign_id)
    shared.record_audit(
        user, "delete_campaign", f"campaign:{campaign_id}", f"Deleted from status {result['previous_status']}"
    )
    return result


def _mark_background_failure(campaign_id: int, error: Exception) -> None:
    """Failures must reach the database as well as the log, or pollers would wait on `running` forever."""
    content = str(error).strip() or "error without a message"
    message = f"{type(error).__name__}: {content}"[:MAX_ERROR_LENGTH]
    LOGGER.exception(
        "background_task_failed campaign_id=%s error_type=%s", campaign_id, type(error).__name__, exc_info=error
    )
    try:
        get_runner().mark_failed(campaign_id, message)
    except Exception:  # noqa: BLE001 - the checkpointer may be what broke; never leave the row stuck on `running`
        LOGGER.exception("Could not record the failure in the checkpoint for campaign_id=%s", campaign_id)
        _set_campaign_status(campaign_id, "failed")


def _run_pipeline_step(campaign_id: int, key: str, endpoint: str, operation, *, keep_draft: bool) -> None:
    """Shared body of every background task. A replayed key must still restore the status set before it started."""
    try:
        result, _ = shared.get_or_execute(db.get_engine(), key, endpoint, campaign_id, operation)
    except shared.AlreadyRunningError:
        return  # the first request is still working and will settle the status itself
    except Exception as error:  # noqa: BLE001
        _mark_background_failure(campaign_id, error)
        return

    status = result.get("status") if isinstance(result, dict) else None
    if keep_draft:
        _set_campaign_status(campaign_id, status if status in FAILED_STATUSES else "draft")
    elif status:
        _set_campaign_status(campaign_id, status)


def start_run(campaign_id: int, user: AuthenticatedUser) -> dict:
    with db.get_session() as session:
        campaign = session.get(db.Campaign, campaign_id)
        if campaign is None:
            raise not_found(campaign_id)
        status = campaign.status
    if status in NON_RUNNABLE_STATUSES:
        raise ServiceError(409, "campaign_not_runnable", f"A campaign in status `{status}` cannot be run again")
    # Set before responding, so a poll right after the response never sees `draft` and starts another run.
    _set_campaign_status(campaign_id, "running")
    shared.record_audit(user, "run_pipeline", f"campaign:{campaign_id}")
    return _running_payload(campaign_id)


def run_in_background(campaign_id: int, key: str) -> None:
    _run_pipeline_step(
        campaign_id, key, _endpoint("run", campaign_id), lambda: get_runner().run(campaign_id), keep_draft=False
    )


def _ensure_clarification_pending(campaign_id: int) -> None:
    # Resuming any other interrupt would feed this answer to the approval step and reject the campaign.
    if not get_runner().is_waiting_for_clarification(campaign_id):
        raise ServiceError(409, "no_clarification_pending", "This campaign is not waiting for an answer")


def start_answer(campaign_id: int, user: AuthenticatedUser) -> dict:
    _ensure_clarification_pending(campaign_id)
    _set_campaign_status(campaign_id, "running")
    shared.record_audit(user, "answer_brief", f"campaign:{campaign_id}", "Added brief details")
    return _running_payload(campaign_id, current_node="clarification")


def answer_in_background(campaign_id: int, key: str, brief_additions: dict) -> None:
    _run_pipeline_step(
        campaign_id,
        key,
        _endpoint("answer", campaign_id),
        lambda: get_runner().answer(campaign_id, brief_additions),
        keep_draft=False,
    )


# --- Chat drafts: campaigns that stay `draft` until the marketer submits them ---


def start_chat_draft(
    user: AuthenticatedUser,
    brief: dict,
    key: str,
    *,
    name: str = "",
    chat_session_id: str | None = None,
) -> dict:
    if chat_session_id:
        with db.get_session() as session:
            _owned_chat_session(session, chat_session_id, user)

    def operation() -> dict:
        campaign_id = get_runner().create(brief, created_by=user.email, created_by_id=user.id, name=name)
        shared.record_audit(user, "create_campaign", f"campaign:{campaign_id}", "Chat draft")
        return {"draft_id": campaign_id}

    try:
        started, _ = shared.get_or_execute(
            db.get_engine(), key, _endpoint("chat_draft.create", user.id), None, operation
        )
    except shared.AlreadyRunningError as error:
        raise ServiceError(409, "already_running", str(error)) from error

    campaign_id = int(started["draft_id"])
    if chat_session_id:
        with db.get_session() as session:
            session.get(db.Campaign, campaign_id).chat_session_id = chat_session_id
            session.commit()
    _set_campaign_status(campaign_id, "running")
    return _running_payload(campaign_id) | {"draft_id": campaign_id, "campaign_id": None}


def run_chat_draft_in_background(campaign_id: int, key: str) -> None:
    _run_pipeline_step(
        campaign_id,
        key,
        _endpoint("chat_draft.run", campaign_id),
        lambda: get_runner().run(campaign_id, keep_campaign_draft=True),
        keep_draft=True,
    )


def start_chat_draft_answer(campaign_id: int) -> dict:
    _ensure_clarification_pending(campaign_id)
    _set_campaign_status(campaign_id, "running")
    return _running_payload(campaign_id, current_node="clarification") | {"draft_id": campaign_id, "campaign_id": None}


def answer_chat_draft_in_background(campaign_id: int, key: str, brief_additions: dict) -> None:
    _run_pipeline_step(
        campaign_id,
        key,
        _endpoint("chat_draft.answer", campaign_id),
        lambda: get_runner().answer(campaign_id, brief_additions, keep_campaign_draft=True),
        keep_draft=True,
    )


def submit_chat_draft(campaign_id: int, user: AuthenticatedUser, selected_content_item_ids: list[int], key: str) -> dict:
    try:
        result, is_first_run = shared.get_or_execute(
            db.get_engine(),
            key,
            _endpoint("chat_draft.submit", campaign_id),
            campaign_id,
            lambda: get_runner().promote_chat_draft(campaign_id, selected_content_item_ids),
        )
    except shared.AlreadyRunningError as error:
        raise ServiceError(409, "already_running", str(error)) from error
    except InvalidContentSelectionError as error:
        raise ServiceError(409, "invalid_selection", str(error)) from error
    except ContentNotReadyForApprovalError as error:
        raise ServiceError(409, "content_not_ready", str(error)) from error
    except KeyError as error:
        raise not_found(campaign_id) from error
    except ValueError as error:
        raise ServiceError(409, "draft_not_ready", str(error)) from error

    if is_first_run:
        shared.record_audit(
            user,
            "submit_for_approval",
            f"campaign:{campaign_id}",
            "Submitted selected variants for manager approval",
        )
    return result


# --- Content editing ---------------------------------------------------------------


# Downgrading the status and writing the version must happen together, or edited text keeps its approval.
MANUAL_SCHEDULE_REASON = "Schedule edited by the marketer"


class CampaignEditForbiddenError(PermissionError):
    pass


class CampaignNotEditableError(RuntimeError):
    def __init__(self, status: str):
        self.status = status
        super().__init__(f"A campaign in status `{status}` cannot be edited")


def _save_schedule(session, campaign_id: int, content_item_id: int, scheduled_at: str | None) -> tuple[bool, db.ScheduleSlot | None]:
    slot = session.query(db.ScheduleSlot).filter_by(content_item_id=content_item_id).one_or_none()
    if scheduled_at is None or (slot is not None and slot.scheduled_at == scheduled_at):
        return False, slot

    if slot is None:
        slot = db.ScheduleSlot(
            campaign_id=campaign_id,
            content_item_id=content_item_id,
            scheduled_at=scheduled_at,
            status="proposed",
            reason=MANUAL_SCHEDULE_REASON,
        )
        session.add(slot)
    else:
        slot.scheduled_at = scheduled_at
        slot.status = "proposed"
        slot.reason = MANUAL_SCHEDULE_REASON
        slot.approved_by = ""
        slot.approved_by_id = None
        slot.approved_at = None
    return True, slot


def manual_edit_draft(
    engine,
    *,
    campaign_id: int,
    content_item_id: int,
    new_draft: dict,
    edited_by: str,
    edited_by_id: str,
    scheduled_at: str | None = None,
) -> dict:
    """Save a draft and its schedule in one transaction. Changed text voids old validations and citations."""
    draft = utils.normalize_draft_nfc(dict(new_draft or {}))
    with db.session_for(engine) as session:
        campaign = session.get(db.Campaign, campaign_id)
        if campaign is None:
            raise ValueError(f"No campaign {campaign_id}")
        if campaign.created_by_id != edited_by_id:
            raise CampaignEditForbiddenError(f"Campaign {campaign_id} belongs to someone else")
        if campaign.status != "draft":
            raise CampaignNotEditableError(campaign.status)

        item = session.query(db.ContentItem).filter_by(id=content_item_id, campaign_id=campaign_id).one_or_none()
        if item is None:
            raise ValueError(f"No content item id={content_item_id} in campaign {campaign_id}")

        # Channel and variant identify the row; a crafted payload must not change them.
        draft["channel"] = item.channel
        draft["variant"] = item.variant
        rendered = render_outbound_text(draft).strip()
        if not rendered:
            raise ValueError("The edited content must not be empty")

        old_meta = dict(item.meta or {})
        content_changed = rendered != item.body or draft != old_meta.get("draft")

        if content_changed:
            version = session.query(db.ContentVersion).filter_by(content_item_id=content_item_id).count() + 1
            session.add(
                db.ContentVersion(
                    content_item_id=content_item_id,
                    version=version,
                    body=item.body,
                    created_by=edited_by,
                    created_by_id=edited_by_id or None,
                    created_at=current_timestamp(),
                )
            )
            item.body = rendered
            item.meta = {
                **old_meta,
                "draft": draft,
                "angle": draft.get("angle"),
                "hashtags": draft.get("hashtags", []),
                "validations": {},
                "quality_review": None,
                "quality_review_status": "pending",
                "content_revision": content_revision(draft),
                "validated_revision": None,
                "quality_review_revision": None,
                "selected_for_approval": False,
                "writer_error": None,
            }
            item.status = "draft"
            session.query(db.ContentCitation).filter_by(content_item_id=content_item_id).delete()

        schedule_changed, slot = _save_schedule(session, campaign_id, content_item_id, scheduled_at)

        session.commit()
        return {
            "changed": content_changed or schedule_changed,
            "content_changed": content_changed,
            "schedule_changed": schedule_changed,
            "status": item.status,
            "draft": dict((item.meta or {}).get("draft") or draft),
            "scheduled_at": slot.scheduled_at if slot is not None else None,
        }


def _edit_with_ai(
    campaign_id: int,
    content_item_id: int,
    user: AuthenticatedUser,
    instruction: str,
    target_text: str,
) -> dict:
    with db.get_session() as session:
        campaign = session.get(db.Campaign, campaign_id)
        item = session.get(db.ContentItem, content_item_id)
        if not campaign or not item or item.campaign_id != campaign_id:
            raise ValueError(f"No content item {content_item_id} in campaign {campaign_id}")
        if campaign.status != "draft":
            raise CampaignNotEditableError(campaign.status)
        channel = item.channel
        draft = dict((item.meta or {}).get("draft") or {})
        model_id = str((campaign.brief or {}).get("model_id") or "").strip()

    return manual_edit_draft(
        db.get_engine(),
        campaign_id=campaign_id,
        content_item_id=content_item_id,
        new_draft=writer.rewrite_draft(draft, channel, model_id, instruction, target_text),
        edited_by=user.email,
        edited_by_id=user.id,
    )


def _not_editable(status: str) -> ServiceError:
    return ServiceError(409, "campaign_not_editable", f"A campaign in status `{status}` cannot be edited")


def _revalidation_after_edit(campaign_id: int, content_item_id: int, content_changed: bool) -> dict | None:
    if not content_changed:
        with db.get_session() as session:
            item = session.get(db.ContentItem, content_item_id)
            metadata = dict(item.meta or {}) if item is not None else None
        if metadata is None or not campaign_runner.content_needs_revalidation(metadata):
            return None
    return campaign_runner.revalidate_content(db.get_engine(), campaign_id, content_item_id)


def _edit_response(content_item_id: int, result: dict, revalidation: dict | None) -> dict:
    if revalidation is None:
        status = result["status"]
    else:
        status = "passed" if revalidation["passed"] else "needs_human"
    return {
        "content": {"content_item_id": content_item_id, "status": status, "draft": result["draft"]},
        "changed": result["changed"],
        "revalidation": revalidation,
    }


def _parse_schedule(campaign_id: int, scheduled_date: str, scheduled_time: str) -> str:
    try:
        parsed_date = date.fromisoformat(scheduled_date)
        scheduled_at = utils.vietnam_datetime(parsed_date, scheduled_time)
    except (TypeError, ValueError) as error:
        raise ServiceError(422, "invalid_schedule", "The posting date or time is invalid") from error

    with db.get_session() as session:
        campaign = session.get(db.Campaign, campaign_id)
        if campaign is None:
            raise not_found(campaign_id)
        if campaign.status != "draft":
            raise _not_editable(campaign.status)
        brief = dict(campaign.brief or {})

    try:
        date_from = date.fromisoformat(str(brief.get("date_from", "")))
        date_to = date.fromisoformat(str(brief.get("date_to", "")))
    except ValueError as error:
        raise ServiceError(422, "brief_missing_dates", "The brief has no valid date range") from error
    if not date_from <= parsed_date <= date_to:
        raise ServiceError(
            422,
            "schedule_outside_campaign",
            f"The posting date must be between {date_from.isoformat()} and {date_to.isoformat()}",
        )
    return scheduled_at


def update_content(
    campaign_id: int,
    content_item_id: int,
    user: AuthenticatedUser,
    *,
    draft: dict,
    scheduled_date: str,
    scheduled_time: str,
) -> dict:
    scheduled_at = _parse_schedule(campaign_id, scheduled_date, scheduled_time)
    try:
        result = manual_edit_draft(
            db.get_engine(),
            campaign_id=campaign_id,
            content_item_id=content_item_id,
            new_draft=draft,
            edited_by=user.email,
            edited_by_id=user.id,
            scheduled_at=scheduled_at,
        )
    except ValueError as error:
        raise ServiceError(404, "content_not_found", str(error)) from error
    except CampaignEditForbiddenError as error:
        raise not_found(campaign_id) from error
    except CampaignNotEditableError as error:
        raise _not_editable(error.status) from error

    revalidation = _revalidation_after_edit(campaign_id, content_item_id, result["content_changed"])
    return _edit_response(content_item_id, result, revalidation) | {
        "schedule": {"scheduled_at": result["scheduled_at"], "status": "proposed"},
    }


def ai_edit_content(
    campaign_id: int,
    content_item_id: int,
    user: AuthenticatedUser,
    *,
    instruction: str,
    target_text: str = "",
) -> dict:
    try:
        result = _edit_with_ai(campaign_id, content_item_id, user, instruction, target_text)
    except CampaignNotEditableError as error:
        raise _not_editable(error.status) from error
    except CampaignEditForbiddenError as error:
        raise not_found(campaign_id) from error
    except ValueError as error:
        raise ServiceError(404, "content_not_found", str(error)) from error

    revalidation = _revalidation_after_edit(campaign_id, content_item_id, result["content_changed"])
    return _edit_response(content_item_id, result, revalidation)


def record_manual_send(
    campaign_id: int,
    user: AuthenticatedUser,
    *,
    content_item_id: int,
    channel: str,
    sent_content: str,
    recipients: str = "",
    recipient_count: int = 0,
) -> dict:
    """Zalo and SMS are sent by hand, so this is their audit trail. The content must already be approved."""
    with db.get_session() as session:
        item = session.get(db.ContentItem, content_item_id)
        if item is None or item.campaign_id != campaign_id:
            raise ServiceError(404, "content_not_found", f"Campaign {campaign_id} has no content {content_item_id}")
        if item.status != "approved":
            raise ServiceError(409, "content_not_approved", f"The content is `{item.status}`; it must be approved first")
        session.add(
            db.ManualSend(
                content_item_id=item.id,
                channel=channel,
                sent_content=sent_content,
                recipients=recipients,
                recipient_count=recipient_count,
                sent_by=user.email,
                sent_by_id=user.id,
            )
        )
        session.commit()

    shared.record_audit(
        user,
        "manual_send",
        f"content:{content_item_id}",
        f"Sent by {channel} to {recipient_count} people" + (f" ({recipients})" if recipients else ""),
    )
    return {"recorded": True}


# --- Chat sessions --------------------------------------------------------------


def _linked_campaigns_by_chat(session, chat_session_ids: list[str]) -> dict[str, db.Campaign]:
    if not chat_session_ids:
        return {}
    campaigns = (
        session.query(db.Campaign)
        .filter(db.Campaign.chat_session_id.in_(chat_session_ids))
        .order_by(db.Campaign.updated_at.desc(), db.Campaign.id.desc())
        .all()
    )
    latest: dict[str, db.Campaign] = {}
    for campaign in campaigns:
        latest.setdefault(campaign.chat_session_id, campaign)
    return latest


def _chat_display_title(chat: db.ChatSession, campaign: db.Campaign | None) -> str:
    current = str(chat.title or "").strip()
    if campaign is None:
        return current
    brief = campaign.brief or {}
    raw_prompt = str(brief.get("raw_prompt") or "").strip()
    automatic_titles = {str(campaign.name or "").strip(), raw_prompt[:38], raw_prompt[:200], DEFAULT_CHAT_TITLE}
    return campaign_display_name(campaign.name, brief) if current in automatic_titles else current


def _message_view(message: db.ChatMessage) -> dict:
    return {
        "id": message.id,
        "role": message.role,
        "content": message.content,
        "metadata": message.message_metadata,
        "created_at": message.created_at,
    }


def create_chat_session(user: AuthenticatedUser, title: str) -> dict:
    with db.get_session() as session:
        chat = db.ChatSession(marketer_id=user.id, title=title.strip())
        session.add(chat)
        session.commit()
        return {"id": chat.id, "title": chat.title, "created_at": chat.created_at, "updated_at": chat.updated_at}


def list_chat_sessions(user: AuthenticatedUser) -> list[dict]:
    with db.get_session() as session:
        rows = (
            session.query(db.ChatSession)
            .filter_by(marketer_id=user.id)
            .order_by(db.ChatSession.updated_at.desc())
            .all()
        )
        campaigns = _linked_campaigns_by_chat(session, [row.id for row in rows])
        return [
            {
                "id": row.id,
                "title": _chat_display_title(row, campaigns.get(row.id)),
                "created_at": row.created_at,
                "updated_at": row.updated_at,
            }
            for row in rows
        ]


def get_chat_session(user: AuthenticatedUser, chat_session_id: str) -> dict:
    with db.get_session() as session:
        chat = _owned_chat_session(session, chat_session_id, user)
        messages = session.query(db.ChatMessage).filter_by(chat_session_id=chat.id).order_by(db.ChatMessage.id).all()
        linked = (
            session.query(db.Campaign)
            .filter_by(chat_session_id=chat.id)
            .order_by(db.Campaign.updated_at.desc(), db.Campaign.id.desc())
            .all()
        )
        return {
            "id": chat.id,
            "title": _chat_display_title(chat, linked[0] if linked else None),
            "messages": [_message_view(message) for message in messages],
            "campaign_ids": [campaign.id for campaign in linked],
        }


def update_chat_session(user: AuthenticatedUser, chat_session_id: str, title: str) -> dict:
    with db.get_session() as session:
        chat = _owned_chat_session(session, chat_session_id, user)
        chat.title = title.strip()
        chat.updated_at = utils.current_timestamp()
        session.commit()
        return {"id": chat.id, "title": chat.title, "updated_at": chat.updated_at}


def delete_chat_session(user: AuthenticatedUser, chat_session_id: str) -> dict:
    with db.get_session() as session:
        session.delete(_owned_chat_session(session, chat_session_id, user))
        session.commit()
        return {"deleted": True, "id": chat_session_id}


def create_chat_message(user: AuthenticatedUser, chat_session_id: str, role: str, content: str, metadata: dict) -> dict:
    with db.get_session() as session:
        chat = _owned_chat_session(session, chat_session_id, user)
        message = db.ChatMessage(
            chat_session_id=chat.id, role=role, content=content.strip(), message_metadata=metadata
        )
        chat.updated_at = utils.current_timestamp()
        session.add(message)
        session.commit()
        return _message_view(message)


def update_chat_message(
    user: AuthenticatedUser, chat_session_id: str, message_id: int, content: str, metadata: dict
) -> dict:
    with db.get_session() as session:
        _owned_chat_session(session, chat_session_id, user)
        message = session.get(db.ChatMessage, message_id)
        if message is None or message.chat_session_id != chat_session_id:
            raise ServiceError(404, "chat_message_not_found", "Chat message not found")
        message.content = content.strip()
        message.message_metadata = metadata
        session.commit()
        return _message_view(message)

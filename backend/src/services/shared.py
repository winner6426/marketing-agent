"""What the role services share: errors, audit log, idempotency, campaign views, channels, schedules, shared."""

from __future__ import annotations

import logging
from collections import Counter
from collections.abc import Callable
from datetime import date

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from src.agents.campaign_runner import get_runner
from src.models import db
from src.models.campaign_state import VALID_CHANNELS, campaign_display_name, campaign_summary
from src.utils import current_timestamp, nfc

LOGGER = logging.getLogger(__name__)

class ServiceError(Exception):
    """A business failure the API layer turns into one uniform JSON error."""

    def __init__(
        self,
        status_code: int,
        code: str,
        message: str,
        *,
        headers: dict[str, str] | None = None,
        **details,
    ):
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.headers = headers
        self.details = details


# Audit log, for people to read. Not a source of truth: no code may decide anything based on this table.
MAX_DETAILS_LENGTH = 500
MAX_LOGIN_NAME_LENGTH = 50
MAX_TARGET_LENGTH = 50


def record_audit(user, action: str, target: str = "", details: str = "") -> None:
    """Log in its own session. A logging failure must never break the action that was already done."""
    try:
        with db.get_session() as session:
            session.add(
                db.AuditLog(
                    user_id=user.id,
                    login_name=user.email.split("@", 1)[0][:MAX_LOGIN_NAME_LENGTH],
                    role=user.role,
                    action=action,
                    target=target[:MAX_TARGET_LENGTH],
                    details=details[:MAX_DETAILS_LENGTH],
                )
            )
            session.commit()
    except Exception as error:  # noqa: BLE001
        LOGGER.warning("Could not write audit log for action `%s`: %s", action, error)


def _serialize_audit_row(row: db.AuditLog) -> dict:
    return {
        "timestamp": row.created_at,
        "login_name": row.login_name,
        "role": row.role,
        "action": row.action,
        "target": row.target,
        "details": row.details,
    }


def user_history(session, user_id: str, limit: int = 200) -> list[dict]:
    rows = (
        session.query(db.AuditLog)
        .filter_by(user_id=user_id)
        .order_by(db.AuditLog.created_at.desc())
        .limit(min(limit, 500))
        .all()
    )
    return [_serialize_audit_row(row) for row in rows]


def all_history(session, limit: int = 300) -> list[dict]:
    rows = session.query(db.AuditLog).order_by(db.AuditLog.created_at.desc()).limit(min(limit, 1000)).all()
    return [_serialize_audit_row(row) for row in rows]


def summarize_by_user(session) -> list[dict]:
    rows = (
        session.query(
            db.AuditLog.user_id,
            db.AuditLog.login_name,
            db.AuditLog.role,
            db.AuditLog.action,
            func.count(db.AuditLog.id),
            func.max(db.AuditLog.created_at),
        )
        .group_by(db.AuditLog.user_id, db.AuditLog.login_name, db.AuditLog.role, db.AuditLog.action)
        .all()
    )

    by_user: dict[str, dict] = {}
    for user_id, login_name, role, action, count, latest in rows:
        entry = by_user.setdefault(
            user_id,
            {"user_id": user_id, "login_name": login_name, "role": role, "by_action": {}, "latest": ""},
        )
        entry["by_action"][action] = count
        entry["latest"] = max(entry["latest"], latest or "")

    for entry in by_user.values():
        entry["total"] = sum(entry["by_action"].values())
    return sorted(by_user.values(), key=lambda entry: entry["latest"], reverse=True)


# Idempotency: reserve first, so the DB unique constraint arbitrates double clicks on costly operations.
class AlreadyRunningError(RuntimeError):
    pass


def get_or_execute(
    engine,
    key: str,
    endpoint: str,
    campaign_id: int | None,
    operation: Callable[[], dict],
) -> tuple[dict, bool]:
    """Return (response, is_first_run). Raises AlreadyRunningError while another request holds the key."""
    with db.session_for(engine) as session:
        try:
            session.add(
                db.IdempotencyKey(
                    key=key,
                    endpoint=endpoint,
                    campaign_id=campaign_id,
                    response_json={},
                    created_at=current_timestamp(),
                )
            )
            session.commit()
        except IntegrityError:
            session.rollback()
            existing = session.query(db.IdempotencyKey).filter_by(key=key, endpoint=endpoint).one()
            if not existing.response_json:
                raise AlreadyRunningError(f"An operation with Idempotency-Key '{key}' is still running.") from None
            return existing.response_json, False

    try:
        result = operation()
    except Exception:
        # Release the key, or a failed operation would stay locked forever.
        with db.session_for(engine) as session:
            session.query(db.IdempotencyKey).filter_by(key=key, endpoint=endpoint).delete()
            session.commit()
        raise

    with db.session_for(engine) as session:
        row = session.query(db.IdempotencyKey).filter_by(key=key, endpoint=endpoint).one()
        row.response_json = result
        session.commit()
    return result, True


def not_found(campaign_id: int) -> ServiceError:
    return ServiceError(404, "campaign_not_found", f"No campaign {campaign_id}")


def campaign_list_item(campaign: db.Campaign) -> dict:
    return {
        "campaign_id": campaign.id,
        "name": campaign.name,
        "display_name": campaign_display_name(campaign.name, campaign.brief),
        "summary": campaign_summary(campaign.brief),
        "status": campaign.status,
        "created_by": campaign.created_by,
        "created_at": campaign.created_at,
        "updated_at": campaign.updated_at,
    }


def campaign_detail(campaign_id: int) -> dict:
    """Merge graph state with the campaign row, which is authoritative while background runs are starting or failed."""
    detail = get_runner().get(campaign_id)
    with db.get_session() as session:
        campaign = session.get(db.Campaign, campaign_id)
        if campaign is None:
            raise not_found(campaign_id)
        detail["name"] = campaign.name
        detail["display_name"] = campaign_display_name(campaign.name, campaign.brief)
        detail["summary"] = campaign_summary(campaign.brief)

        if campaign.status in {"failed", "generation_failed"}:
            detail["status"] = campaign.status
            detail["error"] = detail.get("error") or (
                "The background run stopped; it can be restarted from its checkpoint."
                if campaign.status == "failed"
                else "The writer produced no usable content."
            )
            return detail

        # An error left in the checkpoint must not show once a retry has moved on.
        detail["error"] = None
        if campaign.status == "draft":
            detail["status"] = "draft"
            if (detail.get("pending_human_action") or {}).get("kind") == "approval":
                detail["pending_human_action"] = None
        elif campaign.status == "running" and not detail["contents"] and not detail["pending_human_action"]:
            detail["status"] = "running"
            detail["current_node"] = detail.get("current_node") or "brief_analyst"
    return detail


def enum_value(raw) -> str | None:
    if raw is None:
        return None
    return raw.value if hasattr(raw, "value") else str(raw)


def channel_view(channel: db.Channel, content_counts: dict[str, int]) -> dict:
    content_channel = enum_value(channel.content_channel)
    return {
        "id": channel.id,
        "name": nfc(channel.name),
        "platform": enum_value(channel.platform) or "",
        "account_ref": channel.account_ref,
        "content_channel": content_channel,
        "status": enum_value(channel.status) or "",
        "is_connected": bool(channel.is_connected),
        "note": nfc(channel.note or ""),
        "content_count": content_counts.get(content_channel, 0) if content_channel else 0,
        "created_at": channel.created_at,
        "updated_at": channel.updated_at,
    }


def count_content_by_channel(session) -> dict[str, int]:
    rows = session.query(db.ContentItem.channel, func.count(db.ContentItem.id)).group_by(db.ContentItem.channel)
    return {enum_value(channel) or "": int(total) for channel, total in rows}


def list_channels(*, include_inactive: bool = True) -> list[dict]:
    with db.get_session() as session:
        query = session.query(db.Channel)
        if not include_inactive:
            query = query.filter(db.Channel.status == "active")
        channels = query.order_by(db.Channel.platform, db.Channel.name, db.Channel.id).all()
        content_counts = count_content_by_channel(session)
        return [channel_view(channel, content_counts) for channel in channels]


def _parse_range(date_from: str, date_to: str) -> tuple[date, date]:
    try:
        start, end = date.fromisoformat(date_from), date.fromisoformat(date_to)
    except ValueError as error:
        raise ServiceError(422, "invalid_date", "Dates must use the YYYY-MM-DD format") from error
    if end < start:
        raise ServiceError(422, "invalid_date_range", "The end date must not be before the start date")
    return start, end


def _schedule_title(body: str | None) -> str:
    lines = (body or "").splitlines()
    return lines[0][:100] if lines else ""


def list_schedules(date_from: str, date_to: str, channel: str | None = None, owner_id: str | None = None) -> dict:
    """Only slots a manager confirmed; `owner_id` limits the result to one marketer's campaigns."""
    start, end = _parse_range(date_from, date_to)
    if channel is not None and channel not in VALID_CHANNELS:
        raise ServiceError(422, "invalid_channel", f"Channel `{channel}` is not supported")

    with db.get_session() as session:
        query = (
            session.query(db.ScheduleSlot, db.ContentItem, db.Campaign)
            .join(db.ContentItem, db.ContentItem.id == db.ScheduleSlot.content_item_id)
            .join(db.Campaign, db.Campaign.id == db.ScheduleSlot.campaign_id)
            .filter(db.ScheduleSlot.status.in_(("scheduled", "published")))
            .filter(db.ScheduleSlot.scheduled_at >= f"{start.isoformat()}T00:00:00+07:00")
            .filter(db.ScheduleSlot.scheduled_at <= f"{end.isoformat()}T23:59:59+07:00")
        )
        if channel:
            query = query.filter(db.ContentItem.channel == channel)
        if owner_id is not None:
            query = query.filter(db.Campaign.created_by_id == owner_id)

        rows = query.order_by(db.ScheduleSlot.scheduled_at, db.ScheduleSlot.id).all()
        return {
            "schedules": [
                {
                    "slot_id": slot.id,
                    "campaign_id": campaign.id,
                    "campaign_name": campaign_display_name(campaign.name, campaign.brief),
                    "content_item_id": content.id,
                    "content_key": f"{content.channel}/{content.variant}",
                    "channel": content.channel,
                    "variant": content.variant,
                    "scheduled_at": slot.scheduled_at,
                    "scheduled_date": slot.scheduled_at[:10],
                    "scheduled_time": slot.scheduled_at[11:16],
                    "status": slot.status,
                    "title": _schedule_title(content.body),
                    "reason": slot.reason,
                }
                for slot, content, campaign in rows
            ]
        }


# Analytics, computed with SQL on real system data. Simulated leads are always counted separately.
def _events_by_content(session, content_item_ids: list[int]) -> dict[int, dict[str, int]]:
    if not content_item_ids:
        return {}
    rows = (
        session.query(db.MetricEvent.content_item_id, db.MetricEvent.event_type, func.count(db.MetricEvent.id))
        .filter(db.MetricEvent.content_item_id.in_(content_item_ids))
        .group_by(db.MetricEvent.content_item_id, db.MetricEvent.event_type)
        .all()
    )
    events: dict[int, dict[str, int]] = {}
    for content_item_id, event_type, total in rows:
        events.setdefault(content_item_id, {})[event_type] = int(total)
    return events


def _leads_by_content(session, content_item_ids: list[int]) -> dict[int, int]:
    if not content_item_ids:
        return {}
    rows = (
        session.query(db.Lead.content_item_id, func.count(db.Lead.id))
        .filter(db.Lead.content_item_id.in_(content_item_ids))
        .group_by(db.Lead.content_item_id)
        .all()
    )
    return {content_item_id: int(total) for content_item_id, total in rows}


def _website_slugs(session, content_item_ids: list[int]) -> dict[int, str]:
    if not content_item_ids:
        return {}
    rows = (
        session.query(db.PublishedPost.content_item_id, db.PublishedPost.external_id)
        .filter(
            db.PublishedPost.content_item_id.in_(content_item_ids),
            db.PublishedPost.channel == "website",
            db.PublishedPost.status == "published",
        )
        .all()
    )
    return dict(rows)


def campaign_overview(session, campaign_id: int | None = None) -> dict:
    query = session.query(db.ContentItem)
    if campaign_id is not None:
        query = query.filter_by(campaign_id=campaign_id)
    contents = query.all()
    content_ids = [content.id for content in contents]

    by_status = Counter(content.status for content in contents)
    approved_count = by_status.get("approved", 0)

    posts = session.query(func.count(db.PublishedPost.id)).filter(
        db.PublishedPost.channel == "website",
        db.PublishedPost.status == "published",
        db.PublishedPost.content_item_id.in_(content_ids),
    )
    approvals = session.query(func.count(db.Approval.id))
    campaign_count = session.query(func.count(db.Campaign.id))
    if campaign_id is not None:
        approvals = approvals.filter(db.Approval.campaign_id == campaign_id)
        campaign_count = campaign_count.filter(db.Campaign.id == campaign_id)

    return {
        "campaign_count": campaign_count.scalar() or 0,
        "content_count": len(contents),
        "by_status": dict(by_status),
        "approved_count": approved_count,
        # A high block rate is not bad: it measures what the system caught before publishing.
        "block_rate": round((len(contents) - approved_count) / len(contents) * 100, 1) if contents else 0.0,
        "published_on_site_count": posts.scalar() or 0,
        "approval_count": approvals.scalar() or 0,
    }


def variant_performance(session, campaign_id: int | None = None) -> list[dict]:
    query = select(db.ContentItem, db.Campaign).join(db.Campaign, db.Campaign.id == db.ContentItem.campaign_id)
    if campaign_id is not None:
        query = query.where(db.ContentItem.campaign_id == campaign_id)

    rows = session.execute(query).all()
    content_ids = [content.id for content, _ in rows]
    events = _events_by_content(session, content_ids)
    leads = _leads_by_content(session, content_ids)
    slugs = _website_slugs(session, content_ids)

    performance = []
    for content, campaign in rows:
        counts = events.get(content.id, {})
        views = counts.get("page_view", 0)
        clicks = counts.get("cta_click", 0)
        performance.append(
            {
                "content_item_id": content.id,
                "campaign": campaign.name,
                "channel": content.channel,
                "variant": content.variant,
                "angle": (content.meta or {}).get("angle", ""),
                "status": content.status,
                "slug": slugs.get(content.id),
                "views": views,
                "scroll_50": counts.get("scroll_50", 0),
                "scroll_90": counts.get("scroll_90", 0),
                "cta_clicks": clicks,
                # None rather than 0: "no data yet" and "measured zero" are different conclusions.
                "ctr": round(clicks / views * 100, 1) if views else None,
                "lead_count": leads.get(content.id, 0),
            }
        )
    return sorted(performance, key=lambda item: (item["channel"], item["variant"]))


def validation_health(session) -> dict:
    citation_count = session.query(func.count(db.ContentCitation.id)).scalar() or 0
    cited_content_count = session.query(func.count(func.distinct(db.ContentCitation.content_item_id))).scalar() or 0

    reasons: Counter[str] = Counter()
    for content in session.query(db.ContentItem).filter(db.ContentItem.status != "approved").all():
        writer_error = (content.meta or {}).get("writer_error") or ""
        if "raw numbers" in writer_error:
            reasons["Wrote raw numbers instead of placeholders"] += 1
        elif "segment" in writer_error:
            reasons["Over the message segment budget"] += 1
        elif writer_error:
            reasons[writer_error[:60]] += 1
        else:
            reasons["Blocked by a validation tier"] += 1

    return {
        "traceable_figures": citation_count,
        "content_with_citations": cited_content_count,
        "distinct_sources": session.query(func.count(func.distinct(db.ContentCitation.source_url))).scalar() or 0,
        "top_block_reasons": [{"reason": reason, "count": count} for reason, count in reasons.most_common(5)],
    }


def lead_funnel(session) -> dict:
    def event_count(event_type: str) -> int:
        return session.query(func.count(db.MetricEvent.id)).filter(db.MetricEvent.event_type == event_type).scalar() or 0

    by_status = dict(session.query(db.Lead.status, func.count(db.Lead.id)).group_by(db.Lead.status).all())
    real_count = session.query(func.count(db.Lead.id)).filter(db.Lead.source == "real").scalar() or 0
    simulated_count = session.query(func.count(db.Lead.id)).filter(db.Lead.source == "simulated").scalar() or 0

    return {
        "views": event_count("page_view"),
        "cta_clicks": event_count("cta_click"),
        "lead_count": real_count + simulated_count,
        "real_lead_count": real_count,
        "simulated_lead_count": simulated_count,
        "by_status": by_status,
        "test_drive_scheduled": by_status.get("test_drive_scheduled", 0) + by_status.get("converted", 0),
    }


def analytics_overview(session, campaign_id: int | None = None) -> dict:
    return {
        "campaigns": campaign_overview(session, campaign_id),
        "content": variant_performance(session, campaign_id),
        "validations": validation_health(session),
        "leads": lead_funnel(session),
    }

"""Admin operations: user roles, the system-wide campaign list, and the publishing channel catalog."""

from __future__ import annotations

from typing import Any

from sqlalchemy import func
from sqlalchemy.exc import IntegrityError

from src.models import db
from src.services import shared
from src.services.auth_service import AuthenticatedUser
from src.services.shared import ServiceError
from src.utils import current_timestamp, nfc

# Distinguishes "field not sent" from "field sent as null".
UNSET = object()

ASSIGNABLE_ROLES = ("marketer", "manager")


def _role_value(profile: db.UserProfile) -> str:
    return profile.role.value if isinstance(profile.role, db.UserRole) else str(profile.role)


def _user_view(profile: db.UserProfile) -> dict:
    return {
        "user_id": str(profile.id),
        "email": profile.email,
        "full_name": nfc(profile.name),
        "role": _role_value(profile),
        "created_at": profile.created_at,
        "updated_at": profile.updated_at,
    }


def list_users() -> list[dict]:
    with db.get_session() as session:
        profiles = session.query(db.UserProfile).order_by(db.UserProfile.created_at, db.UserProfile.id).all()
        return [_user_view(profile) for profile in profiles]


def change_role(actor: AuthenticatedUser, target_id: str, new_role: str) -> dict:
    """The role change and its audit row commit in one transaction."""
    if new_role not in ASSIGNABLE_ROLES:
        raise ServiceError(422, "invalid_role", f"Role must be one of {', '.join(ASSIGNABLE_ROLES)}")

    with db.get_session() as session:
        target = session.get(db.UserProfile, target_id)
        if target is None:
            raise ServiceError(404, "user_not_found", "User not found")
        if target_id == actor.id:
            raise ServiceError(403, "cannot_change_own_role", "Admins cannot change their own role")

        old_role = _role_value(target)
        if old_role == "admin":
            raise ServiceError(403, "cannot_change_admin", "The role of an admin account cannot be changed")
        if old_role == new_role:
            return _user_view(target)

        timestamp = current_timestamp()
        target.role = db.UserRole(new_role)
        target.updated_at = timestamp
        session.add(
            db.AuditLog(
                user_id=actor.id,
                login_name=actor.email.split("@", 1)[0][:50],
                role=actor.role,
                action="change_role",
                target=f"user:{target_id}"[:50],
                details=f"{old_role} -> {new_role}",
                created_at=timestamp,
            )
        )
        session.commit()
        return _user_view(target)


def _brief_text(brief: dict[str, Any], key: str) -> str:
    value = brief.get(key)
    return nfc(str(value)) if value is not None else ""


def _brief_channels(brief: dict[str, Any]) -> list[str]:
    values = brief.get("channels")
    if not isinstance(values, list):
        return []
    return [nfc(value) for value in values if isinstance(value, str) and value.strip()]


def list_campaigns() -> list[dict[str, Any]]:
    """A safe projection: never the whole brief or the graph state."""
    with db.get_session() as session:
        content_stats = (
            session.query(
                db.ContentItem.campaign_id.label("campaign_id"),
                func.count(db.ContentItem.id).label("content_count"),
            )
            .group_by(db.ContentItem.campaign_id)
            .subquery()
        )
        rows = (
            session.query(db.Campaign, func.coalesce(content_stats.c.content_count, 0))
            .outerjoin(content_stats, content_stats.c.campaign_id == db.Campaign.id)
            .order_by(db.Campaign.updated_at.desc(), db.Campaign.id.desc())
            .all()
        )
        items = []
        for campaign, content_count in rows:
            brief = campaign.brief or {}
            items.append(
                {
                    "campaign_id": campaign.id,
                    "campaign_name": nfc(campaign.name),
                    "model_id": _brief_text(brief, "model_id"),
                    "goal": _brief_text(brief, "goal"),
                    "segment": _brief_text(brief, "segment"),
                    "owner_email": campaign.created_by,
                    "status": campaign.status,
                    "channels": _brief_channels(brief),
                    "content_count": int(content_count),
                    "created_at": campaign.created_at,
                    "updated_at": campaign.updated_at,
                }
            )
        return items


def channel_options() -> dict:
    return {
        "platforms": list(db.CHANNEL_PLATFORMS),
        "statuses": list(db.CHANNEL_STATUSES),
        "content_channels": list(db.APP_CHANNELS),
    }


def list_channels() -> list[dict]:
    return shared.list_channels(include_inactive=True)


def _invalid_channel(message: str) -> ServiceError:
    return ServiceError(422, "invalid_channel", message)


def _duplicate_channel() -> ServiceError:
    return ServiceError(409, "duplicate_channel", "Another channel already uses this platform and account")


def _clean_text(value, *, field: str, max_length: int, required: bool = True) -> str:
    text = nfc(str(value or "")).strip()
    if required and not text:
        raise _invalid_channel(f"Missing required field: {field}")
    if len(text) > max_length:
        raise _invalid_channel(f"Field {field} exceeds {max_length} characters")
    return text


def _clean_option(value, *, field: str, options: tuple[str, ...]) -> str:
    text = str(value or "").strip()
    if text not in options:
        raise _invalid_channel(f"Invalid {field}: {text or '(empty)'}")
    return text


def _clean_content_channel(value) -> str | None:
    if value in (None, ""):
        return None
    return _clean_option(value, field="content_channel", options=db.APP_CHANNELS)


def create_channel(
    *,
    actor_id: str,
    name: str,
    platform: str,
    account_ref: str,
    content_channel: str | None = None,
    status: str = "active",
    is_connected: bool = False,
    note: str = "",
) -> dict:
    timestamp = current_timestamp()
    channel = db.Channel(
        name=_clean_text(name, field="name", max_length=120),
        platform=_clean_option(platform, field="platform", options=db.CHANNEL_PLATFORMS),
        account_ref=_clean_text(account_ref, field="account_ref", max_length=200),
        content_channel=_clean_content_channel(content_channel),
        status=_clean_option(status, field="status", options=db.CHANNEL_STATUSES),
        is_connected=bool(is_connected),
        note=_clean_text(note, field="note", max_length=500, required=False),
        created_by_id=actor_id,
        created_at=timestamp,
        updated_at=timestamp,
    )
    with db.get_session() as session:
        session.add(channel)
        try:
            session.commit()
        except IntegrityError as error:
            session.rollback()
            raise _duplicate_channel() from error
        return shared.channel_view(channel, shared.count_content_by_channel(session))


def update_channel(
    channel_id: int,
    *,
    name=UNSET,
    platform=UNSET,
    account_ref=UNSET,
    content_channel=UNSET,
    status=UNSET,
    is_connected=UNSET,
    note=UNSET,
) -> dict:
    with db.get_session() as session:
        channel = session.get(db.Channel, channel_id)
        if channel is None:
            raise ServiceError(404, "channel_not_found", "Channel not found")

        if name is not UNSET:
            channel.name = _clean_text(name, field="name", max_length=120)
        if platform is not UNSET:
            channel.platform = _clean_option(platform, field="platform", options=db.CHANNEL_PLATFORMS)
        if account_ref is not UNSET:
            channel.account_ref = _clean_text(account_ref, field="account_ref", max_length=200)
        if content_channel is not UNSET:
            channel.content_channel = _clean_content_channel(content_channel)
        if status is not UNSET:
            channel.status = _clean_option(status, field="status", options=db.CHANNEL_STATUSES)
        if is_connected is not UNSET:
            channel.is_connected = bool(is_connected)
        if note is not UNSET:
            channel.note = _clean_text(note, field="note", max_length=500, required=False)

        channel.updated_at = current_timestamp()
        try:
            session.commit()
        except IntegrityError as error:
            session.rollback()
            raise _duplicate_channel() from error
        return shared.channel_view(channel, shared.count_content_by_channel(session))


def delete_channel(channel_id: int) -> dict:
    with db.get_session() as session:
        channel = session.get(db.Channel, channel_id)
        if channel is None:
            raise ServiceError(404, "channel_not_found", "Channel not found")
        removed = shared.channel_view(channel, shared.count_content_by_channel(session))
        session.delete(channel)
        session.commit()
        return removed

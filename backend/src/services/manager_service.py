"""Manager operations: the review queue, approval decisions, publishing and system-wide reporting."""

from __future__ import annotations

import re
import unicodedata

from src import content_locale
from src.agents.campaign_runner import get_runner
from src.models import db
from src.services import shared
from src.services.auth_service import AuthenticatedUser
from src.services.shared import ServiceError, campaign_detail, campaign_list_item, not_found

# Publishing: only `approved` items qualify, because validation alone is not a signature.
WEBSITE_CHANNEL = "website"
FALLBACK_SLUG = "article"


class PublishingEligibilityError(RuntimeError):
    pass


def create_slug(text: str, max_length: int = 80) -> str:
    # NFD does not decompose these letters, so they must be mapped before stripping accents.
    for letter, replacement in content_locale.SLUG_LETTER_MAP.items():
        text = text.replace(letter, replacement)
    without_accents = "".join(
        character for character in unicodedata.normalize("NFD", text) if not unicodedata.combining(character)
    )
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", without_accents).strip("-").lower()
    return slug[:max_length].strip("-") or FALLBACK_SLUG


def unique_slug(session, base_slug: str) -> str:
    slug, suffix = base_slug, 2
    while session.query(db.PublishedPost).filter_by(channel=WEBSITE_CHANNEL, external_id=slug).first() is not None:
        slug = f"{base_slug}-{suffix}"
        suffix += 1
    return slug


def publish_to_site(session, content_item_id: int, *, published_by: str = "", published_by_id: str = "") -> db.PublishedPost:
    """Publishing twice returns the existing post, so retries stay harmless."""
    item = session.get(db.ContentItem, content_item_id)
    if item is None:
        raise PublishingEligibilityError(f"No content item id={content_item_id}.")

    existing = session.query(db.PublishedPost).filter_by(content_item_id=item.id, channel=WEBSITE_CHANNEL).first()
    if existing is not None:
        if existing.status == "published":
            return existing
        session.delete(existing)
        session.flush()

    if item.status != "approved":
        raise PublishingEligibilityError(f"Content item id={item.id} is `{item.status}`, not approved.")
    if not (item.body or "").strip():
        raise PublishingEligibilityError(f"Content item id={item.id} is empty.")

    campaign = session.get(db.Campaign, item.campaign_id)
    model_id = (campaign.brief or {}).get("model_id", "")
    slug = unique_slug(session, create_slug(f"{campaign.name} {model_id} variant {item.variant}"))

    post = db.PublishedPost(
        content_item_id=item.id,
        channel=WEBSITE_CHANNEL,
        external_id=slug,
        url=f"/articles/{slug}",
        status="published",
        published_by=published_by,
        published_by_id=published_by_id,
    )
    session.add(post)
    session.flush()
    return post


def _run_idempotently(key: str, endpoint: str, campaign_id: int, operation) -> dict:
    # The campaign id is part of the scope, so a reused key can never return another campaign's response.
    scoped_endpoint = f"{endpoint}:{campaign_id}"
    try:
        result, _ = shared.get_or_execute(db.get_engine(), key, scoped_endpoint, campaign_id, operation)
        return result
    except shared.AlreadyRunningError as error:
        raise ServiceError(409, "already_running", str(error)) from error


def _ensure_campaign_exists(campaign_id: int) -> None:
    with db.get_session() as session:
        if session.get(db.Campaign, campaign_id) is None:
            raise not_found(campaign_id)


def list_campaigns() -> list[dict]:
    with db.get_session() as session:
        rows = session.query(db.Campaign).order_by(db.Campaign.updated_at.desc(), db.Campaign.id.desc()).all()
        return [campaign_list_item(campaign) for campaign in rows]


def _selected_review_payload(payload: dict) -> dict:
    """When the marketer selected variants, the manager reviews only those."""
    selected = [item for item in payload.get("contents", []) if item.get("selected_for_approval") is True]
    if not selected:
        return payload
    selected_ids = {item["content_item_id"] for item in selected}
    return payload | {
        "contents": selected,
        "schedules": [slot for slot in payload.get("schedules", []) if slot.get("content_item_id") in selected_ids],
    }


def get_campaign(campaign_id: int) -> dict:
    _ensure_campaign_exists(campaign_id)
    detail = campaign_detail(campaign_id)
    return _selected_review_payload(detail) if detail.get("status") == "waiting_approval" else detail


def review_campaign(campaign_id: int, user: AuthenticatedUser, decision: str, reason: str, key: str) -> dict:
    """A rejection needs a reason; otherwise the marketer cannot tell what to fix."""
    _ensure_campaign_exists(campaign_id)
    if decision == "reject" and not reason.strip():
        raise ServiceError(422, "reason_required", "A rejection must include a reason for the marketer")

    def operation() -> dict:
        with db.get_session() as session:
            campaign = session.get(db.Campaign, campaign_id)
            status = campaign.status if campaign is not None else None
        # The graph also pauses here for unsubmitted chat drafts; those are not the manager's to decide yet.
        if status != "waiting_approval":
            raise ServiceError(409, "not_waiting_approval", f"The campaign is `{status}`, not waiting for approval")
        return get_runner().review(
            campaign_id,
            {"decision": decision, "reason": reason},
            reviewer=user.email,
            reviewer_id=user.id,
        )

    result = _run_idempotently(key, "manager.review", campaign_id, operation)
    shared.record_audit(
        user,
        "approve" if decision == "approve" else "reject",
        f"campaign:{campaign_id}",
        reason.strip() or ("Approved the campaign" if decision == "approve" else "Rejected"),
    )
    return result


def publish_campaign(campaign_id: int, user: AuthenticatedUser, key: str) -> dict:
    """Publish every approved item, and report what was skipped so nobody assumes the whole batch went out."""
    _ensure_campaign_exists(campaign_id)

    def operation() -> dict:
        published_items: list[dict] = []
        skipped_items: list[dict] = []
        with db.get_session() as session:
            contents = session.query(db.ContentItem).filter_by(campaign_id=campaign_id).all()
            if not contents:
                raise ServiceError(404, "no_content", f"Campaign {campaign_id} has no content yet")

            for content in contents:
                try:
                    post = publish_to_site(
                        session, content.id, published_by=user.email, published_by_id=user.id
                    )
                except PublishingEligibilityError as error:
                    skipped_items.append({"content_item_id": content.id, "reason": str(error)})
                    continue
                published_items.append({"content_item_id": content.id, "slug": post.external_id, "url": post.url})
                slot = session.query(db.ScheduleSlot).filter_by(content_item_id=content.id).one_or_none()
                if slot is not None:
                    slot.status = "published"

            if not published_items:
                raise ServiceError(
                    409,
                    "nothing_to_publish",
                    "No content is eligible for the site. Approve it first.",
                    skipped_items=skipped_items,
                )
            session.get(db.Campaign, campaign_id).status = "published"
            session.commit()

        shared.record_audit(
            user,
            "publish",
            f"campaign:{campaign_id}",
            f"Published {len(published_items)} items" + (f", skipped {len(skipped_items)}" if skipped_items else ""),
        )
        return {"campaign_id": campaign_id, "published": published_items, "skipped": skipped_items}

    return _run_idempotently(key, "manager.publish", campaign_id, operation)


def analytics_overview(campaign_id: int | None = None) -> dict:
    with db.get_session() as session:
        return shared.analytics_overview(session, campaign_id)


def audit_history() -> dict:
    with db.get_session() as session:
        return {"entries": shared.all_history(session), "summary": shared.summarize_by_user(session)}


def list_schedules(date_from: str, date_to: str, channel: str | None = None) -> dict:
    return shared.list_schedules(date_from, date_to, channel)


def list_channels() -> list[dict]:
    return shared.list_channels(include_inactive=False)

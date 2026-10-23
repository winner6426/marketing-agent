"""Deterministic scheduling: spreads validated content across the campaign dates using internal time slots."""

from __future__ import annotations

from datetime import date, timedelta

from src import utils
from src.models.campaign_state import CampaignState, passes_all_tiers, render_outbound_text

INTERNAL_TIME_SLOTS = {
    ("facebook", "A"): "09:00",
    ("facebook", "B"): "19:30",
    ("direct_message", "A"): "10:30",
    ("direct_message", "B"): "16:30",
    ("instagram", "A"): "11:30",
    ("instagram", "B"): "18:30",
    ("tiktok", "A"): "12:30",
    ("tiktok", "B"): "20:30",
}
DEFAULT_TIME = "12:00"
INTERNAL_REASON = "Spread evenly across the campaign dates by internal convention"


def _campaign_dates(brief: dict) -> tuple[date, date]:
    try:
        date_from = date.fromisoformat(str(brief.get("date_from", "")))
        date_to = date.fromisoformat(str(brief.get("date_to", "")))
    except ValueError as error:
        raise ValueError("Campaign dates must use the YYYY-MM-DD format") from error
    if date_to < date_from:
        raise ValueError("The campaign ends before it starts")
    return date_from, date_to


def _is_eligible(state: CampaignState, content_key: str) -> bool:
    draft = (state.get("drafts") or {}).get(content_key, {})
    validation = (state.get("validations") or {}).get(content_key, {})
    return (
        not draft.get("writer_error")
        and bool(render_outbound_text(draft).strip())
        and passes_all_tiers(validation)
    )


def build_schedule(state: CampaignState) -> dict[str, dict]:
    date_from, date_to = _campaign_dates(state.get("brief") or {})
    content_keys = sorted(key for key in (state.get("drafts") or {}) if _is_eligible(state, key))
    if not content_keys:
        return {}

    day_span = (date_to - date_from).days
    last_index = max(len(content_keys) - 1, 1)
    schedules = {}
    for index, content_key in enumerate(content_keys):
        channel, variant = content_key.split("/", 1)
        day_offset = round(index * day_span / last_index) if day_span else 0
        scheduled_date = date_from + timedelta(days=day_offset)
        scheduled_time = INTERNAL_TIME_SLOTS.get((channel, variant), DEFAULT_TIME)
        schedules[content_key] = {
            "content_key": content_key,
            "channel": channel,
            "variant": variant,
            "scheduled_at": utils.vietnam_datetime(scheduled_date, scheduled_time),
            "scheduled_date": scheduled_date.isoformat(),
            "scheduled_time": scheduled_time,
            "status": "proposed",
            "reason": INTERNAL_REASON,
        }
    return schedules


def scheduler_node(state: CampaignState) -> dict:
    return {"schedules": build_schedule(state), "status": "waiting_approval"}

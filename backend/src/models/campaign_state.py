"""Campaign vocabulary, the LangGraph state schema and names derived from a brief."""

from __future__ import annotations

import re
from typing import Any, TypedDict

from src import content_locale
from src.utils import nfc

VALID_GOALS = {"launch", "test_drive", "promotion"}
VALID_CHANNELS = {"facebook", "direct_message", "instagram", "tiktok"}
VALID_FUNNEL_STAGES = {"awareness", "consideration", "intent"}

CHANNEL_ALIASES = {
    "fb": "facebook",
    "fanpage": "facebook",
    "facebook": "facebook",
    "zalo": "direct_message",
    "sms": "direct_message",
    "direct_message": "direct_message",
    "instagram": "instagram",
    "insta": "instagram",
    "ig": "instagram",
    "tiktok": "tiktok",
    "tik tok": "tiktok",
    **content_locale.CHANNEL_ALIASES,
}

CAMPAIGN_STATUSES = (
    "draft",
    "running",
    "needs_clarification",
    "brief_ok",
    "plan_ok",
    "draft_ok",
    "waiting_approval",
    "approval",
    "scheduled",
    "published",
    "rejected",
    "failed",
    "generation_failed",
)
CONTENT_STATUSES = ("draft", "needs_human", "passed", "approved")
SCHEDULE_STATUSES = ("proposed", "scheduled", "cancelled", "published")

# The three deterministic validation tiers, cheapest first.
VALIDATION_TIERS = ("channel_spec", "brand_rules", "fact_check")

# Draft fields that are not outbound text and must not be validated.
METADATA_FIELDS = {"channel", "variant", "angle", "writer_error"}


def normalize_channel(value: object) -> str:
    channel = str(value or "").strip().casefold()
    return CHANNEL_ALIASES.get(channel, channel)


def normalize_channels(values: object) -> list[str] | object:
    if not isinstance(values, list) or not all(isinstance(item, str) for item in values):
        return values
    return list(dict.fromkeys(normalize_channel(item) for item in values if item.strip()))


def passes_all_tiers(validation: dict) -> bool:
    return all((validation.get(tier) or {}).get("ok") is True for tier in VALIDATION_TIERS)


def draft_text_fields(draft: dict) -> dict[str, str]:
    return {key: value for key, value in draft.items() if isinstance(value, str) and key not in METADATA_FIELDS}


def render_outbound_text(draft: dict) -> str:
    parts = [draft[name] for name in ("hook", "body") if draft.get(name)]
    for name, value in draft_text_fields(draft).items():
        if name not in {"hook", "body"} and value:
            parts.append(value)
    return "\n\n".join(parts)


class CampaignState(TypedDict, total=False):
    brief: dict
    safe_brief: str
    questions: list[str]
    remaining_issue_count: int
    plan: dict
    # "<channel>/<variant>" -> draft / the RAG chunks the writer read / the tier results.
    drafts: dict[str, dict]
    rag_documents: dict[str, list[str]]
    validations: dict[str, dict]
    rewrite_queue: list[tuple[str, str]]
    recently_written: list[str]
    retry_channel_spec: dict[str, int]
    retry_fact: dict[str, int]
    # Advisory judge scores. A missing key means "not scored", which differs from a low score.
    quality_review: dict[str, dict]
    schedules: dict[str, dict]
    approval: dict
    status: str
    error: str


DEFAULT_NAME = "Campaign"
MAX_NAME_LENGTH = 200

GOAL_LABELS = {
    "launch": "Launch",
    "test_drive": "Test drive",
    "promotion": "Promotion",
}

GOAL_PATTERNS = (
    ("test_drive", rf"\b(?:test[\s-]*drive|{content_locale.TEST_DRIVE_WORDS})\b"),
    ("launch", rf"\b(?:launch|{content_locale.LAUNCH_WORDS})\b"),
    ("promotion", rf"\b(?:promotion|{content_locale.PROMOTION_WORDS})\b"),
)

SUMMARY_FIELDS = ("goal", "model_id", "segment", "funnel_stage", "channels", "date_from", "date_to")


def _text(value: Any) -> str:
    return nfc(str(value or "")).strip()


def _model_label(value: Any) -> str:
    model_id = re.sub(r"\s+", "", _text(value)).upper()
    match = re.fullmatch(r"VF(\d{1,2})", model_id)
    return f"VF {match.group(1)}" if match else model_id


def _sentence_case(value: Any) -> str:
    text = _text(value)
    return text[:1].upper() + text[1:] if text else ""


def _goal_value(brief: dict) -> str:
    explicit = _text(brief.get("goal")).casefold()
    if explicit in GOAL_LABELS:
        return explicit
    prompt = _text(brief.get("raw_prompt")).casefold()
    for value, pattern in GOAL_PATTERNS:
        if re.search(pattern, prompt, flags=re.IGNORECASE):
            return value
    return ""


def _compose(title_parts: tuple[str, str], segment: str) -> str:
    title = " ".join(part for part in title_parts if part)
    if segment:
        title = f"{title} · {segment}"
    return nfc(title).strip()[:MAX_NAME_LENGTH]


def campaign_name(brief: dict | None) -> str:
    """Build `[goal] [model] · [segment]`: deterministic, so no LLM call is needed."""
    data = brief or {}
    goal = GOAL_LABELS.get(_goal_value(data), DEFAULT_NAME)
    return _compose((goal, _model_label(data.get("model_id"))), _sentence_case(data.get("segment")))


def _provisional_names(brief: dict) -> set[str]:
    # Names given before the brief analyst worked out the goal, with and without the segment known at the time.
    title_parts = (DEFAULT_NAME, _model_label(brief.get("model_id")))
    return {_compose(title_parts, _sentence_case(brief.get("segment"))), _compose(title_parts, "")}


def campaign_display_name(name: str | None, brief: dict | None) -> str:
    """Keep a custom name, but replace a generated one now that the brief has more detail."""
    data = brief or {}
    current = _text(name)
    raw_prompt = _text(data.get("raw_prompt"))
    is_generated = (
        not current
        or current in {DEFAULT_NAME, *_provisional_names(data)}
        or (bool(raw_prompt) and current == raw_prompt[:MAX_NAME_LENGTH])
    )
    generated = campaign_name(data)
    if is_generated and generated != DEFAULT_NAME:
        return generated
    return current or generated


def campaign_summary(brief: dict | None) -> dict[str, Any]:
    data = brief or {}
    result = {field: data.get(field) for field in SUMMARY_FIELDS}
    result["goal"] = _goal_value(data) or result["goal"]
    return result

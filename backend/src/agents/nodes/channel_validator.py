"""Tier 1: channel spec rules read from `channel_specs`. Costs no tokens, so it runs first.

Only decorative excess is auto-fixed. Trimming copy would change meaning without review, so that goes back to the writer.
"""

from __future__ import annotations

import math
import re

from src import content_locale, utils
from src.models import db
from src.models.campaign_state import draft_text_fields


# One character outside GSM-7 moves a whole SMS to UCS-2, cutting a segment from 160 to 70.
def is_gsm7_encodable(text: str) -> bool:
    return all(character in content_locale.GSM7_BASIC or character in content_locale.GSM7_EXTENDED for character in text)


def utf16_length(text: str) -> int:
    return len(text.encode("utf-16-le")) // 2


def count_segments(text: str) -> int:
    if not text:
        return 1
    if is_gsm7_encodable(text):
        length = sum(2 if character in content_locale.GSM7_EXTENDED else 1 for character in text)
        single, per_segment = 160, 153
    else:
        length = utf16_length(text)
        single, per_segment = 70, 67
    return 1 if length <= single else math.ceil(length / per_segment)


_EMOJI = re.compile("[\U0001f300-\U0001faff\U00002600-\U000027bf\U0001f1e6-\U0001f1ff⬀-⯿]")


class MissingSpecError(RuntimeError):
    """A channel with no rows must raise: passing would silently skip every constraint."""


def _full_text(draft: dict) -> str:
    return " ".join(draft_text_fields(draft).values())


def _body(draft: dict) -> str:
    return draft.get("body") or ""


# rule_key -> measure. Rules without a measure are reported as unchecked, never skipped silently.
_MEASURES = {
    "hook_max_chars": lambda draft: len(draft.get("hook") or ""),
    "body_max_chars": lambda draft: len(_body(draft)),
    "caption_max_chars": lambda draft: len(draft.get("caption") or ""),
    "scene_max_chars": lambda draft: len(draft.get("scene") or ""),
    "hashtag_count": lambda draft: len(draft.get("hashtags") or []),
    "primary_cta_max": lambda draft: 1 if (draft.get("cta") or "").strip() else 0,
    "emoji_max": lambda draft: len(_EMOJI.findall(_full_text(draft))),
    "emoji": lambda draft: len(_EMOJI.findall(_full_text(draft))),
    "sms_ucs2_3_segment": lambda draft: utf16_length(_body(draft)) if not is_gsm7_encodable(_body(draft)) else 0,
    "sms_gsm7_3_segment": lambda draft: len(_body(draft)) if is_gsm7_encodable(_body(draft)) else 0,
}


class _MissingFormatValue(dict):
    # A typo in a human-written message must not stop the whole pipeline.
    def __missing__(self, key):
        return ""


def _validation_message(spec: dict, value: int) -> str:
    """Say by how much, since the writer cannot fix a bare "spec violation"."""
    excess = value - spec["value_max"] if spec["value_max"] is not None and value > spec["value_max"] else 0
    missing = spec["value_min"] - value if spec["value_min"] is not None and value < spec["value_min"] else 0

    if "{" in spec["message"]:
        return spec["message"].format_map(_MissingFormatValue(excess=excess, missing=missing, actual=value))

    detail = f", over by {excess}" if excess else f", short by {missing}" if missing else ""
    return f"{spec['message']} (currently {value}{detail})"


def _auto_fix(draft: dict, spec: dict) -> str | None:
    if spec["rule_key"] == "hashtag_count" and len(draft.get("hashtags") or []) > spec["value_max"]:
        excess = len(draft["hashtags"]) - spec["value_max"]
        draft["hashtags"] = draft["hashtags"][: spec["value_max"]]
        return f"Removed {excess} excess hashtags (kept the first {spec['value_max']})"
    return None


def _is_violated(spec: dict, value: int) -> bool:
    operator = spec["op"]
    return (
        (operator == "max" and value > spec["value_max"])
        or (operator == "min" and value < spec["value_min"])
        or (operator == "range" and not spec["value_min"] <= value <= spec["value_max"])
        or (operator == "forbid" and value > 0)
    )


def _load_specs(channel: str) -> list[dict]:
    with db.get_session() as session:
        rows = session.query(db.ChannelSpec).filter_by(channel=channel).all()
        if not rows:
            raise MissingSpecError(f"Channel `{channel}` has no rows in `channel_specs`.")
        return [
            {
                "rule_key": row.rule_key,
                "op": row.op,
                "value_min": row.value_min,
                "value_max": row.value_max,
                "rule_type": row.rule_type,
                "source_tier": row.source_tier,
                "source_url": row.source_url,
                "message": row.message,
            }
            for row in rows
        ]


def validate(draft: dict) -> dict:
    """Check one draft. Callers must use the returned `draft`, which may contain safe auto-fixes."""
    channel = draft.get("channel", "")
    specs = _load_specs(channel)

    draft = utils.normalize_draft_nfc(draft)
    violations: list[dict] = []
    auto_fix_notes: list[str] = []
    checked_rules: list[str] = []
    unchecked_rules: list[dict] = []

    for spec in specs:
        measure = _MEASURES.get(spec["rule_key"])
        if measure is None:
            unchecked_rules.append(
                {
                    "rule_key": spec["rule_key"],
                    "rule_type": spec["rule_type"],
                    "source_tier": spec["source_tier"],
                    "source_url": spec["source_url"],
                    "message": f"Rule {spec['rule_key']} is not checked by code",
                }
            )
            continue
        checked_rules.append(spec["rule_key"])

        value = measure(draft)
        if spec["rule_key"].startswith("sms_") and value == 0:
            continue  # this message uses the other encoding
        if not _is_violated(spec, value):
            continue
        if note := _auto_fix(draft, spec):
            auto_fix_notes.append(note)
            continue

        violations.append(
            {
                "rule_key": spec["rule_key"],
                "value": value,
                "limit": spec["value_max"] if spec["op"] != "range" else spec["value_min"],
                "rule_type": spec["rule_type"],
                "source_tier": spec["source_tier"],
                "source_url": spec["source_url"],
                "message": _validation_message(spec, value),
            }
        )

    return {
        "ok": not violations,
        "violations": violations,
        "draft": draft,
        "auto_fixed": bool(auto_fix_notes),
        "auto_fix_notes": auto_fix_notes,
        "checked_rules": checked_rules,
        "unchecked_rules": unchecked_rules,
        "segment_count": count_segments(_body(draft)) if channel == "direct_message" else None,
    }

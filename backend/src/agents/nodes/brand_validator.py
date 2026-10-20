"""Tier 2: brand rules read from `brand_rules`. `block` stops publishing; `warning` only flags for the reviewer."""

from __future__ import annotations

import re

from src.models import db
from src.models.campaign_state import draft_text_fields, render_outbound_text

RETIRED_BRAND_RULE_KEYS = frozenset({"academic_disclaimer", "academic_disclaimer_short"})


def is_active_brand_rule(rule_key: str) -> bool:
    return rule_key not in RETIRED_BRAND_RULE_KEYS


class MissingRuleError(RuntimeError):
    """An empty rule table must raise: passing would silently skip the whole tier."""


def _load_rules() -> list[dict]:
    with db.get_session() as session:
        rules = [rule for rule in session.query(db.BrandRule).all() if is_active_brand_rule(rule.rule_key)]
        if not rules:
            raise MissingRuleError("The `brand_rules` table is empty.")
        return [
            {
                "rule_group": rule.rule_group,
                "rule_key": rule.rule_key,
                "pattern": rule.pattern,
                "mode": rule.mode,
                "trigger_pattern": rule.trigger_pattern,
                "applicable_channel": rule.applicable_channel,
                "severity": rule.severity,
                "message": rule.message,
                "source_url": rule.source_url,
            }
            for rule in rules
        ]


def _violation(rule: dict, field: str | None = None, match: re.Match | None = None) -> dict:
    return {
        "rule_group": rule["rule_group"],
        "rule_key": rule["rule_key"],
        "severity": rule["severity"],
        "message": rule["message"],
        "source_url": rule["source_url"],
        "field": field,
        "start": match.start() if match else None,
        "end": match.end() if match else None,
        "matched_text": match.group() if match else None,
    }


def validate(draft: dict) -> dict:
    """`forbidden` rules scan each field so the UI can highlight; `required` rules scan the full outbound text."""
    rules = _load_rules()
    fields = draft_text_fields(draft)
    # The real outbound order matters: some rules anchor to the very start of the message.
    outbound_text = render_outbound_text(draft)
    channel = draft.get("channel", "")

    violations: list[dict] = []
    for rule in rules:
        if rule["applicable_channel"] and channel and rule["applicable_channel"] != channel:
            continue
        pattern = re.compile(rule["pattern"], re.IGNORECASE)

        if rule["mode"] == "forbidden":
            for field, text in fields.items():
                if match := pattern.search(text):
                    violations.append(_violation(rule, field, match))
            continue

        trigger = rule["trigger_pattern"]
        if trigger and not re.search(trigger, outbound_text, re.IGNORECASE):
            continue
        if not pattern.search(outbound_text):
            violations.append(_violation(rule))

    block_count = sum(1 for violation in violations if violation["severity"] == "block")
    return {
        "ok": block_count == 0,
        "violations": violations,
        "block_count": block_count,
        "warning_count": len(violations) - block_count,
    }

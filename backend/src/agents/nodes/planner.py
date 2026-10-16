"""Build a structured campaign plan. Code computes the valid angles and CTAs; the LLM chooses and explains."""

from __future__ import annotations

import json

from src import utils
from src.agents import guardrails, llm
from src.models import db
from src.models.campaign_state import CampaignState, normalize_channel

MIN_RATIONALE_LENGTH = 15

SYSTEM_PROMPT = """You are an electric-vehicle marketing planner in Vietnam, writing for a dealership's \
marketing team.

Return ONLY one JSON object, with no explanation outside it:

{
  "main_message": "one sentence, the message running through the whole campaign",
  "channels": [
    {
      "channel": "<channel name>",
      "variants": [
        {"variant": "A", "angle": "<choose from the supplied list>",
         "cta": "<choose from the supplied list>",
         "rationale": "1-2 sentences: why this angle fits this segment and funnel stage"}
      ]
    }
  ]
}

MANDATORY RULES:
1. Each channel has exactly 2 variants, and they MUST use different `angle` values. A/B only means something \
when the two versions test different hypotheses, not different wording.
2. `angle` and `cta` must come ONLY from the list supplied for that channel.
3. NEVER write prices, driving range or battery capacity figures. The system inserts numbers from the database \
later; any number you write is blocked and must be redone.
4. `rationale` gives the strategic reason; it does not repeat the content to be written.
5. Write `main_message` and `rationale` in Vietnamese. Keep JSON keys, `channel`, `variant` and `angle` as given."""


def _has_active_promotion(model_id: str) -> bool:
    # The `urgency` angle needs a real running promotion; otherwise it would be fake scarcity.
    with db.get_session() as session:
        promotions = session.query(db.Promotion).filter(db.Promotion.model_id == model_id).all()
        return any(utils.is_active(promotion.valid_from, promotion.valid_to) for promotion in promotions)


def _select_for_channels(brief: dict) -> dict[str, dict]:
    has_promotion = _has_active_promotion(brief.get("model_id", ""))
    with db.get_session() as session:
        angles = [
            row.angle
            for row in session.query(db.Angle).all()
            if brief["funnel_stage"] in (row.funnel_stages or []) and (not row.condition or has_promotion)
        ]
        cta_rows = session.query(db.CtaMap).filter_by(funnel_stage=brief["funnel_stage"]).all()
        return {
            channel: {"angles": angles, "ctas": [row.cta_text for row in cta_rows if row.channel == channel]}
            for channel in brief["channels"]
        }


def _parse(raw: str) -> dict:
    start, end = raw.find("{"), raw.rfind("}")
    if start < 0 or end < start:
        raise ValueError("no JSON object in the output")
    return json.loads(raw[start : end + 1])


def _normalize_plan_channels(plan: dict) -> dict:
    for channel_plan in plan.get("channels", []):
        channel = channel_plan.get("channel")
        if isinstance(channel, str):
            channel_plan["channel"] = normalize_channel(channel)
    return plan


def _repair_and_flag(plan: dict, selections: dict[str, dict]) -> dict:
    """Repair invalid picks without spending a retry, and flag them: the LLM's rationale no longer matches."""
    for channel_plan in plan["channels"]:
        allowed = selections[channel_plan["channel"]]
        used_angles: list[str] = []

        for variant in channel_plan["variants"]:
            variant.setdefault("needs_review", False)

            if variant.get("angle") not in allowed["angles"] or variant.get("angle") in used_angles:
                remaining = [angle for angle in allowed["angles"] if angle not in used_angles]
                variant["angle"] = remaining[0]
                variant["needs_review"] = True
            used_angles.append(variant["angle"])

            if variant.get("cta") not in allowed["ctas"]:
                variant["cta"] = allowed["ctas"][0]
                variant["needs_review"] = True
    return plan


def _validate_shape(plan: dict, brief: dict) -> None:
    if not isinstance(plan.get("main_message"), str) or not plan["main_message"].strip():
        raise ValueError("missing `main_message`")

    planned_channels = {channel_plan.get("channel") for channel_plan in plan.get("channels", [])}
    if missing := set(brief["channels"]) - planned_channels:
        raise ValueError(f"missing channels: {sorted(missing)}")

    for channel_plan in plan["channels"]:
        channel = channel_plan.get("channel")
        variants = channel_plan.get("variants") or []
        if len(variants) != 2:
            raise ValueError(f"channel {channel} must have exactly 2 variants")

        # Labels are half of the `drafts` key: duplicates would make one draft overwrite the other.
        labels = [variant.get("variant") for variant in variants]
        if any(not isinstance(label, str) or not label.strip() for label in labels):
            raise ValueError(f"channel {channel} has a variant without a `variant` label")
        if len(set(labels)) != len(labels):
            raise ValueError(f"channel {channel} has duplicate variant labels: {labels}")

        for variant in variants:
            if len((variant.get("rationale") or "").strip()) < MIN_RATIONALE_LENGTH:
                raise ValueError(f"variant {variant.get('variant')} is missing a rationale")


def planner_node(state: CampaignState) -> dict:
    brief = state.get("brief") or {}

    safe_brief = state.get("safe_brief")
    if not safe_brief:
        return {"status": "failed", "error": "`safe_brief` is missing; the planner must not use the raw brief."}

    selections = _select_for_channels(brief)
    options = "\n".join(
        f"- Channel `{channel}`: valid angles = {values['angles']}; valid CTAs = {values['ctas']}"
        for channel, values in selections.items()
    )
    user_message = f"{safe_brief}\n\nAllowed choices:\n{options}"

    last_error = ""
    for attempt in range(2):
        raw = llm.generate(
            role="planner",
            system_prompt=SYSTEM_PROMPT,
            user_message=user_message
            if attempt == 0
            else f"{user_message}\n\nYour last output was invalid: {last_error}. Return EXACTLY one JSON object.",
        )
        try:
            plan = _normalize_plan_channels(_parse(raw))
            _validate_shape(plan, brief)
            plan = _repair_and_flag(plan, selections)
        except (ValueError, KeyError, TypeError, IndexError) as error:
            last_error = str(error)[:200]
            continue

        llm_text = plan["main_message"] + " ".join(
            variant["rationale"] for channel_plan in plan["channels"] for variant in channel_plan["variants"]
        )
        if raw_numbers := guardrails.find_raw_numbers(llm_text):
            return {"status": "failed", "error": f"The plan contains raw numbers: {raw_numbers}."}

        return {"status": "plan_ok", "plan": plan}

    return {"status": "failed", "error": f"Planner output was invalid after 2 attempts: {last_error}"}

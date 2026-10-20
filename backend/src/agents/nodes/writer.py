"""Writer: generates each channel x variant. Enforces only the schema and the no-raw-number rule.

Channel limits are stated in the prompt but enforced by tier 1, so the writer and channel retry budgets stay separate.
"""

from __future__ import annotations

import json
import logging
import re

from pydantic import BaseModel, Field, ValidationError

from src import content_locale, utils
from src.agents import guardrails, llm, rag
from src.agents.nodes import channel_validator
from src.agents.nodes.brand_validator import is_active_brand_rule
from src.agents.nodes.channel_validator import is_gsm7_encodable, utf16_length
from src.models import catalog, db
from src.models.campaign_state import CampaignState, normalize_channel

LOGGER = logging.getLogger(__name__)

RAG_CHUNK_COUNT = 3

# Groq allows 12,000 tokens per minute; four parallel calls hit that immediately.
BATCH_SIZE = 2


class FanpageDraft(BaseModel):
    hook: str = Field(..., min_length=1, max_length=500)
    body: str = Field(..., min_length=1, max_length=5000)
    hashtags: list[str] = Field(..., max_length=10)
    cta: str = Field(..., min_length=1, max_length=100)


class MessageDraft(BaseModel):
    body: str = Field(..., min_length=1, max_length=500)


class InstagramDraft(BaseModel):
    caption: str = Field(..., min_length=1, max_length=2200)
    hashtags: list[str] = Field(..., max_length=10)
    cta: str = Field(..., min_length=1, max_length=100)


class TikTokDraft(BaseModel):
    hook: str = Field(..., min_length=1, max_length=100)
    scene: str = Field(..., min_length=1, max_length=500)
    voiceOver: str = Field(..., min_length=1, max_length=500)  # noqa: N815 - JSON field name shown to the LLM
    overlay: str = Field(..., min_length=1, max_length=100)
    cta: str = Field(..., min_length=1, max_length=100)
    caption: str = Field(..., min_length=1, max_length=2200)
    hashtags: list[str] = Field(..., max_length=10)


CHANNEL_SCHEMAS: dict[str, type[BaseModel]] = {
    "facebook": FanpageDraft,
    "direct_message": MessageDraft,
    "instagram": InstagramDraft,
    "tiktok": TikTokDraft,
}

SYSTEM_PROMPT = (
    """You write electric-vehicle marketing content for a dealership in Vietnam. Write ALL content in natural \
Vietnamese, speaking to the reader like a real person, with no stock phrases.

Return ONLY one JSON object matching the described schema, with no explanation.

NUMBERS, THE MOST IMPORTANT RULE:
NEVER write price, driving range or battery capacity figures yourself. Use exactly the placeholders listed; the \
system inserts real numbers from the database and cites the source. Any number you write is blocked and must be redone.

These quantified claims are also blocked unless a matching placeholder is listed: savings or comparison \
percentages, self-computed unit costs (e.g. VND per km), customer counts or social proof, and warranty durations. \
The only ways out: do not make that claim, or use exactly a listed placeholder.

SOCIAL PROOF, even WITHOUT digits:
These phrases are BLOCKED and force a full rewrite: """
    + content_locale.BANNED_SOCIAL_PROOF_EXAMPLES
    + """.
No source counts users, so any such sentence is invented. Vague phrases like """
    + content_locale.VAGUE_SOCIAL_PROOF_EXAMPLE
    + """ are not auto-blocked but nothing backs them either. Write about the CAR and what it does for the reader.

DRIVING RANGE, copy this pattern exactly; this is the most common mistake:

    CORRECT: """
    + content_locale.RANGE_CORRECT_EXAMPLE
    + """
    WRONG:   """
    + content_locale.RANGE_WRONG_EXAMPLES[0]
    + """
    WRONG:   """
    + content_locale.RANGE_WRONG_EXAMPLES[1]
    + """

The word `km` RIGHT AFTER `{{range_km:...}}` is mandatory. Without it the sentence renders as \""""
    + content_locale.RANGE_RENDERED_WRONG_EXAMPLE
    + """\", a bare number with no unit, and it is blocked even though the placeholder was right.

`{{range_km_standard:...}}` resolves to the standard's NAME ("NEDC"/"WLTP"), not a number. It may only follow \""""
    + content_locale.RANGE_STANDARD_LEAD_IN
    + """\" and never \""""
    + content_locale.RANGE_WRONG_LEAD_IN
    + """\".

The same applies to other numbers: `{{battery_kwh:...}} kWh`.
`{{price_vnd:...}}` ALREADY carries the currency symbol; adding a unit word renders as \""""
    + content_locale.PRICE_DOUBLE_UNIT_EXAMPLE
    + """\". Use it directly: `"""
    + content_locale.PRICE_CORRECT_EXAMPLE
    + """`.

WRITE FOR A READER WITH A QUESTION:
Good content answers a specific worry; it does not list features."""
)

_AD_LABEL = re.compile(content_locale.AD_LABEL_PATTERN, re.IGNORECASE)
_OPT_OUT = re.compile(content_locale.OPT_OUT_PATTERN, re.IGNORECASE)
_RANGE_PLACEHOLDER = re.compile(r"\{\{range_km:([A-Za-z0-9-]+):([a-z_]+)\}\}")
_REGEX_SYNTAX = re.compile(r"[\\(\[|?*+^$]")


@utils.cached_reference()
def channel_constraints(channel: str) -> str:
    with db.get_session() as session:
        rows = session.query(db.ChannelSpec).filter_by(channel=channel).all()
        lines = []
        for row in rows:
            if row.op == "range":
                limit = f"{row.value_min}-{row.value_max}"
            elif row.op == "max":
                limit = f"at most {row.value_max}"
            elif row.op == "min":
                limit = f"at least {row.value_min}"
            else:
                limit = "do not use"
            lines.append(f"- {row.rule_key}: {limit} ({row.unit})")
        return "\n".join(lines)


@utils.cached_reference()
def mandatory_rules(channel: str) -> str:
    """Only required + block rules. Listing banned words here would just suggest them to the model."""
    with db.get_session() as session:
        rows = (
            session.query(db.BrandRule)
            .filter(db.BrandRule.mode == "required", db.BrandRule.severity == "block")
            .all()
        )
        lines = []
        for row in rows:
            if not is_active_brand_rule(row.rule_key):
                continue
            if row.applicable_channel and row.applicable_channel != channel:
                continue
            # Quote the pattern only when it is readable text, or the model copies the regex syntax.
            pattern = (row.pattern or "").strip()
            is_literal = pattern and not _REGEX_SYNTAX.search(pattern)
            lines.append(f"- {row.message}" + (f"; the content MUST contain: `{pattern}`" if is_literal else ""))
        return "\n".join(lines)


def _attach_ad_label(draft: dict, channel: str) -> dict:
    if channel != "direct_message":
        return draft
    body = str(draft.get("body") or "")
    if not _AD_LABEL.search(body):
        draft["body"] = f"{content_locale.AD_LABEL} {body.lstrip()}"
    return draft


def _attach_opt_out(draft: dict, channel: str) -> dict:
    """Must run last: the opt-out rule requires this sentence at the very end of the message."""
    if channel != "direct_message":
        return draft
    body = str(draft.get("body") or "").rstrip()
    if not _OPT_OUT.search(body):
        draft["body"] = f"{body} {content_locale.OPT_OUT_SENTENCE}".strip()
    return draft


def _attach_range_standard(draft: dict) -> dict:
    """A stated range needs its standard, so add it from the placeholder the model already used."""
    text = " ".join(value for value in draft.values() if isinstance(value, str))
    if "{{range_km_standard:" in text:
        return draft
    match = _RANGE_PLACEHOLDER.search(text)
    if not match:
        return draft
    placeholder = f"{{{{range_km_standard:{match.group(1)}:{match.group(2)}}}}}"
    note = content_locale.RANGE_STANDARD_NOTE.format(placeholder=placeholder)
    draft["body"] = f"{str(draft.get('body') or '').rstrip()}\n{note}"
    return draft


@utils.cached_reference()
def promotion_reminder(model_id: str) -> str:
    """Campaign dates read like an offer deadline, so tell the writer whether any promotion really exists."""
    with db.get_session() as session:
        rows = session.query(db.Promotion).filter_by(model_id=model_id).all()
        active = [
            f"- {row.description} (until {row.valid_to})"
            for row in rows
            if utils.is_active(row.valid_from, row.valid_to)
        ]

    if not active:
        return (
            f"PROMOTIONS: there is NO active program for {model_id} in the verified data.\n"
            "NEVER mention offers, promotions, gifts, discounts or offer deadlines, even if the brief has campaign "
            "dates. Those dates are the POSTING schedule, not the term of an offer. Mentioning one blocks the content "
            "as an invented program.\n\n"
        )
    return "ACTIVE PROMOTIONS (mention only these):\n" + "\n".join(active) + "\n\n"


def length_reminder(channel: str) -> str:
    """Stated as a command with a word count: as a bare table value the model overran the budget tenfold."""
    if channel != "direct_message":
        return ""
    return (
        "MESSAGE LENGTH, A HARD CONSTRAINT THAT BLOCKS ON VIOLATION:\n"
        "Accented Vietnamese uses UCS-2. The system adds the [QC] label and the opt-out sentence itself. Do NOT "
        "write those two parts, or they will appear twice.\n"
        "Your part is the main content only, at most 161 characters (about 24-28 words). Use the room to state one "
        "complete benefit plus a clear call to action: do not cut a sentence short just to be shorter, and do not "
        "pad it either.\n"
        "Exceeding 161 characters in your part is BLOCKED, with no exceptions.\n"
        "Write it like a real text message, NOT a miniature post.\n\n"
    )


def _warranty_lines(model_id: str, variant_name: str, variant) -> list[str]:
    lines = []
    if variant.warranty_vehicle_years is not None and variant.warranty_vehicle_km is not None:
        lines += [
            f"- New vehicle warranty, years ({variant_name}): {{{{warranty_vehicle_years:{model_id}:{variant_name}}}}}",
            f"- New vehicle warranty, km ({variant_name}): {{{{warranty_vehicle_km:{model_id}:{variant_name}}}}}",
        ]
    if variant.warranty_high_voltage_battery_years is not None and variant.warranty_high_voltage_battery_km is not None:
        lines += [
            f"- High-voltage battery warranty, years ({variant_name}): "
            f"{{{{warranty_high_voltage_battery_years:{model_id}:{variant_name}}}}}",
            f"- High-voltage battery warranty, km ({variant_name}): "
            f"{{{{warranty_high_voltage_battery_km:{model_id}:{variant_name}}}}}",
        ]
    return lines


@utils.cached_reference()
def placeholder_hint(model_id: str) -> str:
    """List placeholders for the variants that really exist, so the model is never invited to use a missing one."""
    with db.get_session() as session:
        variants = catalog.variant_ground_truth(session, model_id)
        names = sorted(variants)
        if not names:
            return f"(no variant data for {model_id}; is the brief's model wrong?)"

        lines = [f"Real variants of {model_id}: {', '.join(names)}. Every placeholder MUST use one of them."]
        has_warranty = False
        for name in names:
            variant = variants[name]
            # Only attributes with exactly one value, so the fact checker never has to guess.
            if variant.price_battery_included_vnd is not None:
                lines.append(f"- Price with battery ({name}): {{{{price_vnd:{model_id}:{name}:battery_included}}}}")
            if variant.range_km is not None:
                lines.append(f"- Driving range ({name}): {{{{range_km:{model_id}:{name}}}}}")
            if variant.battery_kwh is not None:
                lines.append(f"- Battery capacity ({name}): {{{{battery_kwh:{model_id}:{name}}}}}")
            if variant.range_km_standard:
                lines.append(f"- Range standard ({name}): {{{{range_km_standard:{model_id}:{name}}}}}")
            warranty_lines = _warranty_lines(model_id, name, variant)
            has_warranty = has_warranty or bool(warranty_lines)
            lines += warranty_lines

    lines.append("A missing variant or price type is blocked: two variants differ by tens of millions of VND.")
    if not has_warranty:
        lines.append(
            "WARRANTY: there is NO warranty placeholder because the verified data has no such figure. Every warranty "
            f"NUMBER is blocked and forces a full rewrite: {content_locale.WARRANTY_NUMBER_EXAMPLES}. A generic "
            f"sentence such as {content_locale.WARRANTY_GENERIC_EXAMPLE} is not auto-blocked but proves nothing. To "
            "convey peace of mind, rely on what is actually listed above."
        )
    return "\n".join(lines)


@utils.cached_reference()
def _rag_context(model_id: str, angle_text: str) -> tuple[str, list[str]]:
    """Return the wrapped block plus raw chunks for the judge. RAG is optional context, so failures must not block."""
    try:
        results = rag.retrieve(
            db.get_engine(), f"{model_id} {angle_text}".strip(), model_id=model_id, k=RAG_CHUNK_COUNT
        )
    except Exception as error:  # noqa: BLE001 - a broken optional layer must not stop the writer
        LOGGER.warning(
            "rag_retrieval_failed model=%s error_type=%s error=%s; writing without source documents, "
            "and the judge will drop the source_grounding axis",
            model_id,
            type(error).__name__,
            error,
        )
        return "", []
    if not results:
        LOGGER.warning("RAG returned no chunks for model `%s`; the judge will drop source_grounding.", model_id)
        return "", []
    chunks = [f"[{result.source_url}, {result.snapshot_date}]\n{result.text}" for result in results]
    return guardrails.wrap_untrusted("\n\n".join(chunks), tag="documents") + "\n\n", chunks


@utils.cached_reference()
def _objection_table() -> str:
    with db.get_session() as session:
        rows = session.query(db.Objection).order_by(db.Objection.id).all()
        return "\n".join(
            f'- "{row.objection}" -> {row.response_content} (avoid: {row.common_mistake})' for row in rows
        )


def _find_variant(plan: dict, channel: str, variant: str) -> dict | None:
    for channel_plan in plan.get("channels", []):
        if normalize_channel(channel_plan.get("channel")) == normalize_channel(channel):
            for item in channel_plan.get("variants", []):
                if item.get("variant") == variant:
                    return item
    return None


def _validate_numbers(draft: dict) -> list[str]:
    text = " ".join(value for value in draft.values() if isinstance(value, str))
    return guardrails.find_raw_numbers(text) + guardrails.invalid_placeholders(text)


def _validate_message_budget(draft: dict) -> list[str]:
    """Bring SMS length errors into the writer's retry, using tier 1's own segment measure."""
    if draft.get("channel") != "direct_message":
        return []

    tier_result = channel_validator.validate(draft)
    errors = [
        f"{violation['message']}; the whole message is {tier_result['segment_count']} segments"
        for violation in tier_result["violations"]
        if violation["rule_key"] in {"sms_ucs2_3_segment", "sms_gsm7_3_segment"}
    ]

    with db.get_session() as session:
        budget_row = session.query(db.ChannelSpec).filter_by(channel="direct_message", rule_key="sms_content_budget").one()
        ucs2_row = session.query(db.ChannelSpec).filter_by(channel="direct_message", rule_key="sms_ucs2_3_segment").one()
        budget = int(budget_row.value_max)
        reserved = int(ucs2_row.value_max) - budget

    body = draft.get("body") or ""
    free_content = max(0, utf16_length(body) - reserved)
    # The budget applies to UCS-2 only; GSM-7 messages have a larger ceiling, checked by tier 1 above.
    if not is_gsm7_encodable(body) and free_content > budget:
        errors.append(
            f"free content is {free_content} UCS-2 units, {free_content - budget} over the budget of {budget}; "
            f"the whole message is {tier_result['segment_count']} segments"
        )
    return errors


def parse_draft_response(raw: str, schema: type[BaseModel]) -> dict:
    start, end = raw.find("{"), raw.rfind("}")
    if start < 0 or end < start:
        raise ValueError(f"no JSON object found; output={' '.join(raw.split())[:120]!r}")
    return schema(**json.loads(raw[start : end + 1])).model_dump()


@utils.cached_reference()
def _model_catalog() -> dict[str, tuple[str, ...]]:
    with db.get_session() as session:
        return catalog.model_identity_catalog(session)


@utils.cached_reference()
def _angle_message_axis(angle: str) -> str | None:
    with db.get_session() as session:
        row = session.get(db.Angle, angle)
        return row.message_axis if row is not None else None


def _build_user_message(
    state: CampaignState,
    channel: str,
    variant: str,
    plan_variant: dict,
    angle_text: str,
    rag_block: str,
) -> str:
    model_id = str((state.get("brief") or {}).get("model_id") or "").strip()
    schema = CHANNEL_SCHEMAS[channel]
    return (
        f"{state.get('safe_brief')}\n\n"
        f"{guardrails.wrap_untrusted(state.get('plan') or {}, tag='plan')}\n\n"
        f"{rag_block}"
        f"SELECTED VEHICLE MODEL: `{model_id}`.\n"
        "Every vehicle name, model hashtag, and product placeholder in the output must use exactly "
        f"`{model_id}`. Never substitute another vehicle model.\n\n"
        f"Write for channel `{channel}`, variant {variant}.\n"
        f"Required angle: `{plan_variant['angle']}`: {angle_text}\n"
        f'Required call to action: "{plan_variant["cta"]}"\n\n'
        f"Channel constraints (follow them to avoid rework):\n{channel_constraints(channel)}\n\n"
        f"{length_reminder(channel)}"
        f"{promotion_reminder(model_id)}"
        f"MUST appear in the content, or it is blocked:\n{mandatory_rules(channel)}\n\n"
        f"Allowed placeholders:\n{placeholder_hint(model_id)}\n\n"
        f"Common buyer worries and how to answer them:\n{_objection_table()}\n\n"
        f"JSON schema: {json.dumps(schema.model_json_schema()['properties'], ensure_ascii=False)}"
    )


def finalize_draft(draft: dict, channel: str) -> dict:
    """Normalize, then add what code can add reliably; the opt-out sentence must stay last."""
    draft = utils.normalize_draft_nfc(draft)
    draft = _attach_range_standard(draft)
    draft = _attach_ad_label(draft, channel)
    return _attach_opt_out(draft, channel)


def write_content(state: CampaignState, channel: str, variant: str) -> dict:
    """Generate one draft, returning `{"status": "draft_ok", "draft": ...}` or a failure."""
    brief = state.get("brief") or {}
    expected_model_id = str(brief.get("model_id") or "").strip()

    if not state.get("safe_brief"):
        return {"status": "failed", "error": "`safe_brief` is missing; the writer must not use the raw brief."}

    plan_variant = _find_variant(state.get("plan") or {}, channel, variant)
    if plan_variant is None:
        return {"status": "failed", "error": f"The plan has no variant {variant} for channel {channel}"}

    schema = CHANNEL_SCHEMAS[channel]
    model_catalog = _model_catalog()
    message_axis = _angle_message_axis(plan_variant["angle"])
    angle_text = message_axis if message_axis is not None else plan_variant["angle"]
    rag_block, rag_chunks = _rag_context(expected_model_id, angle_text)
    user_message = _build_user_message(state, channel, variant, plan_variant, angle_text, rag_block)

    last_error = ""
    for attempt in range(2):
        try:
            raw = llm.generate(
                role="writer",
                system_prompt=SYSTEM_PROMPT,
                user_message=(
                    user_message
                    if attempt == 0
                    else f"{user_message}\n\nYour last output was invalid: {last_error}. Fix exactly that."
                ),
                response_validator=lambda text: parse_draft_response(text, schema),
            )
            draft = parse_draft_response(raw, schema)
        except (*llm.RECOVERABLE_LLM_ERRORS, ValueError, ValidationError) as error:
            last_error = str(error)[:200]
            continue

        draft = finalize_draft(draft, channel)

        if mismatched := guardrails.find_mismatched_models(draft, expected_model_id, model_catalog):
            expected = guardrails.canonical_model_id(expected_model_id, model_catalog)
            last_error = (
                f"wrong vehicle model(s) {mismatched}; the selected campaign model is {expected}. "
                "Rewrite every vehicle name, hashtag, and placeholder for the selected model"
            )
            continue

        if violations := _validate_numbers(draft):
            last_error = f"wrote raw numbers {violations} instead of placeholders"
            continue

        draft_with_metadata = draft | {"channel": channel, "variant": variant, "angle": plan_variant["angle"]}
        if violations := _validate_message_budget(draft_with_metadata):
            last_error = "; ".join(violations)
            continue

        return {"status": "draft_ok", "draft": draft_with_metadata, "rag_documents": rag_chunks}

    return {"status": "failed", "error": f"Writer {channel}/{variant}: {last_error}"}


def list_write_targets(plan: dict) -> list[tuple[str, str]]:
    return [
        (normalize_channel(channel_plan["channel"]), item["variant"])
        for channel_plan in plan.get("channels", [])
        for item in channel_plan.get("variants", [])
    ]


def split_batches(targets: list[tuple[str, str]], batch_size: int = BATCH_SIZE) -> list[list[tuple[str, str]]]:
    return [targets[index : index + batch_size] for index in range(0, len(targets), batch_size)]


def _build_rewrite_prompt(
    channel: str,
    model_id: str,
    draft: dict,
    instruction: str,
    target_text: str,
    schema_properties: dict,
) -> str:
    prompt = (
        "You help a marketer edit a marketing draft. Keep the content in Vietnamese.\n\n"
        f"THE MARKETER'S INSTRUCTION:\n{guardrails.wrap_untrusted(instruction, tag='edit_instruction')}\n\n"
    )
    if target_text:
        prompt += (
            f"Apply it especially to this part:\n{guardrails.wrap_untrusted(target_text, tag='edit_target')}\n"
            "Then adjust the rest of the article so it reads smoothly.\n\n"
        )
    return prompt + (
        f"CURRENT DRAFT (JSON):\n{guardrails.wrap_untrusted(draft, tag='current_draft')}\n\n"
        f"SELECTED VEHICLE MODEL: `{model_id}`.\n"
        f"Every placeholder and vehicle name must be exactly `{model_id}`. Never substitute another vehicle model.\n\n"
        f"Constraints of channel `{channel}` still apply:\n{channel_constraints(channel)}\n\n"
        f"{length_reminder(channel)}"
        f"{promotion_reminder(model_id)}"
        f"MUST appear in the content:\n{mandatory_rules(channel)}\n\n"
        f"Allowed placeholders:\n{placeholder_hint(model_id)}\n\n"
        "PRODUCE THE NEW EDITED DRAFT.\n"
        f"Return ONLY one JSON object matching this schema:\n{json.dumps(schema_properties, ensure_ascii=False)}"
    )


def rewrite_draft(draft: dict, channel: str, model_id: str, instruction: str, target_text: str = "") -> dict:
    """Rewrite an existing draft from a marketer's instruction; saving and revalidation belong to the caller."""
    schema = CHANNEL_SCHEMAS.get(channel)
    if schema is None:
        raise ValueError(f"AI editing is not supported for channel {channel}")
    raw = llm.generate(
        role="writer",
        system_prompt=SYSTEM_PROMPT,
        user_message=_build_rewrite_prompt(
            channel, model_id, draft, instruction, target_text, schema.model_json_schema()["properties"]
        ),
        response_validator=lambda text: parse_draft_response(text, schema),
    )
    return finalize_draft(parse_draft_response(raw, schema), channel) | {"angle": draft.get("angle")}

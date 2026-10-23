"""Tier 3: resolve placeholders from `product_variants`, check promotion dates and record citations. Costs no tokens.

Unverified ground truth still gets inserted, but it must never be labelled as matching its source.
"""

from __future__ import annotations

import re

from src import content_locale, utils
from src.agents import guardrails
from src.config import get_settings
from src.models import catalog, db
from src.models.campaign_state import draft_text_fields

# A signature set by automation is not a human attestation.
MACHINE_SIGNATURE_PREFIX = "MACHINE"


def is_ground_truth_verified() -> bool:
    """Whether a person has checked `product_variants` against the source pages."""
    signature = get_settings().ground_truth_verified_by.strip()
    return bool(signature) and not signature.startswith(MACHINE_SIGNATURE_PREFIX)


# `{{name:MODEL:variant}}` or `{{name:MODEL:variant:price_type}}`.
_PLACEHOLDER = re.compile(r"\{\{([a-z_]+):([A-Za-z0-9_-]+):([a-z_]+)(?::([a-z_]+))?\}\}")
_ANY_PLACEHOLDER = re.compile(r"\{\{[^}]*\}\}")
_PROMOTION_CLAIM = re.compile(content_locale.PROMOTION_CLAIM_PATTERN, re.IGNORECASE)
_DATE_IN_TEXT = re.compile(r"\b\d{1,2}/\d{1,2}/\d{4}\b")

VERIFIED_LABEL = "✓ matches source"
UNVERIFIED_LABEL = "⚠ value inserted, source NOT verified"

PRICE_TYPES = {"battery_included": ("price_battery_included_vnd", "battery included")}
PRICE_BASIS_LABELS = {
    "list_price": "list price",
    "after_incentive": "price after incentive",
    "estimated_on_road": "estimated on-road price",
}
VARIANT_LABELS = {"eco": "Eco", "plus": "Plus", "standard": ""}

# placeholder -> (condition, is a distance in km)
_WARRANTY_FIELDS = {
    "warranty_vehicle_years": ("new vehicle warranty", False),
    "warranty_vehicle_km": ("new vehicle warranty", True),
    "warranty_high_voltage_battery_years": ("high-voltage battery warranty, first purchase with a new vehicle", False),
    "warranty_high_voltage_battery_km": ("high-voltage battery warranty, first purchase with a new vehicle", True),
}
_GROUND_TRUTH_NUMBER_FIELDS = (
    "price_battery_included_vnd",
    "range_km",
    "battery_kwh",
    "warranty_vehicle_years",
    "warranty_vehicle_km",
    "warranty_high_voltage_battery_years",
    "warranty_high_voltage_battery_km",
)


def _format_integer(value: int) -> str:
    return f"{value:,}".replace(",", ".")


def _format_currency(value: int) -> str:
    return _format_integer(value) + content_locale.CURRENCY_SYMBOL


def _format_number(value: float) -> str:
    return str(int(value)) if float(value).is_integer() else f"{value}".replace(".", ",")


def _variant_label(variant_key: str) -> str:
    public_key = catalog.STANDARD_VARIANT if variant_key == catalog.BASE_VARIANT_KEY else variant_key
    return VARIANT_LABELS.get(public_key, public_key)


def _resolve_price(model_id: str, price_type: str | None, variant) -> tuple[str, str, str]:
    if price_type is None:
        raise ValueError("price placeholder needs a price type, e.g. `:battery_included`.")
    if price_type == "battery_lease":
        raise ValueError(f"{model_id} is no longer sold with a battery lease; do not write about it")
    if price_type not in PRICE_TYPES:
        raise ValueError(f"invalid price type `{price_type}`")

    column, type_label = PRICE_TYPES[price_type]
    price = getattr(variant, column)
    if price is None:
        raise ValueError(f"{model_id} has no {type_label} price in ground truth; do not write about it")
    if variant.price_basis is None:
        raise ValueError(f"{model_id} has no price basis in product_variants; an unclear price cannot be stamped")
    basis = PRICE_BASIS_LABELS.get(variant.price_basis, variant.price_basis)
    condition = f"{basis}, {type_label}, variant {_variant_label(variant.variant_key)}".rstrip()
    return str(price), _format_currency(price), condition


def _resolve(name: str, model_id: str, price_type: str | None, variant) -> tuple[str, str, str]:
    """Return (raw_value, display_value, condition); raises ValueError with a readable reason."""
    if name == "price_vnd":
        return _resolve_price(model_id, price_type, variant)

    variant_key = variant.variant_key
    if name == "range_km":
        if variant.range_km is None or variant.range_km_standard is None:
            raise ValueError(f"{model_id} variant {variant_key} has no range or range standard")
        condition = f"{variant.range_km_standard} standard, variant {_variant_label(variant_key)}".rstrip()
        return str(variant.range_km), _format_number(variant.range_km), condition
    if name == "battery_kwh":
        if variant.battery_kwh is None:
            raise ValueError(f"{model_id} variant {variant_key} has no battery capacity")
        return str(variant.battery_kwh), _format_number(variant.battery_kwh), "nominal capacity"
    if name == "range_km_standard":
        if variant.range_km_standard is None:
            raise ValueError(f"{model_id} variant {variant_key} has no range standard")
        return variant.range_km_standard, variant.range_km_standard, ""

    if name in _WARRANTY_FIELDS:
        condition, is_distance = _WARRANTY_FIELDS[name]
        value = getattr(variant, name)
        if value is None:
            raise ValueError(f"{model_id} variant {variant_key} has no `{name}`; do not infer it from another model")
        return str(value), _format_integer(value) if is_distance else str(value), condition

    raise ValueError(f"placeholder `{name}` is not supported")


def _save_citations(engine, content_item_id: int, citations: list[dict]) -> None:
    """Upsert, because LangGraph reruns whole nodes on resume."""
    with db.session_for(engine) as session:
        for citation in citations:
            row = (
                session.query(db.ContentCitation)
                .filter_by(content_item_id=content_item_id, placeholder=citation["placeholder"])
                .one_or_none()
            )
            if row is None:
                session.add(db.ContentCitation(content_item_id=content_item_id, **citation))
            else:
                for key, value in citation.items():
                    setattr(row, key, value)
        session.commit()


def _load_ground_truth(engine, model_id: str) -> tuple[dict, dict, list[dict]]:
    with db.session_for(engine) as session:
        variants = catalog.variant_ground_truth(session, model_id)
        model_catalog = catalog.model_identity_catalog(session)
        promotions = [
            {
                "id": promotion.id,
                "description": promotion.description,
                "valid_from": promotion.valid_from,
                "valid_to": promotion.valid_to,
                "source_url": promotion.source_url,
                "snapshot_date": promotion.snapshot_date,
            }
            for promotion in session.query(db.Promotion).filter_by(model_id=model_id)
        ]
        session.expunge_all()
    return variants, model_catalog, promotions


def _semantic_errors(draft: dict, variants: dict) -> list[dict]:
    """Must run before placeholders are resolved, while system-filled values can still be told from invented ones."""
    standards = {str(variant.range_km_standard or "").strip() for variant in variants.values()}
    numbers: set[float] = set()
    for variant in variants.values():
        for column in _GROUND_TRUTH_NUMBER_FIELDS:
            value = getattr(variant, column, None)
            if isinstance(value, (int, float)):
                numbers.add(float(value))

    text = " ".join(draft_text_fields(draft).values())
    return [
        {"placeholder": "semantic claim", "reason": violation}
        for violation in guardrails.validate_semantics(
            text,
            ground_truth_standards={standard for standard in standards if standard},
            # None when nothing loaded: unknown ground truth must not turn every number into a violation.
            ground_truth_numbers=numbers or None,
        )
    ]


def _promotion_findings(text: str, promotions: list[dict], model_id: str, timestamp: str) -> tuple[list[dict], list[dict]]:
    if not _PROMOTION_CLAIM.search(text):
        return [], []

    dates = _DATE_IN_TEXT.findall(text)
    active = [promotion for promotion in promotions if utils.is_active(promotion["valid_from"], promotion["valid_to"])]
    if not active:
        reason = f"no active promotion for `{model_id}` in the `promotions` table"
        return [{"placeholder": dates[0] if dates else "promotion", "reason": reason}], []

    errors: list[dict] = []
    citations: list[dict] = []
    for literal in dates:
        iso_date = utils.dmy_to_iso(literal)
        match = next(
            (promotion for promotion in active if iso_date is not None and iso_date in {promotion["valid_from"], promotion["valid_to"]}),
            None,
        )
        if match is None:
            errors.append({"placeholder": literal, "reason": f"date `{literal}` matches no promotion valid_from/valid_to"})
            continue
        citations.append(
            {
                "placeholder": literal,
                "raw_value": iso_date,
                "display_value": literal,
                "source_table": "promotions",
                "source_key": str(match["id"]),
                "source_url": match["source_url"],
                "snapshot_date": match["snapshot_date"],
                "condition": match["description"],
                "resolved_at": timestamp,
            }
        )
    return errors, citations


def validate(draft: dict, model_id: str, content_item_id: int | None = None) -> dict:
    """Callers must use the returned `draft`, which has the numbers inserted."""
    engine = db.get_engine()
    variants, model_catalog, promotions = _load_ground_truth(engine, model_id)

    draft = utils.normalize_draft_nfc(draft)
    citations: list[dict] = []
    errors: list[dict] = []
    timestamp = utils.current_timestamp()

    if mismatched := guardrails.find_mismatched_models(draft, model_id, model_catalog):
        expected = guardrails.canonical_model_id(model_id, model_catalog)
        errors.append(
            {
                "placeholder": "model_id",
                "reason": f"output mentions {', '.join(mismatched)} but the campaign model is {expected}",
            }
        )

    errors += _semantic_errors(draft, variants)

    def replace_placeholder(match: re.Match) -> str:
        name, placeholder_model, variant_key, price_type = match.groups()
        literal = match.group(0)

        if placeholder_model != model_id or not variants:
            errors.append({"placeholder": literal, "reason": f"model `{placeholder_model}` is not in `product_variants`"})
            return literal

        variant = variants.get(variant_key)
        if variant is None:
            errors.append(
                {
                    "placeholder": literal,
                    "reason": f"`{placeholder_model}` has no variant `{variant_key}`; available: {sorted(variants)}",
                }
            )
            return literal

        try:
            raw_value, display_value, condition = _resolve(name, placeholder_model, price_type, variant)
        except ValueError as error:
            errors.append({"placeholder": literal, "reason": str(error)})
            return literal

        citations.append(
            {
                "placeholder": literal,
                "raw_value": raw_value,
                "display_value": display_value,
                "source_table": "product_variants",
                "source_key": f"{placeholder_model}/{variant_key}",
                "source_url": variant.source_url,
                "snapshot_date": variant.snapshot_date,
                "condition": condition,
                "resolved_at": timestamp,
            }
        )
        return display_value

    for field, text in draft_text_fields(draft).items():
        draft[field] = _PLACEHOLDER.sub(replace_placeholder, text)

    outbound_text = " ".join(draft_text_fields(draft).values())
    for leftover in _ANY_PLACEHOLDER.findall(outbound_text):
        if not any(error["placeholder"] == leftover for error in errors):
            errors.append({"placeholder": leftover, "reason": "malformed or unsupported placeholder"})

    promotion_errors, promotion_citations = _promotion_findings(outbound_text, promotions, model_id, timestamp)
    errors += promotion_errors
    citations += promotion_citations

    if content_item_id is not None and citations:
        _save_citations(engine, content_item_id, citations)

    verified = is_ground_truth_verified()
    return {
        "ok": not errors,
        "draft": draft,
        "citations": citations,
        "errors": errors,
        "verified": verified,
        "label": VERIFIED_LABEL if verified else UNVERIFIED_LABEL,
    }

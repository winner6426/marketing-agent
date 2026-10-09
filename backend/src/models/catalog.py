from __future__ import annotations

import re

from sqlalchemy import select

from src.models import db

# `product_variants.variant_key` for single-variant models, exposed to placeholders as `standard`.
BASE_VARIANT_KEY = "base"
STANDARD_VARIANT = "standard"


def _public_variant(variant_key: str) -> str:
    return STANDARD_VARIANT if variant_key == BASE_VARIANT_KEY else variant_key


def model_id_from_product_id(product_id: str) -> str:
    value = product_id.strip().lower()
    match = re.fullmatch(r"vf-(\d+)", value)
    return f"VF{match.group(1)}" if match else value.upper()


def product_id_from_model_id(model_id: str) -> str:
    return re.sub(r"^vf(?=\d)", "vf-", model_id.strip().lower())


def brief_catalog(session) -> list[dict]:
    """Products selectable in a brief: only those with typed ground truth."""
    rows = session.execute(
        select(db.Product, db.ProductVariant)
        .join(db.ProductVariant, db.ProductVariant.product_id == db.Product.product_id)
        .order_by(db.Product.name, db.ProductVariant.variant_key)
    ).all()
    grouped: dict[str, dict] = {}
    for product, variant in rows:
        item = grouped.setdefault(
            product.product_id,
            {
                "product_id": product.product_id,
                "model_id": model_id_from_product_id(product.product_id),
                "name": product.name,
                "vehicle_type": product.vehicle_type,
                "source_url": variant.source_url,
                "snapshot_date": variant.snapshot_date,
                "variants": [],
            },
        )
        item["variants"].append(_public_variant(variant.variant_key))
        if variant.snapshot_date >= item["snapshot_date"]:
            item["source_url"] = variant.source_url
            item["snapshot_date"] = variant.snapshot_date
    return sorted(grouped.values(), key=lambda item: item["name"].casefold())


def model_identity_catalog(session) -> dict[str, tuple[str, ...]]:
    return {
        item["model_id"]: (item["model_id"], item["product_id"], item["name"])
        for item in brief_catalog(session)
    }


def variant_ground_truth(session, model_id: str) -> dict[str, db.ProductVariant]:
    product_id = product_id_from_model_id(model_id)
    rows = session.query(db.ProductVariant).filter_by(product_id=product_id).all()
    return {_public_variant(row.variant_key): row for row in rows}

"""ORM tables plus engine and session helpers."""

from __future__ import annotations

from contextlib import contextmanager
from enum import StrEnum
from pathlib import Path
from uuid import uuid4

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Enum,
    Float,
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    String,
    Text,
    UniqueConstraint,
    create_engine,
    event,
    inspect,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column

from src.models.campaign_state import (
    CAMPAIGN_STATUSES,
    CONTENT_STATUSES,
    SCHEDULE_STATUSES,
)
from src.utils import current_timestamp

VEHICLE_TYPES = ("passenger_car", "commercial_vehicle", "electric_motorcycle", "electric_bicycle")
APP_CHANNELS = ("facebook", "direct_message", "instagram", "tiktok")
CHANNEL_PLATFORMS = ("facebook", "instagram", "tiktok", "zalo", "website", "email")
CHANNEL_STATUSES = ("active", "inactive")
CHANNEL_RULE_TYPES = ("platform_limit", "style_policy")
SOURCE_TIERS = ("technical_standard", "official_document", "third_party", "internal_policy")
RULE_OPERATORS = ("max", "min", "range", "forbid")
RULE_UNITS = ("characters", "words", "seconds", "count")
BRAND_RULE_MODES = ("forbidden", "required")
RULE_SEVERITIES = ("block", "warning")
MARKETING_ANGLES = ("economic", "family", "tech", "social_proof", "urgency")
FUNNEL_STAGES = ("awareness", "consideration", "intent")
DOCUMENT_COLLECTIONS = (
    "brand_docs",
    "product_docs",
    "campaign_examples",
    "blog_docs",
    "promo_docs",
    "other_docs",
)
DOCUMENT_USAGE_RIGHTS = ("self_authored", "permission_granted", "open_license", "short_quote")
CONTENT_VARIANTS = ("A", "B")
APPROVAL_DECISIONS = ("approve", "reject")


EMBED_DIM = 1024

USER_ID_TYPE = String(36).with_variant(UUID(as_uuid=False), "postgresql")


class Base(DeclarativeBase):
    pass


def _sql_in(column: str, options: tuple[str, ...] | set[str]) -> str:
    values = sorted(options) if isinstance(options, set) else options
    return f"{column} IN ({', '.join(repr(value) for value in values)})"


def _named_enum(name: str, values: tuple[str, ...]) -> Enum:
    return Enum(*values, name=name, native_enum=True, create_constraint=True)


def _iso_date_shape(column: str) -> str:
    return f"length({column}) = 10 AND substr({column}, 5, 1) = '-' AND substr({column}, 8, 1) = '-'"


class CarModel(Base):
    __tablename__ = "car_models"

    model_id: Mapped[str] = mapped_column(String(20), primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    source_url: Mapped[str] = mapped_column(String(300))
    snapshot_date: Mapped[str] = mapped_column(String(10))

    __table_args__ = (
        CheckConstraint("length(trim(model_id)) > 0", name="ck_car_models_id_not_blank"),
        CheckConstraint("length(trim(name)) > 0", name="ck_car_models_name_not_blank"),
        CheckConstraint("length(trim(source_url)) > 0", name="ck_car_models_source_not_blank"),
        CheckConstraint(_iso_date_shape("snapshot_date"), name="ck_car_models_snapshot_iso"),
    )


class Product(Base):
    __tablename__ = "products"

    product_id: Mapped[str] = mapped_column(String(100), primary_key=True)
    name: Mapped[str] = mapped_column(String(300))
    vehicle_type: Mapped[str] = mapped_column(_named_enum("vehicle_type", VEHICLE_TYPES), index=True)
    source_url: Mapped[str] = mapped_column(String(500))
    snapshot_date: Mapped[str] = mapped_column(String(10))

    __table_args__ = (
        CheckConstraint("length(trim(product_id)) > 0", name="ck_products_id_not_blank"),
        CheckConstraint("length(trim(name)) > 0", name="ck_products_name_not_blank"),
        CheckConstraint("length(trim(source_url)) > 0", name="ck_products_source_not_blank"),
        CheckConstraint(_iso_date_shape("snapshot_date"), name="ck_products_snapshot_iso"),
    )


class ProductAttribute(Base):
    __tablename__ = "product_attributes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    product_id: Mapped[str] = mapped_column(ForeignKey("products.product_id", ondelete="CASCADE"), index=True)
    variant_key: Mapped[str] = mapped_column(String(50), default="base")
    attribute_name: Mapped[str] = mapped_column(String(80), index=True)
    value: Mapped[object] = mapped_column(JSON)
    unit: Mapped[str] = mapped_column(String(30), default="")
    evidence_text: Mapped[str] = mapped_column(Text)

    __table_args__ = (
        CheckConstraint("length(trim(variant_key)) > 0", name="ck_product_attributes_variant"),
        CheckConstraint("length(trim(attribute_name)) > 0", name="ck_product_attributes_name"),
        CheckConstraint("length(trim(evidence_text)) > 0", name="ck_product_attributes_evidence"),
    )


class ProductVariant(Base):
    __tablename__ = "product_variants"

    product_id: Mapped[str] = mapped_column(ForeignKey("products.product_id", ondelete="CASCADE"), primary_key=True)
    variant_key: Mapped[str] = mapped_column(String(50), primary_key=True)
    price_battery_included_vnd: Mapped[int | None] = mapped_column(Integer, nullable=True)
    price_without_battery_vnd: Mapped[int | None] = mapped_column(Integer, nullable=True)
    price_basis: Mapped[str | None] = mapped_column(String(30), nullable=True)
    battery_kwh: Mapped[float | None] = mapped_column(Float, nullable=True)
    max_power_kw: Mapped[float | None] = mapped_column(Float, nullable=True)
    rated_power_kw: Mapped[float | None] = mapped_column(Float, nullable=True)
    max_speed_kmh: Mapped[float | None] = mapped_column(Float, nullable=True)
    range_km: Mapped[float | None] = mapped_column(Float, nullable=True)
    range_assist_km: Mapped[float | None] = mapped_column(Float, nullable=True)
    range_extra_battery_km: Mapped[float | None] = mapped_column(Float, nullable=True)
    range_km_standard: Mapped[str | None] = mapped_column(String(30), nullable=True)
    length_mm: Mapped[float | None] = mapped_column(Float, nullable=True)
    width_mm: Mapped[float | None] = mapped_column(Float, nullable=True)
    height_mm: Mapped[float | None] = mapped_column(Float, nullable=True)
    payload_kg: Mapped[float | None] = mapped_column(Float, nullable=True)
    cargo_volume_l: Mapped[float | None] = mapped_column(Float, nullable=True)
    seats_min: Mapped[int | None] = mapped_column(Integer, nullable=True)
    seats_max: Mapped[int | None] = mapped_column(Integer, nullable=True)
    warranty_vehicle_years: Mapped[int | None] = mapped_column(Integer, nullable=True)
    warranty_vehicle_km: Mapped[int | None] = mapped_column(Integer, nullable=True)
    warranty_high_voltage_battery_years: Mapped[int | None] = mapped_column(Integer, nullable=True)
    warranty_high_voltage_battery_km: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source_url: Mapped[str] = mapped_column(String(500))
    snapshot_date: Mapped[str] = mapped_column(String(10))

    __table_args__ = (
        CheckConstraint("length(trim(variant_key)) > 0", name="ck_product_variants_variant"),
        CheckConstraint(
            "price_basis IS NULL OR price_basis IN ('list_price', 'after_incentive', 'estimated_on_road')",
            name="ck_product_variants_price_basis",
        ),
        CheckConstraint("length(trim(source_url)) > 0", name="ck_product_variants_source"),
        CheckConstraint(_iso_date_shape("snapshot_date"), name="ck_product_variants_snapshot_iso"),
        CheckConstraint("seats_min IS NULL OR seats_min > 0", name="ck_product_variants_seats_min_positive"),
        CheckConstraint("seats_max IS NULL OR seats_max > 0", name="ck_product_variants_seats_max_positive"),
        CheckConstraint(
            "seats_min IS NULL OR seats_max IS NULL OR seats_min <= seats_max",
            name="ck_product_variants_seats_order",
        ),
        CheckConstraint(
            "warranty_vehicle_years IS NULL OR warranty_vehicle_years > 0",
            name="ck_product_variants_warranty_vehicle_years_positive",
        ),
        CheckConstraint(
            "warranty_vehicle_km IS NULL OR warranty_vehicle_km > 0",
            name="ck_product_variants_warranty_vehicle_km_positive",
        ),
        CheckConstraint(
            "warranty_high_voltage_battery_years IS NULL OR warranty_high_voltage_battery_years > 0",
            name="ck_product_variants_warranty_battery_years_positive",
        ),
        CheckConstraint(
            "warranty_high_voltage_battery_km IS NULL OR warranty_high_voltage_battery_km > 0",
            name="ck_product_variants_warranty_battery_km_positive",
        ),
    )


class Promotion(Base):
    __tablename__ = "promotions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    model_id: Mapped[str] = mapped_column(ForeignKey("car_models.model_id", ondelete="CASCADE"), index=True)
    description: Mapped[str] = mapped_column(String(500))

    valid_from: Mapped[str] = mapped_column(String(10))
    valid_to: Mapped[str] = mapped_column(String(10))
    source_url: Mapped[str] = mapped_column(String(300))
    snapshot_date: Mapped[str] = mapped_column(String(10))

    __table_args__ = (
        CheckConstraint("length(trim(description)) > 0", name="ck_promotions_description_not_blank"),
        CheckConstraint(_iso_date_shape("valid_from"), name="ck_promotions_valid_from_iso"),
        CheckConstraint(_iso_date_shape("valid_to"), name="ck_promotions_valid_to_iso"),
        CheckConstraint("valid_from <= valid_to", name="ck_promotions_valid_period"),
        CheckConstraint("length(trim(source_url)) > 0", name="ck_promotions_source_not_blank"),
        CheckConstraint(_iso_date_shape("snapshot_date"), name="ck_promotions_snapshot_iso"),
    )


class ChannelSpec(Base):
    __tablename__ = "channel_specs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    channel: Mapped[str] = mapped_column(_named_enum("app_channel", APP_CHANNELS), index=True)
    rule_key: Mapped[str] = mapped_column(String(50))
    rule_type: Mapped[str] = mapped_column(_named_enum("channel_rule_type", CHANNEL_RULE_TYPES))
    source_tier: Mapped[str] = mapped_column(_named_enum("source_tier", SOURCE_TIERS))

    op: Mapped[str] = mapped_column(_named_enum("rule_operator", RULE_OPERATORS))
    value_min: Mapped[int | None] = mapped_column(Integer, nullable=True)
    value_max: Mapped[int | None] = mapped_column(Integer, nullable=True)

    unit: Mapped[str] = mapped_column(_named_enum("rule_unit", RULE_UNITS))

    message: Mapped[str] = mapped_column(String(300))

    source_url: Mapped[str] = mapped_column(String(300), default="")
    snapshot_date: Mapped[str] = mapped_column(String(10))
    note: Mapped[str] = mapped_column(String(500), default="")


class Channel(Base):
    """A real publishing account; many accounts can map to one `app_channel` content format."""

    __tablename__ = "channels"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(120))

    platform: Mapped[str] = mapped_column(
        _named_enum("channel_platform", CHANNEL_PLATFORMS), index=True
    )

    account_ref: Mapped[str] = mapped_column(String(200))

    content_channel: Mapped[str | None] = mapped_column(
        _named_enum("app_channel", APP_CHANNELS), nullable=True, index=True
    )

    status: Mapped[str] = mapped_column(
        _named_enum("channel_status", CHANNEL_STATUSES), default="active", index=True
    )

    is_connected: Mapped[bool] = mapped_column(Boolean, default=False)

    note: Mapped[str] = mapped_column(String(500), default="")

    created_by_id: Mapped[str | None] = mapped_column(
        USER_ID_TYPE, ForeignKey("user_profiles.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[str] = mapped_column(String(30), default=current_timestamp)
    updated_at: Mapped[str] = mapped_column(
        String(30), default=current_timestamp, onupdate=current_timestamp
    )

    __table_args__ = (
        UniqueConstraint("platform", "account_ref", name="uq_channels_platform_account"),
        CheckConstraint("length(trim(name)) > 0", name="ck_channels_name_not_blank"),
        CheckConstraint("length(trim(account_ref)) > 0", name="ck_channels_account_ref_not_blank"),
    )


class BrandRule(Base):
    __tablename__ = "brand_rules"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    rule_group: Mapped[str] = mapped_column(String(30), index=True)
    rule_key: Mapped[str] = mapped_column(String(60), unique=True)

    pattern: Mapped[str] = mapped_column(String(1000))

    mode: Mapped[str] = mapped_column(_named_enum("brand_rule_mode", BRAND_RULE_MODES))

    trigger_pattern: Mapped[str] = mapped_column(String(500), default="")

    applicable_channel: Mapped[str] = mapped_column(String(20), default="")

    severity: Mapped[str] = mapped_column(_named_enum("rule_severity", RULE_SEVERITIES))

    message: Mapped[str] = mapped_column(String(300))

    source_url: Mapped[str] = mapped_column(String(300), default="")
    snapshot_date: Mapped[str] = mapped_column(String(10))
    note: Mapped[str] = mapped_column(String(500), default="")


class Angle(Base):
    __tablename__ = "angles"

    angle: Mapped[str] = mapped_column(_named_enum("marketing_angle", MARKETING_ANGLES), primary_key=True)
    message_axis: Mapped[str] = mapped_column(String(300))

    funnel_stages: Mapped[list] = mapped_column(JSON)

    condition: Mapped[str] = mapped_column(String(200), default="")
    description: Mapped[str] = mapped_column(String(500), default="")


class CtaMap(Base):
    __tablename__ = "cta_map"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    funnel_stage: Mapped[str] = mapped_column(_named_enum("funnel_stage", FUNNEL_STAGES), index=True)

    channel: Mapped[str] = mapped_column(_named_enum("app_channel", APP_CHANNELS), index=True)
    cta_text: Mapped[str] = mapped_column(String(100))
    note: Mapped[str] = mapped_column(String(300), default="")


class Objection(Base):
    __tablename__ = "objections"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    objection: Mapped[str] = mapped_column(String(200))
    segment: Mapped[str] = mapped_column(String(100))
    response_content: Mapped[str] = mapped_column(String(500))
    common_mistake: Mapped[str] = mapped_column(String(300))
    note: Mapped[str] = mapped_column(String(300), default="")


class DocChunk(Base):
    __tablename__ = "doc_chunks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    collection: Mapped[str] = mapped_column(String(30), index=True)
    doc_id: Mapped[str] = mapped_column(String(200), index=True)
    chunk_index: Mapped[int] = mapped_column(Integer)

    text: Mapped[str] = mapped_column(Text)

    model_id: Mapped[str | None] = mapped_column(
        ForeignKey("car_models.model_id", ondelete="CASCADE"), nullable=True, index=True
    )

    product_id: Mapped[str | None] = mapped_column(
        ForeignKey("products.product_id", ondelete="CASCADE"), nullable=True, index=True
    )
    channel: Mapped[str] = mapped_column(String(20), default="")
    doc_type: Mapped[str] = mapped_column(String(30), default="")

    source_url: Mapped[str] = mapped_column(String(300))
    snapshot_date: Mapped[str] = mapped_column(String(10))

    usage_rights: Mapped[str] = mapped_column(String(20))
    embedding_model: Mapped[str | None] = mapped_column(String(100), nullable=True)
    embedded_at: Mapped[str | None] = mapped_column(String(30), nullable=True)

    __table_args__ = (
        UniqueConstraint("collection", "doc_id", "chunk_index", name="uq_doc_chunks_collection_doc_index"),
        CheckConstraint(_sql_in("collection", DOCUMENT_COLLECTIONS), name="ck_doc_chunks_collection"),
        CheckConstraint("length(trim(source_url)) > 0", name="ck_doc_chunks_source_url_not_blank"),
        CheckConstraint("length(trim(snapshot_date)) > 0", name="ck_doc_chunks_snapshot_date_not_blank"),
        CheckConstraint(_sql_in("usage_rights", DOCUMENT_USAGE_RIGHTS), name="ck_doc_chunks_usage_rights"),
        CheckConstraint(
            "collection != 'campaign_examples' OR usage_rights != 'short_quote'",
            name="ck_doc_chunks_style_examples_require_strong_rights",
        ),
    )


class UserRole(StrEnum):
    MARKETER = "marketer"
    MANAGER = "manager"
    ADMIN = "admin"


class UserProfile(Base):
    __tablename__ = "user_profiles"

    id: Mapped[str] = mapped_column(USER_ID_TYPE, primary_key=True)
    email: Mapped[str] = mapped_column(String(320), index=True)
    name: Mapped[str] = mapped_column(String(200), default="")
    role: Mapped[UserRole] = mapped_column(
        Enum(
            UserRole,
            name="user_role",
            values_callable=lambda roles: [role.value for role in roles],
            validate_strings=True,
        ),
        default=UserRole.MARKETER,
    )
    is_active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[str] = mapped_column(String(30), default=current_timestamp)
    updated_at: Mapped[str] = mapped_column(String(30), default=current_timestamp, onupdate=current_timestamp)


class ChatSession(Base):
    __tablename__ = "chat_sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    marketer_id: Mapped[str] = mapped_column(
        USER_ID_TYPE, ForeignKey("user_profiles.id", ondelete="RESTRICT"), index=True
    )
    title: Mapped[str] = mapped_column(String(200), default="New conversation")
    created_at: Mapped[str] = mapped_column(String(30), default=current_timestamp)
    updated_at: Mapped[str] = mapped_column(String(30), default=current_timestamp, onupdate=current_timestamp)

    __table_args__ = (CheckConstraint("length(trim(title)) > 0", name="ck_chat_sessions_title_not_blank"),)


class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    chat_session_id: Mapped[str] = mapped_column(ForeignKey("chat_sessions.id", ondelete="CASCADE"), index=True)
    role: Mapped[str] = mapped_column(_named_enum("chat_message_role", ("user", "assistant")))
    content: Mapped[str] = mapped_column(Text)
    message_metadata: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[str] = mapped_column(String(30), default=current_timestamp, index=True)

    __table_args__ = (CheckConstraint("length(trim(content)) > 0", name="ck_chat_messages_content_not_blank"),)


class Campaign(Base):
    __tablename__ = "campaigns"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(200))

    brief: Mapped[dict] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(_named_enum("campaign_status", CAMPAIGN_STATUSES), default="draft")

    created_by: Mapped[str] = mapped_column(String(100))

    created_by_id: Mapped[str | None] = mapped_column(
        USER_ID_TYPE, ForeignKey("user_profiles.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    chat_session_id: Mapped[str | None] = mapped_column(
        ForeignKey("chat_sessions.id", ondelete="SET NULL"), nullable=True, index=True
    )
    created_at: Mapped[str] = mapped_column(String(30), default=current_timestamp)
    updated_at: Mapped[str] = mapped_column(String(30), default=current_timestamp, onupdate=current_timestamp)


class ContentItem(Base):
    __tablename__ = "content_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    campaign_id: Mapped[int] = mapped_column(ForeignKey("campaigns.id", ondelete="CASCADE"), index=True)
    channel: Mapped[str] = mapped_column(_named_enum("app_channel", APP_CHANNELS))
    variant: Mapped[str] = mapped_column(_named_enum("content_variant", CONTENT_VARIANTS), default="A")

    body: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(_named_enum("content_status", CONTENT_STATUSES), default="draft")

    meta: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[str] = mapped_column(String(30), default=current_timestamp)
    updated_at: Mapped[str] = mapped_column(String(30), default=current_timestamp, onupdate=current_timestamp)

    __table_args__ = (
        UniqueConstraint("campaign_id", "channel", "variant", name="uq_content_items_campaign_channel_variant"),
        UniqueConstraint("id", "campaign_id", name="uq_content_items_id_campaign"),
    )


class ScheduleSlot(Base):
    __tablename__ = "schedule_slots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    campaign_id: Mapped[int] = mapped_column(ForeignKey("campaigns.id", ondelete="CASCADE"), index=True)
    content_item_id: Mapped[int] = mapped_column(index=True, unique=True)

    scheduled_at: Mapped[str] = mapped_column(String(30), index=True)
    status: Mapped[str] = mapped_column(_named_enum("schedule_status", SCHEDULE_STATUSES), default="proposed")
    reason: Mapped[str] = mapped_column(String(500), default="")
    approved_by: Mapped[str] = mapped_column(String(100), default="")
    approved_by_id: Mapped[str | None] = mapped_column(
        USER_ID_TYPE, ForeignKey("user_profiles.id", ondelete="RESTRICT"), nullable=True
    )
    approved_at: Mapped[str | None] = mapped_column(String(30), nullable=True)
    created_at: Mapped[str] = mapped_column(String(30), default=current_timestamp)
    updated_at: Mapped[str] = mapped_column(String(30), default=current_timestamp, onupdate=current_timestamp)

    __table_args__ = (
        ForeignKeyConstraint(
            ["content_item_id", "campaign_id"],
            ["content_items.id", "content_items.campaign_id"],
            ondelete="CASCADE",
            name="fk_schedule_slots_content_item_campaign",
        ),
    )


class Approval(Base):
    __tablename__ = "approvals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    campaign_id: Mapped[int] = mapped_column(ForeignKey("campaigns.id", ondelete="CASCADE"), index=True)

    content_item_id: Mapped[int | None] = mapped_column(index=True, nullable=True)
    decision: Mapped[str] = mapped_column(_named_enum("approval_decision", APPROVAL_DECISIONS))
    reason: Mapped[str] = mapped_column(String(1000), default="")

    decided_by: Mapped[str] = mapped_column(String(100))
    decided_by_id: Mapped[str | None] = mapped_column(
        USER_ID_TYPE, ForeignKey("user_profiles.id", ondelete="RESTRICT"), nullable=True
    )

    decided_at: Mapped[str] = mapped_column(String(30), default=current_timestamp)

    __table_args__ = (
        ForeignKeyConstraint(
            ["content_item_id", "campaign_id"],
            ["content_items.id", "content_items.campaign_id"],
            ondelete="CASCADE",
            name="fk_approvals_content_item_campaign",
        ),
    )


class ContentVersion(Base):
    __tablename__ = "content_versions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    content_item_id: Mapped[int] = mapped_column(ForeignKey("content_items.id", ondelete="CASCADE"), index=True)

    version: Mapped[int] = mapped_column(Integer)

    body: Mapped[str] = mapped_column(Text)
    created_by: Mapped[str] = mapped_column(String(100))
    created_by_id: Mapped[str | None] = mapped_column(
        USER_ID_TYPE, ForeignKey("user_profiles.id", ondelete="RESTRICT"), nullable=True
    )

    created_at: Mapped[str] = mapped_column(String(30), default=current_timestamp)

    __table_args__ = (UniqueConstraint("content_item_id", "version", name="uq_content_versions_item_version"),)


class ContentCitation(Base):
    __tablename__ = "content_citations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    content_item_id: Mapped[int] = mapped_column(ForeignKey("content_items.id", ondelete="CASCADE"), index=True)

    placeholder: Mapped[str] = mapped_column(String(100))

    raw_value: Mapped[str] = mapped_column(String(100))

    display_value: Mapped[str] = mapped_column(String(100))
    source_table: Mapped[str] = mapped_column(String(50))
    source_key: Mapped[str] = mapped_column(String(50))
    source_url: Mapped[str] = mapped_column(String(300))
    snapshot_date: Mapped[str] = mapped_column(String(10))

    condition: Mapped[str] = mapped_column(String(200), default="")

    resolved_at: Mapped[str] = mapped_column(String(30), default=current_timestamp)

    __table_args__ = (UniqueConstraint("content_item_id", "placeholder", name="uq_citation_item_placeholder"),)


class IdempotencyKey(Base):
    __tablename__ = "idempotency_keys"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    key: Mapped[str] = mapped_column(String(100), index=True)
    endpoint: Mapped[str] = mapped_column(String(100))

    campaign_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)

    response_json: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[str] = mapped_column(String(30), default=current_timestamp)

    __table_args__ = (UniqueConstraint("key", "endpoint", name="uq_idempotency_key_endpoint"),)


PUBLICATION_CHANNELS = ("website", "facebook")


MANUAL_SEND_CHANNELS = ("zalo", "sms")

PUBLICATION_STATUSES = ("published", "failed", "removed")


METRIC_EVENT_TYPES = ("page_view", "scroll_50", "scroll_90", "cta_click", "lead_submit")


MEDIA_USAGE_RIGHTS = ("self_captured", "open_license", "permission_granted", "short_quote")


MEDIA_TYPES = ("exterior", "interior", "detail", "vehicle_color", "context", "graphic")


class MediaAsset(Base):
    __tablename__ = "media_assets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    model_id: Mapped[str] = mapped_column(String(20), default="", index=True)
    media_type: Mapped[str] = mapped_column(_named_enum("media_type", MEDIA_TYPES), index=True)

    path: Mapped[str] = mapped_column(String(300))
    alt_text: Mapped[str] = mapped_column(String(300))

    caption: Mapped[str] = mapped_column(String(300), default="")
    source_url: Mapped[str] = mapped_column(String(500))
    snapshot_date: Mapped[str] = mapped_column(String(10))
    usage_rights: Mapped[str] = mapped_column(_named_enum("media_usage_right", MEDIA_USAGE_RIGHTS))
    width: Mapped[int] = mapped_column(Integer, default=0)
    height: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[str] = mapped_column(String(30), default=current_timestamp)

    __table_args__ = (
        UniqueConstraint("path", name="uq_media_assets_path"),
        CheckConstraint("length(trim(alt_text)) > 0", name="ck_media_assets_alt_not_blank"),
        CheckConstraint("length(trim(source_url)) > 0", name="ck_media_assets_source_not_blank"),
    )


class ContentImage(Base):
    __tablename__ = "content_images"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    content_item_id: Mapped[int] = mapped_column(ForeignKey("content_items.id", ondelete="CASCADE"), index=True)
    media_asset_id: Mapped[int] = mapped_column(ForeignKey("media_assets.id", ondelete="RESTRICT"), index=True)

    sort_order: Mapped[int] = mapped_column(Integer, default=0)

    __table_args__ = (UniqueConstraint("content_item_id", "media_asset_id", name="uq_content_image"),)


class PublishedPost(Base):
    __tablename__ = "published_posts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    content_item_id: Mapped[int] = mapped_column(ForeignKey("content_items.id", ondelete="CASCADE"), index=True)
    channel: Mapped[str] = mapped_column(_named_enum("publication_channel", PUBLICATION_CHANNELS))

    external_id: Mapped[str | None] = mapped_column(String(200), nullable=True, default=None)
    url: Mapped[str] = mapped_column(String(500), default="")
    status: Mapped[str] = mapped_column(_named_enum("publication_status", PUBLICATION_STATUSES), default="published")

    error: Mapped[str] = mapped_column(String(1000), default="")
    published_by: Mapped[str] = mapped_column(String(100), default="")
    published_by_id: Mapped[str] = mapped_column(String(100), default="")
    published_at: Mapped[str] = mapped_column(String(30), default=current_timestamp)

    __table_args__ = (
        UniqueConstraint("content_item_id", "channel", name="uq_published_item_channel"),
        UniqueConstraint("channel", "external_id", name="uq_published_channel_external"),
    )


class MetricEvent(Base):
    __tablename__ = "metric_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    content_item_id: Mapped[int] = mapped_column(ForeignKey("content_items.id", ondelete="CASCADE"), index=True)
    event_type: Mapped[str] = mapped_column(_named_enum("metric_event_type", METRIC_EVENT_TYPES), index=True)

    session_id: Mapped[str] = mapped_column(String(64), index=True)

    path: Mapped[str] = mapped_column(String(300), default="")
    ts: Mapped[str] = mapped_column(String(30), default=current_timestamp)


class ManualSend(Base):
    __tablename__ = "manual_sends"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    content_item_id: Mapped[int] = mapped_column(ForeignKey("content_items.id", ondelete="CASCADE"), index=True)
    channel: Mapped[str] = mapped_column(_named_enum("manual_send_channel", MANUAL_SEND_CHANNELS))

    sent_content: Mapped[str] = mapped_column(Text, default="")

    recipients: Mapped[str] = mapped_column(String(300), default="")
    recipient_count: Mapped[int] = mapped_column(Integer, default=0)
    sent_by: Mapped[str] = mapped_column(String(100), default="")
    sent_by_id: Mapped[str] = mapped_column(String(100), default="")
    sent_at: Mapped[str] = mapped_column(String(30), default=current_timestamp)


LEAD_SOURCES = ("real", "simulated")


LEAD_STATUSES = ("new", "contacted", "test_drive_scheduled", "converted", "not_interested")


SIMULATED_PHONE_PREFIX = "09000000"


class Lead(Base):
    __tablename__ = "leads"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    full_name: Mapped[str] = mapped_column(String(100))
    phone_number: Mapped[str] = mapped_column(String(20), index=True)
    email: Mapped[str] = mapped_column(String(100), default="")
    region: Mapped[str] = mapped_column(String(100), default="")

    model_id: Mapped[str] = mapped_column(String(20), default="", index=True)

    content_item_id: Mapped[int | None] = mapped_column(
        ForeignKey("content_items.id", ondelete="SET NULL"), index=True, nullable=True
    )

    session_id: Mapped[str] = mapped_column(String(64), default="", index=True)
    source: Mapped[str] = mapped_column(_named_enum("lead_source", LEAD_SOURCES), default="real", index=True)
    status: Mapped[str] = mapped_column(_named_enum("lead_status", LEAD_STATUSES), default="new", index=True)
    note: Mapped[str] = mapped_column(String(1000), default="")
    created_at: Mapped[str] = mapped_column(String(30), default=current_timestamp)
    updated_at: Mapped[str] = mapped_column(String(30), default=current_timestamp, onupdate=current_timestamp)

    __table_args__ = (
        CheckConstraint(
            f"source <> 'simulated' OR phone_number LIKE '{SIMULATED_PHONE_PREFIX}%'",
            name="ck_leads_simulated_phone_uses_safe_prefix",
        ),
    )


AUDIT_ACTIONS = (
    "login",
    "create_campaign",
    "run_pipeline",
    "answer_brief",
    "submit_for_approval",
    "approve",
    "reject",
    "publish",
    "manual_send",
    "delete_campaign",
    "change_role",
)


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    user_id: Mapped[str] = mapped_column(String(100), index=True)
    login_name: Mapped[str] = mapped_column(String(50), default="", index=True)
    role: Mapped[str] = mapped_column(String(20), default="")
    action: Mapped[str] = mapped_column(_named_enum("audit_action", AUDIT_ACTIONS), index=True)

    target: Mapped[str] = mapped_column(String(50), default="", index=True)

    details: Mapped[str] = mapped_column(String(500), default="")
    created_at: Mapped[str] = mapped_column(String(30), default=current_timestamp, index=True)


def make_engine(url: str | None = None):
    if url is None:
        from src.config import get_settings

        url = get_settings().database_url

    if url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+psycopg://", 1)
    elif url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql+psycopg://", 1)

    is_sqlite = url.startswith("sqlite:")
    if url.startswith("sqlite:///"):
        path = Path(url.removeprefix("sqlite:///"))
        if path.parent != Path(""):
            path.parent.mkdir(parents=True, exist_ok=True)

    engine_kwargs = {}
    if url.startswith("postgresql+psycopg://"):
        engine_kwargs = {
            "pool_size": 3,
            "max_overflow": 1,
            "pool_timeout": 30,
            "pool_pre_ping": True,
            # Recycle below the Supabase pooler idle timeout to avoid "server closed the connection".
            "pool_recycle": 300,
        }

    engine = create_engine(url, **engine_kwargs)
    if is_sqlite:
        _enable_sqlite_foreign_keys(engine)
    return engine


def _enable_sqlite_foreign_keys(engine) -> None:
    @event.listens_for(engine, "connect")
    def _enable(dbapi_connection, _connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


class SchemaDriftError(RuntimeError):
    pass


def check_schema_drift(engine) -> None:
    """Fail early when an existing table lacks a column: `create_all()` never alters tables."""
    inspector = inspect(engine)
    differences: list[str] = []

    for table_name, table in Base.metadata.tables.items():
        if not inspector.has_table(table_name):
            continue
        existing_columns = {column["name"] for column in inspector.get_columns(table_name)}
        missing_columns = sorted({column.name for column in table.columns} - existing_columns)
        if missing_columns:
            differences.append(f"  - table `{table_name}` is missing: {', '.join(missing_columns)}")

    if differences:
        raise SchemaDriftError(
            "The database schema is older than the models:\n"
            + "\n".join(differences)
            + "\nDelete the local SQLite file, or add the columns with ALTER TABLE on Postgres."
        )


@contextmanager
def session_for(engine):
    session = Session(engine)
    try:
        yield session
    finally:
        session.close()


_default_engine = None


def get_engine():
    global _default_engine
    if _default_engine is None:
        _default_engine = make_engine()
        check_schema_drift(_default_engine)
        Base.metadata.create_all(_default_engine)
    return _default_engine


@contextmanager
def get_session():
    with session_for(get_engine()) as s:
        yield s

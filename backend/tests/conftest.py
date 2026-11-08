from __future__ import annotations

import json
import re
import shutil
import time

import jwt
import pytest
from fastapi.testclient import TestClient
from langgraph.checkpoint.memory import MemorySaver

from src import utils
from src.agents import campaign_graph, campaign_runner, llm
from src.config import get_settings
from src.main import app
from src.models import db
from src.services import auth_service
from tests import samples

SUPABASE_URL = "https://project.supabase.test"
JWT_SECRET = "a-test-secret-that-is-long-enough-for-hs256"

MARKETER_ID = "11111111-1111-1111-1111-111111111111"
OTHER_MARKETER_ID = "22222222-2222-2222-2222-222222222222"
MANAGER_ID = "33333333-3333-3333-3333-333333333333"
ADMIN_ID = "44444444-4444-4444-4444-444444444444"


@pytest.fixture(scope="session")
def database_template(tmp_path_factory):
    path = tmp_path_factory.mktemp("template") / "template.db"
    engine = db.make_engine(f"sqlite:///{path}")
    db.Base.metadata.create_all(engine)
    engine.dispose()
    return path


@pytest.fixture(autouse=True)
def environment(monkeypatch, tmp_path, database_template):
    """Give every test its own database, settings and clean process-wide caches."""
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("SUPABASE_URL", SUPABASE_URL)
    monkeypatch.setenv("SUPABASE_ANON_KEY", "anon-key")
    monkeypatch.setenv("SUPABASE_JWT_SECRET", JWT_SECRET)
    monkeypatch.setenv("AUTH_DEV_BYPASS", "false")
    monkeypatch.setenv("GROUND_TRUTH_VERIFIED_BY", "")
    monkeypatch.delenv("QDRANT_URL", raising=False)
    monkeypatch.delenv("CLOUDFLARE_ACCOUNT_ID", raising=False)
    get_settings.cache_clear()
    utils.clear_reference_cache()

    shutil.copy(database_template, tmp_path / "test.db")
    monkeypatch.setattr(db, "_default_engine", db.make_engine(f"sqlite:///{tmp_path}/test.db"))

    monkeypatch.setattr(auth_service, "LOGIN_RATE_LIMIT", utils.RateLimiter(1000, 60))
    monkeypatch.setattr(auth_service, "REGISTRATION_RATE_LIMIT", utils.RateLimiter(1000, 60))

    campaign_runner.set_runner(
        campaign_runner.CampaignRunner(app=campaign_graph.build_campaign_graph(MemorySaver()))
    )
    yield
    campaign_runner.set_runner(None)
    utils.clear_reference_cache()
    get_settings.cache_clear()


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client


def token_for(user_id: str, email: str = "user@example.com", *, secret: str = JWT_SECRET, expires_in: int = 3600) -> str:
    return jwt.encode(
        {
            "sub": user_id,
            "email": email,
            "aud": "authenticated",
            "iss": f"{SUPABASE_URL}/auth/v1",
            "exp": int(time.time()) + expires_in,
        },
        secret,
        algorithm="HS256",
    )


def auth_headers(user_id: str, *, key: str | None = None) -> dict[str, str]:
    headers = {"Authorization": f"Bearer {token_for(user_id)}"}
    if key:
        headers["Idempotency-Key"] = key
    return headers


@pytest.fixture
def users():
    with db.get_session() as session:
        for user_id, email, role in (
            (MARKETER_ID, "marketer@example.com", db.UserRole.MARKETER),
            (OTHER_MARKETER_ID, "other@example.com", db.UserRole.MARKETER),
            (MANAGER_ID, "manager@example.com", db.UserRole.MANAGER),
            (ADMIN_ID, "admin@example.com", db.UserRole.ADMIN),
        ):
            session.add(db.UserProfile(id=user_id, email=email, name=email, role=role))
        session.commit()


@pytest.fixture
def seeded_catalog():
    """The minimum reference data the pipeline needs for VF3 on two channels."""
    with db.get_session() as session:
        session.add(
            db.Product(
                product_id="vf-3",
                name="VinFast VF 3",
                vehicle_type="passenger_car",
                source_url="https://example.com/vf3",
                snapshot_date="2030-01-01",
            )
        )
        session.flush()
        session.add(
            db.ProductVariant(
                product_id="vf-3",
                variant_key="eco",
                price_battery_included_vnd=235000000,
                price_basis="list_price",
                range_km=210.0,
                range_km_standard="NEDC",
                battery_kwh=18.64,
                source_url="https://example.com/vf3",
                snapshot_date="2030-01-01",
            )
        )
        common = {"source_tier": "technical_standard", "snapshot_date": "2030-01-01", "source_url": "https://example.com"}
        session.add_all(
            [
                db.ChannelSpec(channel="facebook", rule_key="hook_max_chars", rule_type="platform_limit", op="max",
                               value_max=125, unit="characters", message="Hook too long", **common),
                db.ChannelSpec(channel="facebook", rule_key="hashtag_count", rule_type="style_policy", op="range",
                               value_min=3, value_max=5, unit="count", message="Hashtag count", **common),
                db.ChannelSpec(channel="direct_message", rule_key="sms_ucs2_3_segment", rule_type="platform_limit",
                               op="max", value_max=201, unit="characters", message="SMS too long", **common),
                db.ChannelSpec(channel="direct_message", rule_key="sms_content_budget", rule_type="style_policy",
                               op="max", value_max=161, unit="characters", message="SMS budget", **common),
            ]
        )
        session.add(
            db.BrandRule(
                rule_group="absolute_claims",
                rule_key="unprovable_superlative",
                pattern=samples.BANNED_PHRASE,
                mode="forbidden",
                severity="block",
                message="Unprovable superlative",
                snapshot_date="2030-01-01",
            )
        )
        session.add_all(
            [
                db.Angle(angle="economic", message_axis="Lower running cost",
                         funnel_stages=["awareness", "consideration", "intent"]),
                db.Angle(angle="family", message_axis="Safe for family",
                         funnel_stages=["awareness", "consideration", "intent"]),
            ]
        )
        session.add_all(
            [
                db.CtaMap(funnel_stage="consideration", channel="facebook", cta_text=samples.SAFE_CTA),
                db.CtaMap(funnel_stage="consideration", channel="direct_message", cta_text=samples.SAFE_CTA),
            ]
        )
        session.add(
            db.Objection(
                objection=samples.OBJECTION,
                segment="all",
                response_content=samples.OBJECTION_RESPONSE,
                common_mistake=samples.OBJECTION_MISTAKE,
            )
        )
        session.commit()


def valid_brief() -> dict:
    return {
        "goal": "test_drive",
        "model_id": "VF3",
        "segment": "Young families",
        "funnel_stage": "consideration",
        "channels": ["facebook", "direct_message"],
        "date_from": "2030-09-10",
        "date_to": "2030-09-20",
    }


def _plan_response(user_message: str) -> str:
    channels = re.findall(r"- Channel `(\w+)`", user_message)
    return json.dumps(
        {
            "main_message": samples.PLAN_MESSAGE,
            "channels": [
                {
                    "channel": channel,
                    "variants": [
                        {"variant": "A", "angle": "economic", "cta": samples.SAFE_CTA,
                         "rationale": samples.PLAN_RATIONALE},
                        {"variant": "B", "angle": "family", "cta": samples.SAFE_CTA,
                         "rationale": samples.PLAN_RATIONALE},
                    ],
                }
                for channel in channels
            ],
        },
        ensure_ascii=False,
    )


def _writer_response(user_message: str) -> str:
    if "channel `direct_message`" in user_message:
        return json.dumps({"body": samples.SMS_BODY}, ensure_ascii=False)
    return json.dumps(
        {
            "hook": samples.SAFE_HOOK,
            "body": f"{samples.SAFE_BODY} {samples.RANGE_BODY}",
            "hashtags": ["#VF3", "#XeDien", "#GiaDinh"],
            "cta": samples.SAFE_CTA,
        },
        ensure_ascii=False,
    )


class FakeLLM:
    def __init__(self):
        self.calls: list[str] = []
        self.writer_override = None

    def fallback(self, system_prompt, user_message, candidates, response_validator=None):
        if "marketing planner" in system_prompt:
            self.calls.append("planner")
            return _plan_response(user_message)
        if "write electric-vehicle marketing content" in system_prompt:
            self.calls.append("writer")
            if self.writer_override is not None:
                return self.writer_override(user_message)
            return _writer_response(user_message)
        self.calls.append("brief_analyst")
        return "{}"

    def single(self, provider, system_prompt, user_message, model=None):
        self.calls.append("judge")
        article = user_message.split("<article>\n", 1)[1].split("\n</article>", 1)[0]
        quote = article[:20]
        axes = ("source_grounding", "human_voice", "persuasiveness", "coherence", "distinctiveness")
        return json.dumps({axis: {"score": 4, "quote": quote} for axis in axes}, ensure_ascii=False)


@pytest.fixture
def fake_llm(monkeypatch):
    fake = FakeLLM()
    monkeypatch.setattr(llm, "call_llm_with_fallback", fake.fallback)
    monkeypatch.setattr(llm, "call_single_provider", fake.single)
    return fake

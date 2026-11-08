from __future__ import annotations

import json

import httpx
import pytest

from src import utils
from src.models import db
from src.services import auth_service
from tests.conftest import ADMIN_ID, MANAGER_ID, MARKETER_ID, auth_headers, token_for

NEW_USER_ID = "55555555-5555-5555-5555-555555555555"
PASSWORD = "correct-horse-battery"


def _session_body(user_id: str = NEW_USER_ID, email: str = "new@example.com") -> dict:
    return {
        "access_token": token_for(user_id, email),
        "refresh_token": "refresh-token",
        "expires_in": 3600,
        "user": {"id": user_id, "email": email},
    }


@pytest.fixture
def supabase(monkeypatch):
    """Route the adapter to a scripted Supabase and record each request."""
    requests: list[httpx.Request] = []
    responses: dict[str, tuple[int, dict]] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        path = request.url.path.removeprefix("/auth/v1")
        grant = request.url.params.get("grant_type")
        status, body = responses[f"{path}?{grant}" if grant else path]
        return httpx.Response(status, json=body)

    monkeypatch.setattr(auth_service, "_transport", lambda: httpx.MockTransport(handler))
    return responses, requests


def _profile(user_id: str) -> db.UserProfile | None:
    with db.get_session() as session:
        return session.get(db.UserProfile, user_id)


def test_register_creates_marketer_profile_and_returns_tokens(client, supabase):
    responses, requests = supabase
    responses["/signup"] = (200, _session_body())

    response = client.post(
        "/api/auth/register", json={"email": "new@example.com", "password": PASSWORD, "full_name": " New User "}
    )

    assert response.status_code == 201
    body = response.json()
    assert body["access_token"] and body["email_confirmation_required"] is False
    assert body["user"]["role"] == "marketer"
    assert body["user"]["full_name"] == "New User"
    assert requests[0].headers["apikey"] == "anon-key"
    assert _profile(NEW_USER_ID).role == db.UserRole.MARKETER


def test_register_cannot_choose_a_role(client, supabase):
    response = client.post(
        "/api/auth/register",
        json={"email": "new@example.com", "password": PASSWORD, "full_name": "X", "role": "admin"},
    )
    assert response.status_code == 422
    assert supabase[1] == []


def test_register_answer_does_not_reveal_whether_email_is_taken(client, supabase):
    responses, _ = supabase
    # Supabase returns a fake user with no identities for a taken email when confirmation is on.
    responses["/signup"] = (200, {"id": NEW_USER_ID, "email": "taken@example.com", "identities": []})
    taken = client.post("/api/auth/register", json={"email": "taken@example.com", "password": PASSWORD, "full_name": "X"})

    responses["/signup"] = (200, {"id": NEW_USER_ID, "email": "taken@example.com", "identities": [{"id": "1"}]})
    fresh = client.post("/api/auth/register", json={"email": "taken@example.com", "password": PASSWORD, "full_name": "X"})

    assert taken.status_code == fresh.status_code == 201
    assert taken.json() == fresh.json() == {"email": "taken@example.com", "email_confirmation_required": True}


def test_fake_signup_user_gets_no_profile(client, supabase):
    responses, _ = supabase
    responses["/signup"] = (200, {"id": NEW_USER_ID, "email": "taken@example.com", "identities": []})
    client.post("/api/auth/register", json={"email": "taken@example.com", "password": PASSWORD, "full_name": "X"})
    assert _profile(NEW_USER_ID) is None


@pytest.mark.parametrize(
    ("payload", "field"),
    [
        ({"email": "not-an-email", "password": PASSWORD, "full_name": "X"}, "body.email"),
        ({"email": "a@example.com", "password": "short", "full_name": "X"}, "body.password"),
        ({"email": "a@example.com", "password": PASSWORD, "full_name": "   "}, "body.full_name"),
    ],
)
def test_register_validates_input_without_echoing_it(client, supabase, payload, field):
    response = client.post("/api/auth/register", json=payload)
    assert response.status_code == 422
    assert response.json()["error"]["details"]["errors"][0]["field"] == field
    assert "short" not in json.dumps(response.json()["error"]["details"])
    assert supabase[1] == []


def test_duplicate_email_maps_to_conflict(client, supabase):
    responses, _ = supabase
    responses["/signup"] = (422, {"error_code": "user_already_exists", "msg": "User already registered"})
    response = client.post("/api/auth/register", json={"email": "a@example.com", "password": PASSWORD, "full_name": "X"})
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "email_already_registered"


def test_login_returns_tokens_and_role_from_database(client, supabase, users):
    responses, _ = supabase
    responses["/token?password"] = (200, _session_body(MANAGER_ID, "manager@example.com"))

    response = client.post("/api/auth/login", json={"email": "manager@example.com", "password": PASSWORD})

    assert response.status_code == 200
    assert response.json()["user"]["role"] == "manager"
    assert response.json()["access_token"]


def test_login_creates_missing_profile_as_marketer(client, supabase):
    responses, _ = supabase
    responses["/token?password"] = (200, _session_body())
    response = client.post("/api/auth/login", json={"email": "new@example.com", "password": PASSWORD})
    assert response.status_code == 200
    assert response.json()["user"]["role"] == "marketer"


def test_login_records_audit_entry(client, supabase, users):
    responses, _ = supabase
    responses["/token?password"] = (200, _session_body(MARKETER_ID, "marketer@example.com"))
    client.post("/api/auth/login", json={"email": "marketer@example.com", "password": PASSWORD})
    with db.get_session() as session:
        assert session.query(db.AuditLog).filter_by(user_id=MARKETER_ID, action="login").count() == 1


def test_wrong_password_is_unauthorized(client, supabase):
    responses, _ = supabase
    responses["/token?password"] = (400, {"error_code": "invalid_credentials", "msg": "Invalid login credentials"})
    response = client.post("/api/auth/login", json={"email": "a@example.com", "password": "wrong-password"})
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "invalid_credentials"
    assert response.headers["www-authenticate"] == "Bearer"


def test_disabled_account_cannot_log_in(client, supabase, users):
    responses, _ = supabase
    responses["/token?password"] = (200, _session_body(MARKETER_ID, "marketer@example.com"))
    with db.get_session() as session:
        session.get(db.UserProfile, MARKETER_ID).is_active = False
        session.commit()
    response = client.post("/api/auth/login", json={"email": "marketer@example.com", "password": PASSWORD})
    assert response.status_code == 403


def test_supabase_outage_is_service_unavailable(client, monkeypatch):
    def fail(request):
        raise httpx.ConnectError("down")

    monkeypatch.setattr(auth_service, "_transport", lambda: httpx.MockTransport(fail))
    response = client.post("/api/auth/login", json={"email": "a@example.com", "password": PASSWORD})
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "auth_unavailable"


def test_refresh_and_logout(client, supabase, users):
    responses, requests = supabase
    responses["/token?refresh_token"] = (200, _session_body(MARKETER_ID, "marketer@example.com"))
    responses["/logout"] = (204, {})

    assert client.post("/api/auth/refresh", json={"refresh_token": "r"}).json()["access_token"]
    token = token_for(MARKETER_ID)
    assert client.post("/api/auth/logout", headers={"Authorization": f"Bearer {token}"}).status_code == 204
    assert requests[-1].headers["authorization"] == f"Bearer {token}"


def test_invalid_refresh_token_is_unauthorized(client, supabase):
    responses, _ = supabase
    responses["/token?refresh_token"] = (400, {"error_code": "refresh_token_not_found", "msg": "Invalid"})
    response = client.post("/api/auth/refresh", json={"refresh_token": "bad"})
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "invalid_refresh_token"


def test_login_is_rate_limited(client, supabase, monkeypatch):
    responses, _ = supabase
    responses["/token?password"] = (400, {"error_code": "invalid_credentials", "msg": "x"})
    monkeypatch.setattr(auth_service, "LOGIN_RATE_LIMIT", utils.RateLimiter(2, 60))
    payload = {"email": "a@example.com", "password": "wrong-password"}

    assert client.post("/api/auth/login", json=payload).status_code == 401
    assert client.post("/api/auth/login", json=payload).status_code == 401
    limited = client.post("/api/auth/login", json=payload)
    assert limited.status_code == 429
    assert int(limited.headers["retry-after"]) >= 1


def test_spoofed_cloudflare_header_cannot_dodge_the_limit(client, supabase, monkeypatch):
    responses, _ = supabase
    responses["/token?password"] = (400, {"error_code": "invalid_credentials", "msg": "x"})
    monkeypatch.setattr(auth_service, "LOGIN_RATE_LIMIT", utils.RateLimiter(1, 60))
    payload = {"email": "a@example.com", "password": "wrong-password"}

    client.post("/api/auth/login", json=payload, headers={"CF-Connecting-IP": "1.1.1.1"})
    limited = client.post("/api/auth/login", json=payload, headers={"CF-Connecting-IP": "2.2.2.2"})
    assert limited.status_code == 429


def test_me_requires_token(client):
    response = client.get("/api/auth/me")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "missing_token"


def test_me_reads_and_updates_profile(client, users):
    headers = auth_headers(MARKETER_ID)
    assert client.get("/api/auth/me", headers=headers).json()["email"] == "marketer@example.com"
    updated = client.patch("/api/auth/me", headers=headers, json={"full_name": "Renamed"})
    assert updated.json()["full_name"] == "Renamed"


def test_token_signed_with_wrong_key_is_rejected(client, users):
    token = token_for(MARKETER_ID, secret="another-secret-that-is-long-enough-for-hs256")
    response = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "invalid_token"


def test_expired_token_is_rejected(client, users):
    token = token_for(MARKETER_ID, expires_in=-10)
    response = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 401


def test_unsigned_token_is_rejected(client, users):
    import jwt

    token = jwt.encode({"sub": ADMIN_ID, "aud": "authenticated"}, key="", algorithm="none")
    response = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 401


def test_token_for_user_without_profile_is_rejected(client):
    response = client.get("/api/auth/me", headers=auth_headers(NEW_USER_ID))
    assert response.status_code == 401


def test_role_comes_from_database_not_token(client, users):
    import time

    import jwt

    from tests.conftest import JWT_SECRET, SUPABASE_URL

    forged_role = jwt.encode(
        {
            "sub": MARKETER_ID,
            "role": "admin",
            "app_metadata": {"role": "admin"},
            "aud": "authenticated",
            "iss": f"{SUPABASE_URL}/auth/v1",
            "exp": int(time.time()) + 3600,
        },
        JWT_SECRET,
        algorithm="HS256",
    )
    response = client.get("/api/admin/users", headers={"Authorization": f"Bearer {forged_role}"})
    assert response.status_code == 403


def _es256_setup(monkeypatch, key_id: str = "key-1"):
    import json as json_module

    from cryptography.hazmat.primitives.asymmetric import ec
    from jwt.algorithms import ECAlgorithm

    from src.config import get_settings

    private_key = ec.generate_private_key(ec.SECP256R1())
    public_jwk = json_module.loads(ECAlgorithm.to_jwk(private_key.public_key()))
    monkeypatch.setenv("SUPABASE_JWKS_JSON", json_module.dumps({"keys": [public_jwk | {"kid": key_id, "alg": "ES256"}]}))
    monkeypatch.setenv("SUPABASE_JWT_SECRET", "")
    get_settings.cache_clear()
    return private_key, public_jwk


def _claims(user_id: str) -> dict:
    import time

    from tests.conftest import SUPABASE_URL

    return {
        "sub": user_id,
        "aud": "authenticated",
        "iss": f"{SUPABASE_URL}/auth/v1",
        "exp": int(time.time()) + 3600,
    }


def test_es256_token_is_verified_with_the_public_key(client, users, monkeypatch):
    import jwt

    private_key, _ = _es256_setup(monkeypatch)
    token = jwt.encode(_claims(MARKETER_ID), private_key, algorithm="ES256", headers={"kid": "key-1"})
    assert client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"}).status_code == 200


def test_es256_token_with_unknown_key_id_is_rejected(client, users, monkeypatch):
    import jwt

    private_key, _ = _es256_setup(monkeypatch)
    token = jwt.encode(_claims(MARKETER_ID), private_key, algorithm="ES256", headers={"kid": "other"})
    assert client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"}).status_code == 401


def test_es256_token_signed_by_another_key_is_rejected(client, users, monkeypatch):
    import jwt
    from cryptography.hazmat.primitives.asymmetric import ec

    _es256_setup(monkeypatch)
    forged = jwt.encode(
        _claims(ADMIN_ID), ec.generate_private_key(ec.SECP256R1()), algorithm="ES256", headers={"kid": "key-1"}
    )
    assert client.get("/api/admin/users", headers={"Authorization": f"Bearer {forged}"}).status_code == 401


def test_public_key_cannot_be_used_as_an_hs256_secret(client, users, monkeypatch):
    """Algorithm confusion: signing HS256 with the published key must not pass when only JWKS is configured."""
    import jwt

    _, public_jwk = _es256_setup(monkeypatch)
    forged = jwt.encode(_claims(ADMIN_ID), public_jwk["x"] + public_jwk["y"], algorithm="HS256")
    response = client.get("/api/admin/users", headers={"Authorization": f"Bearer {forged}"})
    assert response.status_code == 401


def test_dev_bypass_accepts_role_token_outside_production(client, monkeypatch):
    from src.config import get_settings

    monkeypatch.setenv("AUTH_DEV_BYPASS", "true")
    get_settings.cache_clear()
    assert client.get("/api/admin/users", headers={"Authorization": "Bearer dev:admin"}).status_code == 200
    assert client.get("/api/admin/users", headers={"Authorization": "Bearer dev:marketer"}).status_code == 403
    assert client.get("/api/admin/users").status_code == 401


def test_dev_user_satisfies_foreign_keys(client, monkeypatch):
    from src.config import get_settings

    monkeypatch.setenv("AUTH_DEV_BYPASS", "true")
    get_settings.cache_clear()
    created = client.post(
        "/api/admin/channels",
        headers={"Authorization": "Bearer dev:admin"},
        json={"name": "Page", "platform": "facebook", "account_ref": "p1"},
    )
    assert created.status_code == 201


def test_dev_bypass_is_refused_in_production(client, monkeypatch):
    from src.config import get_settings

    monkeypatch.setenv("AUTH_DEV_BYPASS", "true")
    monkeypatch.setenv("APP_ENV", "production")
    get_settings.cache_clear()
    response = client.get("/api/admin/users", headers={"Authorization": "Bearer dev:admin"})
    assert response.status_code == 401

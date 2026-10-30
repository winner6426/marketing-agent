"""Registration, login and identity. Supabase stores the credentials; roles always come from `user_profiles`."""

from __future__ import annotations

import json
import logging
import math
from dataclasses import dataclass, field
from typing import Any
from uuid import NAMESPACE_URL, uuid5

import httpx
import jwt
from sqlalchemy.exc import IntegrityError

from src import utils
from src.config import get_settings
from src.models import db
from src.services.shared import ServiceError, record_audit
from src.utils import current_timestamp, nfc

LOGGER = logging.getLogger(__name__)

# Supabase Auth REST adapter. Passwords pass through and are never stored or logged.
REQUEST_TIMEOUT_SECONDS = 15.0


class SupabaseAuthError(Exception):
    def __init__(self, status_code: int, error_code: str, message: str):
        super().__init__(message)
        self.status_code = status_code
        self.error_code = error_code
        self.message = message


class SupabaseAuthUnavailableError(Exception):
    """Supabase cannot be reached or is not configured."""


@dataclass(frozen=True)
class AuthSession:
    access_token: str
    refresh_token: str
    expires_in: int
    user_id: str
    email: str


@dataclass(frozen=True)
class SignUpResult:
    # None when Supabase requires email confirmation first.
    session: AuthSession | None
    user_id: str
    email: str
    # Supabase returns an obfuscated user with no identities when the email is taken and confirmation is on.
    is_new_user: bool = field(default=True)


def _base_url() -> tuple[str, str]:
    settings = get_settings()
    if not settings.supabase_url or not settings.supabase_anon_key:
        raise SupabaseAuthUnavailableError("SUPABASE_URL or SUPABASE_ANON_KEY is not set")
    return f"{settings.supabase_url.rstrip('/')}/auth/v1", settings.supabase_anon_key


def _transport() -> httpx.BaseTransport | None:
    """Overridden in tests."""
    return None


def _post(path: str, *, json: dict | None = None, bearer: str | None = None) -> dict:
    base_url, anon_key = _base_url()
    headers = {"apikey": anon_key, "Authorization": f"Bearer {bearer or anon_key}"}
    try:
        with httpx.Client(transport=_transport(), timeout=REQUEST_TIMEOUT_SECONDS) as client:
            response = client.post(f"{base_url}{path}", headers=headers, json=json)
    except httpx.HTTPError as error:
        raise SupabaseAuthUnavailableError(f"Could not reach Supabase Auth: {type(error).__name__}") from error

    if response.status_code >= 500:
        raise SupabaseAuthUnavailableError(f"Supabase Auth returned HTTP {response.status_code}")
    try:
        body = response.json() if response.content else {}
    except ValueError as error:
        raise SupabaseAuthUnavailableError("Supabase Auth returned an invalid response") from error
    if response.status_code >= 400:
        raise SupabaseAuthError(
            response.status_code,
            str(body.get("error_code") or body.get("error") or "auth_error"),
            str(body.get("msg") or body.get("error_description") or body.get("message") or "Authentication failed"),
        )
    return body


def _session_from(body: dict) -> AuthSession:
    user = body.get("user") or {}
    if not body.get("access_token") or not user.get("id"):
        raise SupabaseAuthUnavailableError("Supabase Auth returned no session")
    return AuthSession(
        access_token=body["access_token"],
        refresh_token=body.get("refresh_token", ""),
        expires_in=int(body.get("expires_in") or 0),
        user_id=user["id"],
        email=user.get("email") or "",
    )


def sign_up(email: str, password: str, full_name: str) -> SignUpResult:
    body = _post("/signup", json={"email": email, "password": password, "data": {"name": full_name}})
    if body.get("access_token"):
        session = _session_from(body)
        return SignUpResult(session=session, user_id=session.user_id, email=session.email or email)
    return SignUpResult(
        session=None,
        user_id=str(body.get("id") or ""),
        email=body.get("email") or email,
        is_new_user=bool(body.get("identities")),
    )


def sign_in(email: str, password: str) -> AuthSession:
    return _session_from(_post("/token?grant_type=password", json={"email": email, "password": password}))


def refresh_session(refresh_token: str) -> AuthSession:
    return _session_from(_post("/token?grant_type=refresh_token", json={"refresh_token": refresh_token}))


def sign_out(access_token: str) -> None:
    _post("/logout", bearer=access_token)


# Local verification of Supabase access tokens, without any network call.
ASYMMETRIC_ALGORITHMS = {"ES256", "RS256"}


class TokenError(Exception):
    pass


def _jwks_key(token: str, jwks_json: str) -> tuple[Any, str]:
    try:
        header = jwt.get_unverified_header(token)
        serialized = jwks_json.strip()
        # Docker --env-file keeps surrounding single quotes, unlike python-dotenv.
        if len(serialized) >= 2 and serialized[0] == serialized[-1] == "'":
            serialized = serialized[1:-1]
        jwks = json.loads(serialized)
    except (jwt.InvalidTokenError, json.JSONDecodeError, TypeError) as error:
        raise TokenError("Invalid token or SUPABASE_JWKS_JSON") from error

    algorithm, key_id = header.get("alg", ""), header.get("kid")
    if algorithm not in ASYMMETRIC_ALGORITHMS or not key_id:
        raise TokenError("The token does not use a supported Supabase signing key")

    matching_key = next((item for item in jwks.get("keys", []) if item.get("kid") == key_id), None)
    if matching_key is None:
        raise TokenError("The token's signing key is not in SUPABASE_JWKS_JSON")
    try:
        return jwt.PyJWK.from_dict(matching_key, algorithm=algorithm).key, algorithm
    except (jwt.PyJWKError, ValueError, TypeError) as error:
        raise TokenError("Invalid Supabase signing key") from error


def verify_claims(token: str) -> dict[str, Any]:
    settings = get_settings()
    if not settings.supabase_url:
        raise TokenError("SUPABASE_URL is not set")

    try:
        algorithm = jwt.get_unverified_header(token).get("alg", "")
    except jwt.InvalidTokenError as error:
        raise TokenError("Invalid token") from error

    # The algorithm is picked per key type, so an HS256 token can never be checked against a public key.
    if algorithm == "HS256":
        if not settings.supabase_jwt_secret:
            raise TokenError("SUPABASE_JWT_SECRET is not set")
        key = settings.supabase_jwt_secret
    elif algorithm in ASYMMETRIC_ALGORITHMS:
        if not settings.supabase_jwks_json:
            raise TokenError("SUPABASE_JWKS_JSON is not set")
        key, algorithm = _jwks_key(token, settings.supabase_jwks_json)
    else:
        raise TokenError("Unsupported JWT signing algorithm")

    try:
        return jwt.decode(
            token,
            key,
            algorithms=[algorithm],
            audience="authenticated",
            issuer=f"{settings.supabase_url.rstrip('/')}/auth/v1",
            options={"require": ["exp", "iss", "aud", "sub"]},
        )
    except jwt.ExpiredSignatureError as error:
        raise TokenError("The token has expired; log in again") from error
    except jwt.InvalidTokenError as error:
        raise TokenError("Invalid token") from error


# Identity and account operations.
DEFAULT_ROLE = "marketer"
VALID_ROLES = {"marketer", "manager", "admin"}
DEV_TOKEN_PREFIX = "dev:"
BEARER_PREFIX = "bearer "

LOGIN_RATE_LIMIT = utils.RateLimiter(max_requests=10, window_seconds=60)
REGISTRATION_RATE_LIMIT = utils.RateLimiter(max_requests=5, window_seconds=3600)


@dataclass(frozen=True)
class AuthenticatedUser:
    id: str
    email: str
    role: str

    @property
    def is_admin(self) -> bool:
        return self.role == "admin"

    @property
    def is_manager(self) -> bool:
        return self.role == "manager"

    @property
    def is_marketer(self) -> bool:
        return self.role == "marketer"


def _unauthorized(code: str, message: str) -> ServiceError:
    return ServiceError(401, code, message, headers={"WWW-Authenticate": "Bearer"})


def _role_value(profile: db.UserProfile) -> str:
    return profile.role.value if isinstance(profile.role, db.UserRole) else str(profile.role)


def _dev_user(token: str | None) -> AuthenticatedUser:
    role = (token or "").removeprefix(DEV_TOKEN_PREFIX).strip() or DEFAULT_ROLE
    if role not in VALID_ROLES:
        role = DEFAULT_ROLE
    LOGGER.warning("AUTH BYPASS is on: this request is treated as `%s`. Use in development only.", role)
    # A stable UUID is valid on Postgres, and the profile row keeps foreign keys intact.
    user = AuthenticatedUser(id=str(uuid5(NAMESPACE_URL, f"dev-user:{role}")), email=f"{role}@dev.local", role=role)
    _ensure_profile(user.id, user.email, role=db.UserRole(role))
    return user


def authenticate_token(token: str | None) -> AuthenticatedUser:
    """Verify the signature locally, then read role and account state from the database, never from the token."""
    settings = get_settings()
    if settings.auth_dev_bypass:
        if settings.app_env == "production":
            raise _unauthorized("invalid_token", "AUTH_DEV_BYPASS is not allowed in production")
        return _dev_user(token)
    if not token:
        raise _unauthorized("missing_token", "You must log in to use this feature")

    try:
        claims = verify_claims(token)
    except TokenError as error:
        raise _unauthorized("invalid_token", str(error)) from error

    user_id = claims.get("sub")
    if not user_id:
        raise _unauthorized("invalid_token", "The token has no `sub` claim")

    with db.get_session() as session:
        profile = session.get(db.UserProfile, user_id)
        if profile is None:
            raise _unauthorized("invalid_token", "This account has no application profile")
        if not profile.is_active:
            raise _unauthorized("account_disabled", "This account has been disabled")
        role = _role_value(profile)
        email = claims.get("email") or profile.email

    if role not in VALID_ROLES:
        raise _unauthorized("invalid_token", "The profile has an invalid role")
    return AuthenticatedUser(id=user_id, email=email, role=role)


def user_from_authorization(authorization: str | None) -> AuthenticatedUser:
    if not authorization or not authorization.lower().startswith(BEARER_PREFIX):
        raise _unauthorized("missing_token", "You must log in to use this feature")
    return authenticate_token(authorization[len(BEARER_PREFIX) :].strip())


def enforce_rate_limit(limiter: utils.RateLimiter, request) -> None:
    ip = utils.client_ip(request, trust_cf_connecting_ip=get_settings().trust_cf_connecting_ip)
    allowed, wait_seconds = limiter.allow(utils.hash_identifier(ip))
    if not allowed:
        raise ServiceError(
            429,
            "too_many_requests",
            "Too many attempts. Try again later.",
            headers={"Retry-After": str(max(1, math.ceil(wait_seconds)))},
        )


def _translate_supabase_error(error: SupabaseAuthError) -> ServiceError:
    code = error.error_code
    if code in {"invalid_credentials", "invalid_grant"}:
        return _unauthorized("invalid_credentials", "Incorrect email or password")
    if code == "email_not_confirmed":
        return ServiceError(403, "email_not_confirmed", "Confirm your email before logging in")
    if code in {"user_already_exists", "email_exists"}:
        return ServiceError(409, "email_already_registered", "This email is already registered")
    if code == "weak_password":
        return ServiceError(422, "weak_password", error.message)
    if code == "signup_disabled":
        return ServiceError(403, "signup_disabled", "Registration is disabled")
    if error.status_code == 429 or code.startswith("over_"):
        return ServiceError(429, "too_many_requests", "Too many attempts. Try again later.")
    return ServiceError(400, "auth_rejected", error.message)


def _call_supabase(operation, *args):
    try:
        return operation(*args)
    except SupabaseAuthUnavailableError as error:
        LOGGER.error("Supabase Auth is unavailable: %s", error)
        raise ServiceError(503, "auth_unavailable", "The authentication service is unavailable") from error
    except SupabaseAuthError as error:
        raise _translate_supabase_error(error) from error


def _ensure_profile(user_id: str, email: str, full_name: str = "", role: db.UserRole = db.UserRole.MARKETER) -> None:
    """New accounts start as marketers; only an admin can change a role. An existing role is never touched."""
    with db.get_session() as session:
        profile = session.get(db.UserProfile, user_id)
        if profile is not None:
            if email and profile.email != email:
                profile.email = email
                session.commit()
            return
        session.add(db.UserProfile(id=user_id, email=email, name=nfc(full_name), role=role))
        try:
            session.commit()
        except IntegrityError:
            # Another request or a database trigger created it first.
            session.rollback()


def _session_payload(session: AuthSession) -> dict:
    return {
        "access_token": session.access_token,
        "refresh_token": session.refresh_token,
        "token_type": "bearer",
        "expires_in": session.expires_in,
    }


def register(email: str, password: str, full_name: str) -> dict:
    result = _call_supabase(sign_up, email, password, full_name)
    if result.session is None:
        # The same answer whether the email is new or taken, so it cannot be used to discover accounts.
        if result.is_new_user and result.user_id:
            _ensure_profile(result.user_id, result.email, full_name)
        return {"email": email, "email_confirmation_required": True}

    _ensure_profile(result.user_id, result.email, full_name)
    return {
        "email": result.email,
        "email_confirmation_required": False,
        "user": get_profile(result.user_id),
        **_session_payload(result.session),
    }


def login(email: str, password: str) -> dict:
    session = _call_supabase(sign_in, email, password)
    _ensure_profile(session.user_id, session.email or email)
    profile = get_profile(session.user_id)
    if not profile["is_active"]:
        raise ServiceError(403, "account_disabled", "This account has been disabled")
    record_audit(AuthenticatedUser(session.user_id, profile["email"], profile["role"]), "login")
    return {"user": profile, **_session_payload(session)}


def refresh(refresh_token: str) -> dict:
    try:
        session = _call_supabase(refresh_session, refresh_token)
    except ServiceError as error:
        if error.status_code in {400, 401}:
            raise _unauthorized("invalid_refresh_token", "The session has expired; log in again") from error
        raise
    return _session_payload(session)


def logout(access_token: str) -> None:
    _call_supabase(sign_out, access_token)


def _profile_view(profile: db.UserProfile) -> dict:
    return {
        "user_id": str(profile.id),
        "email": profile.email,
        "full_name": nfc(profile.name),
        "role": _role_value(profile),
        "is_active": bool(profile.is_active),
        "created_at": profile.created_at,
        "updated_at": profile.updated_at,
    }


def get_profile(user_id: str) -> dict:
    with db.get_session() as session:
        profile = session.get(db.UserProfile, user_id)
        if profile is None:
            raise ServiceError(404, "profile_not_found", "User profile not found")
        return _profile_view(profile)


def update_profile(user_id: str, *, full_name: str) -> dict:
    with db.get_session() as session:
        profile = session.get(db.UserProfile, user_id)
        if profile is None:
            raise ServiceError(404, "profile_not_found", "User profile not found")
        profile.name = nfc(full_name.strip())
        profile.updated_at = current_timestamp()
        session.commit()
        return _profile_view(profile)

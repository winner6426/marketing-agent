"""The single LLM entry point for every node, with provider failover and API key rotation."""

from __future__ import annotations

import logging
import os
import re
import time
from collections.abc import Callable

import requests

LOGGER = logging.getLogger(__name__)

# Key health is tracked per (key, model) because free-tier quotas are per model. No network calls here.
# A shorter retry delay means a per-minute limit; a longer one means the daily quota is gone.
DAILY_EXHAUSTION_THRESHOLD_SECONDS = 600
MAX_KEY_SUFFIXES = 10

ALIVE = "alive"
COOLDOWN = "cooldown"
EXHAUSTED = "exhausted"
INVALID = "invalid"


def mask_key(key: str) -> str:
    if not key:
        return "(empty)"
    if len(key) <= 12:
        return key[:3] + "…"
    return f"{key[:6]}…{key[-3:]}"


def read_keys_from_env(env: dict | None = None) -> list[str]:
    """Collect OPENAI_API_KEY, OPENAI_API_KEY_2..N and OPENAI_API_KEYS, keeping order without duplicates."""
    env = env if env is not None else os.environ
    candidates = [env.get("OPENAI_API_KEY", "")]
    candidates += [env.get(f"OPENAI_API_KEY_{suffix}", "") for suffix in range(2, MAX_KEY_SUFFIXES + 1)]
    candidates += (env.get("OPENAI_API_KEYS") or "").split(",")

    keys: list[str] = []
    for raw in candidates:
        key = (raw or "").strip().strip("'\"")
        if key and key not in keys:
            keys.append(key)
    return keys


class KeyPool:
    """Picks a usable key. A 429 penalizes one (key, model) pair; a 401/403 removes the key for every model."""

    def __init__(self, keys: list[str] | None = None, time_fn=time.time):
        self._time = time_fn
        self._keys = list(keys) if keys is not None else read_keys_from_env()
        self._states: dict[tuple[str, str], dict] = {}
        self._invalid_keys: set[str] = set()

    def __len__(self) -> int:
        return len(self._keys)

    def _info(self, key: str, model: str) -> dict:
        return self._states.setdefault((key, model), {"status": ALIVE, "wait_until": 0.0, "reason": ""})

    def _current_status(self, key: str, model: str) -> str:
        if key in self._invalid_keys:
            return INVALID
        info = self._info(key, model)
        if info["status"] in (COOLDOWN, EXHAUSTED) and self._time() >= info["wait_until"]:
            info["status"] = ALIVE
            info["reason"] = ""
        return info["status"]

    def available_keys(self, model: str = "") -> list[str]:
        return [key for key in self._keys if self._current_status(key, model) == ALIVE]

    def has_live_key(self, model: str = "") -> bool:
        return bool(self.available_keys(model))

    def next_key(self, model: str = "") -> str | None:
        available = self.available_keys(model)
        return available[0] if available else None

    def longest_wait(self, model: str = "") -> float:
        """Seconds until the earliest key recovers; infinity when every key is permanently invalid."""
        if self.has_live_key(model):
            return 0.0
        wait_times = [
            self._info(key, model)["wait_until"]
            for key in self._keys
            if self._current_status(key, model) in (COOLDOWN, EXHAUSTED)
        ]
        if not wait_times:
            return float("inf")
        return max(min(wait_times) - self._time(), 0.0)

    def failure_reasons(self, model: str = "") -> list[str]:
        reasons = []
        for key in self._keys:
            reason = "HTTP 401/403" if key in self._invalid_keys else self._info(key, model)["reason"]
            if reason:
                reasons.append(f"{mask_key(key)}: {reason}")
        return reasons

    def mark_success(self, key: str, model: str = "") -> None:
        if key in self._keys:
            self._info(key, model).update(status=ALIVE, wait_until=0.0, reason="")

    def mark_exhausted(self, key: str, wait_seconds: float, reason: str = "", model: str = "") -> None:
        if key in self._keys:
            self._info(key, model).update(
                status=EXHAUSTED if wait_seconds >= DAILY_EXHAUSTION_THRESHOLD_SECONDS else COOLDOWN,
                wait_until=self._time() + wait_seconds,
                reason=reason or "HTTP 429",
            )

    def mark_invalid(self, key: str, reason: str = "") -> None:
        if key in self._keys:
            self._invalid_keys.add(key)
            self._info(key, "")["reason"] = reason or "HTTP 401/403"


_pool: KeyPool | None = None


def shared_pool() -> KeyPool:
    global _pool
    if _pool is None:
        _pool = KeyPool()
    return _pool


def set_shared_pool(pool: KeyPool | None) -> None:
    global _pool
    _pool = pool


GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
GEMINI_URL_TEMPLATE = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
DEFAULT_OPENAI_BASE_URL = "https://api.openai.com/v1"
DEFAULT_OPENAI_MODEL = "gpt-4o-mini"
DEFAULT_GROQ_MODEL = "llama-3.3-70b-versatile"
DEFAULT_GEMINI_MODEL = "gemini-2.5-flash"

REQUEST_TIMEOUT_SECONDS = 30
COOLDOWN_SECONDS = 60

# The key pool tracks (key, model) itself; a provider-wide cooldown would block its fallback models.
SELF_MANAGED_COOLDOWN = {"openai"}


class ProviderQuotaError(Exception):
    def __init__(self, message: str, retry_after_seconds: float = COOLDOWN_SECONDS):
        super().__init__(message)
        self.retry_after_seconds = retry_after_seconds


class ProviderError(Exception):
    pass


class ProviderNetworkError(ProviderError):
    """Network failure, kept separate so an outage never marks healthy keys as bad."""


class ProviderAuthError(ProviderError):
    pass


_cooldown_until: dict[str, float] = {}


def _resolve_cooldown_seconds(response) -> float:
    """Read Retry-After, or the `retryDelay` Gemini puts in the response body."""
    retry_after = response.headers.get("Retry-After")
    if retry_after:
        try:
            return max(float(retry_after), 1.0)
        except ValueError:
            pass
    try:
        match = re.search(r"retryDelay\"?\s*:\s*\"?(\d+(?:\.\d+)?)s", response.text)
    except Exception:  # noqa: BLE001 - reading the body can fail on a broken connection
        match = None
    return max(float(match.group(1)) + 1, 1.0) if match else COOLDOWN_SECONDS


def _call_openai_once(api_key: str, base: str, model_name: str, system_prompt: str, user_message: str) -> str:
    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": user_message})

    try:
        response = requests.post(
            f"{base}/chat/completions",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={"model": model_name, "messages": messages, "temperature": 0},
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
    except requests.exceptions.RequestException as error:
        raise ProviderNetworkError(f"Could not reach {base}: {type(error).__name__}") from error

    if response.status_code == 429:
        raise ProviderQuotaError(
            f"OpenAI-compatible rate limit (429) on model '{model_name}': {response.text[:300]}",
            retry_after_seconds=_resolve_cooldown_seconds(response),
        )
    # Google returns 400 "Please pass a valid API key" rather than 401.
    if response.status_code in (401, 403) or (response.status_code == 400 and "api key" in response.text.lower()):
        raise ProviderAuthError(f"API key rejected (HTTP {response.status_code}): {response.text[:180]}")
    if response.status_code != 200:
        raise ProviderError(f"OpenAI-compatible HTTP {response.status_code} on '{model_name}': {response.text[:300]}")

    try:
        choice = response.json()["choices"][0]
        message = choice["message"]
    except (KeyError, IndexError, ValueError) as error:
        raise ProviderError(f"Unexpected OpenAI-compatible response: {error}") from error

    # Thinking models sometimes return only reasoning fields through the compatible endpoint.
    for field in ("content", "reasoning_content", "reasoning"):
        if message.get(field):
            return message[field]

    raise ProviderError(
        f"Model '{model_name}' returned an empty response (finish_reason={choice.get('finish_reason')!r})."
    )


def _call_openai_compat(system_prompt: str, user_message: str, model: str | None = None) -> str:
    """Rotate through the key pool: a 429 penalizes the key, a 401 removes it, a network error raises at once."""
    pool = shared_pool()
    if len(pool) == 0:
        raise ProviderError("No API key configured. Set OPENAI_API_KEY or OPENAI_API_KEYS.")

    base = (os.environ.get("OPENAI_BASE_URL") or DEFAULT_OPENAI_BASE_URL).rstrip("/")
    model_name = model or os.environ.get("LLM_MODEL") or DEFAULT_OPENAI_MODEL
    last_error: Exception | None = None

    for _ in range(len(pool)):
        api_key = pool.next_key(model_name)
        if api_key is None:
            break
        try:
            result = _call_openai_once(api_key, base, model_name, system_prompt, user_message)
            pool.mark_success(api_key, model=model_name)
            return result
        except ProviderQuotaError as error:
            pool.mark_exhausted(api_key, error.retry_after_seconds, str(error)[:120], model=model_name)
            LOGGER.warning("Key %s out of quota on '%s'; rotating.", mask_key(api_key), model_name)
            last_error = error
        except ProviderAuthError as error:
            pool.mark_invalid(api_key, str(error)[:120])
            LOGGER.warning("Key %s rejected; removing it for this process.", mask_key(api_key))
            last_error = error

    if not pool.has_live_key(model_name):
        wait = pool.longest_wait(model_name)
        state = "no key is usable" if wait == float("inf") else f"the earliest key recovers in {wait:.0f}s"
        details = str(last_error) if last_error else "; ".join(pool.failure_reasons(model_name)) or "unknown cause"
        raise ProviderQuotaError(
            f"Tried all {len(pool)} keys for model '{model_name}': {state}. {details}",
            retry_after_seconds=COOLDOWN_SECONDS if wait == float("inf") else wait,
        )
    raise last_error or ProviderError("No key could be called.")


def _call_openai_direct(system_prompt: str, user_message: str, model: str | None = None) -> str:
    api_key = os.environ.get("OPENAI_DIRECT_API_KEY", "")
    if not api_key:
        raise ProviderError("OPENAI_DIRECT_API_KEY is not set.")
    base = (os.environ.get("OPENAI_DIRECT_BASE_URL") or DEFAULT_OPENAI_BASE_URL).rstrip("/")
    model_name = (model or os.environ.get("STRONG_MODEL") or "").strip()
    if not model_name:
        raise ProviderError("STRONG_MODEL is not set.")
    return _call_openai_once(api_key, base, model_name, system_prompt, user_message)


def _call_groq(system_prompt: str, user_message: str, model: str | None = None) -> str:
    api_key = os.environ.get("GROQ_API_KEY", "")
    if not api_key:
        raise ProviderError("GROQ_API_KEY is not set.")
    payload = {
        "model": model or os.environ.get("GROQ_MODEL") or DEFAULT_GROQ_MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ],
        "temperature": 0,
    }
    try:
        response = requests.post(
            GROQ_URL,
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json=payload,
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
    except requests.exceptions.RequestException as error:
        raise ProviderNetworkError(f"Could not reach Groq: {type(error).__name__}") from error

    if response.status_code == 429:
        raise ProviderQuotaError(
            f"Groq rate limit (429): {response.text[:200]}",
            retry_after_seconds=_resolve_cooldown_seconds(response),
        )
    if response.status_code != 200:
        raise ProviderError(f"Groq HTTP {response.status_code}: {response.text[:200]}")
    try:
        return response.json()["choices"][0]["message"]["content"]
    except (KeyError, IndexError, ValueError) as error:
        raise ProviderError(f"Unexpected Groq response: {error}") from error


def _call_gemini(system_prompt: str, user_message: str, model: str | None = None) -> str:
    api_key = os.environ.get("GEMINI_API_KEY", "")
    if not api_key:
        raise ProviderError("GEMINI_API_KEY is not set.")
    model_name = model or os.environ.get("GEMINI_MODEL") or DEFAULT_GEMINI_MODEL
    payload = {
        "systemInstruction": {"parts": [{"text": system_prompt}]},
        "contents": [{"role": "user", "parts": [{"text": user_message}]}],
        "generationConfig": {"temperature": 0},
    }
    try:
        # The key goes in a header: as a query parameter it would leak through error messages.
        response = requests.post(
            GEMINI_URL_TEMPLATE.format(model=model_name),
            headers={"x-goog-api-key": api_key},
            json=payload,
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
    except requests.exceptions.RequestException as error:
        raise ProviderNetworkError(f"Could not reach Gemini: {type(error).__name__}") from error

    if response.status_code == 429:
        raise ProviderQuotaError(
            f"Gemini rate limit (429): {response.text[:200]}",
            retry_after_seconds=_resolve_cooldown_seconds(response),
        )
    if response.status_code != 200:
        raise ProviderError(f"Gemini HTTP {response.status_code}: {response.text[:200]}")
    try:
        return response.json()["candidates"][0]["content"]["parts"][0]["text"]
    except (KeyError, IndexError, ValueError) as error:
        raise ProviderError(f"Unexpected Gemini response: {error}") from error


def _call_local(system_prompt: str, user_message: str, model: str | None = None) -> str:
    """Self-hosted endpoint. It bypasses the key pool: a 503 during model load must not mark it as dead."""
    base = (os.environ.get("LOCAL_LLM_BASE_URL") or "").rstrip("/")
    if not base:
        raise ProviderError("LOCAL_LLM_BASE_URL is not set.")
    model_name = model or os.environ.get("LOCAL_LLM_MODEL") or "local-model"
    api_key = os.environ.get("LOCAL_LLM_API_KEY") or "local-no-auth"
    return _call_openai_once(api_key, base, model_name, system_prompt, user_message)


_CALLERS: dict[str, Callable[..., str]] = {
    "openai": _call_openai_compat,
    "openai_direct": _call_openai_direct,
    "groq": _call_groq,
    "gemini": _call_gemini,
    "local": _call_local,
}


def call_single_provider(name: str, system_prompt: str, user_message: str, model: str | None = None) -> str:
    """Call exactly one provider with no failover."""
    if name not in _CALLERS:
        raise ProviderError(f"Unknown provider {name!r}. Valid: {sorted(_CALLERS)}")
    return _CALLERS[name](system_prompt, user_message, model)


def call_llm_with_fallback(
    system_prompt: str,
    user_message: str,
    candidates: list[tuple[str, str | None]],
    response_validator: Callable[[str], object] | None = None,
) -> str:
    """Try each (provider, model) in order. Unusable output counts as a failure, so the next tier runs."""
    if not candidates:
        raise ProviderError("No LLM tier is configured.")

    now = time.time()
    errors: list[str] = []
    for name, model in candidates:
        if name not in _CALLERS:
            errors.append(f"{name}: unknown provider")
            continue
        if name not in SELF_MANAGED_COOLDOWN and now < _cooldown_until.get(name, 0.0):
            errors.append(f"{name}: cooling down for {int(_cooldown_until[name] - now)}s")
            continue

        try:
            text = _CALLERS[name](system_prompt, user_message, model)
            if response_validator is not None:
                try:
                    response_validator(text)
                except (TypeError, ValueError) as error:
                    raise ProviderError(f"invalid output: {error}") from error
            return text
        except ProviderQuotaError as error:
            LOGGER.warning("Provider '%s' out of quota; trying the next one. (%s)", name, error)
            if name not in SELF_MANAGED_COOLDOWN:
                _cooldown_until[name] = time.time() + error.retry_after_seconds
            errors.append(f"{name}: {error}")
        except ProviderError as error:
            LOGGER.warning("Provider '%s' failed; trying the next one. (%s)", name, error)
            errors.append(f"{name}: {error}")

    raise ProviderError("Could not call any LLM.\n" + "\n".join(errors))


ALLOWED_ROLES = {"brief_analyst", "planner", "writer", "judge"}

RECOVERABLE_LLM_ERRORS = (ProviderError, ProviderQuotaError)

TIER_DEFAULTS = {
    "STRONG": ("openai_direct", "gpt-4o"),
    "AVERAGE": ("gemini", "gemini-3.6-flash"),
    "WEAK": ("groq", "openai/gpt-oss-120b"),
}

ROLE_TIER_CHAINS = {
    "planner": ("STRONG", "AVERAGE", "WEAK"),
    "writer": ("AVERAGE", "WEAK", "STRONG"),
    "brief_analyst": ("WEAK", "AVERAGE", "STRONG"),
}


def _check_role(role: str) -> None:
    if role not in ALLOWED_ROLES:
        raise ValueError(f"Invalid role: {role!r}. Valid: {sorted(ALLOWED_ROLES)}")


def _candidates_for_role(role: str) -> list[tuple[str, str]]:
    candidates = []
    for tier in ROLE_TIER_CHAINS[role]:
        default_provider, default_model = TIER_DEFAULTS[tier]
        provider = os.environ.get(f"{tier}_PROVIDER", default_provider).strip()
        model = os.environ.get(f"{tier}_MODEL", default_model).strip()
        if not provider or not model:
            raise ProviderError(f"{tier}_PROVIDER or {tier}_MODEL is empty.")
        candidates.append((provider, model))
    return candidates


def primary_model(role: str) -> str:
    return _candidates_for_role(role)[0][1]


def generate(
    role: str,
    system_prompt: str,
    user_message: str,
    response_validator: Callable[[str], object] | None = None,
) -> str:
    """Call the LLM for a node. `user_message` must already be wrapped by `prompt_guard`."""
    _check_role(role)
    return call_llm_with_fallback(
        system_prompt=system_prompt,
        user_message=user_message,
        candidates=_candidates_for_role(role),
        response_validator=response_validator,
    ).strip()


def generate_with_provider(
    role: str, provider: str, system_prompt: str, user_message: str, model: str | None = None
) -> str:
    """Call one named provider without failover, for callers that must know which model answered."""
    _check_role(role)
    return call_single_provider(provider, system_prompt, user_message, model).strip()

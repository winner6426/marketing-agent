"""Shared helpers: Unicode normalization, Vietnam time, the reference cache and rate limiting."""

from __future__ import annotations

import hashlib
import os
import threading
import time
import unicodedata
from collections import OrderedDict, deque
from collections.abc import Callable, Sized
from datetime import date, datetime
from datetime import time as clock_time
from functools import wraps
from typing import Any, TypeVar
from zoneinfo import ZoneInfo


# NFC first: NFD Vietnamese miscounts SMS segments and slips past brand-rule regexes.
def nfc(text: str | None) -> str:
    return unicodedata.normalize("NFC", text) if text else ""


def normalize_draft_nfc(draft: dict) -> dict:
    normalized = {}
    for key, value in draft.items():
        if isinstance(value, str):
            normalized[key] = nfc(value)
        elif isinstance(value, list):
            normalized[key] = [nfc(item) if isinstance(item, str) else item for item in value]
        else:
            normalized[key] = value
    return normalized


# Single source of timestamps: promotion dates are Vietnam calendar days, so UTC would be off by 7 hours.
VIETNAM_TIMEZONE = ZoneInfo("Asia/Ho_Chi_Minh")


def now_vietnam() -> datetime:
    return datetime.now(VIETNAM_TIMEZONE)


def current_timestamp() -> str:
    return now_vietnam().isoformat(timespec="seconds")


def today_vietnam() -> date:
    return now_vietnam().date()


def vietnam_date() -> str:
    return today_vietnam().isoformat()


def vietnam_datetime(date_value: date, time_value: str) -> str:
    parsed_time = clock_time.fromisoformat(time_value)
    return datetime.combine(date_value, parsed_time, tzinfo=VIETNAM_TIMEZONE).isoformat(timespec="seconds")


def dmy_to_iso(value: str) -> str | None:
    """Convert `DD/MM/YYYY` to ISO; an invalid date returns None."""
    try:
        day, month, year = (int(part) for part in value.split("/"))
        return date(year, month, day).isoformat()
    except (TypeError, ValueError):
        return None


def is_active(valid_from: str, valid_to: str, reference_date: date | None = None) -> bool:
    """Inclusive on both ends; malformed dates count as inactive so we never advertise an unclear offer."""
    reference_date = reference_date or today_vietnam()
    try:
        return date.fromisoformat(valid_from) <= reference_date <= date.fromisoformat(valid_to)
    except (ValueError, TypeError):
        return False


# TTL cache for config tables that writer prompts read repeatedly during one run.
_lock = threading.Lock()
_store: dict[tuple[str, tuple], tuple[float, Any]] = {}

F = TypeVar("F", bound=Callable[..., Any])


def _default_ttl() -> float:
    return float(os.environ.get("REFERENCE_CACHE_TTL_SECONDS", "300"))


def _should_store(value: Any) -> bool:
    # An empty result usually signals a failure (RAG timeout, wrong model), so let the next call retry.
    if value is None:
        return False
    if isinstance(value, tuple):
        return any(_should_store(item) for item in value)
    if isinstance(value, Sized):
        return len(value) > 0
    return True


def cached_reference(ttl_seconds: float | None = None) -> Callable[[F], F]:
    """Only for functions that depend solely on their arguments, never on campaign state."""

    def decorator(function: F) -> F:
        name = f"{function.__module__}.{function.__qualname__}"

        @wraps(function)
        def wrapper(*args, **kwargs):
            ttl = _default_ttl() if ttl_seconds is None else ttl_seconds
            key = (name, args + tuple(sorted(kwargs.items())))
            now = time.monotonic()

            with _lock:
                entry = _store.get(key)
                if entry is not None and entry[0] > now:
                    return entry[1]

            # Runs outside the lock: this may hit the database or the network.
            value = function(*args, **kwargs)

            with _lock:
                if _should_store(value):
                    _store[key] = (now + ttl, value)
            return value

        return wrapper  # type: ignore[return-value]

    return decorator


def clear_reference_cache() -> None:
    with _lock:
        _store.clear()


# In-memory sliding-window limiter; IPs are only kept as salted hashes for the length of the window.
_SALT = os.urandom(16)


def hash_identifier(identifier: str) -> str:
    return hashlib.blake2b(identifier.encode("utf-8"), key=_SALT, digest_size=16).hexdigest()


class RateLimiter:
    def __init__(
        self,
        max_requests: int,
        window_seconds: float,
        *,
        max_keys: int = 20_000,
        clock: Callable[[], float] = time.monotonic,
    ):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.max_keys = max_keys
        self._clock = clock
        self._entries: OrderedDict[str, deque[float]] = OrderedDict()
        self._last_cleanup = clock()

    def _cleanup(self, now: float) -> None:
        expired = [key for key, hits in self._entries.items() if not hits or now - hits[-1] >= self.window_seconds]
        for key in expired:
            del self._entries[key]
        self._last_cleanup = now

    def _should_cleanup(self, now: float) -> bool:
        return now - self._last_cleanup >= self.window_seconds or len(self._entries) > self.max_keys // 2

    def allow(self, key: str) -> tuple[bool, float]:
        """Return (allowed, seconds until the next request would be allowed)."""
        now = self._clock()
        if self._should_cleanup(now):
            self._cleanup(now)

        hits = self._entries.get(key)
        if hits is None:
            hits = deque()
            self._entries[key] = hits
        else:
            self._entries.move_to_end(key)

        while hits and now - hits[0] >= self.window_seconds:
            hits.popleft()

        if len(hits) >= self.max_requests:
            wait = self.window_seconds if not hits else self.window_seconds - (now - hits[0])
            return False, max(wait, 0.0)

        hits.append(now)
        while len(self._entries) > self.max_keys:
            self._entries.popitem(last=False)
        return True, 0.0


def client_ip(request, *, trust_cf_connecting_ip: bool = False) -> str:
    """X-Forwarded-For is never read: clients can prepend any value to it."""
    if trust_cf_connecting_ip:
        forwarded = request.headers.get("cf-connecting-ip", "").strip()
        if forwarded:
            return forwarded
    return request.client.host if request.client else "unknown"

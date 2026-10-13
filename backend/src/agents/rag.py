"""Retrieval: encode the query with Cloudflare, search vectors in Qdrant, read text and sources from Postgres."""

from __future__ import annotations

import logging
import math
import os
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any, Protocol

import httpx
from sqlalchemy import select

from src.models import db

LOGGER = logging.getLogger(__name__)

CLOUDFLARE_BGE_M3 = "@cf/baai/bge-m3"
DEFAULT_EMBED_DIM = 1024
DEFAULT_TIMEOUT_SECONDS = 20.0
DEFAULT_MAX_RETRIES = 2
MAX_RETRY_AFTER_SECONDS = 30.0


class EmbeddingProviderError(RuntimeError):
    """Sanitized failure: never carries the API token or user text."""


class EmbeddingClient(Protocol):
    def encode(self, texts: list[str], *, normalize_embeddings: bool = True, **kwargs: object) -> list[list[float]]: ...


class HttpTransport(Protocol):
    def post(self, url: str, *, headers: dict[str, str], json: dict[str, Any], timeout: float) -> Any: ...


class CloudflareEmbeddingClient:
    def __init__(
        self,
        *,
        account_id: str,
        api_token: str,
        model: str = CLOUDFLARE_BGE_M3,
        dimension: int = DEFAULT_EMBED_DIM,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
        max_retries: int = DEFAULT_MAX_RETRIES,
        transport: HttpTransport | None = None,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        if not account_id.strip():
            raise EmbeddingProviderError("CLOUDFLARE_ACCOUNT_ID is not set")
        if not api_token.strip():
            raise EmbeddingProviderError("CLOUDFLARE_API_TOKEN is not set")
        if dimension < 1:
            raise EmbeddingProviderError("EMBED_DIM must be greater than 0")
        if timeout_seconds <= 0:
            raise EmbeddingProviderError("EMBED_TIMEOUT_SECONDS must be greater than 0")
        if max_retries < 0:
            raise EmbeddingProviderError("EMBED_MAX_RETRIES must not be negative")

        self._account_id = account_id.strip()
        self._api_token = api_token.strip()
        self._model = model.strip() or CLOUDFLARE_BGE_M3
        self._dimension = dimension
        self._timeout_seconds = float(timeout_seconds)
        self._max_retries = max_retries
        self._transport = transport or httpx.Client()
        self._sleeper = sleeper

    def encode(self, texts: list[str], *, normalize_embeddings: bool = True, **_kwargs: object) -> list[list[float]]:
        if not texts:
            return []
        if any(not isinstance(text, str) or not text.strip() for text in texts):
            raise EmbeddingProviderError("Embedding text must not be empty")
        response = self._post_with_retry(texts)
        vectors = self._parse_vectors(response, expected=len(texts))
        return [self._validate_vector(vector, normalize=normalize_embeddings) for vector in vectors]

    def _post_with_retry(self, texts: list[str]) -> Any:
        url = f"https://api.cloudflare.com/client/v4/accounts/{self._account_id}/ai/run/{self._model}"
        headers = {"Authorization": f"Bearer {self._api_token}", "Content-Type": "application/json"}

        for attempt in range(self._max_retries + 1):
            try:
                response = self._transport.post(url, headers=headers, json={"text": texts}, timeout=self._timeout_seconds)
            except (httpx.TimeoutException, TimeoutError) as error:
                if attempt >= self._max_retries:
                    raise EmbeddingProviderError("Cloudflare embedding timed out") from error
                self._sleeper(float(2**attempt))
                continue

            status = int(getattr(response, "status_code", 0))
            if status == 429 or status >= 500:
                if attempt >= self._max_retries:
                    raise EmbeddingProviderError(f"Cloudflare embedding HTTP {status}")
                self._sleeper(self._retry_delay(response, attempt))
                continue
            if status < 200 or status >= 300:
                raise EmbeddingProviderError(f"Cloudflare embedding HTTP {status}")
            return response

        raise EmbeddingProviderError("Cloudflare embedding did not complete")

    @staticmethod
    def _retry_delay(response: Any, attempt: int) -> float:
        raw = getattr(response, "headers", {}).get("Retry-After")
        if raw is not None:
            try:
                return min(max(float(raw), 0.0), MAX_RETRY_AFTER_SECONDS)
            except (TypeError, ValueError):
                pass
        return float(2**attempt)

    @staticmethod
    def _parse_vectors(response: Any, *, expected: int) -> list[Any]:
        try:
            body = response.json()
        except (TypeError, ValueError) as error:
            raise EmbeddingProviderError("Invalid Cloudflare embedding response") from error
        if not isinstance(body, dict) or body.get("success") is not True:
            raise EmbeddingProviderError("Invalid Cloudflare embedding response")
        result = body.get("result")
        data = result.get("data") if isinstance(result, dict) else None
        if not isinstance(data, list):
            raise EmbeddingProviderError("Cloudflare embedding response has no vectors")
        if len(data) != expected:
            raise EmbeddingProviderError("Cloudflare returned a different number of vectors than texts")
        return data

    def _validate_vector(self, raw: Any, *, normalize: bool) -> list[float]:
        if not isinstance(raw, list) or len(raw) != self._dimension:
            raise EmbeddingProviderError(f"Embedding must have exactly {self._dimension} dimensions")
        try:
            vector = [float(value) for value in raw]
        except (TypeError, ValueError) as error:
            raise EmbeddingProviderError("Embedding contains a non-numeric value") from error
        if not all(math.isfinite(value) for value in vector):
            raise EmbeddingProviderError("Embedding contains a non-finite value")
        norm = math.sqrt(sum(value * value for value in vector))
        if norm == 0:
            raise EmbeddingProviderError("Embedding is a zero vector")
        return [value / norm for value in vector] if normalize else vector


def cloudflare_embedder_from_env(
    env: Mapping[str, str] | None = None,
    *,
    transport: HttpTransport | None = None,
    sleeper: Callable[[float], None] = time.sleep,
) -> CloudflareEmbeddingClient:
    values = env if env is not None else os.environ
    try:
        dimension = int(values.get("EMBED_DIM", str(DEFAULT_EMBED_DIM)))
        timeout_seconds = float(values.get("EMBED_TIMEOUT_SECONDS", str(DEFAULT_TIMEOUT_SECONDS)))
        max_retries = int(values.get("EMBED_MAX_RETRIES", str(DEFAULT_MAX_RETRIES)))
    except ValueError as error:
        raise EmbeddingProviderError("Invalid numeric embedding configuration") from error

    return CloudflareEmbeddingClient(
        account_id=values.get("CLOUDFLARE_ACCOUNT_ID", ""),
        api_token=values.get("CLOUDFLARE_API_TOKEN", ""),
        model=values.get("EMBED_MODEL", CLOUDFLARE_BGE_M3),
        dimension=dimension,
        timeout_seconds=timeout_seconds,
        max_retries=max_retries,
        transport=transport,
        sleeper=sleeper,
    )


class VectorClient(Protocol):
    def query_points(self, collection_name: str, query: list[float], query_filter: Any, limit: int) -> Any: ...


@dataclass(frozen=True)
class SearchHit:
    id: int
    score: float


def get_client() -> VectorClient:
    from qdrant_client import QdrantClient

    url = os.environ.get("QDRANT_URL", "")
    if not url:
        raise RuntimeError("QDRANT_URL is not set.")
    # An explicit timeout: cold queries come close to the client's 5s default.
    return QdrantClient(
        url=url,
        api_key=os.environ.get("QDRANT_API_KEY") or None,
        timeout=int(os.environ.get("QDRANT_TIMEOUT_SECONDS", "30")),
    )


def _collection_name() -> str:
    return os.environ.get("QDRANT_COLLECTION", "doc_chunks")


def _build_filter(filters: dict[str, Any]) -> tuple[Any, bool]:
    """Return (filter, matches_nothing). An empty list means no value is valid, not "skip this filter"."""
    from qdrant_client.models import FieldCondition, Filter, IsNullCondition, MatchAny, MatchValue, PayloadField

    conditions = []
    for key, value in filters.items():
        if value is None:
            continue
        if not isinstance(value, (list, tuple, set)):
            conditions.append(FieldCondition(key=key, match=MatchValue(value=value)))
            continue
        if not value:
            return None, True
        has_null = any(item is None for item in value)
        real_values = sorted(item for item in value if item is not None)
        if not has_null:
            conditions.append(FieldCondition(key=key, match=MatchAny(any=real_values)))
            continue
        # Qdrant's MatchAny cannot match null, so `None` becomes an OR clause that still ANDs with other keys.
        branches = [IsNullCondition(is_null=PayloadField(key=key))]
        if real_values:
            branches.append(FieldCondition(key=key, match=MatchAny(any=real_values)))
        conditions.append(Filter(should=branches))
    return (Filter(must=conditions) if conditions else None), False


def search(
    query_vector: list[float],
    *,
    filters: dict[str, Any] | None = None,
    k: int = 5,
    client: VectorClient | None = None,
    collection_name: str | None = None,
) -> list[SearchHit]:
    """Filter values may be scalars (exact match) or lists (any of); filters are never relaxed on empty results."""
    if k <= 0:
        return []
    client = client or get_client()
    query_filter = None
    if filters:
        query_filter, matches_nothing = _build_filter(filters)
        if matches_nothing:
            return []

    # One retry: a dropped connection costs an article its source documents.
    collection = collection_name or _collection_name()
    for attempt in range(2):
        try:
            result = client.query_points(
                collection_name=collection,
                query=query_vector,
                query_filter=query_filter,
                limit=k,
            )
            break
        except Exception as error:  # noqa: BLE001 - retried once, then re-raised
            if attempt == 1:
                raise
            LOGGER.warning("Qdrant call failed (%s); retrying once.", type(error).__name__)
    return [SearchHit(id=point.id, score=point.score) for point in result.points]


@dataclass(frozen=True)
class RetrievedChunk:
    text: str
    collection: str
    doc_id: str
    chunk_index: int
    source_url: str
    snapshot_date: str
    score: float


def _model_filter(model_id: str | None) -> list[str | None] | None:
    # Shared brand documents carry no model id (stored as null or ""), and must always come along.
    return [model_id, "", None] if model_id else None


def _encode_query(query: str, embedder) -> list[float]:
    embedder = embedder or cloudflare_embedder_from_env()
    encoded = embedder.encode([query], normalize_embeddings=True)
    if len(encoded) != 1:
        raise ValueError("Embedder returned a different number of vectors than queries")
    vector = [float(value) for value in encoded[0]]
    if len(vector) != db.EMBED_DIM:
        raise ValueError(f"Query embedding must have exactly {db.EMBED_DIM} dimensions")
    if not all(math.isfinite(value) for value in vector):
        raise ValueError("Query embedding contains NaN or infinity")
    norm = math.sqrt(sum(value * value for value in vector))
    if norm == 0:
        raise ValueError("Query embedding must not be a zero vector")
    return [value / norm for value in vector]


def retrieve(
    engine: Any,
    query: str,
    *,
    collection: str | None = None,
    model_id: str | None = None,
    product_id: str | None = None,
    k: int = 5,
    embedder=None,
    client: VectorClient | None = None,
) -> list[RetrievedChunk]:
    """Search vectors in Qdrant, then read text and sources from Postgres by `doc_chunks.id`."""
    if k <= 0:
        return []

    hits = search(
        _encode_query(query, embedder),
        filters={"collection": collection, "model_id": _model_filter(model_id), "product_id": product_id},
        k=k,
        client=client,
    )
    if not hits:
        return []

    table = db.DocChunk.__table__
    with db.session_for(engine) as session:
        rows = session.execute(
            select(
                table.c.id,
                table.c.text,
                table.c.collection,
                table.c.doc_id,
                table.c.chunk_index,
                table.c.source_url,
                table.c.snapshot_date,
            ).where(table.c.id.in_([hit.id for hit in hits]))
        ).all()
    rows_by_id = {row.id: row for row in rows}

    return [
        RetrievedChunk(
            text=row.text,
            collection=row.collection,
            doc_id=row.doc_id,
            chunk_index=row.chunk_index,
            source_url=row.source_url,
            snapshot_date=row.snapshot_date,
            score=hit.score,
        )
        for hit in hits
        if (row := rows_by_id.get(hit.id)) is not None
    ]

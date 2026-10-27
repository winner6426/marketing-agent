"""The stateful campaign graph, with two human interrupt points.

A node containing `interrupt()` runs again in full on resume, so nothing may be written before the interrupt.
"""

from __future__ import annotations

import functools
import os
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor

from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, StateGraph
from langgraph.types import interrupt

from src import utils
from src.agents.nodes import brand_validator, channel_validator, fact_checker, planner, scheduler, writer
from src.agents.nodes.brief_analyst import brief_analyst_node, merge_brief_additions
from src.agents.nodes.quality_judge import quality_judge_node
from src.models import db
from src.models.campaign_state import CampaignState, normalize_channel, passes_all_tiers, render_outbound_text

# Per content item; the channel-spec and fact counters are separate so one cannot use up the other's turns.
MAX_RETRIES = 2

THREAD_ID_PREFIX = "campaign-"


# Routing: pure functions, state in and next node name out.
def after_brief(state: CampaignState) -> str:
    return "planner" if state.get("status") == "brief_ok" else "clarification"


def after_planner(state: CampaignState) -> str:
    return "writer" if state.get("status") == "plan_ok" else END


def after_fact_check(state: CampaignState) -> str:
    # Checked first: asking a manager to approve an empty list means asking them to sign nothing.
    if state.get("status") == "generation_failed":
        return END
    return "writer" if state.get("rewrite_queue") else "scheduler"


# Node contract: LangGraph silently drops keys that are not in `CampaignState`.
VALID_KEYS = frozenset(CampaignState.__annotations__)


class NodeContractError(RuntimeError):
    pass


def wrap_node(fn: Callable[..., dict], name: str = "") -> Callable[..., dict]:
    """Validate the output shape only. Exceptions pass through, because `interrupt()` relies on them."""
    label = name or getattr(fn, "__name__", "?")

    # *args/**kwargs are required: LangGraph inspects the signature to decide whether to pass `config`.
    @functools.wraps(fn)
    def _run(state: CampaignState, *args, **kwargs) -> dict:
        result = fn(state, *args, **kwargs)
        if result is None:
            return {}
        if not isinstance(result, dict):
            raise NodeContractError(f"Node `{label}` returned {type(result).__name__}; LangGraph needs a dict")
        if invalid_keys := sorted(key for key in result if key not in VALID_KEYS):
            raise NodeContractError(
                f"Node `{label}` returned keys missing from CampaignState: {invalid_keys}. "
                "LangGraph would drop them silently."
            )
        return result

    return _run


def _content_key(channel: str, variant: str) -> str:
    return f"{channel}/{variant}"


def _writer_concurrency() -> int:
    # key_pool always returns the same first key, so raising this concentrates traffic on one key.
    return max(1, int(os.environ.get("WRITER_CONCURRENCY", writer.BATCH_SIZE)))


def clarification_node(state: CampaignState) -> dict:
    response = interrupt(
        {
            "kind": "clarification",
            "questions": state.get("questions", []),
            "remaining_issue_count": state.get("remaining_issue_count", 0),
        }
    )
    return {"brief": merge_brief_additions(state.get("brief"), response.get("brief_additions"))}


def _validate_write_targets(write_targets: list) -> None:
    keys = [_content_key(channel, variant) for channel, variant in (tuple(target) for target in write_targets)]
    if duplicates := sorted({key for key in keys if keys.count(key) > 1}):
        raise ValueError(f"Duplicate content keys in the write batch: {duplicates}.")
    if not keys:
        raise ValueError("Nothing to write: the plan and the routing disagree.")


def writing_node(state: CampaignState) -> dict:
    """Write what is missing or was sent back. Parallel within a batch, sequential across batches."""
    drafts = dict(state.get("drafts") or {})
    documents = dict(state.get("rag_documents") or {})
    write_targets = state.get("rewrite_queue") or writer.list_write_targets(state.get("plan") or {})
    write_targets = [(normalize_channel(channel), variant) for channel, variant in write_targets]
    _validate_write_targets(write_targets)
    concurrency = _writer_concurrency()

    for batch in writer.split_batches(write_targets):
        if concurrency > 1 and len(batch) > 1:
            with ThreadPoolExecutor(max_workers=min(len(batch), concurrency)) as pool:
                futures = [
                    pool.submit(writer.write_content, state, channel=channel, variant=variant)
                    for channel, variant in batch
                ]
                # In submission order, so results match a sequential run.
                results = [future.result() for future in futures]
        else:
            results = [writer.write_content(state, channel=channel, variant=variant) for channel, variant in batch]

        for (channel, variant), result in zip(batch, results, strict=True):
            key = _content_key(channel, variant)
            if result["status"] == "draft_ok":
                drafts[key] = result["draft"]
                # Copied because cached RAG results can be shared between articles.
                documents[key] = list(result.get("rag_documents") or [])
            else:
                # The writer already spent its internal retry; this goes straight to a person.
                drafts[key] = {
                    "channel": channel,
                    "variant": variant,
                    "angle": "?",
                    "body": "",
                    "writer_error": result["error"],
                }
    return {
        "drafts": drafts,
        "rag_documents": documents,
        "rewrite_queue": [],
        "recently_written": [_content_key(channel, variant) for channel, variant in write_targets],
    }


def _validation_targets(state: CampaignState) -> list[str]:
    # Only what was just written: rechecking a resolved draft would overwrite its citations with an empty list.
    recent = state.get("recently_written")
    return list(recent) if recent else list((state.get("drafts") or {}).keys())


def channel_validation_node(state: CampaignState) -> dict:
    results = dict(state.get("validations") or {})
    drafts = dict(state.get("drafts") or {})
    for key in _validation_targets(state):
        draft = drafts[key]
        if draft.get("writer_error"):
            results[key] = {"channel_spec": {"ok": False, "violations": [{"message": draft["writer_error"]}]}}
            continue
        outcome = channel_validator.validate(draft)
        drafts[key] = outcome["draft"]
        results[key] = {"channel_spec": outcome}
    return {"validations": results, "drafts": drafts}


def brand_validation_node(state: CampaignState) -> dict:
    results = dict(state.get("validations") or {})
    drafts = state.get("drafts") or {}
    for key in _validation_targets(state):
        if not drafts[key].get("writer_error"):
            results[key] = dict(results.get(key, {})) | {"brand_rules": brand_validator.validate(drafts[key])}
    return {"validations": results}


def _campaign_id_from_config(config: RunnableConfig | None) -> int | None:
    thread_id = ((config or {}).get("configurable") or {}).get("thread_id", "")
    if not isinstance(thread_id, str) or not thread_id.startswith(THREAD_ID_PREFIX):
        return None
    try:
        campaign_id = int(thread_id.removeprefix(THREAD_ID_PREFIX))
    except ValueError:
        return None
    return campaign_id if campaign_id > 0 else None


def _ensure_content_item(campaign_id: int | None, content_key: str, draft: dict) -> int | None:
    """The fact checker needs this row's id to store citations; the runner fills in the rest afterwards."""
    if campaign_id is None:
        return None

    channel, variant = content_key.split("/", 1)
    with db.get_session() as session:
        if session.get(db.Campaign, campaign_id) is None:
            return None
        item = (
            session.query(db.ContentItem)
            .filter_by(campaign_id=campaign_id, channel=channel, variant=variant)
            .one_or_none()
        )
        if item is None:
            item = db.ContentItem(
                campaign_id=campaign_id,
                channel=channel,
                variant=variant,
                body=render_outbound_text(draft),
                status="draft",
            )
            session.add(item)
        else:
            item.body = render_outbound_text(draft)
            item.status = "draft"
        session.commit()
        return item.id


def fact_check_node(state: CampaignState, config: RunnableConfig) -> dict:
    results = dict(state.get("validations") or {})
    drafts = dict(state.get("drafts") or {})
    model_id = (state.get("brief") or {}).get("model_id", "")
    campaign_id = _campaign_id_from_config(config)

    for key in _validation_targets(state):
        draft = drafts[key]
        if draft.get("writer_error"):
            continue
        content_item_id = _ensure_content_item(campaign_id, key, draft)
        outcome = fact_checker.validate(draft, model_id=model_id, content_item_id=content_item_id)
        drafts[key] = outcome["draft"]
        results[key] = dict(results.get(key, {})) | {"fact_check": outcome}
    return {"validations": results, "drafts": drafts}


def retry_counter_node(state: CampaignState) -> dict:
    """Count retries per content item and decide which items get rewritten."""
    results = state.get("validations") or {}
    channel_retries = dict(state.get("retry_channel_spec") or {})
    fact_retries = dict(state.get("retry_fact") or {})
    write_targets: list[tuple[str, str]] = []
    drafts = state.get("drafts") or {}

    for key, validation in results.items():
        if (drafts.get(key) or {}).get("writer_error"):
            continue
        channel_failed = not validation.get("channel_spec", {}).get("ok", True)
        fact_failed = not validation.get("fact_check", {}).get("ok", True)
        if not (channel_failed or fact_failed):
            continue

        if channel_failed:
            channel_retries[key] = channel_retries.get(key, 0) + 1
        if fact_failed:
            fact_retries[key] = fact_retries.get(key, 0) + 1

        has_turns_left = (not channel_failed or channel_retries[key] <= MAX_RETRIES) and (
            not fact_failed or fact_retries[key] <= MAX_RETRIES
        )
        if has_turns_left:
            channel, variant = key.split("/")
            write_targets.append((channel, variant))

    result = {"retry_channel_spec": channel_retries, "retry_fact": fact_retries, "rewrite_queue": write_targets}
    usable = [draft for draft in drafts.values() if not draft.get("writer_error") and render_outbound_text(draft).strip()]
    if not usable:
        writer_errors = [draft["writer_error"] for draft in drafts.values() if draft.get("writer_error")]
        details = " | ".join(writer_errors) if writer_errors else "The writer returned no drafts."
        result |= {"status": "generation_failed", "error": f"The writer produced no usable content. {details}"}
    return result


def approval_node(state: CampaignState) -> dict:
    """Wait for the manager. Nothing is written before `interrupt()` because this node reruns on resume."""
    results = state.get("validations") or {}
    drafts = state.get("drafts") or {}
    reviews = state.get("quality_review") or {}

    contents = []
    passed_count = needs_attention_count = 0
    for key, draft in drafts.items():
        if draft.get("writer_error") or not render_outbound_text(draft).strip():
            continue
        validation = results.get(key, {})
        passed = passes_all_tiers(validation)
        passed_count += passed
        needs_attention_count += not passed
        # Only `passed` decides approval; the judge score is advisory and may be missing.
        contents.append(
            {
                "content_key": key,
                "draft": draft,
                "validations": validation,
                "passed": passed,
                "quality_review": reviews.get(key),
            }
        )

    decision = interrupt(
        {
            "kind": "approval",
            "contents": contents,
            "schedules": list((state.get("schedules") or {}).values()),
            "passed_count": passed_count,
            "needs_attention_count": needs_attention_count,
        }
    )
    return {"approval": decision}


def finalize_approval_node(state: CampaignState) -> dict:
    approval = state.get("approval") or {}
    approved = approval.get("decision") == "approve"
    schedules = {
        key: dict(slot)
        | {
            "status": "scheduled" if approved else "cancelled",
            "approved_by_id": str(approval.get("decided_by_id") or ""),
            "approved_by_email": str(approval.get("decided_by") or ""),
            "approved_at": utils.current_timestamp(),
        }
        for key, slot in (state.get("schedules") or {}).items()
    }
    return {"status": "approval" if approved else "rejected", "schedules": schedules}


def build_campaign_graph(checkpointer):
    # brief_analyst (<-> clarification) -> planner -> writer -> channel_validation -> brand_validation
    # -> fact_check -> retry_counter (-> writer) -> scheduler -> quality_judge -> approval -> finalize_approval
    graph = StateGraph(CampaignState)

    for node_name, node_function in (
        ("brief_analyst", brief_analyst_node),
        ("clarification", clarification_node),
        ("planner", planner.planner_node),
        ("writer", writing_node),
        ("channel_validation", channel_validation_node),
        ("brand_validation", brand_validation_node),
        ("fact_check", fact_check_node),
        ("retry_counter", retry_counter_node),
        ("scheduler", scheduler.scheduler_node),
        ("quality_judge", quality_judge_node),
        ("approval", approval_node),
        ("finalize_approval", finalize_approval_node),
    ):
        graph.add_node(node_name, wrap_node(node_function, node_name))

    graph.set_entry_point("brief_analyst")
    graph.add_conditional_edges("brief_analyst", after_brief, ["planner", "clarification"])
    graph.add_edge("clarification", "brief_analyst")
    graph.add_conditional_edges("planner", after_planner, ["writer", END])
    graph.add_edge("writer", "channel_validation")
    graph.add_edge("channel_validation", "brand_validation")
    graph.add_edge("brand_validation", "fact_check")
    graph.add_edge("fact_check", "retry_counter")
    graph.add_conditional_edges("retry_counter", after_fact_check, ["writer", "scheduler", END])
    # After the retry loop so it never scores a draft about to be replaced; before approval so managers see the score.
    graph.add_edge("scheduler", "quality_judge")
    graph.add_edge("quality_judge", "approval")
    graph.add_edge("approval", "finalize_approval")
    graph.add_edge("finalize_approval", END)

    return graph.compile(checkpointer=checkpointer)


def make_checkpointer():
    """Postgres when DATABASE_URL is Postgres, otherwise SQLite. The saver lives as long as the process."""
    from src.config import get_settings

    url = get_settings().database_url

    if url.startswith(("postgresql://", "postgres://", "postgresql+psycopg://")):
        from langgraph.checkpoint.postgres import PostgresSaver
        from psycopg_pool import ConnectionPool

        pool = ConnectionPool(
            url.replace("postgresql+psycopg://", "postgresql://"),
            min_size=1,
            max_size=2,
            timeout=30,
            kwargs={"autocommit": True, "prepare_threshold": 0},
            open=True,
        )
        saver = PostgresSaver(pool)
        saver.setup()
        return saver

    import sqlite3
    from pathlib import Path

    from langgraph.checkpoint.sqlite import SqliteSaver

    Path("data").mkdir(parents=True, exist_ok=True)
    # FastAPI runs sync handlers in a thread pool, so the connection crosses threads.
    connection = sqlite3.connect("data/checkpoints.db", check_same_thread=False)
    saver = SqliteSaver(connection)
    saver.setup()
    return saver

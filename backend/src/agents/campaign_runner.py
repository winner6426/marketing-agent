"""The boundary between services and the graph: LangGraph details such as interrupts and thread ids stop here."""

from __future__ import annotations

import hashlib
import json
import logging

from src import utils
from src.agents import campaign_graph
from src.agents.nodes import brand_validator, channel_validator, fact_checker, quality_judge
from src.models import db
from src.models.campaign_state import campaign_name, passes_all_tiers, render_outbound_text

LOGGER = logging.getLogger(__name__)

# Revalidate one edited draft outside the graph: resuming would replay stale checkpoint data.

class ContentRevisionConflictError(RuntimeError):
    """The draft changed while its previous revision was being evaluated."""


def content_revision(draft: dict) -> str:
    normalized_draft = utils.normalize_draft_nfc(dict(draft or {}))
    serialized = json.dumps(normalized_draft, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def content_needs_revalidation(metadata: dict) -> bool:
    metadata = metadata or {}
    draft = dict(metadata.get("draft") or {})
    current_revision = metadata.get("content_revision") or content_revision(draft)
    if metadata.get("validated_revision") != current_revision:
        return True
    if passes_all_tiers(dict(metadata.get("validations") or {})):
        return (
            metadata.get("quality_review_revision") != current_revision
            or metadata.get("quality_review_status") != "completed"
        )
    return False


def _load_for_revalidation(engine, campaign_id: int, content_item_id: int) -> tuple[dict, str, str, str, list | None]:
    with db.session_for(engine) as session:
        campaign = session.get(db.Campaign, campaign_id)
        item = session.query(db.ContentItem).filter_by(id=content_item_id, campaign_id=campaign_id).one_or_none()
        if campaign is None or item is None:
            raise ValueError(f"No content item id={content_item_id} in campaign {campaign_id}")
        metadata = dict(item.meta or {})
        draft = utils.normalize_draft_nfc(dict(metadata.get("draft") or {}))
        if not draft:
            raise ValueError(f"Content item id={content_item_id} has no structured draft")
        brief = campaign.brief or {}
        return (
            draft,
            metadata.get("content_revision") or content_revision(draft),
            str(brief.get("model_id") or ""),
            str(brief.get("segment") or "").strip(),
            # The chunks the writer actually read; None (not []) makes the judge drop the grounding axis.
            list(metadata.get("rag_documents") or []) or None,
        )


def revalidate_content(engine, campaign_id: int, content_item_id: int) -> dict:
    draft, starting_revision, model_id, persona, documents = _load_for_revalidation(engine, campaign_id, content_item_id)

    channel_result = channel_validator.validate(draft)
    channel_draft = dict(channel_result.get("draft") or draft)
    brand_result = brand_validator.validate(channel_draft)
    fact_result = fact_checker.validate(channel_draft, model_id=model_id, content_item_id=content_item_id)
    evaluated_draft = utils.normalize_draft_nfc(dict(fact_result.get("draft") or channel_draft))
    validations = {"channel_spec": channel_result, "brand_rules": brand_result, "fact_check": fact_result}
    passed = passes_all_tiers(validations)

    quality_review = None
    quality_review_status = "not_run"
    if passed:
        try:
            quality_review = quality_judge.score(evaluated_draft, documents=documents, persona=persona or None)
            quality_review_status = "completed"
        except Exception as error:  # noqa: BLE001 - an advisory failure must leave a safe, retryable draft
            quality_review_status = "failed"
            LOGGER.warning("The judge failed for content item `%s`: %s", content_item_id, error)

    final_revision = content_revision(evaluated_draft)
    with db.session_for(engine) as session:
        item = session.query(db.ContentItem).filter_by(id=content_item_id, campaign_id=campaign_id).one_or_none()
        if item is None:
            raise ValueError(f"No content item id={content_item_id} in campaign {campaign_id}")
        current_metadata = dict(item.meta or {})
        current_draft = dict(current_metadata.get("draft") or {})
        current_revision = current_metadata.get("content_revision") or content_revision(current_draft)
        if current_revision != starting_revision:
            raise ContentRevisionConflictError(
                f"Content item id={content_item_id} changed while revision {starting_revision} was being evaluated"
            )

        item.body = render_outbound_text(evaluated_draft)
        item.status = "passed" if passed else "needs_human"
        item.meta = {
            **current_metadata,
            "draft": evaluated_draft,
            "validations": validations,
            "quality_review": quality_review,
            "quality_review_status": quality_review_status,
            "content_revision": final_revision,
            "validated_revision": final_revision,
            "quality_review_revision": final_revision if quality_review_status == "completed" else None,
            "selected_for_approval": False,
        }
        session.commit()

    return {
        "content_item_id": content_item_id,
        "passed": passed,
        "validations": validations,
        "quality_review": quality_review,
        "quality_review_status": quality_review_status,
        "content_revision": final_revision,
    }


# Graph statuses copied onto the campaign row as soon as a run stops, so pollers never wait on a stale `running`.
PERSISTED_RUN_STATUSES = {"waiting_approval", "generation_failed", "failed", "needs_clarification"}


class InvalidContentSelectionError(ValueError):
    """The marketer did not choose exactly one content item per channel."""


class ContentNotReadyForApprovalError(ValueError):
    """A selected item does not carry fresh validation and quality evidence."""


def _thread(campaign_id: int) -> dict:
    return {"configurable": {"thread_id": f"{campaign_graph.THREAD_ID_PREFIX}{campaign_id}"}}


class CampaignRunner:
    def __init__(self, app=None):
        self._app = app or campaign_graph.build_campaign_graph(campaign_graph.make_checkpointer())

    def create(self, brief: dict, *, created_by: str, created_by_id: str, name: str = "") -> int:
        with db.get_session() as session:
            campaign = db.Campaign(
                name=name or campaign_name(brief),
                brief=brief,
                status="draft",
                created_by=created_by,
                created_by_id=created_by_id,
            )
            session.add(campaign)
            session.commit()
            return campaign.id

    def _sync_content(self, campaign_id: int, state: dict) -> None:
        """Upsert by (campaign, channel, variant) because nodes rerun on resume and retries."""
        validation_results = state.get("validations") or {}
        quality_reviews = state.get("quality_review") or {}
        documents_by_key = state.get("rag_documents") or {}
        with db.get_session() as session:
            for key, draft in (state.get("drafts") or {}).items():
                channel, variant = key.split("/")
                validation = validation_results.get(key, {})
                passed = passes_all_tiers(validation)

                row = (
                    session.query(db.ContentItem)
                    .filter_by(campaign_id=campaign_id, channel=channel, variant=variant)
                    .one_or_none()
                )
                revision = content_revision(draft)
                quality_review = quality_reviews.get(key)
                previous_meta = dict(row.meta or {}) if row is not None else {}
                meta = {
                    "draft": draft,
                    "angle": draft.get("angle"),
                    "validations": validation,
                    "hashtags": draft.get("hashtags", []),
                    "quality_review": quality_review,
                    "quality_review_status": (
                        "completed" if quality_review is not None else ("failed" if passed else "not_run")
                    ),
                    "content_revision": revision,
                    "validated_revision": revision,
                    "quality_review_revision": revision if quality_review is not None else None,
                    "selected_for_approval": bool(previous_meta.get("selected_for_approval", False)),
                    "writer_error": draft.get("writer_error"),
                    # Keep older documents when this run's retrieval failed.
                    "rag_documents": documents_by_key.get(key) or previous_meta.get("rag_documents") or [],
                }
                status = "passed" if passed else "needs_human"
                body = render_outbound_text(draft)

                if row is None:
                    session.add(
                        db.ContentItem(
                            campaign_id=campaign_id,
                            channel=channel,
                            variant=variant,
                            body=body,
                            status=status,
                            meta=meta,
                        )
                    )
                else:
                    row.body = body
                    row.status = status
                    row.meta = meta
            session.commit()

    def _sync_schedules(self, campaign_id: int, state: dict) -> None:
        schedules = state.get("schedules") or {}
        if not schedules:
            return
        with db.get_session() as session:
            for content_key, slot in schedules.items():
                channel, variant = content_key.split("/", 1)
                content = (
                    session.query(db.ContentItem)
                    .filter_by(campaign_id=campaign_id, channel=channel, variant=variant)
                    .one_or_none()
                )
                if content is None:
                    continue
                row = session.query(db.ScheduleSlot).filter_by(content_item_id=content.id).one_or_none()
                values = {
                    "campaign_id": campaign_id,
                    "content_item_id": content.id,
                    "scheduled_at": slot["scheduled_at"],
                    "status": slot.get("status", "proposed"),
                    "reason": slot.get("reason", ""),
                    "approved_by": slot.get("approved_by_email", ""),
                    "approved_by_id": slot.get("approved_by_id") or None,
                    "approved_at": slot.get("approved_at") or None,
                }
                if row is None:
                    session.add(db.ScheduleSlot(**values))
                else:
                    for key, value in values.items():
                        setattr(row, key, value)
            session.commit()

    @staticmethod
    def _schedule_payload(session, campaign_id: int) -> list[dict]:
        rows = (
            session.query(db.ScheduleSlot, db.ContentItem)
            .join(db.ContentItem, db.ContentItem.id == db.ScheduleSlot.content_item_id)
            .filter(db.ScheduleSlot.campaign_id == campaign_id)
            .order_by(db.ScheduleSlot.scheduled_at, db.ScheduleSlot.id)
            .all()
        )
        return [
            {
                "slot_id": slot.id,
                "content_key": f"{content.channel}/{content.variant}",
                "content_item_id": content.id,
                "channel": content.channel,
                "variant": content.variant,
                "scheduled_at": slot.scheduled_at,
                "scheduled_date": slot.scheduled_at[:10],
                "scheduled_time": slot.scheduled_at[11:16],
                "status": slot.status,
                "reason": slot.reason,
            }
            for slot, content in rows
        ]

    @staticmethod
    def _record_approval(campaign_id: int, decision: dict, reviewer: str, reviewer_id: str) -> None:
        """One row per item the decision applies to; approving never records items that failed validation."""
        is_approved = decision.get("decision") == "approve"
        with db.get_session() as session:
            for item in session.query(db.ContentItem).filter_by(campaign_id=campaign_id).all():
                if is_approved and item.status != "passed":
                    continue
                session.add(
                    db.Approval(
                        campaign_id=campaign_id,
                        content_item_id=item.id,
                        decision=decision.get("decision", "reject"),
                        reason=decision.get("reason", ""),
                        decided_by=reviewer,
                        decided_by_id=reviewer_id,
                    )
                )
                if is_approved:
                    item.status = "approved"
            session.commit()

    def _invoke(self, campaign_id: int, input_data, *, keep_campaign_draft: bool = False) -> dict:
        output = self._app.invoke(input_data, _thread(campaign_id))
        snapshot = self._app.get_state(_thread(campaign_id))
        state = snapshot.values
        self._sync_content(campaign_id, state)
        self._sync_schedules(campaign_id, state)
        status = state.get("status")
        if status in PERSISTED_RUN_STATUSES:
            with db.get_session() as session:
                campaign = session.get(db.Campaign, campaign_id)
                if campaign is not None:
                    campaign.status = "draft" if keep_campaign_draft and status == "waiting_approval" else status
                    session.commit()
        return self._translate(campaign_id, output, state, snapshot)

    def _translate(self, campaign_id: int, output: dict, state: dict, snapshot) -> dict:
        with db.get_session() as session:
            rows = (
                session.query(db.ContentItem)
                .filter_by(campaign_id=campaign_id)
                .order_by(db.ContentItem.channel, db.ContentItem.variant)
                .all()
            )
            contents = [self._content_payload(session, row, state) for row in rows]
            schedules = self._schedule_payload(session, campaign_id)

        pending = tuple(getattr(snapshot, "next", ()) or ())
        return {
            "campaign_id": campaign_id,
            "status": state.get("status", "draft"),
            "error": state.get("error") or None,
            "current_node": str(pending[0]) if pending else None,
            "pending_human_action": dict(output["__interrupt__"][0].value) if "__interrupt__" in output else None,
            "plan": state.get("plan"),
            "schedules": schedules,
            "contents": contents,
        }

    @staticmethod
    def _content_payload(session, content: db.ContentItem, state: dict) -> dict:
        key = f"{content.channel}/{content.variant}"
        meta = dict(content.meta or {})
        draft = dict(
            meta.get("draft")
            or (state.get("drafts") or {}).get(key)
            or {"channel": content.channel, "variant": content.variant, "body": content.body}
        )
        citations = (
            session.query(db.ContentCitation)
            .filter_by(content_item_id=content.id)
            .order_by(db.ContentCitation.id)
            .all()
        )
        return {
            "content_key": key,
            "content_item_id": content.id,
            "draft": draft,
            "validations": dict(meta.get("validations") or (state.get("validations") or {}).get(key, {})),
            "citations": [
                {
                    "placeholder": citation.placeholder,
                    "raw_value": citation.raw_value,
                    "display_value": citation.display_value,
                    "source_table": citation.source_table,
                    "source_key": citation.source_key,
                    "source_url": citation.source_url,
                    "snapshot_date": citation.snapshot_date,
                    "condition": citation.condition,
                    "resolved_at": citation.resolved_at,
                }
                for citation in citations
            ],
            # None means "could not be scored", which the UI must show differently from a low score.
            "quality_review": (
                meta["quality_review"] if "quality_review" in meta else (state.get("quality_review") or {}).get(key)
            ),
            "selected_for_approval": bool(meta.get("selected_for_approval", False)),
            "writer_error": draft.get("writer_error"),
            "status": content.status,
        }

    def _brief(self, campaign_id: int) -> dict:
        with db.get_session() as session:
            campaign = session.get(db.Campaign, campaign_id)
            if campaign is None:
                raise KeyError(f"No campaign id={campaign_id}")
            return dict(campaign.brief or {})

    def run(self, campaign_id: int, *, keep_campaign_draft: bool = False) -> dict:
        brief = self._brief(campaign_id)
        # After a node failure the checkpoint holds the unfinished task; invoke(None) continues it.
        snapshot = self._app.get_state(_thread(campaign_id))
        if (getattr(snapshot, "values", {}) or {}).get("error"):
            self._app.update_state(_thread(campaign_id), {"error": ""})
            return self._invoke(campaign_id, None, keep_campaign_draft=keep_campaign_draft)
        return self._invoke(campaign_id, {"brief": brief}, keep_campaign_draft=keep_campaign_draft)

    def mark_failed(self, campaign_id: int, message: str) -> None:
        self._app.update_state(_thread(campaign_id), {"error": message})
        with db.get_session() as session:
            campaign = session.get(db.Campaign, campaign_id)
            if campaign is not None:
                campaign.status = "failed"
                session.commit()

    def is_waiting_for_clarification(self, campaign_id: int) -> bool:
        return "clarification" in (getattr(self._app.get_state(_thread(campaign_id)), "next", ()) or ())

    def answer(self, campaign_id: int, brief_additions: dict, *, keep_campaign_draft: bool = False) -> dict:
        from langgraph.types import Command

        result = self._invoke(
            campaign_id,
            Command(resume={"brief_additions": brief_additions}),
            keep_campaign_draft=keep_campaign_draft,
        )
        merged_brief = dict(self._app.get_state(_thread(campaign_id)).values.get("brief") or {})
        # Persist the interpreted brief so a later retry never starts over.
        with db.get_session() as session:
            campaign = session.get(db.Campaign, campaign_id)
            if campaign is not None:
                campaign.brief = merged_brief or (dict(campaign.brief or {}) | brief_additions)
                session.commit()
        return result

    def promote_chat_draft(self, campaign_id: int, selected_content_item_ids: list[int]) -> dict:
        """Send exactly one fresh, validated variant per channel to manager review."""
        state = dict(self._app.get_state(_thread(campaign_id)).values or {})
        if state.get("status") != "waiting_approval" or not state.get("drafts"):
            raise ValueError("The chat draft is not ready for approval")

        selected_ids = list(selected_content_item_ids or [])
        if len(selected_ids) != len(set(selected_ids)):
            raise InvalidContentSelectionError("selected_content_item_ids contains duplicates")

        selected_drafts: dict[str, dict] = {}
        selected_validations: dict[str, dict] = {}
        selected_reviews: dict[str, dict] = {}
        with db.get_session() as session:
            campaign = session.get(db.Campaign, campaign_id)
            if campaign is None:
                raise KeyError(f"No campaign id={campaign_id}")
            if campaign.status != "draft":
                raise ValueError("The campaign is not a chat draft")
            items = (
                session.query(db.ContentItem)
                .filter_by(campaign_id=campaign_id)
                .order_by(db.ContentItem.channel, db.ContentItem.variant)
                .all()
            )
            selected_items = [item for item in items if item.id in set(selected_ids)]
            if len(selected_items) != len(selected_ids):
                raise InvalidContentSelectionError("A selected content item does not belong to this campaign")

            selected_channels = [item.channel for item in selected_items]
            if set(selected_channels) != {item.channel for item in items} or len(selected_channels) != len(
                set(selected_channels)
            ):
                raise InvalidContentSelectionError("Select exactly one content item for every campaign channel")

            for item in selected_items:
                metadata = dict(item.meta or {})
                draft = dict(metadata.get("draft") or {})
                revision = metadata.get("content_revision") or content_revision(draft)
                validations = dict(metadata.get("validations") or {})
                has_fresh_review = (
                    metadata.get("quality_review_status") == "completed"
                    and metadata.get("quality_review_revision") == revision
                    and metadata.get("quality_review") is not None
                )
                if (
                    item.status != "passed"
                    or metadata.get("validated_revision") != revision
                    or not passes_all_tiers(validations)
                    or not has_fresh_review
                ):
                    raise ContentNotReadyForApprovalError(
                        f"Content item id={item.id} must finish fresh validation and quality review before submission"
                    )
                key = f"{item.channel}/{item.variant}"
                selected_drafts[key] = draft
                selected_validations[key] = validations
                selected_reviews[key] = dict(metadata["quality_review"])

            selected_id_set = set(selected_ids)
            for item in items:
                metadata = dict(item.meta or {})
                is_selected = item.id in selected_id_set
                metadata["selected_for_approval"] = is_selected
                item.meta = metadata
                if not is_selected:
                    item.status = "draft"
            session.commit()

        self._app.update_state(
            _thread(campaign_id),
            {
                "drafts": selected_drafts,
                "validations": selected_validations,
                "quality_review": selected_reviews,
                "schedules": {
                    key: slot for key, slot in (state.get("schedules") or {}).items() if key in selected_drafts
                },
            },
        )

        with db.get_session() as session:
            campaign = session.get(db.Campaign, campaign_id)
            if campaign is None:
                raise KeyError(f"No campaign id={campaign_id}")
            campaign.status = "waiting_approval"
            session.commit()
        return self.get(campaign_id)

    def delete(self, campaign_id: int) -> dict:
        with db.get_session() as session:
            campaign = session.get(db.Campaign, campaign_id)
            if campaign is None:
                raise KeyError(f"No campaign id={campaign_id}")
            previous_status = campaign.status
            session.delete(campaign)
            session.commit()

        checkpointer = getattr(self._app, "checkpointer", None)
        if checkpointer is not None and hasattr(checkpointer, "delete_thread"):
            checkpointer.delete_thread(f"{campaign_graph.THREAD_ID_PREFIX}{campaign_id}")
        return {"campaign_id": campaign_id, "deleted": True, "previous_status": previous_status}

    def review(self, campaign_id: int, decision: dict, reviewer: str, reviewer_id: str) -> dict:
        from langgraph.types import Command

        result = self._invoke(
            campaign_id,
            Command(resume=decision | {"decided_by": reviewer, "decided_by_id": reviewer_id}),
        )
        self._record_approval(campaign_id, decision, reviewer, reviewer_id)
        with db.get_session() as session:
            campaign = session.get(db.Campaign, campaign_id)
            if campaign is not None:
                campaign.status = result["status"]
                session.commit()
        return result

    def get(self, campaign_id: int) -> dict:
        """Read current state, including a pending interrupt that only `invoke` output would otherwise expose."""
        snapshot = self._app.get_state(_thread(campaign_id))
        interrupts = [
            interrupt
            for task in getattr(snapshot, "tasks", ()) or ()
            for interrupt in (getattr(task, "interrupts", ()) or ())
        ]
        output = {"__interrupt__": interrupts} if interrupts else {}
        return self._translate(campaign_id, output, snapshot.values, snapshot)


# Built lazily because the checkpointer touches disk; tests inject one backed by MemorySaver.
_runner: CampaignRunner | None = None


def get_runner() -> CampaignRunner:
    global _runner
    if _runner is None:
        _runner = CampaignRunner()
    return _runner


def set_runner(runner: CampaignRunner | None) -> None:
    global _runner
    _runner = runner

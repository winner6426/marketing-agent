"""End-to-end flows over HTTP with a real graph and database; only the LLM is faked."""

from __future__ import annotations

import pytest

from src.agents import campaign_graph, campaign_runner
from src.models import db
from tests import samples
from tests.conftest import MANAGER_ID, MARKETER_ID, OTHER_MARKETER_ID, auth_headers, valid_brief

MARKETER = auth_headers(MARKETER_ID)
RUN_PATH = "/api/marketer/campaigns/{}/run"


def _marketer(key: str) -> dict:
    return auth_headers(MARKETER_ID, key=key)


def _manager(key: str | None = None) -> dict:
    return auth_headers(MANAGER_ID, key=key)


def _create_and_run(client, brief: dict | None = None) -> int:
    created = client.post("/api/marketer/campaigns", headers=auth_headers(MARKETER_ID), json={"brief": brief or valid_brief()})
    campaign_id = created.json()["campaign_id"]
    response = client.post(RUN_PATH.format(campaign_id), headers=_marketer("run-1"))
    assert response.status_code == 202
    assert response.json()["status"] == "running"
    return campaign_id


def _detail(client, campaign_id: int) -> dict:
    response = client.get(f"/api/marketer/campaigns/{campaign_id}", headers=auth_headers(MARKETER_ID))
    assert response.status_code == 200
    return response.json()


def _create_chat_draft(client) -> tuple[int, dict]:
    response = client.post("/api/marketer/chat-drafts", headers=_marketer("draft-1"), json={"brief": valid_brief()})
    assert response.status_code == 202
    draft_id = response.json()["draft_id"]
    return draft_id, _detail(client, draft_id)


def _one_item_per_channel(detail: dict) -> list[int]:
    chosen = {}
    for content in detail["contents"]:
        chosen.setdefault(content["draft"]["channel"], content["content_item_id"])
    return list(chosen.values())


@pytest.fixture
def ready(users, seeded_catalog, fake_llm):
    return fake_llm


def test_chat_draft_flow_on_the_production_sqlite_checkpointer(client, ready, monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    runner = campaign_runner.CampaignRunner()
    assert type(runner._app.checkpointer).__name__ == "SqliteSaver"
    campaign_runner.set_runner(runner)

    created = client.post("/api/marketer/chat-drafts", headers=_marketer("d"), json={"brief": {"model_id": "VF3"}})
    draft_id = created.json()["draft_id"]
    assert _detail(client, draft_id)["pending_human_action"]["kind"] == "clarification"

    answered = client.post(
        f"/api/marketer/chat-drafts/{draft_id}/answer",
        headers=_marketer("a"),
        json={"brief_additions": valid_brief()},
    )
    assert answered.status_code == 202
    detail = _detail(client, draft_id)
    assert detail["status"] == "draft"

    submitted = client.post(
        f"/api/marketer/chat-drafts/{draft_id}/submit",
        headers=_marketer("s"),
        json={"selected_content_item_ids": _one_item_per_channel(detail)},
    )
    assert submitted.status_code == 201
    review = client.post(
        f"/api/manager/campaigns/{draft_id}/review", headers=_manager("r"), json={"decision": "approve"}
    )
    assert review.json()["status"] == "approval"
    assert len(client.post(f"/api/manager/campaigns/{draft_id}/publish", headers=_manager("p")).json()["published"]) == 2

    deleted = client.delete(
        f"/api/marketer/campaigns/{draft_id}", headers=auth_headers(MARKETER_ID), params={"confirm_approved": True}
    )
    assert deleted.json()["deleted"] is True


def test_full_campaign_flow_generates_validates_reviews_and_publishes(client, ready):
    campaign_id = _create_and_run(client)
    detail = _detail(client, campaign_id)

    assert detail["status"] == "waiting_approval"
    assert detail["error"] is None
    assert len(detail["contents"]) == 4
    assert {content["status"] for content in detail["contents"]} == {"passed"}
    assert detail["pending_human_action"]["kind"] == "approval"
    assert detail["plan"]["main_message"] == samples.PLAN_MESSAGE
    assert len(detail["schedules"]) == 4

    facebook = next(c for c in detail["contents"] if c["content_key"] == "facebook/A")
    # Placeholders were resolved from the database, with the source and condition attached.
    assert samples.RESOLVED_PRICE in facebook["draft"]["body"]
    assert "210 km" in facebook["draft"]["body"]
    assert "{{" not in facebook["draft"]["body"]
    citations = {citation["placeholder"]: citation for citation in facebook["citations"]}
    price = citations["{{price_vnd:VF3:eco:battery_included}}"]
    assert price["raw_value"] == "235000000"
    assert price["source_table"] == "product_variants"
    assert price["source_url"] == "https://example.com/vf3"
    assert "list price" in price["condition"]
    assert facebook["validations"]["fact_check"]["ok"] is True
    # No human signature configured, so the citation must not claim to match its source.
    assert facebook["validations"]["fact_check"]["verified"] is False
    assert "NOT verified" in facebook["validations"]["fact_check"]["label"]
    assert facebook["quality_review"]["average"] == 4

    sms = next(c for c in detail["contents"] if c["content_key"] == "direct_message/A")
    assert sms["draft"]["body"].startswith("[QC] ")
    assert sms["draft"]["body"].endswith("Soan TC gui 9999 de tu choi.")

    review = client.post(
        f"/api/manager/campaigns/{campaign_id}/review", headers=_manager("review-1"), json={"decision": "approve"}
    )
    assert review.status_code == 200
    assert review.json()["status"] == "approval"
    with db.get_session() as session:
        assert session.query(db.Approval).filter_by(campaign_id=campaign_id, decision="approve").count() == 4
        assert session.query(db.ContentItem).filter_by(status="approved").count() == 4

    calendar = client.get(
        "/api/manager/schedules", headers=_manager(), params={"date_from": "2030-09-01", "date_to": "2030-09-30"}
    )
    assert len(calendar.json()["schedules"]) == 4

    publish = client.post(f"/api/manager/campaigns/{campaign_id}/publish", headers=_manager("publish-1"))
    assert publish.status_code == 200
    assert len(publish.json()["published"]) == 4
    assert publish.json()["published"][0]["url"].startswith("/articles/")
    assert _detail(client, campaign_id)["contents"]

    send = client.post(
        f"/api/marketer/campaigns/{campaign_id}/manual-sends",
        headers=auth_headers(MARKETER_ID),
        json={"content_item_id": sms["content_item_id"], "channel": "sms", "sent_content": "x", "recipient_count": 2},
    )
    assert send.status_code == 201

    with db.get_session() as session:
        actions = {row.action for row in session.query(db.AuditLog).all()}
    assert {"create_campaign", "run_pipeline", "approve", "publish", "manual_send"} <= actions

    analytics = client.get("/api/manager/analytics", headers=_manager(), params={"campaign_id": campaign_id}).json()
    assert analytics["campaigns"]["content_count"] == 4
    assert analytics["campaigns"]["published_on_site_count"] == 4


def test_incomplete_brief_asks_every_question_before_any_generation(client, ready):
    campaign_id = _create_and_run(client, {"model_id": "VF3"})
    detail = _detail(client, campaign_id)

    assert detail["status"] == "needs_clarification"
    pending = detail["pending_human_action"]
    assert pending["kind"] == "clarification"
    assert pending["remaining_issue_count"] == 5
    assert "writer" not in ready.calls and "planner" not in ready.calls

    answer = client.post(
        f"/api/marketer/campaigns/{campaign_id}/answer",
        headers=_marketer("answer-1"),
        json={"brief_additions": valid_brief()},
    )
    assert answer.status_code == 202
    assert _detail(client, campaign_id)["status"] == "waiting_approval"


def test_answer_is_refused_unless_a_question_is_pending(client, ready):
    campaign_id = _create_and_run(client)
    response = client.post(
        f"/api/marketer/campaigns/{campaign_id}/answer",
        headers=_marketer("answer-2"),
        json={"brief_additions": {"goal": "launch"}},
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "no_clarification_pending"
    assert _detail(client, campaign_id)["status"] == "waiting_approval"


def test_unknown_model_is_questioned_not_corrected(client, ready):
    campaign_id = _create_and_run(client, valid_brief() | {"model_id": "VF33"})
    detail = _detail(client, campaign_id)
    assert detail["status"] == "needs_clarification"
    assert any("VF33" in question for question in detail["pending_human_action"]["questions"])


def test_rerunning_a_campaign_awaiting_approval_is_refused(client, ready):
    campaign_id = _create_and_run(client)
    response = client.post(RUN_PATH.format(campaign_id), headers=_marketer("run-2"))
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "campaign_not_runnable"


def test_replayed_run_key_does_not_rerun_or_leave_status_running(client, ready):
    created = client.post("/api/marketer/campaigns", headers=auth_headers(MARKETER_ID), json={"brief": {"model_id": "VF3"}})
    campaign_id = created.json()["campaign_id"]
    client.post(RUN_PATH.format(campaign_id), headers=_marketer("same"))
    calls_before = len(ready.calls)

    client.post(RUN_PATH.format(campaign_id), headers=_marketer("same"))

    assert len(ready.calls) == calls_before
    with db.get_session() as session:
        assert session.get(db.Campaign, campaign_id).status == "needs_clarification"


def test_idempotency_key_is_not_shared_between_campaigns(client, ready):
    first = _create_and_run(client)
    created = client.post("/api/marketer/campaigns", headers=auth_headers(MARKETER_ID), json={"brief": valid_brief()})
    second = created.json()["campaign_id"]
    client.post(RUN_PATH.format(second), headers=_marketer("run-1"))
    assert first != second
    assert _detail(client, second)["status"] == "waiting_approval"


def test_failed_run_reaches_the_database(client, users, seeded_catalog, fake_llm, monkeypatch):
    from src.agents.nodes import planner

    def explode(_state):
        raise RuntimeError("database connection lost")

    monkeypatch.setattr(planner, "planner_node", explode)
    from langgraph.checkpoint.memory import MemorySaver

    campaign_runner.set_runner(campaign_runner.CampaignRunner(app=campaign_graph.build_campaign_graph(MemorySaver())))

    campaign_id = _create_and_run(client)
    detail = _detail(client, campaign_id)
    assert detail["status"] == "failed"
    assert "database connection lost" in detail["error"]


def test_writer_that_always_fails_ends_as_generation_failed(client, ready):
    ready.writer_override = lambda _message: "this is not json"
    campaign_id = _create_and_run(client)
    detail = _detail(client, campaign_id)
    assert detail["status"] == "generation_failed"
    assert detail["pending_human_action"] is None
    assert ready.calls.count("judge") == 0


def test_writer_raw_numbers_are_rejected_and_retried(client, ready):
    attempts = []

    def writer(message: str) -> str:
        attempts.append("corrected" if "raw numbers" in message else "first")
        if "raw numbers" not in message and "channel `facebook`" in message:
            return (
                '{"hook": "Hook", "body": "' + samples.RAW_NUMBER_CASES[1][0] + '", '
                '"hashtags": ["#a", "#b", "#c"], "cta": "CTA"}'
            )
        if "channel `direct_message`" in message:
            return '{"body": "' + samples.SMS_BODY + '"}'
        return '{"hook": "Hook", "body": "' + samples.SAFE_BODY + '", "hashtags": ["#a", "#b", "#c"], "cta": "CTA"}'

    ready.writer_override = writer
    campaign_id = _create_and_run(client)
    assert "corrected" in attempts
    assert {content["status"] for content in _detail(client, campaign_id)["contents"]} == {"passed"}


def test_banned_word_blocks_content_but_not_the_campaign(client, ready):
    def writer(message: str) -> str:
        if "channel `direct_message`" in message:
            return '{"body": "' + samples.SMS_BODY + '"}'
        variant_a = "variant A" in message
        body = samples.BANNED_TEXT if variant_a else samples.SAFE_BODY
        return '{"hook": "Hook", "body": "' + body + '", "hashtags": ["#a", "#b", "#c"], "cta": "CTA"}'

    ready.writer_override = writer
    campaign_id = _create_and_run(client)
    contents = {content["content_key"]: content for content in _detail(client, campaign_id)["contents"]}

    assert contents["facebook/A"]["status"] == "needs_human"
    violation = contents["facebook/A"]["validations"]["brand_rules"]["violations"][0]
    assert violation["field"] == "body" and violation["matched_text"] == samples.BANNED_PHRASE
    assert contents["facebook/B"]["status"] == "passed"

    client.post(f"/api/manager/campaigns/{campaign_id}/review", headers=_manager("r"), json={"decision": "approve"})
    with db.get_session() as session:
        # An item that failed validation is neither approved nor recorded as approved.
        item_id = contents["facebook/A"]["content_item_id"]
        assert session.get(db.ContentItem, item_id).status == "needs_human"
        assert session.query(db.Approval).filter_by(content_item_id=item_id).count() == 0

    publish = client.post(f"/api/manager/campaigns/{campaign_id}/publish", headers=_manager("p"))
    assert len(publish.json()["skipped"]) == 1


def test_rejection_requires_reason(client, ready):
    campaign_id = _create_and_run(client)
    url = f"/api/manager/campaigns/{campaign_id}/review"
    missing = client.post(url, headers=_manager("r1"), json={"decision": "reject", "reason": "  "})
    assert missing.status_code == 422
    assert missing.json()["error"]["code"] == "reason_required"

    rejected = client.post(url, headers=_manager("r2"), json={"decision": "reject", "reason": "Wrong tone"})
    assert rejected.json()["status"] == "rejected"
    publish = client.post(f"/api/manager/campaigns/{campaign_id}/publish", headers=_manager("p"))
    assert publish.status_code == 409
    assert publish.json()["error"]["code"] == "nothing_to_publish"


def test_replayed_review_key_returns_the_first_result(client, ready):
    campaign_id = _create_and_run(client)
    url = f"/api/manager/campaigns/{campaign_id}/review"
    first = client.post(url, headers=_manager("same"), json={"decision": "approve"})
    second = client.post(url, headers=_manager("same"), json={"decision": "approve"})
    assert first.status_code == second.status_code == 200
    with db.get_session() as session:
        assert session.query(db.Approval).filter_by(campaign_id=campaign_id).count() == 4


def test_second_decision_with_a_new_key_is_refused(client, ready):
    campaign_id = _create_and_run(client)
    url = f"/api/manager/campaigns/{campaign_id}/review"
    client.post(url, headers=_manager("one"), json={"decision": "approve"})
    response = client.post(url, headers=_manager("two"), json={"decision": "reject", "reason": "Changed my mind"})
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "not_waiting_approval"


def test_chat_draft_flow_with_selection(client, ready):
    draft_id, detail = _create_chat_draft(client)
    assert detail["status"] == "draft"
    assert detail["pending_human_action"] is None
    assert len(detail["contents"]) == 4

    # The graph is paused at approval, but the marketer has not submitted anything yet.
    early = client.post(
        f"/api/manager/campaigns/{draft_id}/review", headers=_manager("early"), json={"decision": "approve"}
    )
    assert early.status_code == 409
    assert early.json()["error"]["code"] == "not_waiting_approval"

    selected = _one_item_per_channel(detail)
    submitted = client.post(
        f"/api/marketer/chat-drafts/{draft_id}/submit",
        headers=_marketer("submit-1"),
        json={"selected_content_item_ids": selected},
    )
    assert submitted.status_code == 201

    queue = client.get(f"/api/manager/campaigns/{draft_id}", headers=_manager()).json()
    assert queue["status"] == "waiting_approval"
    assert sorted(content["content_item_id"] for content in queue["contents"]) == sorted(selected)
    assert len(queue["schedules"]) == 2

    review = client.post(
        f"/api/manager/campaigns/{draft_id}/review", headers=_manager("review"), json={"decision": "approve"}
    )
    assert review.status_code == 200
    with db.get_session() as session:
        statuses = {item.id: item.status for item in session.query(db.ContentItem).filter_by(campaign_id=draft_id)}
    assert {statuses[item_id] for item_id in selected} == {"approved"}
    assert sorted(statuses.values()).count("draft") == 2

    publish = client.post(f"/api/manager/campaigns/{draft_id}/publish", headers=_manager("publish"))
    assert len(publish.json()["published"]) == 2


@pytest.mark.parametrize(
    ("pick", "code"),
    [
        (lambda ids: ids[:1], "invalid_selection"),
        (lambda ids: [ids[0], ids[0]], "invalid_selection"),
        (lambda ids: [*ids[:-1], 999999], "invalid_selection"),
    ],
)
def test_chat_draft_selection_must_cover_each_channel_once(client, ready, pick, code):
    draft_id, detail = _create_chat_draft(client)
    response = client.post(
        f"/api/marketer/chat-drafts/{draft_id}/submit",
        headers=_marketer("submit"),
        json={"selected_content_item_ids": pick(_one_item_per_channel(detail))},
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == code


def test_manual_edit_returns_to_draft_and_is_revalidated(client, ready):
    draft_id, detail = _create_chat_draft(client)
    content = next(c for c in detail["contents"] if c["content_key"] == "facebook/A")
    new_draft = content["draft"] | {"body": samples.BANNED_TEXT}

    response = client.patch(
        f"/api/marketer/campaigns/{draft_id}/content/{content['content_item_id']}",
        headers=auth_headers(MARKETER_ID),
        json={"draft": new_draft, "scheduled_date": "2030-09-12", "scheduled_time": "09:00"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["changed"] is True
    assert body["content"]["status"] == "needs_human"
    assert body["revalidation"]["validations"]["brand_rules"]["ok"] is False
    assert body["schedule"]["scheduled_at"].startswith("2030-09-12T09:00:00")
    with db.get_session() as session:
        assert session.query(db.ContentVersion).filter_by(content_item_id=content["content_item_id"]).count() == 1


def test_typed_wrong_price_is_caught_after_manual_edit(client, ready):
    draft_id, detail = _create_chat_draft(client)
    content = next(c for c in detail["contents"] if c["content_key"] == "facebook/A")
    wrong = content["draft"]["body"].replace("235.000.000", "135.000.000")
    response = client.patch(
        f"/api/marketer/campaigns/{draft_id}/content/{content['content_item_id']}",
        headers=auth_headers(MARKETER_ID),
        json={"draft": content["draft"] | {"body": wrong}, "scheduled_date": "2030-09-12", "scheduled_time": "09:00"},
    )
    fact_check = response.json()["revalidation"]["validations"]["fact_check"]
    assert fact_check["ok"] is False
    assert "135.000.000" in fact_check["errors"][0]["reason"]


def test_system_resolved_numbers_survive_revalidation(client, ready):
    draft_id, detail = _create_chat_draft(client)
    content = next(c for c in detail["contents"] if c["content_key"] == "facebook/A")
    edited = content["draft"] | {"hook": samples.EDITED_HOOK}
    response = client.patch(
        f"/api/marketer/campaigns/{draft_id}/content/{content['content_item_id']}",
        headers=auth_headers(MARKETER_ID),
        json={"draft": edited, "scheduled_date": "2030-09-12", "scheduled_time": "09:00"},
    )
    assert response.json()["content"]["status"] == "passed"


def test_edit_outside_campaign_dates_is_refused(client, ready):
    draft_id, detail = _create_chat_draft(client)
    content = detail["contents"][0]
    response = client.patch(
        f"/api/marketer/campaigns/{draft_id}/content/{content['content_item_id']}",
        headers=auth_headers(MARKETER_ID),
        json={"draft": content["draft"], "scheduled_date": "2031-01-01", "scheduled_time": "09:00"},
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "schedule_outside_campaign"


def test_edit_after_submission_is_refused(client, ready):
    campaign_id = _create_and_run(client)
    content = _detail(client, campaign_id)["contents"][0]
    response = client.patch(
        f"/api/marketer/campaigns/{campaign_id}/content/{content['content_item_id']}",
        headers=auth_headers(MARKETER_ID),
        json={"draft": content["draft"], "scheduled_date": "2030-09-12", "scheduled_time": "09:00"},
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "campaign_not_editable"


def test_ai_edit_rewrites_and_revalidates(client, ready):
    draft_id, detail = _create_chat_draft(client)
    content = next(c for c in detail["contents"] if c["content_key"] == "direct_message/A")
    ready.writer_override = lambda _message: '{"body": "' + samples.EDITED_SMS_BODY + '"}'
    response = client.post(
        f"/api/marketer/campaigns/{draft_id}/content/{content['content_item_id']}/ai-edit",
        headers=auth_headers(MARKETER_ID),
        json={"instruction": "Make it friendlier"},
    )
    assert response.status_code == 200
    body = response.json()
    # The model's output has no label or opt-out, so the code must add them again.
    assert body["content"]["draft"]["body"].startswith(f"[QC] {samples.EDITED_SMS_BODY}")
    assert body["content"]["draft"]["angle"] == content["draft"]["angle"]
    assert body["revalidation"]["validations"]["channel_spec"]["ok"] is True


def test_manual_send_requires_approved_content(client, ready):
    draft_id, detail = _create_chat_draft(client)
    response = client.post(
        f"/api/marketer/campaigns/{draft_id}/manual-sends",
        headers=auth_headers(MARKETER_ID),
        json={"content_item_id": detail["contents"][0]["content_item_id"], "channel": "zalo", "sent_content": "x"},
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "content_not_approved"


def test_delete_approved_campaign_needs_confirmation(client, ready):
    campaign_id = _create_and_run(client)
    client.post(f"/api/manager/campaigns/{campaign_id}/review", headers=_manager("r"), json={"decision": "approve"})

    url = f"/api/marketer/campaigns/{campaign_id}"
    refused = client.delete(url, headers=auth_headers(MARKETER_ID))
    assert refused.status_code == 409
    assert refused.json()["error"]["code"] == "delete_confirmation_required"

    deleted = client.delete(url, headers=auth_headers(MARKETER_ID), params={"confirm_approved": True})
    assert deleted.json()["deleted"] is True
    with db.get_session() as session:
        assert session.query(db.ContentItem).filter_by(campaign_id=campaign_id).count() == 0
    assert client.get(url, headers=auth_headers(MARKETER_ID)).status_code == 404


def test_marketer_calendar_is_scoped_to_own_campaigns(client, ready):
    campaign_id = _create_and_run(client)
    client.post(f"/api/manager/campaigns/{campaign_id}/review", headers=_manager("r"), json={"decision": "approve"})
    params = {"date_from": "2030-09-01", "date_to": "2030-09-30"}

    assert len(client.get("/api/marketer/schedules", headers=auth_headers(MARKETER_ID), params=params).json()["schedules"]) == 4
    assert client.get("/api/marketer/schedules", headers=auth_headers(OTHER_MARKETER_ID), params=params).json()["schedules"] == []


def test_marketer_analytics_only_covers_the_requested_campaign(client, ready):
    campaign_id = _create_and_run(client)
    body = client.get(f"/api/marketer/campaigns/{campaign_id}/analytics", headers=auth_headers(MARKETER_ID)).json()
    assert body["campaign"]["campaign_count"] == 1
    assert len(body["content"]) == 4
    assert "leads" not in body


def test_catalog_lists_public_variant_names(client, ready):
    with db.get_session() as session:
        session.add(
            db.ProductVariant(
                product_id="vf-3", variant_key="base", source_url="https://example.com/vf3", snapshot_date="2030-01-01"
            )
        )
        session.commit()
    items = client.get("/api/marketer/products", headers=auth_headers(MARKETER_ID)).json()["items"]
    assert items[0]["model_id"] == "VF3"
    assert sorted(items[0]["variants"]) == ["eco", "standard"]

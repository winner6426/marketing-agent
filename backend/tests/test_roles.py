from __future__ import annotations

import pytest

from src.models import db
from tests.conftest import ADMIN_ID, MANAGER_ID, MARKETER_ID, OTHER_MARKETER_ID, auth_headers, valid_brief

ROLE_ROUTES = [
    ("get", "/api/admin/users", {ADMIN_ID}),
    ("get", "/api/admin/campaigns", {ADMIN_ID}),
    ("get", "/api/admin/channels", {ADMIN_ID}),
    ("get", "/api/manager/campaigns", {MANAGER_ID}),
    ("get", "/api/manager/analytics", {MANAGER_ID}),
    ("get", "/api/manager/audit-log", {MANAGER_ID}),
    ("get", "/api/marketer/campaigns", {MARKETER_ID}),
    ("get", "/api/marketer/products", {MARKETER_ID}),
    ("get", "/api/marketer/chat-sessions", {MARKETER_ID}),
]


@pytest.mark.parametrize(("method", "path", "allowed"), ROLE_ROUTES)
def test_each_route_accepts_only_its_role(client, users, method, path, allowed):
    for user_id in (ADMIN_ID, MANAGER_ID, MARKETER_ID):
        response = getattr(client, method)(path, headers=auth_headers(user_id))
        assert (response.status_code == 200) == (user_id in allowed), f"{path} as {user_id}: {response.status_code}"
        if user_id not in allowed:
            assert response.status_code == 403
            assert response.json()["error"]["code"].endswith("_required")


@pytest.mark.parametrize(("method", "path", "_allowed"), ROLE_ROUTES)
def test_routes_require_authentication(client, method, path, _allowed):
    assert getattr(client, method)(path).status_code == 401


def test_manager_cannot_create_or_run_campaigns(client, users):
    response = client.post(
        "/api/marketer/campaigns", headers=auth_headers(MANAGER_ID), json={"brief": valid_brief()}
    )
    assert response.status_code == 403


def test_marketer_cannot_review(client, users):
    response = client.post(
        "/api/manager/campaigns/1/review",
        headers=auth_headers(MARKETER_ID, key="k"),
        json={"decision": "approve"},
    )
    assert response.status_code == 403


def _create_campaign(client, user_id: str = MARKETER_ID) -> int:
    response = client.post("/api/marketer/campaigns", headers=auth_headers(user_id), json={"brief": valid_brief()})
    assert response.status_code == 201
    return response.json()["campaign_id"]


@pytest.mark.parametrize(
    ("method", "suffix", "kwargs"),
    [
        ("get", "", {}),
        ("delete", "", {}),
        ("post", "/run", {}),
        ("post", "/answer", {"json": {"brief_additions": {}}}),
        ("post", "/answer", {"json": {"wrong_body": True}}),
        ("patch", "/content/1", {"json": {"draft": {}, "scheduled_date": "2030-09-10", "scheduled_time": "09:00"}}),
        ("post", "/content/1/ai-edit", {"json": {"instruction": "x"}}),
        ("post", "/manual-sends", {"json": {"content_item_id": 1, "channel": "sms", "sent_content": "x"}}),
        ("get", "/analytics", {}),
    ],
)
def test_other_marketers_campaign_looks_missing(client, users, method, suffix, kwargs):
    campaign_id = _create_campaign(client)
    response = getattr(client, method)(
        f"/api/marketer/campaigns/{campaign_id}{suffix}",
        headers=auth_headers(OTHER_MARKETER_ID, key="k"),
        **kwargs,
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "campaign_not_found"


def test_marketer_lists_only_own_campaigns(client, users):
    mine = _create_campaign(client)
    _create_campaign(client, OTHER_MARKETER_ID)
    rows = client.get("/api/marketer/campaigns", headers=auth_headers(MARKETER_ID)).json()
    assert [row["campaign_id"] for row in rows] == [mine]


def test_manager_sees_all_campaigns(client, users):
    _create_campaign(client)
    _create_campaign(client, OTHER_MARKETER_ID)
    assert len(client.get("/api/manager/campaigns", headers=auth_headers(MANAGER_ID)).json()) == 2


def test_chat_sessions_are_private(client, users):
    created = client.post("/api/marketer/chat-sessions", headers=auth_headers(MARKETER_ID), json={"title": "Mine"})
    session_id = created.json()["id"]

    other = auth_headers(OTHER_MARKETER_ID)
    assert client.get(f"/api/marketer/chat-sessions/{session_id}", headers=other).status_code == 404
    assert client.delete(f"/api/marketer/chat-sessions/{session_id}", headers=other).status_code == 404
    assert client.get("/api/marketer/chat-sessions", headers=other).json() == []


def test_chat_session_message_lifecycle(client, users):
    headers = auth_headers(MARKETER_ID)
    session_id = client.post("/api/marketer/chat-sessions", headers=headers, json={}).json()["id"]

    message = client.post(
        f"/api/marketer/chat-sessions/{session_id}/messages",
        headers=headers,
        json={"role": "user", "content": " hello "},
    ).json()
    assert message["content"] == "hello"

    updated = client.patch(
        f"/api/marketer/chat-sessions/{session_id}/messages/{message['id']}",
        headers=headers,
        json={"content": "edited"},
    )
    assert updated.json()["content"] == "edited"

    detail = client.get(f"/api/marketer/chat-sessions/{session_id}", headers=headers).json()
    assert [item["content"] for item in detail["messages"]] == ["edited"]
    assert client.delete(f"/api/marketer/chat-sessions/{session_id}", headers=headers).json()["deleted"] is True


def test_chat_draft_cannot_attach_to_someone_elses_session(client, users):
    session_id = client.post(
        "/api/marketer/chat-sessions", headers=auth_headers(OTHER_MARKETER_ID), json={}
    ).json()["id"]
    response = client.post(
        "/api/marketer/chat-drafts",
        headers=auth_headers(MARKETER_ID, key="k"),
        json={"brief": valid_brief(), "chat_session_id": session_id},
    )
    assert response.status_code == 404
    with db.get_session() as session:
        assert session.query(db.Campaign).count() == 0


def test_admin_changes_role_and_it_takes_effect(client, users):
    response = client.patch(
        f"/api/admin/users/{MARKETER_ID}/role", headers=auth_headers(ADMIN_ID), json={"role": "manager"}
    )
    assert response.status_code == 200
    assert response.json()["role"] == "manager"
    assert client.get("/api/manager/campaigns", headers=auth_headers(MARKETER_ID)).status_code == 200
    with db.get_session() as session:
        assert session.query(db.AuditLog).filter_by(action="change_role").count() == 1


@pytest.mark.parametrize(
    ("target", "role", "status", "code"),
    [
        (ADMIN_ID, "manager", 403, "cannot_change_own_role"),
        ("99999999-9999-9999-9999-999999999999", "manager", 404, "user_not_found"),
    ],
)
def test_role_change_guards(client, users, target, role, status, code):
    response = client.patch(f"/api/admin/users/{target}/role", headers=auth_headers(ADMIN_ID), json={"role": role})
    assert response.status_code == status
    assert response.json()["error"]["code"] == code


def test_admin_role_cannot_be_granted_through_the_api(client, users):
    response = client.patch(
        f"/api/admin/users/{MARKETER_ID}/role", headers=auth_headers(ADMIN_ID), json={"role": "admin"}
    )
    assert response.status_code == 422


def test_another_admin_cannot_be_demoted(client, users):
    second_admin = "66666666-6666-6666-6666-666666666666"
    with db.get_session() as session:
        session.add(db.UserProfile(id=second_admin, email="b@example.com", role=db.UserRole.ADMIN))
        session.commit()
    response = client.patch(
        f"/api/admin/users/{second_admin}/role", headers=auth_headers(ADMIN_ID), json={"role": "marketer"}
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "cannot_change_admin"


def test_channel_catalog_crud(client, users):
    headers = auth_headers(ADMIN_ID)
    payload = {"name": "Main page", "platform": "facebook", "account_ref": "page-1", "content_channel": "facebook"}

    created = client.post("/api/admin/channels", headers=headers, json=payload)
    assert created.status_code == 201
    channel_id = created.json()["id"]

    assert client.post("/api/admin/channels", headers=headers, json=payload).status_code == 409
    assert client.patch(f"/api/admin/channels/{channel_id}", headers=headers, json={}).status_code == 422

    updated = client.patch(f"/api/admin/channels/{channel_id}", headers=headers, json={"status": "inactive"})
    assert updated.json()["status"] == "inactive"
    # `content_channel` was not sent, so it must survive the partial update.
    assert updated.json()["content_channel"] == "facebook"

    assert client.get("/api/marketer/channels", headers=auth_headers(MARKETER_ID)).json()["items"] == []
    assert len(client.get("/api/admin/channels", headers=headers).json()["items"]) == 1
    assert client.delete(f"/api/admin/channels/{channel_id}", headers=headers).status_code == 200
    assert client.delete(f"/api/admin/channels/{channel_id}", headers=headers).status_code == 404


def test_errors_share_one_shape(client, users):
    missing_route = client.get("/api/does-not-exist")
    assert missing_route.status_code == 404
    assert set(missing_route.json()["error"]) == {"code", "message", "details"}

    invalid = client.post("/api/marketer/campaigns", headers=auth_headers(MARKETER_ID), json={})
    assert invalid.status_code == 422
    assert invalid.json()["error"]["code"] == "invalid_request"


def test_promote_admin_script(client, users):
    from scripts.promote_admin import promote

    assert promote("missing@example.com") is False
    assert promote("marketer@example.com") is True
    assert client.get("/api/admin/users", headers=auth_headers(MARKETER_ID)).status_code == 200


def test_costly_operations_require_idempotency_key(client, users):
    campaign_id = _create_campaign(client)
    response = client.post(f"/api/marketer/campaigns/{campaign_id}/run", headers=auth_headers(MARKETER_ID))
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "idempotency_key_required"

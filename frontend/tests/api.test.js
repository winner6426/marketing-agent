import assert from "node:assert/strict";
import { test } from "node:test";

import { ApiError, createApiClient, isCampaignSettled, mapCampaignFromApi } from "../src/services/api.js";

function jsonResponse(status, payload) {
  return { ok: status >= 200 && status < 300, status, json: async () => payload };
}

function recordingFetch(responses) {
  const calls = [];
  const fetchImpl = async (url, init) => {
    calls.push({ url, init });
    const next = responses.shift();
    return typeof next === "function" ? next() : next;
  };
  return { calls, fetchImpl };
}

test("requests send the bearer token, idempotency key and JSON body", async () => {
  const { calls, fetchImpl } = recordingFetch([jsonResponse(202, { draft_id: 7, status: "running" })]);
  const client = createApiClient({ baseUrl: "http://api/", fetchImpl });

  await client.createChatDraft("tok", { brief: { raw_prompt: "x" }, chatSessionId: "s1" }, "key-1");

  assert.equal(calls[0].url, "http://api/api/marketer/chat-drafts");
  assert.equal(calls[0].init.method, "POST");
  assert.equal(calls[0].init.headers.Authorization, "Bearer tok");
  assert.equal(calls[0].init.headers["Idempotency-Key"], "key-1");
  assert.deepEqual(JSON.parse(calls[0].init.body), {
    name: "",
    brief: { raw_prompt: "x" },
    chat_session_id: "s1",
  });
});

test("register sends full_name, the field the backend expects", async () => {
  const { calls, fetchImpl } = recordingFetch([jsonResponse(201, { email_confirmation_required: true })]);
  const client = createApiClient({ fetchImpl });

  await client.register({ email: "a@b.vn", password: "12345678", fullName: "An" });

  assert.deepEqual(JSON.parse(calls[0].init.body), {
    email: "a@b.vn",
    password: "12345678",
    full_name: "An",
  });
});

test("backend errors keep their code and message", async () => {
  const { fetchImpl } = recordingFetch([
    jsonResponse(401, { error: { code: "invalid_credentials", message: "Wrong password", details: {} } }),
  ]);
  const client = createApiClient({ fetchImpl });

  await assert.rejects(client.login("a@b.vn", "x"), (error) => {
    assert.ok(error instanceof ApiError);
    assert.equal(error.status, 401);
    assert.equal(error.code, "invalid_credentials");
    assert.equal(error.message, "Wrong password");
    return true;
  });
});

test("a network failure becomes an ApiError with status 0", async () => {
  const client = createApiClient({
    fetchImpl: async () => {
      throw new TypeError("fetch failed");
    },
  });
  await assert.rejects(client.listCampaigns("tok"), (error) => error instanceof ApiError && error.status === 0);
});

test("logout's empty 204 response is not parsed as JSON", async () => {
  const { fetchImpl } = recordingFetch([
    { ok: true, status: 204, json: async () => assert.fail("must not parse") },
  ]);
  const client = createApiClient({ fetchImpl });
  assert.equal(await client.logout("tok"), null);
});

test("campaign detail maps the pending action and content keys", () => {
  const campaign = mapCampaignFromApi({
    campaign_id: 3,
    status: "needs_clarification",
    current_node: "clarification",
    pending_human_action: { kind: "clarification", questions: ["Which model?"] },
    contents: [{ content_key: "facebook/A", quality_review: null }],
  });
  assert.equal(campaign.humanWait.type, "clarification");
  assert.deepEqual(campaign.humanWait.questions, ["Which model?"]);
  assert.equal(campaign.contentItems[0].key, "facebook/A");
  assert.equal(campaign.contentItems[0].qualityReview, null);
});

test("intermediate graph statuses are not treated as finished", () => {
  for (const status of ["running", "brief_ok", "plan_ok", "draft_ok"]) {
    assert.equal(isCampaignSettled(mapCampaignFromApi({ status })), false, status);
  }
  // A chat draft ends as "draft" once its content exists.
  assert.equal(isCampaignSettled(mapCampaignFromApi({ status: "draft" })), true);
  assert.equal(
    isCampaignSettled(mapCampaignFromApi({ status: "running", pending_human_action: { kind: "clarification" } })),
    true,
  );
});

test("polling waits before each request and stops once the graph settles", async () => {
  const events = [];
  const { fetchImpl } = recordingFetch([
    () => {
      events.push("fetch");
      return jsonResponse(200, { campaign_id: 1, status: "plan_ok", current_node: "writer" });
    },
    () => {
      events.push("fetch");
      return jsonResponse(200, { campaign_id: 1, status: "draft", contents: [{ content_key: "facebook/A" }] });
    },
  ]);
  const client = createApiClient({
    fetchImpl,
    sleepImpl: async () => events.push("sleep"),
  });
  const updates = [];

  const result = await client.waitForResult(1, "tok", { onUpdate: (campaign) => updates.push(campaign.status) });

  assert.deepEqual(events, ["sleep", "fetch", "sleep", "fetch"]);
  assert.deepEqual(updates, ["plan_ok", "draft"]);
  assert.equal(result.contentItems.length, 1);
});

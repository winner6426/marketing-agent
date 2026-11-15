import { label } from "../i18n/translate.js";

const DEFAULT_API_BASE = import.meta.env?.VITE_API_URL ?? "";

export class ApiError extends Error {
  constructor(message, { status = 0, code = "network_error", details = null } = {}) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.details = details;
  }
}

// LangGraph node ids are fixed keys; their labels come from i18n.
const AGENT_STEP_NODES = new Set([
  "brief_analyst",
  "clarification",
  "planner",
  "writer",
  "channel_validation",
  "brand_validation",
  "fact_check",
  "retry_counter",
  "scheduler",
  "quality_judge",
  "approval",
  "finalize_approval",
]);

// Statuses the graph passes through mid-run; polling must continue past them.
const IN_PROGRESS_STATUSES = new Set(["running", "brief_ok", "plan_ok", "draft_ok"]);

export function getAgentStepKey(nodeId) {
  return AGENT_STEP_NODES.has(nodeId) ? `agent.${nodeId}` : "agent.default";
}

export function getAgentFailureMessage(error) {
  const status = Number(error?.status ?? 0);
  if (status === 0 || status === 402 || status >= 500) return label("agent.failure");
  return error?.message || label("agent.failure");
}

/** Adds camelCase views over the backend payload; the original fields stay available. */
export function mapCampaignFromApi(campaign = {}) {
  return {
    ...campaign,
    currentNode: campaign.current_node ?? null,
    humanWait: campaign.pending_human_action
      ? { ...campaign.pending_human_action, type: campaign.pending_human_action.kind }
      : null,
    contentItems: (campaign.contents ?? []).map((item) => ({
      ...item,
      key: item.content_key,
      // null means "not scored", which differs from a low score.
      qualityReview: item.quality_review ?? null,
    })),
    schedules: campaign.schedules ?? [],
  };
}

export function isCampaignSettled(campaign) {
  return Boolean(campaign.humanWait) || !IN_PROGRESS_STATUSES.has(campaign.status);
}

export function createIdempotencyKey(prefix = "request") {
  const uuid =
    globalThis.crypto?.randomUUID?.() ?? `${Date.now()}-${Math.random().toString(16).slice(2)}`;
  return `${prefix}-${uuid}`;
}

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

export function createApiClient({
  baseUrl = DEFAULT_API_BASE,
  fetchImpl = (...args) => globalThis.fetch(...args),
  sleepImpl = sleep,
} = {}) {
  const root = String(baseUrl ?? "").replace(/\/$/, "");

  async function request(path, { token, idemKey, body, ...init } = {}) {
    const headers = {
      Accept: "application/json",
      ...(body !== undefined ? { "Content-Type": "application/json" } : {}),
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...(idemKey ? { "Idempotency-Key": idemKey } : {}),
    };

    let response;
    try {
      response = await fetchImpl(`${root}${path}`, {
        ...init,
        headers,
        ...(body !== undefined ? { body: JSON.stringify(body) } : {}),
      });
    } catch (error) {
      throw new ApiError(label("api.noConnection"), { details: error });
    }

    if (response.status === 204) return null;
    let payload = null;
    try {
      payload = await response.json();
    } catch {
      // A proxy may answer with HTML; the status code is still enough to report.
    }
    if (!response.ok) {
      const apiError = payload?.error;
      throw new ApiError(
        apiError?.message ?? label("api.httpError", { status: response.status }),
        {
          status: response.status,
          code: apiError?.code ?? `http_${response.status}`,
          details: apiError?.details ?? payload,
        },
      );
    }
    return payload;
  }

  /** Poll a campaign until the graph stops: finished, failed or waiting for a person. */
  async function waitForResult(
    campaignId,
    token,
    { pollIntervalMs = 3000, timeoutMs = 15 * 60 * 1000, onUpdate } = {},
  ) {
    const startedAt = Date.now();
    while (Date.now() - startedAt <= timeoutMs) {
      // Wait first: right after an answer is posted, the checkpoint still holds the old question
      // until the background run picks it up.
      await sleepImpl(pollIntervalMs);
      const campaign = await client.getCampaign(token, campaignId);
      onUpdate?.(campaign);
      if (isCampaignSettled(campaign)) return campaign;
    }
    throw new ApiError(label("api.timeout"), { code: "poll_timeout" });
  }

  const marketer = "/api/marketer";
  const client = {
    // --- Auth -----------------------------------------------------------------
    register: ({ email, password, fullName }) =>
      request("/api/auth/register", {
        method: "POST",
        body: { email, password, full_name: fullName },
      }),
    login: (email, password) =>
      request("/api/auth/login", { method: "POST", body: { email, password } }),
    refresh: (refreshToken) =>
      request("/api/auth/refresh", { method: "POST", body: { refresh_token: refreshToken } }),
    logout: (token) => request("/api/auth/logout", { method: "POST", token }),
    getMe: (token) => request("/api/auth/me", { token }),

    // --- Campaigns ------------------------------------------------------------
    listCampaigns: (token) => request(`${marketer}/campaigns`, { token }),
    getCampaign: async (token, campaignId) =>
      mapCampaignFromApi(await request(`${marketer}/campaigns/${campaignId}`, { token })),
    listProducts: async (token) => (await request(`${marketer}/products`, { token })).items ?? [],
    /** An approved or published campaign needs `confirmApproved`; otherwise the API answers 409. */
    deleteCampaign: (token, campaignId, { confirmApproved = false } = {}) =>
      request(
        `${marketer}/campaigns/${campaignId}${confirmApproved ? "?confirm_approved=true" : ""}`,
        { method: "DELETE", token },
      ),
    getCampaignAnalytics: (token, campaignId) =>
      request(`${marketer}/campaigns/${campaignId}/analytics`, { token }),

    // --- Content editing ------------------------------------------------------
    /** Saves the text and the posting slot together; changed text is validated and scored again. */
    updateContent: (token, campaignId, contentItemId, { draft, scheduledDate, scheduledTime }) =>
      request(`${marketer}/campaigns/${campaignId}/content/${contentItemId}`, {
        method: "PATCH",
        token,
        body: { draft, scheduled_date: scheduledDate, scheduled_time: scheduledTime },
      }),
    aiEditContent: (token, campaignId, contentItemId, { instruction, targetText = "" }) =>
      request(`${marketer}/campaigns/${campaignId}/content/${contentItemId}/ai-edit`, {
        method: "POST",
        token,
        body: { instruction, target_text: targetText },
      }),
    recordManualSend: (token, campaignId, payload) =>
      request(`${marketer}/campaigns/${campaignId}/manual-sends`, {
        method: "POST",
        token,
        body: {
          content_item_id: payload.contentItemId,
          channel: payload.channel,
          sent_content: payload.sentContent,
          recipients: payload.recipients ?? "",
          recipient_count: payload.recipientCount ?? 0,
        },
      }),

    // --- Chat drafts ----------------------------------------------------------
    createChatDraft: (token, { name = "", brief, chatSessionId = null }, idemKey) =>
      request(`${marketer}/chat-drafts`, {
        method: "POST",
        token,
        idemKey,
        body: { name, brief, chat_session_id: chatSessionId },
      }),
    answerChatDraft: (token, draftId, briefAdditions, idemKey) =>
      request(`${marketer}/chat-drafts/${draftId}/answer`, {
        method: "POST",
        token,
        idemKey,
        body: { brief_additions: briefAdditions },
      }),
    /** Sends exactly one variant per channel to manager review. */
    submitChatDraft: (token, draftId, selectedContentItemIds, idemKey) =>
      request(`${marketer}/chat-drafts/${draftId}/submit`, {
        method: "POST",
        token,
        idemKey,
        body: { selected_content_item_ids: selectedContentItemIds },
      }),
    waitForResult,

    // --- Chat sessions --------------------------------------------------------
    listChatSessions: (token) => request(`${marketer}/chat-sessions`, { token }),
    createChatSession: (token, title) =>
      request(`${marketer}/chat-sessions`, { method: "POST", token, body: { title } }),
    getChatSession: (token, id) => request(`${marketer}/chat-sessions/${id}`, { token }),
    updateChatSession: (token, id, title) =>
      request(`${marketer}/chat-sessions/${id}`, { method: "PATCH", token, body: { title } }),
    deleteChatSession: (token, id) =>
      request(`${marketer}/chat-sessions/${id}`, { method: "DELETE", token }),
    createChatMessage: (token, sessionId, role, content, metadata = {}) =>
      request(`${marketer}/chat-sessions/${sessionId}/messages`, {
        method: "POST",
        token,
        body: { role, content, metadata },
      }),
    updateChatMessage: (token, sessionId, messageId, content, metadata = {}) =>
      request(`${marketer}/chat-sessions/${sessionId}/messages/${messageId}`, {
        method: "PATCH",
        token,
        body: { content, metadata },
      }),
  };
  return client;
}

export const api = createApiClient();

import { label } from "../i18n/translate.js";

const STATUS_CODES = new Set([
  "draft",
  "running",
  "needs_clarification",
  "brief_ok",
  "plan_ok",
  "draft_ok",
  "waiting_approval",
  "approval",
  "scheduled",
  "published",
  "rejected",
  "failed",
  "generation_failed",
]);

// Colour follows the status code, never the translated label.
const STATUS_TONES = {
  published: "green",
  approval: "green",
  scheduled: "green",
  failed: "red",
  generation_failed: "red",
  rejected: "red",
  waiting_approval: "amber",
  needs_clarification: "amber",
};

/** The status to show, taking a pending human action into account. */
export function effectiveStatus(status, humanWait) {
  if (humanWait?.type === "clarification") return "needs_clarification";
  if (humanWait?.type === "approval") return "waiting_approval";
  return status;
}

export function statusText(status, humanWait) {
  const code = effectiveStatus(status, humanWait);
  return STATUS_CODES.has(code) ? label(`status.${code}`) : (code ?? label("status.unknown"));
}

export function statusTone(status, humanWait) {
  return STATUS_TONES[effectiveStatus(status, humanWait)] ?? "blue";
}

export function campaignProgress(status) {
  if (["approval", "scheduled", "published"].includes(status)) return 100;
  if (status === "running") return 55;
  return 75;
}

export function sortByCreationNewestFirst(campaigns = []) {
  const created = (campaign) => {
    const timestamp = Date.parse(campaign.created_at ?? "");
    return Number.isNaN(timestamp) ? 0 : timestamp;
  };
  return [...campaigns].sort(
    (left, right) =>
      created(right) - created(left) ||
      Number(right.campaign_id ?? 0) - Number(left.campaign_id ?? 0),
  );
}

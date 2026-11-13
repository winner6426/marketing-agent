import { en } from "../i18n/en.js";
import { label } from "../i18n/translate.js";
import { vi } from "../i18n/vi.js";

// The backend treats `raw_prompt[:38]` as an automatic title too, so both sides agree.
const PROVISIONAL_TITLE_LENGTH = 38;

function timestampOf(conversation = {}) {
  const timestamp = Date.parse(conversation.updated_at ?? conversation.created_at ?? "");
  return Number.isFinite(timestamp) ? timestamp : 0;
}

export function sortNewestFirst(conversations = []) {
  return [...conversations].sort(
    (left, right) =>
      timestampOf(right) - timestampOf(left) ||
      String(right.id ?? "").localeCompare(String(left.id ?? "")),
  );
}

export function moveToFront(conversations = [], id) {
  const active = conversations.find((conversation) => conversation.id === id);
  return active ? [active, ...conversations.filter((item) => item.id !== id)] : conversations;
}

export function provisionalTitle(prompt) {
  return String(prompt ?? "")
    .trim()
    .normalize("NFC")
    .slice(0, PROVISIONAL_TITLE_LENGTH);
}

const clean = (value) =>
  String(value ?? "")
    .trim()
    .normalize("NFC");

/** A title the app chose (default or derived from the first prompt), as opposed to one the user typed. */
export function isAutomaticTitle(title, firstPrompt = "") {
  return new Set(["", vi["chat.newConversation"], en["chat.newConversation"], provisionalTitle(firstPrompt)]).has(
    clean(title),
  );
}

/** Replace an automatic title with the campaign's name, but never overwrite one the user chose. */
export function resolveConversationTitle(currentTitle, campaign = {}, firstPrompt = "") {
  const current = clean(currentTitle);
  if (!isAutomaticTitle(current, firstPrompt)) return current;
  return clean(campaign.display_name || campaign.name) || current;
}

export function createLocalConversation(now = Date.now()) {
  const timestamp = new Date(now).toISOString();
  return {
    id: `new-${now}`,
    title: label("chat.newConversation"),
    created_at: timestamp,
    updated_at: timestamp,
  };
}

export function isLocalConversation(id) {
  return String(id ?? "").startsWith("new-");
}

/** Keep unsaved local conversations above the server's list. */
export function mergeChatHistory(current = [], serverRows = []) {
  const localRows = current.filter((conversation) => isLocalConversation(conversation.id));
  const localIds = new Set(localRows.map((conversation) => conversation.id));
  return [...localRows, ...sortNewestFirst(serverRows).filter((row) => !localIds.has(row.id))];
}

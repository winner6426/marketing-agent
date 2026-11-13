/**
 * Pure helpers for the content studio: which fields a channel's draft has, how validation and
 * quality results read, and which variants can be sent to review. No React, so `node --test` runs it.
 */

// Text fields in reading order. Field names match the writer's JSON schemas in the backend.
export const DRAFT_TEXT_FIELDS = ["hook", "scene", "voiceOver", "overlay", "body", "caption", "cta"];

// The fields each pipeline channel writes, with the backend's maximum lengths.
export const CHANNEL_FIELDS = {
  facebook: { hook: 500, body: 5000, cta: 100 },
  instagram: { caption: 2200, cta: 100 },
  tiktok: { hook: 100, scene: 500, voiceOver: 500, overlay: 100, cta: 100, caption: 2200 },
  direct_message: { body: 500 },
};

// Channels whose drafts carry hashtags.
const HASHTAG_CHANNELS = new Set(["facebook", "instagram", "tiktok"]);
export const MAX_HASHTAGS = 10;

// Draft keys that describe the row rather than hold outbound text.
const METADATA_FIELDS = new Set(["channel", "variant", "angle", "writer_error"]);

export const CHANNEL_ORDER = ["facebook", "instagram", "tiktok", "direct_message"];
export const VALIDATION_TIERS = ["channel_spec", "brand_rules", "fact_check"];
export const QUALITY_AXES = [
  "human_voice",
  "persuasiveness",
  "coherence",
  "distinctiveness",
  "source_grounding",
];

export function channelOfItem(item) {
  return String(item?.content_key ?? item?.key ?? "").split("/", 1)[0];
}

export function variantOfItem(item) {
  return item?.draft?.variant ?? String(item?.content_key ?? item?.key ?? "").split("/")[1] ?? "";
}

/** Content items grouped by channel, channels in a fixed order and variants sorted A, B, ... */
export function groupByChannel(contentItems = []) {
  const groups = new Map();
  for (const item of contentItems) {
    const channel = channelOfItem(item);
    if (!groups.has(channel)) groups.set(channel, []);
    groups.get(channel).push(item);
  }
  const rank = (channel) => {
    const index = CHANNEL_ORDER.indexOf(channel);
    return index === -1 ? CHANNEL_ORDER.length : index;
  };
  return [...groups.entries()]
    .sort(([left], [right]) => rank(left) - rank(right) || left.localeCompare(right))
    .map(([channel, items]) => ({
      channel,
      items: [...items].sort((left, right) => variantOfItem(left).localeCompare(variantOfItem(right))),
    }));
}

/** The text fields to show or edit: the channel's own fields plus any other text the draft holds. */
export function editableFields(draft = {}, channel = draft.channel) {
  const known = Object.keys(CHANNEL_FIELDS[channel] ?? {});
  const extra = Object.entries(draft)
    .filter(
      ([name, value]) =>
        typeof value === "string" && !METADATA_FIELDS.has(name) && !known.includes(name),
    )
    .map(([name]) => name);
  const order = (name) => {
    const index = DRAFT_TEXT_FIELDS.indexOf(name);
    return index === -1 ? DRAFT_TEXT_FIELDS.length : index;
  };
  return [...known, ...extra].sort((left, right) => order(left) - order(right));
}

export function fieldLimit(channel, field) {
  return CHANNEL_FIELDS[channel]?.[field] ?? null;
}

export function hasHashtags(channel, draft = {}) {
  return HASHTAG_CHANNELS.has(channel) || Array.isArray(draft.hashtags);
}

/** Split typed hashtags on spaces or commas, add the `#`, drop duplicates. */
export function parseHashtags(text = "") {
  const seen = new Set();
  const tags = [];
  for (const raw of String(text).split(/[\s,]+/)) {
    const word = raw.replace(/^#+/, "").trim();
    if (!word) continue;
    const tag = `#${word}`;
    const folded = tag.toLowerCase();
    if (seen.has(folded)) continue;
    seen.add(folded);
    tags.push(tag);
  }
  return tags;
}

export function formatHashtags(hashtags) {
  return Array.isArray(hashtags) ? hashtags.join(" ") : "";
}

/** The editor's starting values for one draft. */
export function draftToForm(draft = {}, channel = draft.channel) {
  const fields = Object.fromEntries(
    editableFields(draft, channel).map((name) => [name, draft[name] ?? ""]),
  );
  return { fields, hashtags: formatHashtags(draft.hashtags) };
}

/** The draft to save: the original row identity and angle, with the edited text and hashtags. */
export function formToDraft(original = {}, form = { fields: {}, hashtags: "" }, channel = original.channel) {
  const draft = { ...original };
  delete draft.writer_error;
  for (const [name, value] of Object.entries(form.fields ?? {})) draft[name] = String(value ?? "");
  if (hasHashtags(channel, original)) draft.hashtags = parseHashtags(form.hashtags);
  return draft;
}

/** Problems that stop a save, as `{ field, key, vars }` for translation. */
export function draftProblems(draft = {}, channel = draft.channel) {
  const problems = [];
  const fields = editableFields(draft, channel);
  if (!fields.some((name) => String(draft[name] ?? "").trim())) {
    problems.push({ field: null, key: "content.problem.empty" });
  }
  for (const name of fields) {
    const limit = fieldLimit(channel, name);
    const length = String(draft[name] ?? "").length;
    if (limit && length > limit) {
      problems.push({ field: name, key: "content.problem.tooLong", vars: { limit, length } });
    }
  }
  if (Array.isArray(draft.hashtags) && draft.hashtags.length > MAX_HASHTAGS) {
    problems.push({ field: "hashtags", key: "content.problem.tooManyHashtags", vars: { max: MAX_HASHTAGS } });
  }
  return problems;
}

/** One row per validation tier. `ok` is null when the tier has not run on this text. */
export function validationSummary(validations = {}) {
  return VALIDATION_TIERS.map((tier) => {
    const result = validations?.[tier];
    if (!result || typeof result !== "object") return { tier, ok: null, messages: [] };
    const messages = (result.violations ?? [])
      .map((violation) =>
        typeof violation === "string" ? violation : (violation?.message ?? violation?.rule ?? ""),
      )
      .filter(Boolean);
    return { tier, ok: result.ok === true, messages };
  });
}

export function passesAllTiers(validations = {}) {
  return validationSummary(validations).every((row) => row.ok === true);
}

/** Judge scores; null means "not scored", which the UI shows differently from a low score. */
export function qualitySummary(review) {
  if (!review || typeof review !== "object") return null;
  const axes = QUALITY_AXES.filter((axis) => review[axis] && typeof review[axis] === "object").map(
    (axis) => ({ axis, score: review[axis].score, quote: review[axis].quote ?? "" }),
  );
  const average =
    typeof review.average === "number"
      ? review.average
      : axes.length
        ? axes.reduce((sum, row) => sum + Number(row.score || 0), 0) / axes.length
        : null;
  return { average, axes, missingAxes: review.missing_axes ?? [] };
}

export function scheduleFor(schedules = [], contentItemId) {
  return schedules.find((slot) => slot.content_item_id === contentItemId) ?? null;
}

/** The posting slot to prefill: the saved one, else the campaign's first day at 09:00. */
export function defaultSchedule(schedules, contentItemId, summary = {}) {
  const slot = scheduleFor(schedules, contentItemId);
  if (slot) return { date: slot.scheduled_date, time: slot.scheduled_time };
  return { date: summary.date_from ?? "", time: "09:00" };
}

/** A variant can go to review once it passed every tier and has a quality score. */
export function isReadyForReview(item) {
  return item?.status === "passed" && passesAllTiers(item.validations) && item.quality_review != null;
}

/** Start from what was submitted before, else the best ready variant of each channel. */
export function defaultSelection(groups = []) {
  const selection = {};
  for (const { channel, items } of groups) {
    const chosen = items.find((item) => item.selected_for_approval);
    if (chosen) {
      selection[channel] = chosen.content_item_id;
      continue;
    }
    const ready = items
      .filter(isReadyForReview)
      .sort(
        (left, right) =>
          (qualitySummary(right.quality_review)?.average ?? 0) -
          (qualitySummary(left.quality_review)?.average ?? 0),
      );
    if (ready.length) selection[channel] = ready[0].content_item_id;
  }
  return selection;
}

/** Why the selection cannot be submitted yet, as translation keys with their values. */
export function submitBlockers(groups = [], selection = {}) {
  const blockers = [];
  for (const { channel, items } of groups) {
    const item = items.find((candidate) => candidate.content_item_id === selection[channel]);
    if (!item) blockers.push({ key: "content.blocker.pick", vars: { channel } });
    else if (!isReadyForReview(item)) {
      blockers.push({
        key: "content.blocker.notReady",
        vars: { channel, variant: variantOfItem(item) },
      });
    }
  }
  return blockers;
}

/** Plain text of a draft, in the order the backend sends it out. */
export function outboundText(draft = {}, channel = draft.channel) {
  const parts = editableFields(draft, channel)
    .map((name) => String(draft[name] ?? "").trim())
    .filter(Boolean);
  const hashtags = formatHashtags(draft.hashtags);
  if (hashtags) parts.push(hashtags);
  return parts.join("\n\n");
}

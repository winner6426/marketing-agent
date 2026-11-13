import { label } from "../i18n/translate.js";

const CHANNEL_LABELS = {
  facebook: "Facebook",
  direct_message: "Zalo / SMS",
  instagram: "Instagram",
  tiktok: "TikTok",
};

const GOAL_KEYS = {
  launch: "purpose.launch",
  test_drive: "purpose.test_drive",
  promotion: "purpose.promotion",
};

const ANGLE_KEYS = {
  family: "angle.family",
  economic: "angle.economic",
  social_proof: "angle.social_proof",
  convenience: "angle.convenience",
  safety: "angle.safety",
  technology: "angle.technology",
  urgency: "angle.urgency",
};

export function getChannelLabel(channel = "") {
  return CHANNEL_LABELS[channel] ?? channel.replaceAll("_", " ");
}

export function getAngleLabel(angle = "") {
  return ANGLE_KEYS[angle] ? label(ANGLE_KEYS[angle]) : angle.replaceAll("_", " ");
}

function cleanText(value = "") {
  return String(value ?? "")
    .trim()
    .normalize("NFC");
}

function formatModelId(modelId = "") {
  const compact = cleanText(modelId).replace(/\s+/g, "").toUpperCase();
  const match = compact.match(/^VF(\d{1,2})$/);
  return match ? `VF ${match[1]}` : compact;
}

function sentenceCase(value = "") {
  const text = cleanText(value);
  return text ? `${text[0].toUpperCase()}${text.slice(1)}` : "";
}

function buildCampaignName(summary = {}) {
  const goalKey = GOAL_KEYS[cleanText(summary.goal).toLowerCase()];
  const goal = goalKey ? label(goalKey) : "";
  const model = formatModelId(summary.model_id);
  const segment = sentenceCase(summary.segment);
  let name = [goal, model].filter(Boolean).join(" ");
  if (segment) name = name ? `${name} · ${segment}` : segment;
  return cleanText(name).slice(0, 200).trim();
}

function formatDateRange(dateFrom, dateTo) {
  const from = cleanText(dateFrom).match(/^(\d{4})-(\d{2})-(\d{2})$/);
  const to = cleanText(dateTo).match(/^(\d{4})-(\d{2})-(\d{2})$/);
  if (!from || !to) return "";
  const [, fromYear, fromMonth, fromDay] = from;
  const [, toYear, toMonth, toDay] = to;
  if (fromYear === toYear && fromMonth === toMonth) {
    return `${fromDay}–${toDay}/${toMonth}/${toYear}`;
  }
  if (fromYear === toYear) return `${fromDay}/${fromMonth}–${toDay}/${toMonth}/${toYear}`;
  return `${fromDay}/${fromMonth}/${fromYear}–${toDay}/${toMonth}/${toYear}`;
}

/** Display fields for a campaign list item (`display_name` and `summary` come from the backend). */
export function presentCampaign(campaign = {}) {
  const summary = campaign.summary ?? {};
  const semanticName = buildCampaignName(summary);
  const displayName =
    cleanText(campaign.display_name || campaign.name || semanticName) ||
    label("presenter.campaignNumbered", { id: campaign.campaign_id ?? "" }).trim();
  const purpose = semanticName && semanticName !== displayName ? semanticName : "";
  const channels = [...new Set((summary.channels ?? []).map(getChannelLabel).filter(Boolean))];
  return {
    displayName,
    purpose,
    context: channels.join(", "),
    dateRange: formatDateRange(summary.date_from, summary.date_to),
  };
}

/** Hide placeholders the fact checker could not resolve instead of showing raw `{{...}}`. */
export function formatContent(value = "") {
  return String(value ?? "").replace(/\{\{[^{}]+\}\}/g, label("presenter.unresolved"));
}

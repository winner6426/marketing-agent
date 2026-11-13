import { label } from "../i18n/translate.js";
import { CONTENT_CHANNEL_BY_ID, channelOfContentKey, toBackendChannel } from "./channels.js";

const channelName = (id) => CONTENT_CHANNEL_BY_ID[id]?.label ?? id;

/**
 * The brief sent to the pipeline. Only what the user chose explicitly is set: the brief analyst
 * extracts the rest (goal, model, funnel stage, channels, dates) from `raw_prompt`.
 */
export function buildBrief({ prompt, product, audience, tone, channels = [], dateFrom, dateTo }) {
  const rawPrompt = String(prompt ?? "").trim();
  if (!rawPrompt) throw new Error(label("chat.promptRequired"));
  const unsupported = channels.filter((channel) => !toBackendChannel(channel));
  if (unsupported.length) {
    throw new Error(
      label("chat.unsupportedChannels", { channels: unsupported.map(channelName).join(", ") }),
    );
  }
  const brief = { raw_prompt: rawPrompt };
  const modelId = String(product ?? "")
    .replace(/\s+/g, "")
    .toUpperCase();
  if (modelId) brief.model_id = modelId;
  if (String(audience ?? "").trim()) brief.segment = audience.trim();
  if (channels.length) brief.channels = [...new Set(channels.map(toBackendChannel))];
  if (dateFrom) brief.date_from = dateFrom;
  if (dateTo) brief.date_to = dateTo;
  if (tone) brief.note = `Tone: ${tone}`;
  return brief;
}

/** Which requested channels got content, and the chat message that says so. */
export function buildGenerationResult({ requestedChannels = [], contentItems = [] } = {}) {
  const generatedChannels = [
    ...new Set(contentItems.map((item) => channelOfContentKey(item.key)).filter(Boolean)),
  ];
  const requested = [...new Set(requestedChannels.filter((channel) => toBackendChannel(channel)))];
  const channels = requested.length ? requested : generatedChannels;
  const generated = new Set(generatedChannels);
  const missingChannels = channels.filter((channel) => !generated.has(channel));
  const message = missingChannels.length
    ? label("generation.partial", {
        done: channels.length - missingChannels.length,
        total: channels.length,
        missing: missingChannels.map(channelName).join(", "),
      })
    : label("generation.done", { count: channels.length });
  return { channels, generatedChannels, missingChannels, message };
}

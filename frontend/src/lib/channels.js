// Served from public/, so this module also loads under plain Node for tests.
const facebookLogo = "/images/channels/facebook.png";
const googleAdsLogo = "/images/channels/google-ads.webp";
const instagramLogo = "/images/channels/instagram.svg";
const metaLogo = "/images/channels/meta.webp";
const tiktokLogo = "/images/channels/tiktok.jpg";

/**
 * Channels shown in the composer. `backend` is the pipeline's channel id; a channel without one
 * is listed as not supported yet and cannot be selected.
 */
export const CONTENT_CHANNELS = [
  {
    id: "facebook",
    label: "Facebook",
    descriptionKey: "channelDesc.facebook",
    asset: facebookLogo,
    backend: "facebook",
  },
  {
    id: "instagram",
    label: "Instagram",
    descriptionKey: "channelDesc.instagram",
    asset: instagramLogo,
    backend: "instagram",
  },
  {
    id: "tiktok",
    label: "TikTok",
    descriptionKey: "channelDesc.tiktok",
    asset: tiktokLogo,
    backend: "tiktok",
  },
  { id: "email", label: "Email Marketing", descriptionKey: "channelDesc.email" },
  { id: "meta_ads", label: "Meta Ads", descriptionKey: "channelDesc.meta_ads", asset: metaLogo },
  { id: "web", label: "Web (SEO/GEO)", descriptionKey: "channelDesc.web" },
  {
    id: "google_ads",
    label: "Google Ads",
    descriptionKey: "channelDesc.google_ads",
    asset: googleAdsLogo,
  },
  {
    id: "zalo_sms",
    label: "Zalo / SMS",
    descriptionKey: "channelDesc.zalo_sms",
    backend: "direct_message",
  },
];

export const CONTENT_CHANNEL_BY_ID = Object.fromEntries(
  CONTENT_CHANNELS.map((channel) => [channel.id, channel]),
);

const UI_CHANNEL_BY_BACKEND = Object.fromEntries(
  CONTENT_CHANNELS.filter((channel) => channel.backend).map((channel) => [
    channel.backend,
    channel.id,
  ]),
);

export function toBackendChannel(channelId) {
  return CONTENT_CHANNEL_BY_ID[channelId]?.backend ?? null;
}

export function fromBackendChannel(channel) {
  return UI_CHANNEL_BY_BACKEND[channel] ?? null;
}

/** The UI channel of a content key such as `direct_message/A`. */
export function channelOfContentKey(key) {
  return fromBackendChannel(String(key ?? "").split("/", 1)[0]);
}

import assert from "node:assert/strict";
import { test } from "node:test";

import {
  isAutomaticTitle,
  mergeChatHistory,
  provisionalTitle,
  resolveConversationTitle,
} from "../src/lib/chat-history.js";
import { addDays, normalizeDateRange, vietnamDate } from "../src/lib/dates.js";
import { buildBrief, buildGenerationResult } from "../src/lib/generation.js";

test("the brief maps UI channels to pipeline channels and only sets chosen fields", () => {
  const brief = buildBrief({
    prompt: "  Ra mắt VF 3 cho sinh viên  ",
    product: "vf 3",
    audience: "Sinh viên",
    tone: "Trẻ trung",
    channels: ["facebook", "zalo_sms"],
    dateFrom: "2026-12-01",
    dateTo: "2026-12-15",
  });
  assert.deepEqual(brief, {
    raw_prompt: "Ra mắt VF 3 cho sinh viên",
    model_id: "VF3",
    segment: "Sinh viên",
    channels: ["facebook", "direct_message"],
    date_from: "2026-12-01",
    date_to: "2026-12-15",
    note: "Tone: Trẻ trung",
  });
});

test("without explicit choices the brief leaves extraction to the backend", () => {
  assert.deepEqual(buildBrief({ prompt: "Khuyến mãi VF 6 trên Facebook" }), {
    raw_prompt: "Khuyến mãi VF 6 trên Facebook",
  });
});

test("an empty prompt or an unsupported channel is refused", () => {
  assert.throws(() => buildBrief({ prompt: "   " }));
  assert.throws(() => buildBrief({ prompt: "x", channels: ["email"] }), /Email Marketing/);
});

test("generation result reports missing channels", () => {
  const result = buildGenerationResult({
    requestedChannels: ["facebook", "zalo_sms"],
    contentItems: [{ key: "facebook/A" }, { key: "facebook/B" }],
  });
  assert.deepEqual(result.generatedChannels, ["facebook"]);
  assert.deepEqual(result.missingChannels, ["zalo_sms"]);
  assert.match(result.message, /1\/2/);
});

test("without requested channels, the generated ones are used", () => {
  const result = buildGenerationResult({
    contentItems: [{ key: "direct_message/A" }, { key: "tiktok/A" }],
  });
  assert.deepEqual(result.channels, ["zalo_sms", "tiktok"]);
  assert.deepEqual(result.missingChannels, []);
});

test("an automatic title is replaced by the campaign name, a custom one is kept", () => {
  const prompt = "Lên chiến dịch lái thử VF 6 cho gia đình trẻ trong tháng 12";
  assert.equal(provisionalTitle(prompt).length, 38);
  assert.equal(isAutomaticTitle("Cuộc trò chuyện mới"), true);
  assert.equal(
    resolveConversationTitle(provisionalTitle(prompt), { display_name: "Lái thử VF 6" }, prompt),
    "Lái thử VF 6",
  );
  assert.equal(
    resolveConversationTitle("Chiến dịch Tết", { display_name: "Lái thử VF 6" }, prompt),
    "Chiến dịch Tết",
  );
});

test("unsaved local conversations stay above the server history", () => {
  const merged = mergeChatHistory(
    [{ id: "new-1", title: "local" }, { id: "a", title: "old copy" }],
    [
      { id: "a", title: "A", updated_at: "2026-01-01T00:00:00Z" },
      { id: "b", title: "B", updated_at: "2026-02-01T00:00:00Z" },
    ],
  );
  assert.deepEqual(
    merged.map((item) => item.id),
    ["new-1", "b", "a"],
  );
});

test("campaign dates use the Vietnam calendar and never run backwards", () => {
  // 18:00 UTC on 31 Dec is already 1 Jan in Vietnam (UTC+7).
  assert.equal(vietnamDate(new Date("2026-12-31T18:00:00Z")), "2027-01-01");
  assert.equal(addDays("2026-12-25", 14), "2027-01-08");
  assert.deepEqual(normalizeDateRange("2026-01-01", "2025-12-01", "2026-03-01"), {
    dateFrom: "2026-03-01",
    dateTo: "2026-03-01",
  });
});

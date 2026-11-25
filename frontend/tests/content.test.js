import assert from "node:assert/strict";
import { test } from "node:test";

import {
  defaultSchedule,
  defaultSelection,
  draftProblems,
  draftToForm,
  editableFields,
  formToDraft,
  groupByChannel,
  parseHashtags,
  qualitySummary,
  submitBlockers,
  validationSummary,
} from "../src/lib/content.js";

const PASSED = {
  channel_spec: { ok: true, violations: [] },
  brand_rules: { ok: true, violations: [] },
  fact_check: { ok: true, violations: [] },
};

function item(key, id, extra = {}) {
  const [channel, variant] = key.split("/");
  return {
    content_key: key,
    content_item_id: id,
    draft: { channel, variant, body: "x" },
    validations: PASSED,
    quality_review: { average: 3 },
    status: "passed",
    selected_for_approval: false,
    ...extra,
  };
}

test("contents are grouped in channel order with variants sorted", () => {
  const groups = groupByChannel([
    item("tiktok/B", 4),
    item("direct_message/A", 5),
    item("facebook/B", 2),
    item("tiktok/A", 3),
    item("facebook/A", 1),
  ]);
  assert.deepEqual(
    groups.map((group) => [group.channel, group.items.map((entry) => entry.content_item_id)]),
    [
      ["facebook", [1, 2]],
      ["tiktok", [3, 4]],
      ["direct_message", [5]],
    ],
  );
});

test("editable fields follow the channel schema and skip metadata", () => {
  assert.deepEqual(editableFields({ channel: "tiktok", angle: "tech", writer_error: "x" }), [
    "hook",
    "scene",
    "voiceOver",
    "overlay",
    "caption",
    "cta",
  ]);
  assert.deepEqual(editableFields({ channel: "facebook", note: "extra" }), ["hook", "body", "cta", "note"]);
});

test("hashtags are normalised and a round trip keeps the row identity", () => {
  assert.deepEqual(parseHashtags("vinfast, #VF3 #vinfast  ##xanh"), ["#vinfast", "#VF3", "#xanh"]);

  const original = {
    channel: "facebook",
    variant: "A",
    angle: "family",
    hook: "Hi",
    body: "Body",
    cta: "Go",
    hashtags: ["#a"],
    writer_error: "old",
  };
  const form = draftToForm(original);
  form.fields.body = "New body";
  form.hashtags = "#a b";
  const saved = formToDraft(original, form);
  assert.equal(saved.body, "New body");
  assert.equal(saved.variant, "A");
  assert.equal(saved.angle, "family");
  assert.deepEqual(saved.hashtags, ["#a", "#b"]);
  assert.equal("writer_error" in saved, false);
});

test("draft problems catch empty text, long fields and too many hashtags", () => {
  assert.deepEqual(
    draftProblems({ channel: "direct_message", body: "  " }).map((problem) => problem.key),
    ["content.problem.empty"],
  );
  const long = draftProblems({ channel: "tiktok", hook: "x".repeat(101) });
  assert.equal(long[0].field, "hook");
  assert.equal(long[0].vars.limit, 100);
  const tags = draftProblems({
    channel: "instagram",
    caption: "ok",
    hashtags: Array.from({ length: 11 }, (_, index) => `#t${index}`),
  });
  assert.equal(tags[0].key, "content.problem.tooManyHashtags");
});

test("validation rows report missing tiers as not run", () => {
  const rows = validationSummary({
    channel_spec: { ok: false, violations: [{ message: "Too long" }, "Bad"] },
    brand_rules: { ok: true, violations: [] },
  });
  assert.deepEqual(rows, [
    { tier: "channel_spec", ok: false, messages: ["Too long", "Bad"] },
    { tier: "brand_rules", ok: true, messages: [] },
    { tier: "fact_check", ok: null, messages: [] },
  ]);
});

test("quality summary keeps 'not scored' apart from a low score", () => {
  assert.equal(qualitySummary(null), null);
  const summary = qualitySummary({
    human_voice: { score: 4, quote: "a" },
    coherence: { score: 2, quote: "b" },
    average: 3,
    missing_axes: ["source_grounding"],
  });
  assert.equal(summary.average, 3);
  assert.deepEqual(
    summary.axes.map((row) => row.axis),
    ["human_voice", "coherence"],
  );
  assert.deepEqual(summary.missingAxes, ["source_grounding"]);
});

test("the schedule prefill uses the saved slot, else the first campaign day", () => {
  const slots = [{ content_item_id: 7, scheduled_date: "2026-12-02", scheduled_time: "18:30" }];
  assert.deepEqual(defaultSchedule(slots, 7, {}), { date: "2026-12-02", time: "18:30" });
  assert.deepEqual(defaultSchedule(slots, 8, { date_from: "2026-12-01" }), {
    date: "2026-12-01",
    time: "09:00",
  });
});

test("selection picks the best ready variant and blocks channels that are not ready", () => {
  const groups = groupByChannel([
    item("facebook/A", 1, { quality_review: { average: 2 } }),
    item("facebook/B", 2, { quality_review: { average: 4 } }),
    item("tiktok/A", 3, { status: "needs_human" }),
  ]);
  const selection = defaultSelection(groups);
  assert.deepEqual(selection, { facebook: 2 });
  assert.deepEqual(
    submitBlockers(groups, selection).map((blocker) => blocker.key),
    ["content.blocker.pick"],
  );
  assert.deepEqual(
    submitBlockers(groups, { ...selection, tiktok: 3 }).map((blocker) => blocker.key),
    ["content.blocker.notReady"],
  );
});

import assert from "node:assert/strict";
import test from "node:test";
import { readFileSync } from "node:fs";
import { sharingRequest } from "../src/app/model/strategySharingModel.ts";

test("readers cannot construct any sharing mutation, including public or private", () => {
  for (const visibility of ["PRIVATE", "PUBLIC", "GROUPS"] as const) {
    assert.equal(sharingRequest(false, { visibility, group_ids: ["group-a"] }, ["group-a"]), null);
  }
});

test("owner must select an eligible nonempty group audience", () => {
  const draft = { visibility: "GROUPS" as const, group_ids: ["group-a"] };
  assert.equal(sharingRequest(true, draft, null), null);
  assert.equal(sharingRequest(true, draft, []), null);
  assert.equal(sharingRequest(true, { ...draft, group_ids: [] }, ["group-a"]), null);
  assert.equal(sharingRequest(true, { ...draft, group_ids: ["group-b"] }, ["group-a"]), null);
  assert.deepEqual(sharingRequest(true, { ...draft, group_ids: ["group-a", "group-a"] }, ["group-a"]), draft);
  const tooMany = Array.from({ length: 101 }, (_, i) => `group-${i}`);
  assert.equal(sharingRequest(true, { ...draft, group_ids: tooMany }, tooMany), null);
});

test("reverting to private clears group sharing without requiring an available catalogue", () => {
  assert.deepEqual(sharingRequest(true, { visibility: "PRIVATE", group_ids: ["old-group"] }, null), {
    visibility: "PRIVATE", group_ids: [],
  });
  assert.deepEqual(sharingRequest(true, { visibility: "PUBLIC", group_ids: ["old-group"] }, null), {
    visibility: "PUBLIC", group_ids: [],
  });
});

test("sharing copy distinguishes authenticated deployment sharing from transfer and editing", () => {
  for (const language of ["en", "zh"]) {
    const messages = JSON.parse(readFileSync(new URL(`../src/i18n/${language}.json`, import.meta.url), "utf8"));
    for (const key of ["title", "private", "public", "groups", "scope_note", "read_only", "visibility", "choose_groups", "groups_unavailable", "save", "saved", "failed"]) {
      assert.ok(messages[`strategy_lab.sharing.${key}`], `${language}:${key}`);
    }
  }
});

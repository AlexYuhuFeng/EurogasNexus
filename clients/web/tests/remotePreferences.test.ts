import assert from "node:assert/strict";
import test from "node:test";

import type { PreferencesDTO } from "../src/api/client.ts";
import { resolveSignInPreferences } from "../src/app/preferences/preferenceResolution.ts";

function server(
  personal: PreferencesDTO["personal"],
  enabled: string[] = ["en", "zh-CN"],
): PreferencesDTO {
  return {
    personal,
    organisation_defaults: {},
    effective: {
      language: personal.language ?? "en",
      theme: personal.theme ?? "system",
      market_view: personal.market_view ?? "curves",
      market_board_layout: personal.market_board_layout ?? "board",
      enabled_languages: enabled,
    },
    updated_at_utc: null,
  };
}

test("a choice made on this device wins here and becomes the personal value", () => {
  const { effective, seed } = resolveSignInPreferences(server({ language: "en" }), { language: "zh-CN" });
  assert.equal(effective.language, "zh-CN");
  assert.deepEqual(seed, { language: "zh-CN" });
});

test("a device with no choice takes the personal value and seeds nothing", () => {
  const { effective, seed } = resolveSignInPreferences(server({ theme: "dark" }), {});
  assert.equal(effective.theme, "dark");
  assert.deepEqual(seed, {});
});

test("an unchanged choice is not saved again; a switched-off language is not kept", () => {
  assert.deepEqual(resolveSignInPreferences(server({ theme: "dark" }), { theme: "dark" }).seed, {});
  const off = resolveSignInPreferences(server({}, ["en"]), { language: "zh-CN" });
  assert.equal(off.effective.language, "en");
  assert.deepEqual(off.seed, {});
});

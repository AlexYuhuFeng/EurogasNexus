import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import {
  DEFAULT_LANGUAGE,
  LANGUAGE_STORAGE_KEY,
  normalizeLanguage,
  readStoredLanguage,
  storeLanguage,
  SUPPORTED_LANGUAGES,
} from "../src/i18n/language.ts";
import { dataPlaneLabelKey, dataPlaneState } from "../src/app/model/dataPlaneStatus.ts";

function readWebSource(relativePath: string): string {
  return readFileSync(new URL(`../src/${relativePath}`, import.meta.url), "utf8");
}

/** Minimal storage double: the module only needs getItem/setItem. */
function memoryStorage(initial: Record<string, string> = {}) {
  const values = new Map(Object.entries(initial));
  return {
    getItem: (key: string) => values.get(key) ?? null,
    setItem: (key: string, value: string) => void values.set(key, value),
    snapshot: () => Object.fromEntries(values),
  };
}

test("the language preference survives a reload through its own storage key", () => {
  const storage = memoryStorage();
  assert.equal(readStoredLanguage(storage), DEFAULT_LANGUAGE);

  assert.equal(storeLanguage("zh-CN", storage), "zh-CN");
  assert.equal(storage.snapshot()[LANGUAGE_STORAGE_KEY], "zh-CN");
  // A later load reads the stored value rather than the shipped default.
  assert.equal(readStoredLanguage(storage), "zh-CN");
});

test("language reads are coerced and hostile values cannot leave the supported set", () => {
  assert.deepEqual([...SUPPORTED_LANGUAGES], ["en", "zh-CN"]);
  // i18next tags and case variants map onto the supported set.
  assert.equal(normalizeLanguage("zh"), "zh-CN");
  assert.equal(normalizeLanguage("zh-Hans"), "zh-CN");
  assert.equal(normalizeLanguage("en-GB"), "en");
  assert.equal(normalizeLanguage("EN"), "en");
  // Anything else - junk, a hostile string, or nothing - falls back to English.
  for (const value of [null, undefined, "", "fr", "<script>", 42, {}]) {
    assert.equal(normalizeLanguage(value), "en");
  }
  assert.equal(readStoredLanguage(memoryStorage({ [LANGUAGE_STORAGE_KEY]: "klingon" })), "en");
});

test("a broken storage never breaks the language switch", () => {
  const throwing = {
    getItem: () => {
      throw new Error("private mode");
    },
    setItem: () => {
      throw new Error("quota exceeded");
    },
  };
  assert.equal(readStoredLanguage(throwing), "en");
  // The switch still reports what it applied even when it cannot persist.
  assert.equal(storeLanguage("zh-CN", throwing), "zh-CN");
  assert.equal(storeLanguage("nonsense", throwing), "en");
});

test("the i18n entry point applies the stored language and owns the switch", () => {
  const i18n = readWebSource("i18n/index.ts");
  assert.match(i18n, /lng: readStoredLanguage\(\)/);
  // One writer: surfaces must go through changeAppLanguage, which persists first.
  assert.match(i18n, /export async function changeAppLanguage\(language: string\)/);
  assert.match(i18n, /const normalized = storeLanguage\(language\)/);
  for (const source of [
    "app/shell/AppShell.tsx",
    "app/workspaces/WorkspaceRenderer.tsx",
  ]) {
    const file = readWebSource(source);
    assert.equal(file.includes("i18n.changeLanguage"), false, `${source} must use changeAppLanguage`);
    assert.ok(file.includes("changeAppLanguage("), `${source} must switch through changeAppLanguage`);
  }
});

test("settings remains the full preferences surface while the header uses one grouped menu", () => {
  const bar = readWebSource("components/WorkspaceTopBar.tsx");
  const menu = readWebSource("components/HeaderPreferencesMenu.tsx");
  const settings = readWebSource("components/SettingsCenter.tsx");
  const signIn = readWebSource("components/SignInScreen.tsx");

  // Preference option sets are not restored as peer toolbar controls. The
  // header owns one grouped menu and delegates persistence to the existing
  // language/theme writers.
  assert.match(bar, /<HeaderPreferencesMenu/);
  assert.match(bar, /onLanguageChange=\{onLanguageChange\}/);
  assert.match(bar, /onModeChange=\{onModeChange\}/);
  assert.match(menu, /t\("settings\.language"\)/);
  assert.match(menu, /t\("settings\.appearance"\)/);
  assert.match(menu, /role="menuitemradio"/);

  // The complete controls still exist in Settings, and sign-in retains its
  // pre-authentication language switch.
  assert.match(settings, /t\("settings\.language"\)/);
  assert.match(settings, /t\("settings\.appearance"\)/);
  assert.match(signIn, /aria-label=\{t\("settings\.language"\)\}/);
});

test("closing the header menu returns focus to its trigger without waiting for a frame", () => {
  const menu = readWebSource("components/HeaderPreferencesMenu.tsx");

  // The accessibility sweep presses Escape and reads `document.activeElement` immediately, so a
  // focus move deferred to the next animation frame is a promise the surface cannot keep. The
  // trigger is always mounted, so it can be focused before the menu closes - and closing after
  // that cannot drop focus into the body, because the focused element is not in the removed
  // subtree.
  const closeHandler =
    /const closeAndReturnFocus = \(\) => \{([\s\S]*?)\n {2}\};/.exec(menu)?.[1] ?? "";
  assert.ok(closeHandler, "the close handler is declared once");
  assert.match(closeHandler, /triggerRef\.current\?\.focus\(\)/);
  assert.equal(closeHandler.includes("requestAnimationFrame"), false);
  assert.match(closeHandler, /setOpen\(false\)/);

  // Escape, and only Escape, routes through it: the same handler serves every item that closes
  // the menu, so no path leaves focus behind.
  assert.match(menu, /event\.key === "Escape"[\s\S]*?closeAndReturnFocus\(\)/);
  assert.match(menu, /const select = \(action: \(\) => void\) => \{\s*action\(\);\s*closeAndReturnFocus\(\);/);
  assert.match(menu, /aria-controls="topbar-preferences-menu"/);
  // Escape is also handled on the document while the menu is open, because the popover moves focus
  // into itself on the next frame: a sweep (or a user) pressing Escape in that window would
  // otherwise leave the menu open with focus on the body. The ARIA menu-button pattern asks for
  // Escape to dismiss the menu and return focus to the trigger, wherever focus is inside it.
  assert.match(menu, /document\.addEventListener\("keydown", onKeyDown\)/);
  assert.match(menu, /document\.removeEventListener\("keydown", onKeyDown\)/);
  assert.match(menu, /if \(event\.key !== "Escape"\) return;/);
  // Opening still moves focus into the menu, which is the other half of the pattern.
  assert.match(menu, /window\.requestAnimationFrame\(\(\) => focusableItems\(\)\[0\]\?\.focus\(\)\)/);
});

test("the data-plane badge speaks the operational vocabulary, not the store name", () => {
  const bar = readWebSource("components/WorkspaceTopBar.tsx");
  const settings = readWebSource("components/SettingsCenter.tsx");
  const en = JSON.parse(readWebSource("i18n/en.json")) as Record<string, string>;
  const zh = JSON.parse(readWebSource("i18n/zh.json")) as Record<string, string>;

  assert.equal(dataPlaneState("runtime"), "ready");
  assert.equal(dataPlaneState("partial"), "partial");
  // Fail-closed: an unknown or unmodelled state must not read as healthy.
  for (const value of ["unavailable", "delayed", "loading", "", null, undefined, "mystery"]) {
    assert.equal(dataPlaneState(value), "unavailable", String(value));
  }
  assert.equal(dataPlaneLabelKey("ready"), "data.ready");

  // One vocabulary in both surfaces, both locales. The store name survives only
  // as the badge's title detail (`data.runtime_detail`), never as the status.
  for (const file of [bar, settings]) {
    assert.match(file, /dataPlaneState\(/);
    assert.match(file, /dataPlaneLabelKey\(/);
    assert.equal(file.includes('"data.runtime"'), false);
    assert.equal(file.includes("`data.${"), false);
  }
  for (const [locale, translations] of [["en", en], ["zh", zh]] as const) {
    for (const key of ["data.ready", "data.partial", "data.unavailable", "data.runtime_detail"]) {
      assert.equal(typeof translations[key], "string", `${locale} ${key}`);
    }
    // The store name is no longer a status label in either language.
    assert.equal("data.runtime" in translations, false, locale);
    assert.equal("data.delayed" in translations, false, locale);
  }
});

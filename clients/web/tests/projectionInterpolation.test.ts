/**
 * Rendered interpolation for the projection context strip (Architecture V2 Wave 5).
 *
 * Every sentence the strip renders carries a value the backend supplied: the projection's as-of
 * instant, how many slices are degraded, how many rows a slice has, how many rows an entitlement
 * withheld, and how much evidence a review resolved. The locales were authored with single-brace
 * placeholders (`{count}`), while i18next interpolates `{{count}}` - so all fifteen entries
 * rendered their placeholder literally ("As of {value}", "{count} slice(s) stale, missing or
 * unavailable") in both languages, on the market, portfolio and review surfaces, plus the same
 * defect in the agents replay strip and the decision case's evidence count.
 *
 * Key parity, non-empty values and "the value is translated" all pass on such a string: it exists,
 * it is translated, and it never reaches the screen as written. What fails is the *interpolation*,
 * so this gate runs the real i18next against the real locale files with the app's own
 * interpolation configuration and asserts the rendered output - value present, no braces left,
 * and the two languages still differ - instead of asserting that a string exists.
 */

import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import i18next from "i18next";

const ROOT = new URL("../", import.meta.url);

function readWebSource(relativePath: string): string {
  return readFileSync(new URL(`src/${relativePath}`, ROOT), "utf8");
}

function readLocale(name: "en" | "zh"): Record<string, string> {
  return JSON.parse(readWebSource(`i18n/${name}.json`)) as Record<string, string>;
}

/**
 * The interface's own interpolation configuration, read from the module that initialises i18next.
 * If that block ever declared a custom prefix/suffix, this gate's expectations would be wrong
 * rather than the locale's - so the configuration is asserted before the locale is.
 */
function declaredInterpolationOptions(): Record<string, string> {
  const index = readWebSource("i18n/index.ts");
  const block = /interpolation:\s*\{([^}]*)\}/.exec(index)?.[1];
  assert.ok(block, "i18n/index.ts declares an interpolation configuration");
  const options: Record<string, string> = {};
  for (const entry of block.split(",")) {
    const [key, value] = entry.split(":").map((part) => part.trim());
    if (key) options[key] = value ?? "";
  }
  return options;
}

async function renderer(): Promise<typeof i18next> {
  const instance = i18next.createInstance();
  await instance.init({
    resources: {
      en: { translation: readLocale("en") },
      "zh-CN": { translation: readLocale("zh") },
    },
    lng: "en",
    fallbackLng: "en",
    // The app's own configuration, so the delimiter this gate relies on is the one the
    // application ships with.
    interpolation: { escapeValue: false },
  });
  return instance;
}

const AS_OF = "2026-09-07T09:30:00Z";

/** Every entry the strip renders, the options its call site passes, and the output per language. */
const STRIP_OUTPUTS: readonly {
  readonly key: string;
  readonly options: Record<string, unknown>;
  readonly en: string;
  readonly zh: string;
}[] = [
  {
    key: "as_of",
    options: { value: AS_OF },
    en: `As of ${AS_OF}`,
    zh: `截至 ${AS_OF}`,
  },
  {
    key: "degraded",
    options: { count: 2 },
    en: "2 slice(s) stale, missing or unavailable",
    zh: "2 个分片过期、缺失或不可用",
  },
  {
    key: "rows",
    options: { count: 7 },
    en: "7 rows",
    zh: "7 行",
  },
  {
    key: "restricted",
    options: { count: 3 },
    en: "3 row(s) withheld by entitlement",
    zh: "因授权限制隐藏 3 行",
  },
];

const PROJECTION_NAMESPACES = ["market_context", "portfolio_context", "review_context"] as const;

test("the app initialises i18next with the default delimiters the locales are written against", () => {
  const options = declaredInterpolationOptions();
  // A single option, and not a delimiter: the locales must therefore use i18next's own `{{ }}`.
  assert.deepEqual(Object.keys(options), ["escapeValue"]);
  assert.equal(options.escapeValue, "false");
});

test("the projection strip renders values in both languages instead of placeholders", async () => {
  const i18n = await renderer();

  for (const namespace of PROJECTION_NAMESPACES) {
    for (const { key, options, en, zh } of STRIP_OUTPUTS) {
      for (const [language, expected] of [["en", en], ["zh-CN", zh]] as const) {
        await i18n.changeLanguage(language);
        const rendered = i18n.t(`${namespace}.${key}`, options);
        assert.equal(rendered, expected, `${namespace}.${key} in ${language}`);
        assert.equal(rendered.includes("{"), false, `${namespace}.${key} in ${language} leaked a placeholder`);
      }
    }
  }

  // The review strip's coverage sentence is the one entry with two placeholders.
  for (const [language, expected] of [["en", "Evidence resolved 2 of 5"], ["zh-CN", "已解析证据 2 / 5"]] as const) {
    await i18n.changeLanguage(language);
    const rendered = i18n.t("review_context.evidence_coverage", { resolved: 2, requested: 5 });
    assert.equal(rendered, expected, `review_context.evidence_coverage in ${language}`);
  }
});

test("the agents replay strip and the decision case count interpolate their values too", async () => {
  // Both carried the same single-brace defect. The agents call site used to splice the timestamp
  // beside the label because the placeholder never resolved, which is why fixing the locale alone
  // would have printed "{{value}}" there: the label owns its value now.
  const i18n = await renderer();
  await i18n.changeLanguage("en");
  assert.equal(i18n.t("agents.run_as_of", { value: "12:05 UTC" }), "Recorded 12:05 UTC");
  assert.equal(i18n.t("decision_case.evidence_count", { count: 2 }), "2 evidence items");
  await i18n.changeLanguage("zh-CN");
  assert.equal(i18n.t("agents.run_as_of", { value: "12:05 UTC" }), "记录时间 12:05 UTC");
  assert.equal(i18n.t("decision_case.evidence_count", { count: 2 }), "2 项证据");

  const agents = readWebSource("components/AgentsWorkspace.tsx");
  assert.match(agents, /t\("agents\.run_as_of", \{\s*value: formatAgentTimestamp\(selectedRun\.created_at\),\s*\}\)/);
  assert.equal(agents.includes("`${t(\"agents.run_as_of\")}"), false);
});

test("the component passes every option its locales declare", () => {
  // Both halves are needed: a locale with `{{value}}` and a caller that passes nothing still
  // prints braces, so the call sites are held to the placeholders the entries declare.
  const strip = readWebSource("components/ProjectionContextStrip.tsx");
  assert.match(strip, /t\(key\("as_of"\), \{ value: formatUtcTimestamp\(asOf, asOf\) \}\)/);
  assert.match(strip, /t\(key\("degraded"\), \{ count: degraded\.length \}\)/);
  assert.match(strip, /t\(key\("rows"\), \{ count: reading\.rowCount \}\)/);
  assert.match(strip, /t\(key\("restricted"\), \{ count: reading\.filteredOut \}\)/);

  const review = readWebSource("components/ReviewContextStrip.tsx");
  assert.match(
    review,
    /t\("review_context\.evidence_coverage", \{\s*resolved: coverage\.resolved,\s*requested: coverage\.requested,\s*\}\)/,
  );
});

test("no locale entry carries an interpolated placeholder i18next cannot fill", () => {
  // The whole locale is held to the rule, not just the entries this gate names: any value that
  // looks like a placeholder must use `{{ }}`. The single declared exception is a value the
  // operator reads - the documented URL template for a licensed tile service - and it is declared
  // with its reason rather than left to look like an oversight.
  const LITERAL_BRACES_BY_DESIGN: Readonly<Record<string, string>> = {
    "settings.map_tile_provider_custom":
      "documents the `{z}/{x}/{y}` template an operator must configure, so the text itself shows it",
  };

  for (const locale of ["en", "zh"] as const) {
    const catalogue = readLocale(locale);
    const singleBrace = Object.entries(catalogue)
      .filter(([, value]) =>
        // What `{{ }}` interpolates is removed first: what remains is a brace the operator
        // would read on screen because no interpolation ever fills it.
        /\{[a-zA-Z_][\w]*\}/.test(value.replace(/\{\{[^{}]*\}\}/g, "")),
      )
      .map(([key]) => key)
      .sort();
    assert.deepEqual(
      singleBrace,
      Object.keys(LITERAL_BRACES_BY_DESIGN).sort(),
      `${locale} declares exactly the literal-brace entries by design`,
    );
    for (const [key, reason] of Object.entries(LITERAL_BRACES_BY_DESIGN)) {
      assert.ok(catalogue[key].includes("{z}/{x}/{y}"), `${locale} ${key} keeps its URL template`);
      assert.ok(reason.trim(), `reason for ${key}`);
    }
  }

  // The three projection namespaces render the same reading on three surfaces, so their
  // templates must stay identical per language rather than drifting apart one key at a time.
  for (const locale of ["en", "zh"] as const) {
    const catalogue = readLocale(locale);
    for (const { key } of STRIP_OUTPUTS) {
      const templates = PROJECTION_NAMESPACES.map((namespace) => catalogue[`${namespace}.${key}`]);
      assert.equal(new Set(templates).size, 1, `${locale} ${key} template differs per surface`);
    }
  }
});

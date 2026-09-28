/**
 * The route-state badge text must stay readable, in both themes, from the stylesheet the
 * product ships.
 *
 * CI 36428725740 measured the Chinese candidate pill as white on `#0ea5e9`: 2.77 against the
 * 4.5 WCAG AA minimum for the pill's 10px label. The pills now take their own badge tokens
 * (`--eg-badge-*-bg`, `--eg-badge-ink`) instead of the map/legend survey colours, and these
 * cases compute every published pair's ratio from `app.css` itself - with the same contrast
 * function the browser sweep measures the rendered pills with
 * (`scripts/uat/readToRender.mjs`, `contrastRatio`) - and pin the map and legend dot palette as
 * unchanged.
 */

import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import {
  contrastRatio,
  ROUTE_BADGE_MIN_CONTRAST,
  ROUTE_BADGE_STATES,
} from "../../../scripts/uat/readToRender.mjs";

const css = readFileSync(new URL("../src/styles/app.css", import.meta.url), "utf8");

/**
 * The body of the theme token block whose header is exactly `header`.
 *
 * `.cockpit-app` is declared more than once (layout and rails); the token block is the one that
 * declares the map palette, so that block is selected rather than whichever came first.
 */
function themeBody(header: string): string {
  const escaped = header.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  const bodies = [...css.matchAll(new RegExp(`(?:^|\\n)${escaped} \\{([^}]*)\\}`, "g"))]
    .map(([, body]) => body);
  const tokenBlock = bodies.find((body) => body.includes("--eg-map-standard"));
  assert.ok(tokenBlock, `missing theme token block: ${header}`);
  return tokenBlock;
}

/** The last declared value of `property` among the rules whose headers name `selector`. */
function activeDeclaration(selector: string, property: string): string {
  const values = [...css.matchAll(/([^{}]+)\{([^{}]*)\}/g)]
    .filter(([, header]) =>
      header
        .replace(/\/\*[\s\S]*?\*\//g, "")
        .split(",")
        .some((item) => item.trim() === selector))
    .flatMap(([, , body]) => [
      ...body.matchAll(new RegExp(`(?:^|;)\\s*${property}:\\s*([^;]+);`, "g")),
    ])
    .map(([, value]) => value.trim());
  assert.ok(values.length > 0, `missing ${property} for ${selector}`);
  return values.at(-1) as string;
}

/** The value of `--token` inside one theme block; its absence is a failure, never a fallback. */
function themeToken(body: string, token: string): string {
  // The declaration is looked up by its own name - anchors before it would be broken by the
  // comments the token blocks carry - and the name's trailing colon keeps a longer token from
  // matching in its place.
  const escaped = token.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  const value = new RegExp(`${escaped}:\\s*([^;]+);`).exec(body)?.[1];
  assert.ok(value, `missing token ${token}`);
  return value.trim();
}

const THEMES = {
  light: themeBody(".cockpit-app"),
  dark: themeBody(":root.dark .cockpit-app"),
};

test("the stylesheet publishes the badge palette for both themes", () => {
  assert.equal(ROUTE_BADGE_MIN_CONTRAST, 4.5);
  for (const [theme, body] of Object.entries(THEMES)) {
    assert.match(themeToken(body, "--eg-badge-ink"), /^#[0-9a-f]{6}$/i, theme);
    for (const state of ROUTE_BADGE_STATES) {
      assert.match(themeToken(body, `--eg-badge-${state}-bg`), /^#[0-9a-f]{6}$/i, `${theme}/${state}`);
    }
  }
  // The pills read the badge tokens; the map tokens they used to share stay on the legend dots.
  assert.equal(activeDeclaration(".resource-route-state-pill", "color"), "var(--eg-badge-ink)");
  for (const state of ROUTE_BADGE_STATES) {
    assert.equal(
      activeDeclaration(`.resource-route-state-pill.${state}`, "background"),
      `var(--eg-badge-${state}-bg)`,
      state,
    );
  }
});

test("every published badge pair reaches the 4.5 minimum in both themes", () => {
  for (const [theme, body] of Object.entries(THEMES)) {
    const ink = themeToken(body, "--eg-badge-ink");
    for (const state of ROUTE_BADGE_STATES) {
      const ratio = contrastRatio(ink, themeToken(body, `--eg-badge-${state}-bg`));
      assert.ok(ratio !== null, `${theme}/${state}: the published colours must be readable`);
      assert.ok(
        (ratio as number) >= ROUTE_BADGE_MIN_CONTRAST,
        `${theme}/${state}: ${ink} on ${themeToken(body, `--eg-badge-${state}-bg`)} is`
        + ` ${(ratio as number).toFixed(2)}:1, below ${ROUTE_BADGE_MIN_CONTRAST}:1`,
      );
    }
  }
});

test("the measured CI defect is reproduced, and the candidate pill no longer carries it", () => {
  // The negative control: white on the survey blue is the 2.77:1 CI 36428725740 measured, so a
  // green badge test cannot be a test that cannot see the defect.
  const reported = contrastRatio("#ffffff", "#0ea5e9") as number;
  assert.ok(Math.abs(reported - 2.77) < 0.01, `expected the reported 2.77, computed ${reported}`);
  assert.ok(reported < ROUTE_BADGE_MIN_CONTRAST);

  // The candidate pill's background is its own token now, and that token passes in both themes.
  assert.equal(
    activeDeclaration(".resource-route-state-pill.candidate", "background"),
    "var(--eg-badge-candidate-bg)",
  );
  for (const [theme, body] of Object.entries(THEMES)) {
    const background = themeToken(body, "--eg-badge-candidate-bg");
    assert.notEqual(background.toLowerCase(), "#0ea5e9", theme);
    const ratio = contrastRatio(themeToken(body, "--eg-badge-ink"), background) as number;
    assert.ok(ratio >= ROUTE_BADGE_MIN_CONTRAST, `${theme}: candidate badge is ${ratio.toFixed(2)}:1`);
  }
});

test("the map and legend dot palette is unchanged", () => {
  // The survey palette the map draws with: the badge fix must not repaint it.
  const palette = {
    light: {
      "--eg-map-hub": "#0f766e",
      "--eg-map-standard": "#0ea5e9",
      "--eg-map-lng": "#7c3aed",
      "--eg-map-interconnector": "#f97316",
      "--eg-map-pipeline": "#4b5563",
      "--eg-map-route": "#111827",
    },
    dark: {
      "--eg-map-hub": "#2dd4bf",
      "--eg-map-standard": "#38bdf8",
      "--eg-map-lng": "#a78bfa",
      "--eg-map-interconnector": "#fb923c",
      "--eg-map-pipeline": "#9ca3af",
      "--eg-map-route": "#f8fafc",
    },
  };
  for (const [theme, tokens] of Object.entries(palette)) {
    for (const [token, value] of Object.entries(tokens)) {
      assert.equal(themeToken(THEMES[theme as keyof typeof THEMES], token), value, `${theme}/${token}`);
    }
  }

  // The legend dots still paint from the map palette / warning token, not from the badge palette.
  assert.equal(activeDeclaration(".route-state-item.allocated i", "background"), "var(--eg-map-hub)");
  assert.equal(
    activeDeclaration(".route-state-item.candidate i", "background"),
    "var(--eg-map-standard)",
  );
  assert.equal(activeDeclaration(".route-state-item.blocked i", "background"), "var(--warning)");
});

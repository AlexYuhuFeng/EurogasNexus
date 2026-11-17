// The situational strip under the top bar in a real browser (role-first redesign §5, rule I13).
//
// - On every page: the strip region (`[data-shell-region="ticker"]`) is absent, or it is one
//   line no taller than a touch control, with no running CSS animation and none of the old
//   marquee's parts.
// - Once per run, as the signed-in identity: with the quiet line switched off in the person's own
//   preferences, hiding every urgent item through the strip's own Hide leaves no region at all
//   (no empty band); the person's preferences are restored afterwards. While items are listed, the
//   keyboard path holds: Enter on "+n more" opens the list with focus inside, ArrowDown moves
//   between items, Escape closes it and focus returns to the trigger; axe is clean on the list.

/** Read in the page: the strip's shape. Serialised by Playwright, so it closes over nothing. */
export function readStripShape() {
  const region = document.querySelector('[data-shell-region="ticker"]');
  if (!region) return { present: false };
  const box = region.getBoundingClientRect();
  const running = (region.getAnimations ? region.getAnimations({ subtree: true }) : [])
    .filter((animation) => animation.playState === "running" && !region.querySelector("[popover]:popover-open, dialog[open]")?.contains(animation.effect?.target ?? null))
    .map((animation) => animation.animationName || animation.constructor.name);
  const animated = [region, ...region.querySelectorAll("*")]
    .filter((element) => !element.closest("[popover], dialog"))
    .filter((element) => getComputedStyle(element).animationName !== "none")
    .map((element) => element.className || element.tagName);
  const line = region.querySelector(".strip-top, .strip-quiet-line");
  const lineBox = line ? line.getBoundingClientRect() : null;
  const lineHeight = line ? parseFloat(getComputedStyle(line).lineHeight) || 0 : 0;
  return {
    present: true,
    state: region.getAttribute("data-strip-state"),
    height: Math.round(box.height),
    width: Math.round(box.width),
    viewport: window.innerWidth,
    // One line: the text inside wraps to no second line (it ends in an ellipsis instead).
    wraps: line ? line.scrollHeight > Math.max(lineBox.height, lineHeight) + 2 : false,
    overflowsPage: box.right > window.innerWidth + 1,
    running,
    animated,
    marquee: Boolean(region.querySelector(".ticker-track, .ticker-pause, [aria-pressed]")),
  };
}

/** I13 failures for one page's strip shape (an empty list when it holds). */
export function stripShapeProblems(shape) {
  if (!shape || !shape.present) return [];
  const problems = [];
  if (shape.height > 48) problems.push(`the situational strip is ${shape.height}px high (one line is at most 48px)`);
  if (shape.wraps) problems.push("the situational strip's line wraps to a second line");
  if (shape.overflowsPage) problems.push("the situational strip runs past the page edge");
  if (shape.running.length || shape.animated.length) {
    problems.push(`the situational strip moves: ${[...shape.running, ...shape.animated].join(", ")}`);
  }
  if (shape.marquee) problems.push("the situational strip still carries the old marquee's parts");
  return problems;
}

async function savePreferences(page, patch) {
  return page.evaluate(async (body) => {
    const me = await fetch("/api/me", { credentials: "include" }).then((response) => response.json());
    const csrf = me?.data?.csrf_token ?? me?.csrf_token ?? "";
    const response = await fetch("/api/me/preferences", {
      method: "PUT",
      credentials: "include",
      headers: { "Content-Type": "application/json", ...(csrf ? { "X-Eurogas-CSRF": csrf } : {}) },
      body: JSON.stringify(body),
    });
    return response.status;
  }, patch);
}

async function reload(page, base) {
  await page.goto(`${base}/?workspace=market&task=overview`, { waitUntil: "domcontentloaded" });
  await page.locator("main").waitFor({ state: "visible", timeout: 20_000 });
  await page.waitForTimeout(4000);
}

/**
 * The once-per-run strip interaction. `record(message)` records a failure; `axe(selector)`
 * returns the violations inside a selector.
 */
export async function situationStripInteraction(page, base, record, axe, observe = () => undefined) {
  const status = await savePreferences(page, { strip_quiet_line: "off", strip_hidden: null });
  if (status !== 200) {
    record(`the strip preferences could not be saved (HTTP ${status})`);
    return;
  }
  try {
    await reload(page, base);
    let shape = await page.evaluate(readStripShape);
    for (const problem of stripShapeProblems(shape)) record(problem);
    if (shape.present && shape.state !== "urgent") {
      record(`with the quiet line off the strip shows state '${shape.state}'`);
    }
    if (shape.present) {
      // Keyboard: open, move, Escape.
      const trigger = page.locator("[data-strip-expand]");
      await trigger.focus();
      await page.keyboard.press("Enter");
      await page.waitForTimeout(400);
      const inside = await page.evaluate(() => Boolean(document.activeElement?.closest("[data-popover=situation-strip], dialog[data-dialog=situation-strip]")));
      if (!inside) record("Enter on the strip's '+n more' did not move focus into the list");
      const items = await page.locator("[data-strip-list] [data-strip-open]").count();
      if (items < 1 || items > 7) record(`the expanded strip lists ${items} items (1 to 7)`);
      if (items > 1) {
        await page.locator("[data-strip-list] [data-strip-open]").first().focus();
        await page.keyboard.press("ArrowDown");
        const second = await page.evaluate(() => {
          const links = [...document.querySelectorAll("[data-strip-list] [data-strip-open]")];
          return links.indexOf(document.activeElement);
        });
        if (second !== 1) record(`ArrowDown in the strip list moved focus to item ${second}, not the second`);
      }
      const why = await page.locator("[data-strip-list] [data-strip-why]").count();
      if (why !== items) record(`${items - why} strip item(s) carry no "why am I seeing this" line`);
      const violations = await axe("[data-strip-list]");
      if (violations.length) record(`axe violations in the expanded strip: ${JSON.stringify(violations)}`);
      await page.keyboard.press("Escape");
      await page.waitForTimeout(300);
      const back = await page.evaluate(() => document.activeElement?.hasAttribute("data-strip-expand") ?? false);
      if (!back) record("Escape did not close the strip list and return focus to '+n more'");
      if (await page.locator("[data-strip-list]").count()) record("the strip list stayed open after Escape");

      // Hide every item through the strip's own Hide: no region is left, not an empty band.
      for (let round = 0; round < 12; round += 1) {
        if (!(await page.locator('[data-shell-region="ticker"]').count())) break;
        await page.locator("[data-strip-expand]").click();
        await page.locator("[data-strip-list] [data-strip-action=hide]").first().click();
        await page.waitForTimeout(400);
        if (await page.locator("[data-strip-list]").count()) await page.keyboard.press("Escape");
        await page.waitForTimeout(300);
      }
      shape = await page.evaluate(readStripShape);
      if (shape.present) record("after hiding every item the strip region is still there");
      observe(`situation strip: ${items} item(s) listed, every one hidden through the strip`);
    } else {
      observe("situation strip: nothing qualifies for this identity and the quiet line is off: no region");
    }
    // Hidden items stay hidden across a reload (they are the person's own preference).
    await reload(page, base);
    shape = await page.evaluate(readStripShape);
    if (shape.present) record("hidden strip items came back after a reload without a change");
    const band = await page.evaluate(() => {
      const header = document.querySelector(".app-header, header");
      const main = document.querySelector("main");
      if (!header || !main) return null;
      // The endpoint banner is the shell's own surface; what is left is what the strip left.
      const banner = document.querySelector(".endpoint-error-banner")?.getBoundingClientRect().height ?? 0;
      return Math.round(main.getBoundingClientRect().top - header.getBoundingClientRect().bottom - banner);
    });
    if (band !== null && band > 48) record(`with no strip there is still a ${band}px band under the top bar`);
  } finally {
    await savePreferences(page, { strip_quiet_line: null, strip_hidden: null });
  }
}

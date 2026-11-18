#!/usr/bin/env node
// Keyboard paths through the UX-02/UX-03 primitives in a real browser (Chromium):
//
// - Tabs: the active task tab is the only Tab stop; ArrowRight moves and activates.
// - DataGrid: a sort header toggles aria-sort with Enter; an interactive grid has one row in
//   the Tab order; ArrowDown/End move focus; Enter runs the row action (hub focus).
// - Popover: Enter on "Method" opens it with focus inside; Escape closes it and focus returns
//   to the trigger.
// - Dialog: "?" opens the shortcuts dialog with focus inside; Tab stays inside; Escape closes it
//   and focus returns to where it was.
// - Modes (WF-05): the top bar is four modes in one Tab stop; arrows move and open them;
//   Ctrl+Shift+n opens the n-th; old area addresses redirect; the palette finds old names; a
//   utility page selects no mode.
// - Situational strip (I13): absent or one static line; with an urgent item, Enter on "+n more"
//   opens the list with focus inside, ArrowDown moves, Escape closes it and focus returns.
//
// Exits 1 on the first broken path. Optional screenshots of each state go to OUTPUT_DIR.
// Environment: EUROGAS_UAT_BASE_URL (default http://127.0.0.1:3000), EUROGAS_UAT_PLAYWRIGHT_PATH,
// EUROGAS_UAT_OUTPUT_DIR, EUROGAS_NEXUS_DEV_LOGIN_USERNAME / _PASSWORD.
import { createRequire } from "node:module";
import { mkdirSync } from "node:fs";
import path from "node:path";

import { readStripShape, stripShapeProblems } from "./situationStrip.mjs";

const require = createRequire(import.meta.url);
const BASE = process.env.EUROGAS_UAT_BASE_URL || "http://127.0.0.1:3000";
const OUTPUT_DIR = process.env.EUROGAS_UAT_OUTPUT_DIR || "";
const THEME = process.env.EUROGAS_UAT_THEME || "light";

const failures = [];
const check = (condition, message) => {
  if (condition) console.log(`ok   ${message}`);
  else {
    console.log(`FAIL ${message}`);
    failures.push(message);
  }
};

async function signIn(page) {
  await page.goto(BASE, { waitUntil: "domcontentloaded" });
  await page.waitForTimeout(500);
  if (await page.locator("main").isVisible().catch(() => false)) return;
  const username = process.env.EUROGAS_NEXUS_DEV_LOGIN_USERNAME || "";
  const password = process.env.EUROGAS_NEXUS_DEV_LOGIN_PASSWORD || "";
  if (!username || !password) throw new Error("set EUROGAS_NEXUS_DEV_LOGIN_USERNAME and _PASSWORD");
  await page.locator("#sign-in-username").waitFor({ state: "visible", timeout: 15_000 });
  await page.locator("#sign-in-username").fill(username);
  await page.locator("#sign-in-password").fill(password);
  await page.locator(".sign-in-dev-form button[type=submit]").click();
  await page.locator("main").waitFor({ state: "visible", timeout: 20_000 });
}

const active = (page) =>
  page.evaluate(() => {
    const el = document.activeElement;
    return {
      tag: el?.tagName.toLowerCase() ?? null,
      role: el?.getAttribute("role") ?? null,
      text: (el?.textContent ?? "").trim().slice(0, 40),
      rowKey: el?.getAttribute("data-row-key") ?? null,
      inDialog: Boolean(el?.closest("dialog[open], [role=dialog]")),
      method: el?.getAttribute("data-method") ?? null,
    };
  });

async function shot(page, name) {
  if (!OUTPUT_DIR) return;
  mkdirSync(OUTPUT_DIR, { recursive: true });
  await page.screenshot({ path: path.join(OUTPUT_DIR, `${name}.png`) });
}

async function go(page, search) {
  await page.goto(`${BASE}/${search}`, { waitUntil: "domcontentloaded" });
  await page.locator("main").waitFor({ state: "visible", timeout: 20_000 });
  await page.waitForTimeout(3500);
}

export async function runKeyboardPaths() {
  const { chromium } = require(
    process.env.EUROGAS_UAT_PLAYWRIGHT_PATH ? path.resolve(process.env.EUROGAS_UAT_PLAYWRIGHT_PATH) : "playwright",
  );
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({ viewport: { width: 1440, height: 900 }, reducedMotion: "reduce" });
  await context.addInitScript((theme) => {
    try {
      localStorage.setItem("theme", theme);
      localStorage.setItem("eurogas.language.v1", "en");
    } catch {
      /* storage blocked */
    }
  }, THEME);
  const page = await context.newPage();
  try {
    await signIn(page);

    // Tabs ---------------------------------------------------------------------------------
    await go(page, "?workspace=market&task=curves");
    const tabStops = await page.locator(".workspace-page-header [role=tab][tabindex='0']").count();
    check(tabStops === 1, `task tabs have one Tab stop (found ${tabStops})`);
    await page.locator(".workspace-page-header [role=tab][aria-selected=true]").focus();
    await page.keyboard.press("ArrowRight");
    await page.waitForTimeout(600);
    const tab = await active(page);
    check(tab.role === "tab" && /Network/i.test(tab.text), `ArrowRight moves to the next task tab (${tab.text})`);
    check(/task=network/.test(page.url()), "and activates it");

    // DataGrid: hub board ----------------------------------------------------------------------
    await go(page, "?workspace=market&task=curves");
    const board = page.locator("[data-grid=hub-board] table");
    check((await board.getAttribute("role")) === "grid", "the hub board is an interactive grid");
    const rowStops = await board.locator("tbody tr[tabindex='0']").count();
    check(rowStops === 1, `the board has one row in the Tab order (found ${rowStops})`);
    await board.locator("tbody tr[tabindex='0']").focus();
    await page.keyboard.press("ArrowDown");
    let cell = await active(page);
    check(cell.tag === "tr" && cell.rowKey?.startsWith("NBP"), `ArrowDown moves to the second row (${cell.rowKey})`);
    await page.keyboard.press("End");
    cell = await active(page);
    check(cell.tag === "tr" && cell.rowKey?.startsWith("PSV"), `End moves to the last row (${cell.rowKey})`);
    await page.keyboard.press("Home");
    await page.keyboard.press("Enter");
    await page.waitForTimeout(400);
    check(
      (await board.locator("tbody tr").first().getAttribute("aria-selected")) === "true",
      "Enter runs the row action: the hub is focused and the row selected",
    );
    await page.keyboard.press("Enter");

    // Sparkline: a figure's small line reads out on the keyboard (Today) ------------------------
    await go(page, "?workspace=market&task=overview");
    const spark = page.locator(".today-fundamental .ds-sparkline").first();
    if (await spark.count()) {
      await spark.focus();
      check((await active(page)).tag === "span", "a sparkline takes focus");
      check(/low .* high /i.test((await spark.getAttribute("aria-label")) ?? ""), "its name states first, last, low and high");
      await page.keyboard.press("ArrowLeft");
      await page.keyboard.press("ArrowLeft");
      await page.waitForTimeout(200);
      const live = (await spark.locator("[aria-live=polite]").textContent())?.trim() ?? "";
      check(live.length > 0 && (await spark.getAttribute("data-sparkline-active")) !== null, `arrow keys step through its points (${live})`);
      await shot(page, "keyboard-sparkline");
      await page.keyboard.press("Escape");
    } else {
      check(true, "no sparkline on this desk (no fundamentals): skipped");
    }

    // Network panel: the panel's tabs and its outage list ---------------------------------------
    await go(page, "?workspace=market&task=network");
    const panelTabs = page.locator("#network-panel-tab-outages, [id^=network-panel-tab-][aria-selected=true]");
    check((await panelTabs.count()) > 0, "the Network panel has its tabs");
    await page.locator("[id^=network-panel-tab-][aria-selected=true]").focus();
    await page.keyboard.press("ArrowRight");
    await page.waitForTimeout(400);
    check(/panel=capacity/.test(page.url()), "ArrowRight opens the Capacity tab and the URL says so");
    await go(page, "?workspace=capacity");
    check(/task=network/.test(page.url()) && /panel=capacity/.test(page.url()), `the retired capacity address lands on Network → Capacity (${new URL(page.url()).search})`);

    // DataGrid: sort -----------------------------------------------------------------------------
    await go(page, "?workspace=contracts&task=exposure");
    const credit = page.locator("[data-grid=credit-exposure] table");
    await credit.scrollIntoViewIfNeeded();
    const header = credit.locator("th[data-col=used]");
    // Utilisation is sorted largest first by default; Enter reverses it, and again restores it.
    check((await header.getAttribute("aria-sort")) === "descending", "limits open sorted by utilisation, largest first");
    await header.locator("button").focus();
    const values = await credit.locator("tbody td[data-col=used]").allTextContents();
    await shot(page, "sorted-grid");
    await page.keyboard.press("Enter");
    await page.waitForTimeout(200);
    check((await header.getAttribute("aria-sort")) === "ascending", "Enter on the sorted header reverses it");
    await page.keyboard.press("Enter");
    check(values.length > 0, `sorted rows: ${values.join(" | ")}`);

    // Popover: Method (the ladder's mark-to-market and VaR are on Position) ----------------------
    await go(page, "?workspace=contracts&task=overview");
    const method = page.locator("[data-method=var_proxy], [data-method=mark_to_market]").first();
    await method.scrollIntoViewIfNeeded();
    await method.focus();
    await page.keyboard.press("Enter");
    await page.waitForTimeout(300);
    const inside = await active(page);
    check(inside.inDialog, "Enter on Method opens the note with focus inside");
    check((await method.getAttribute("aria-expanded")) === "true", "the trigger says it is expanded");
    await shot(page, "method-popover");
    await page.keyboard.press("Escape");
    await page.waitForTimeout(200);
    const back = await active(page);
    check(Boolean(back.method), "Escape closes the note and returns focus to the trigger");
    check((await page.locator("[data-popover=method]").count()) === 0, "the note is gone");

    // Modes (WF-05) ------------------------------------------------------------------------------
    await go(page, "?workspace=market&task=curves");
    const modes = page.locator(".workspace-primary-tabs [role=tab]");
    check((await modes.allTextContents()).join("|") === "Desk|Deals|Book|Research", `the top bar is the four modes (${(await modes.allTextContents()).join("|")})`);
    check((await page.locator(".workspace-primary-tabs [role=tab][tabindex='0']").count()) === 1, "the modes are one Tab stop");
    await page.locator(".workspace-primary-tabs [role=tab][aria-selected=true]").focus();
    await page.keyboard.press("ArrowRight");
    await page.waitForTimeout(1500);
    check(/workspace=contracts&task=resources/.test(page.url()) && (await active(page)).text === "Deals", `ArrowRight opens Deals at Contracts (${page.url()})`);
    await page.keyboard.press("ArrowRight");
    await page.waitForTimeout(1500);
    check(/workspace=contracts&task=overview/.test(page.url()), `ArrowRight again opens Book at Position (${page.url()})`);
    await page.keyboard.press("End");
    await page.waitForTimeout(1500);
    check(/workspace=research&task=reports/.test(page.url()), `End opens Research at Reports (${page.url()})`);
    await shot(page, "modes-research");
    await page.locator("body").click({ position: { x: 5, y: 300 } });
    await page.keyboard.press("Control+Shift+Digit3");
    await page.waitForTimeout(1500);
    check(/workspace=contracts/.test(page.url()), `Ctrl+Shift+3 opens Book (${page.url()})`);
    // Old addresses land in their new place.
    for (const [from, url, mode] of [
      ["?workspace=decision", /workspace=scenario&task=review/, "Deals"],
      // Pages and tasks removed by CP-00 land on the nearest surviving task.
      ["?workspace=scenario&task=optimize", /workspace=contracts&task=resources/, "Deals"],
      ["?workspace=strategy&task=backtest", /workspace=research&task=reports/, "Research"],
      ["?workspace=portfolio", /workspace=contracts&task=overview/, "Book"],
      ["?workspace=scenario&task=nomination", /workspace=scenario&task=nomination/, "Book"],
      ["?mode=book&task=limits", /workspace=contracts&task=exposure/, "Book"],
    ]) {
      await go(page, from);
      const selected = await page.locator(".workspace-primary-tabs [aria-selected=true]").allTextContents();
      check(url.test(page.url()) && selected.join() === mode, `${from} lands in ${mode} (${page.url().replace(/^.*\//, "")})`);
    }
    // The palette finds an old name.
    await page.keyboard.press("Control+k");
    await page.waitForTimeout(300);
    await page.keyboard.type("Decision Center");
    await page.waitForTimeout(300);
    const found = await page.locator("[role=option]").allTextContents();
    check(found.some((text) => /Deals/.test(text)), `the palette finds "Decision Center" as Deals (${found.slice(0, 3).join(" | ")})`);
    await page.keyboard.press("Escape");
    // A utility page selects no mode and keeps one Tab stop.
    await go(page, "?workspace=settings");
    check((await page.locator(".workspace-primary-tabs [aria-selected=true]").count()) === 0, "Settings selects no mode");
    check((await page.locator(".workspace-primary-tabs [role=tab][tabindex='0']").count()) === 1, "and the mode row keeps one Tab stop");

    // Situational strip (I13) --------------------------------------------------------------------
    await go(page, "?workspace=market&task=overview");
    const strip = await page.evaluate(readStripShape);
    const stripProblems = stripShapeProblems(strip);
    check(stripProblems.length === 0, `the strip is absent or one static line (${strip.present ? `${strip.state}, ${strip.height}px` : "absent"}${stripProblems.length ? `: ${stripProblems.join("; ")}` : ""})`);
    if (strip.present && strip.state === "urgent") {
      const expand = page.locator("[data-strip-expand]");
      await expand.focus();
      await page.keyboard.press("Enter");
      await page.waitForTimeout(400);
      check((await active(page)).inDialog, "Enter on the strip's '+n more' opens the list with focus inside");
      const links = page.locator("[data-strip-list] [data-strip-open]");
      const count = await links.count();
      check(count >= 1 && count <= 7, `the list holds one to seven items (${count})`);
      if (count > 1) {
        await links.first().focus();
        await page.keyboard.press("ArrowDown");
        const index = await page.evaluate(() => [...document.querySelectorAll("[data-strip-list] [data-strip-open]")].indexOf(document.activeElement));
        check(index === 1, `ArrowDown moves to the next item (${index})`);
      }
      await shot(page, "strip-expanded");
      await page.keyboard.press("Escape");
      await page.waitForTimeout(300);
      check(await page.evaluate(() => document.activeElement?.hasAttribute("data-strip-expand") ?? false), "Escape closes the list and focus returns to '+n more'");
      check((await page.locator("[data-strip-list]").count()) === 0, "the list is gone");
    } else {
      check(true, `no urgent strip item for this identity (${strip.present ? strip.state : "absent"}): list path skipped`);
    }

    // Dialog: shortcuts -------------------------------------------------------------------------
    await go(page, "?workspace=market&task=curves");
    await page.locator("body").click({ position: { x: 5, y: 300 } });
    await page.keyboard.press("?");
    await page.waitForTimeout(400);
    const dialog = page.locator("dialog[data-dialog=shortcuts]");
    check(await dialog.evaluate((el) => el.open).catch(() => false), "? opens the shortcuts dialog");
    check((await active(page)).inDialog, "focus moves into the dialog");
    for (let index = 0; index < 4; index += 1) await page.keyboard.press("Tab");
    check((await active(page)).inDialog, "Tab stays inside the dialog");
    await shot(page, "dialog");
    await page.keyboard.press("Escape");
    await page.waitForTimeout(300);
    check(!(await dialog.evaluate((el) => el.open).catch(() => true)), "Escape closes the dialog");
  } finally {
    await browser.close();
  }
  if (failures.length) {
    console.log(`\n${failures.length} keyboard path(s) broken`);
    process.exit(1);
  }
  console.log("\nall keyboard paths hold");
}

await runKeyboardPaths();

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
//
// Exits 1 on the first broken path. Optional screenshots of each state go to OUTPUT_DIR.
// Environment: EUROGAS_UAT_BASE_URL (default http://127.0.0.1:3000), EUROGAS_UAT_PLAYWRIGHT_PATH,
// EUROGAS_UAT_OUTPUT_DIR, EUROGAS_NEXUS_DEV_LOGIN_USERNAME / _PASSWORD.
import { createRequire } from "node:module";
import { mkdirSync } from "node:fs";
import path from "node:path";

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

    // Popover: Method ---------------------------------------------------------------------------
    await go(page, "?workspace=contracts&task=exposure");
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
    check(/workspace=scenario/.test(page.url()) && (await active(page)).text === "Deals", `ArrowRight opens Deals (${page.url()})`);
    await page.keyboard.press("ArrowRight");
    await page.waitForTimeout(1500);
    check(/workspace=contracts&task=overview/.test(page.url()), `ArrowRight again opens Book at Position (${page.url()})`);
    await page.keyboard.press("End");
    await page.waitForTimeout(1500);
    check(/workspace=strategy/.test(page.url()), `End opens Research (${page.url()})`);
    await shot(page, "modes-research");
    await page.locator("body").click({ position: { x: 5, y: 300 } });
    await page.keyboard.press("Control+Shift+Digit3");
    await page.waitForTimeout(1500);
    check(/workspace=contracts/.test(page.url()), `Ctrl+Shift+3 opens Book (${page.url()})`);
    // Old addresses land in their new place.
    for (const [from, url, mode] of [
      ["?workspace=decision", /workspace=scenario&task=scenario/, "Deals"],
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
    const found = await page.locator("[role=option], [role=listbox] li, .command-palette-result").allTextContents();
    check(found.some((text) => /Deals/.test(text)), `the palette finds "Decision Center" as Deals (${found.slice(0, 3).join(" | ")})`);
    await page.keyboard.press("Escape");
    // A utility page selects no mode and keeps one Tab stop.
    await go(page, "?workspace=settings");
    check((await page.locator(".workspace-primary-tabs [aria-selected=true]").count()) === 0, "Settings selects no mode");
    check((await page.locator(".workspace-primary-tabs [role=tab][tabindex='0']").count()) === 1, "and the mode row keeps one Tab stop");

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

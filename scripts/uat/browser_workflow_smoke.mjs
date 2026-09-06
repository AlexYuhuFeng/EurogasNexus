// CR-13 browser UAT smoke (optional, not part of npm test).
//
// Usage:
//   npm install playwright --prefix /tmp/eurogas-uat
//   npm install playwright --prefix /tmp/eurogas-uat
//   EUROGAS_UAT_PLAYWRIGHT_PATH=/tmp/eurogas-uat/node_modules/playwright/index.js //     node scripts/uat/browser_workflow_smoke.mjs
//
// Requires the development backend on :8000 and Vite dev server on :3000
// with the UAT fixture already seeded.
import { createRequire } from "node:module";

const require = createRequire(import.meta.url);
const { chromium } = require(
  process.env.EUROGAS_UAT_PLAYWRIGHT_PATH || "playwright",
);

const BASE = "http://127.0.0.1:3000";

export async function runWorkflowSmoke() {
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  const errors = [];
  page.on("pageerror", (error) => errors.push(`pageerror:${error}`));
  page.on("console", (message) => {
    if (message.type() === "error") errors.push(`console:${message.text()}`);
  });
  const steps = [];

  const record = async (name, ok, detail = "") => {
    steps.push({ name, ok, detail });
  };

  // Golden A: Market -> Scenario
  await page.goto(`${BASE}/?workspace=market`, { waitUntil: "domcontentloaded" });
  await page.waitForTimeout(2000);
  const marketText = await page.locator("body").innerText();
  record(
    "golden-a-market-to-scenario",
    marketText.includes("NBP") && marketText.includes("Open in Scenario"),
    "hub board and handoff visible",
  );
  await page.getByRole("button", { name: /Open in Scenario/ }).first().click().catch(() => {});
  await page.waitForTimeout(700);

  // Golden B: Portfolio -> optimize -> review
  await page.goto(`${BASE}/?workspace=contracts`, { waitUntil: "domcontentloaded" });
  await page.waitForTimeout(1500);
  await page.getByRole("button", { name: /Preview TTF portfolio supply/ }).first().click().catch(() => {});
  await page.goto(`${BASE}/?workspace=scenario`, { waitUntil: "domcontentloaded" });
  await page.waitForTimeout(1200);
  await page.getByRole("button", { name: /Optimize Resource Pool/ }).click().catch(() => {});
  await page.waitForTimeout(2500);
  await page.goto(`${BASE}/?workspace=review`, { waitUntil: "domcontentloaded" });
  await page.waitForTimeout(2200);
  const reviewText = await page.locator("body").innerText();
  record(
    "golden-b-portfolio-optimize-review",
    reviewText.includes("Evidence pack") && reviewText.includes("MIN_COST_FLOW"),
    "allocation and evidence visible",
  );

  // Golden C: Strategy deep-link and run history visibility
  await page.goto(`${BASE}/?workspace=strategy`, { waitUntil: "domcontentloaded" });
  await page.waitForTimeout(1500);
  const strategyText = await page.locator("body").innerText();
  record(
    "golden-c-strategy-lab",
    strategyText.includes("Design") && strategyText.includes("Backtest") && strategyText.includes("Shadow"),
    "strategy tasks visible",
  );

  // Keyboard smoke: tab through topbar and workspace tabs without errors
  for (let index = 0; index < 8; index += 1) {
    await page.keyboard.press("Tab");
  }
  record("keyboard-smoke", errors.length === 0, `console/page errors=${errors.length}`);

  await browser.close();
  return { ok: steps.every((step) => step.ok) && errors.length === 0, steps, errors };
}

if (process.argv[1] === new URL(import.meta.url).pathname.replaceAll("/", "\\")) {
  const result = await runWorkflowSmoke();
  console.log(JSON.stringify(result, null, 2));
  process.exit(result.ok ? 0 : 1);
}

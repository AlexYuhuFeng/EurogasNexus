// Contract kinds in the browser (docs/product/CONTRACT_TYPES.md): the Contracts page is the list,
// New contract opens the kind cards, and a saved LNG master and a cargo confirmation under it
// stay on screen as saved, opened beside the list, and appear in the list under their master.
//
// The trust check (owner, 2026-11-19): a save that appears to lose the form is a failure. After
// each save the open contract must show the saved name and terms, and the form must not have
// gone back to an empty draft.
//
// Writes two contracts with a run-unique suffix; nothing else in the store is changed.

const PATH = "/?workspace=contracts&task=resources";

async function pick(page, id, query) {
  const root = page.locator(`[data-record-picker="${id}"]`);
  await root.locator(".ds-ipicker-trigger").click();
  const box = root.locator("input[role=combobox]");
  await box.fill(query);
  await page.waitForTimeout(250);
  await box.press("Enter");
  await page.waitForTimeout(200);
  if (await root.locator(".ds-rpicker-done").count()) await root.locator(".ds-rpicker-done").click();
}

/** Choose a day `monthsAhead` months from the calendar's first month (the 1st or the 10th). */
async function day(page, id, monthsAhead, text) {
  await page.locator(`#${id}`).click();
  for (let i = 0; i < monthsAhead; i += 1) await page.locator(".ds-period-nav").nth(1).click();
  await page
    .locator(".ds-period-grid button:not([disabled])", { hasText: new RegExp(`^${text}$`) })
    .first()
    .click();
  await page.waitForTimeout(120);
}

async function saveAndCheck(page, record, name, expectKind) {
  await page.locator(".contract-kind-actions button[type=submit]").click();
  // The write and the library refresh that follows it.
  await page.waitForResponse((response) => response.url().includes("/api/route-cost/upstream-contracts") && response.request().method() === "POST", { timeout: 20000 }).catch(() => null);
  // The save stays busy until the library and the book are read again after the write.
  await page.locator('.contract-kind-actions button[type=submit]:not([aria-busy="true"])').waitFor({ timeout: 30000 }).catch(() => null);
  await page.waitForTimeout(500);
  const form = page.locator(`[data-contract-kind-form="${expectKind}"]`);
  if (!(await form.count())) {
    record(`after saving '${name}' the ${expectKind} form is no longer open`);
    return;
  }
  const shownName = await page.inputValue("#kind-contract-name").catch(() => "");
  if (shownName !== name) record(`after saving '${name}' the form shows the name '${shownName}' (it went back to a draft)`);
  const title = (await page.locator(".contract-detail-head strong").innerText().catch(() => "")).trim();
  if (title !== name) record(`after saving '${name}' the open contract is titled '${title}'`);
  if (!(await page.locator("[data-kind-reads]").count())) record(`after saving '${name}' the form does not say what the book reads`);
  const needed = await page.locator(".contract-kind-actions .warning-text").count();
  if (needed) record(`after saving '${name}' the form lists terms still needed`);
}

export async function contractKindsInteraction(page, base, record, axe = null) {
  const suffix = Date.now().toString(36).slice(-5);
  const master = `UAT master ${suffix}`;
  const cargo = `UAT cargo ${suffix}`;
  await page.goto(`${base}${PATH}`, { waitUntil: "domcontentloaded" });
  // No waiting for the page's reads: a person may start at once (the reads land meanwhile).
  await page.locator('[data-page-action="contract-new"]').waitFor({ timeout: 30000 });
  await page.locator('[data-page-action="contract-new"]').click();
  if ((await page.locator("button.contract-kind-card").count()) < 4) record("New contract does not offer the four kind cards");
  if (axe) {
    const violations = await axe(".contract-kind-chooser");
    if (violations.length) record(`the kind cards have accessibility violations: ${violations.join(", ")}`);
  }
  await page.locator('button.contract-kind-card[data-contract-kind="LNG_MSPA"]').click();
  await page.fill("#kind-contract-name", master);
  await pick(page, "kind-counterparty_name", `UAT LNG seller ${suffix}`);
  await day(page, "kind-term_start", 0, "1");
  await page.fill("#kind-demurrage_usd_per_day", "55000");
  await saveAndCheck(page, record, master, "LNG_MSPA");

  await page.locator('[data-page-action="contract-new"]').click();
  await page.locator('button.contract-kind-card[data-contract-kind="LNG_CARGO"]').click();
  await page.fill("#kind-contract-name", cargo);
  await pick(page, "kind-master_contract_id", master);
  await page.fill("#kind-quantity_mmbtu", "3400000");
  await pick(page, "kind-discharge_terminal", "UAT terminal");
  await pick(page, "kind-terminal_hub", "TTF");
  await day(page, "kind-window_start", 2, "10");
  await day(page, "kind-window_end", 2, "14");
  await page.fill("#kind-slope", "1.15");
  await page.fill("#kind-constant", "2.5");
  await page.locator("#kind-pricing_month").click();
  await page.locator(".ds-period-months button").nth(11).click();
  // A width that flips for a moment (a full-page capture, a window snapping) must not move the
  // open form between the side panel and the phone sheet and lose what was typed.
  const size = page.viewportSize();
  if (size) {
    await page.setViewportSize({ width: 700, height: size.height });
    await page.waitForTimeout(60);
    await page.setViewportSize(size);
    await page.waitForTimeout(400);
    const kept = await page.inputValue("#kind-quantity_mmbtu").catch(() => "");
    if (kept !== "3400000") record(`a brief width change cleared the cargo form (size now '${kept}')`);
  }
  await saveAndCheck(page, record, cargo, "LNG_CARGO");

  // The list shows the cargo under its master.
  const rows = await page.locator('[data-record="upstream-contract"]').evaluateAll((nodes) =>
    nodes.map((node) => ({ name: node.querySelector("th, td")?.textContent?.trim() ?? "", parent: node.getAttribute("data-master") ?? "" })),
  );
  const masterAt = rows.findIndex((row) => row.name.includes(master));
  const cargoAt = rows.findIndex((row) => row.name.includes(cargo));
  if (masterAt < 0 || cargoAt < 0) record(`the list does not show both '${master}' and '${cargo}'`);
  else if (cargoAt !== masterAt + 1) record(`the cargo is listed at ${cargoAt}, not under its master at ${masterAt}`);
}

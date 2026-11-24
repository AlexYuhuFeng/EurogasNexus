/**
 * UX R7 (research/16B): the desktop shell's native menu names the product as it is now: the four
 * working modes with the Web workspace's own shortcuts, Search on Ctrl/Cmd+K and Settings… on
 * Ctrl/Cmd+, . Every id the menu emits must be one the Web workspace can run, and every id the
 * menu builds must be one the event handler forwards.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import { commandById } from "../src/app/experience/commandPalette.ts";
import { WORKSTATION_SHORTCUTS } from "../src/app/host/workstation.ts";

const main = readFileSync(new URL("../../desktop/src-tauri/src/main.rs", import.meta.url), "utf8");
const built = new Map(
  [...main.matchAll(/MenuItemBuilder::with_id\("([^"]+)", "([^"]+)"\)\s*\.accelerator\("([^"]+)"\)/g)].map((m) => [m[1], { label: m[2], accelerator: m[3] }]),
);
const texts = [...main.matchAll(/\.text\("([^"]+)", "([^"]+)"\)/g)].map((m) => m[1]);
const forwardedBlock = main.slice(main.indexOf('"palette.toggle"\n'), main.indexOf('=> {\n                        let _ = window.emit("workstation-command"'));
const forwarded = [...forwardedBlock.matchAll(/"([^"]+)"/g)].map((m) => m[1]);

test("the menu offers the four modes, Search and Settings with their shortcuts", () => {
  assert.deepEqual(built.get("palette.toggle"), { label: "Search…", accelerator: "CmdOrCtrl+K" });
  assert.deepEqual(built.get("navigate.page.settings"), { label: "Settings…", accelerator: "CmdOrCtrl+Comma" });
  const modes = [["desk", "Desk"], ["deals", "Deals"], ["book", "Book"], ["research", "Research"]];
  for (const [mode, label] of modes) {
    const item = built.get(`navigate.mode.${mode}`);
    assert.ok(item, `${mode} is in the menu`);
    assert.equal(item.label, label);
    // The same binding the Web workspace documents and handles.
    const shortcut = WORKSTATION_SHORTCUTS.find((s) => s.commandId === `navigate.mode.${mode}`);
    assert.ok(shortcut);
    assert.equal(item.accelerator, shortcut.binding.replace("Ctrl", "CmdOrCtrl"));
  }
  assert.doesNotMatch(main, /"(Market|Portfolio|Strategy Lab|Decision Center|Search commands…)"/, "the old workspace names are gone");
});

test("every id the menu emits is forwarded and runs a Web command", () => {
  const menuIds = [...built.keys(), ...texts].filter((id) => !id.startsWith("window."));
  assert.deepEqual([...new Set(menuIds)].sort(), [...new Set(forwarded)].sort());
  for (const id of forwarded) {
    if (id === "palette.toggle") continue; // opens the palette itself
    assert.ok(commandById(id), `${id} is a palette command`);
  }
});

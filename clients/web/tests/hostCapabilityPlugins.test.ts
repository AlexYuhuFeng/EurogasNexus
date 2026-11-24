/**
 * UX R6 (research/16B): the desktop host claims a plugin-backed capability only when the plugin
 * ships. Each `true` in hostCapabilities("desktop") for such a capability must be matched by its
 * crate in clients/desktop/src-tauri/Cargo.toml (or the tauri feature, or the window-creation
 * permission in capabilities/default.json). The signed updater is left out on purpose, so
 * autoUpdate stays false.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import { DESKTOP_CAPABILITY_REQUIREMENTS, hostCapabilities } from "../src/app/host/hostCapabilities.ts";

const TAURI = new URL("../../desktop/src-tauri/", import.meta.url);
const cargo = readFileSync(new URL("Cargo.toml", TAURI), "utf8");
const permissions = JSON.parse(readFileSync(new URL("capabilities/default.json", TAURI), "utf8")).permissions as string[];

function dependsOn(crate: string): boolean {
  const dependencies = cargo.slice(cargo.indexOf("[dependencies]"));
  return new RegExp(`^${crate.replace(/-/g, "[-_]")}\\s*=`, "m").test(dependencies);
}

function tauriFeature(feature: string): boolean {
  const line = cargo.match(/^tauri\s*=\s*\{[^}]*features\s*=\s*\[([^\]]*)\]/m)?.[1] ?? "";
  return line.includes(`"${feature}"`);
}

test("every plugin-backed capability the desktop claims is backed by what ships", () => {
  const desktop = hostCapabilities("desktop");
  for (const [capability, requirement] of Object.entries(DESKTOP_CAPABILITY_REQUIREMENTS)) {
    if (!desktop[capability as keyof typeof desktop]) continue;
    const req = requirement as { crate?: string; tauriFeature?: string; permission?: string };
    if (req.crate) assert.ok(dependsOn(req.crate), `${capability} is claimed but ${req.crate} is not in Cargo.toml`);
    if (req.tauriFeature) assert.ok(tauriFeature(req.tauriFeature), `${capability} is claimed but tauri lacks the ${req.tauriFeature} feature`);
    if (req.permission) assert.ok(permissions.includes(req.permission), `${capability} is claimed but ${req.permission} is not granted`);
  }
});

test("and a plugin that ships is claimed, so a capability is never left dark by mistake", () => {
  const desktop = hostCapabilities("desktop");
  for (const [capability, requirement] of Object.entries(DESKTOP_CAPABILITY_REQUIREMENTS)) {
    const req = requirement as { crate?: string };
    if (req.crate && dependsOn(req.crate)) assert.equal(desktop[capability as keyof typeof desktop], true, `${req.crate} ships but ${capability} is false`);
  }
});

test("the signed updater is left out: autoUpdate is false and no updater plugin is declared", () => {
  assert.equal(hostCapabilities("desktop").autoUpdate, false);
  assert.equal(dependsOn("tauri-plugin-updater"), false);
});

test("a browser claims none of them", () => {
  const browser = hostCapabilities("browser");
  for (const capability of Object.keys(DESKTOP_CAPABILITY_REQUIREMENTS)) {
    assert.equal(browser[capability as keyof typeof browser], false, capability);
  }
});

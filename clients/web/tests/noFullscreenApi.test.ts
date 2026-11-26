/**
 * No Fullscreen API anywhere in the client (owner, 2026-11-26). On macOS, Safari and WebKit full
 * screen (and the Tauri WebView in native full screen) block keyboard input, so the map's finder
 * could not be typed into and dragging the map misbehaved. The map expands within the app window
 * by CSS instead (app/hooks/useExpandedView.ts), and the desktop shell maximises its window.
 */
import assert from "node:assert/strict";
import { readdirSync, readFileSync, statSync } from "node:fs";
import test from "node:test";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const web = resolve(dirname(fileURLToPath(import.meta.url)), "..");

function sources(dir: string): string[] {
  return readdirSync(dir).flatMap((name) => {
    const path = join(dir, name);
    if (statSync(path).isDirectory()) return sources(path);
    return /\.(ts|tsx)$/.test(name) ? [path] : [];
  });
}

test("the client never asks the browser or the OS for full screen", () => {
  const offenders = sources(resolve(web, "src")).filter((path) =>
    /requestFullscreen|webkitRequestFullscreen|webkitEnterFullscreen|fullscreenElement|exitFullscreen/.test(readFileSync(path, "utf8")));
  assert.deepEqual(offenders, []);
  const shell = readFileSync(resolve(web, "../desktop/src-tauri/src/main.rs"), "utf8");
  assert.doesNotMatch(shell, /set_fullscreen/);
});

test("the map expands in the app window and Escape restores it", () => {
  const hook = readFileSync(resolve(web, "src/app/hooks/useExpandedView.ts"), "utf8");
  assert.match(hook, /has-expanded-view/);
  const page = readFileSync(resolve(web, "src/components/NetworkWorkspace.tsx"), "utf8");
  assert.match(page, /expandedView\.exit\(\)/);
  assert.match(page, /event\.key !== "Escape"/);
  // Escape typed in the finder stays in the finder.
  assert.match(page, /target\?\.closest\("input, textarea, select/);
});

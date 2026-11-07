import assert from "node:assert/strict";
import test from "node:test";
import { readFileSync } from "node:fs";

const read = (path: string) => readFileSync(new URL(`../src/${path}`, import.meta.url), "utf8");

test("an unload asks first while a contract or strategy draft holds unsaved edits (#32)", () => {
  const hook = read("app/hooks/useUnsavedChangesGuard.ts");
  assert.match(hook, /addEventListener\("beforeunload"/);
  assert.match(hook, /removeEventListener\("beforeunload"/);
  assert.match(hook, /if \(!dirty\) return undefined;/);

  assert.match(read("App.tsx"), /useUnsavedChangesGuard\(controller\.contractEditor\.draftDirty\)/);
  assert.match(read("app/model/useStrategyDesignDraft.ts"), /useUnsavedChangesGuard\(dirty\)/);
});

/** One control per meaning (#27): retired button variants do not come back. */
import assert from "node:assert/strict";
import { readdirSync, readFileSync, statSync } from "node:fs";
import { join } from "node:path";
import test from "node:test";

function sources(dir: string): string[] {
  return readdirSync(dir).flatMap((name) => {
    const path = join(dir, name);
    if (statSync(path).isDirectory()) return sources(path);
    return path.endsWith(".tsx") ? [path] : [];
  });
}

test("components use the canonical button variants only", () => {
  const retired = [
    'className="text-action"',
    'className="research-text-button"',
    'className="primary-button"',
    'className="button"',
  ];
  for (const path of sources(new URL("../src", import.meta.url).pathname)) {
    const text = readFileSync(path, "utf8");
    for (const name of retired) {
      assert.equal(text.includes(name), false, `${path} uses ${name}`);
    }
  }
});

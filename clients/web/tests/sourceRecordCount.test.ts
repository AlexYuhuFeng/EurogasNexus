/**
 * A source count the server could not read stays unknown in the client, never 0.
 *
 * The API sends ``live_record_count: null`` when its count query failed (before, it sent 0 for
 * every source and a broken query looked like an empty store). The normaliser used to coerce
 * that null to 0 with ``Number(value ?? 0)``.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { stripTypeScriptTypes } from "node:module";
import test from "node:test";
import vm from "node:vm";

function loadNormalizer(): (raw: Record<string, unknown>) => Record<string, unknown> {
  const source = readFileSync(new URL("../src/api/client.ts", import.meta.url), "utf8")
    .replace(
      /^import \{ HOST_COMMANDS, resolveHostKind, tryHostCommand \} from "@\/app\/host\/hostCapabilities";$/m,
      [
        'const HOST_COMMANDS = { readDeploymentConfig: "read", notifyClientReady: "ready", clearSessionData: "clear" };',
        'const resolveHostKind = () => "browser";',
        "const tryHostCommand = async () => null;",
      ].join("\n"),
    )
    .replace("import.meta.env.VITE_EUROGAS_API_BASE_URL", "undefined");
  const executable = stripTypeScriptTypes(source).replace(/^export\s+/gm, "");
  const sandbox: Record<string, unknown> = {
    AbortController, URL, URLSearchParams, console,
    localStorage: { getItem: () => null, removeItem: () => undefined, setItem: () => undefined },
    window: { location: { origin: "https://example.test" } },
  };
  vm.runInNewContext(`${executable}\nglobalThis.__normalize = normalizeSourceSystem;`, sandbox, {
    filename: "client.ts",
  });
  return sandbox.__normalize as (raw: Record<string, unknown>) => Record<string, unknown>;
}

test("a null count from the server is kept null, an absent one still reads as 0", () => {
  const normalize = loadNormalizer();
  const unknown = normalize({
    source_id: "src-entsog", source_system: "ENTSOG", live_record_count: null,
    effective_record_count: null, connectivity_status: "counts_unavailable",
  });
  assert.equal(unknown.live_record_count, null);
  assert.equal(unknown.effective_record_count, null);
  assert.equal(unknown.connectivity_status, "counts_unavailable");
  assert.equal(normalize({ source_system: "GIE" }).live_record_count, 0);
  const counted = normalize({ source_system: "GIE", live_record_count: 4_800 });
  assert.equal(counted.live_record_count, 4_800);
  assert.equal(counted.effective_record_count, 4_800);
});

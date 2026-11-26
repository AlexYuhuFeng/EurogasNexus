/**
 * UX R12 (research/16B): Settings is split by who owns each setting. Personal (how the product
 * looks and reads for this person), Workspace (where the desk opens, what the strip watches),
 * Organisation (the defaults an administrator sets) and Connection and diagnostics (release,
 * API keys, and, behind one Advanced fold, the backend URL, tokens and map tiles a deployment
 * usually fixes). Each of the person's groups goes back to the organisation default in one step.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const SRC = new URL("../src/", import.meta.url);
const read = (file: string) => readFileSync(new URL(file, SRC), "utf8");
const settings = read("components/SettingsCenter.tsx");
const panels = read("components/PreferencesPanels.tsx");

function list(source: string, name: string): string[] {
  const m = source.match(new RegExp(`const ${name}[^=]*= \\[([^\\]]*)\\]`));
  assert.ok(m, `${name} is declared`);
  return [...m[1].matchAll(/"([^"]+)"/g)].map((x) => x[1]);
}

test("four groups, Personal first", () => {
  assert.deepEqual(list(settings, "SETTINGS_GROUPS"), ["personal", "workspace", "organisation", "connection"]);
  assert.match(settings, /<Tabs\s+idPrefix="settings-group"/);
  assert.match(settings, /role="tabpanel"/);
  assert.match(settings, /return \(SETTINGS_GROUPS as readonly string\[\]\)\.includes\(stored \?\? ""\) \? \(stored as SettingsGroup\) : "personal";/);
});

test("Personal holds appearance, language, time and units; Workspace the landing view, board and strip", () => {
  const general = list(panels, "GENERAL_KEYS");
  const display = list(panels, "DISPLAY_KEYS");
  const landing = list(panels, "LANDING_KEYS");
  const strip = list(panels, "STRIP_KEYS");
  assert.deepEqual(general, ["language", "theme", "density", "pnl_colors", "time_zone"]);
  assert.deepEqual(display, ["reporting_currency", "energy_unit"]);
  assert.deepEqual(landing, ["market_view", "market_board_layout"]);
  assert.ok(strip.every((key) => key.startsWith("strip_")));
  assert.match(panels, /personal: \[\.\.\.GENERAL_KEYS, \.\.\.DISPLAY_KEYS\],\s*workspace: \[\.\.\.LANDING_KEYS, \.\.\.STRIP_KEYS\],/);
  // Every chosen key belongs to exactly one group (the organisation panel still lists all).
  const all = [...general, ...display, ...landing, ...strip];
  assert.equal(new Set(all).size, all.length);
  assert.match(settings, /group === "personal" && <PersonalPreferencesPanel t=\{t\} principalId=\{principalId\} group="personal" \/>/);
  assert.match(settings, /group === "workspace" && <PersonalPreferencesPanel t=\{t\} principalId=\{principalId\} group="workspace" \/>/);
  assert.match(panels, /group === "workspace" && \(\s*<FocusHubsField/);
});

test("each of the person's groups resets to the organisation default in one step", () => {
  assert.match(panels, /<Button\s+data-reset-group=\{group\}\s+disabled=\{!anyPersonal\}\s+onClick=\{\(\) => void savePatch\(Object\.fromEntries\(cleared\.map\(\(key\) => \[key, null\]\)\)\)\}/);
  assert.match(panels, /group === "workspace" \? \[\.\.\.PREFERENCE_GROUP_KEYS\.workspace, "strip_focus_hubs"\]/);
  assert.doesNotMatch(panels, /className="(primary|secondary)-button"/, "the shared Button, not a legacy class");
});

test("Organisation holds the defaults; Connection keeps deployment plumbing behind Advanced", () => {
  const organisation = settings.slice(settings.indexOf('group === "organisation"'), settings.indexOf('group === "connection"'));
  assert.match(organisation, /<OrganisationDefaultsPanel/);
  assert.match(organisation, /<NotificationChannelsPanel/);
  const connection = settings.slice(settings.indexOf('group === "connection"'));
  const advanced = connection.slice(connection.indexOf("<details"), connection.indexOf("</details>"));
  assert.match(connection, /settings-about-panel/);
  assert.match(connection, /<PersonalApiKeysPanel/);
  for (const plumbing of ["settings-backend-panel", "settings.api_token", "settings.operator_principal"]) {
    assert.ok(advanced.includes(plumbing), `${plumbing} sits behind the Advanced fold`);
  }
  const personal = settings.slice(0, settings.indexOf('group === "organisation"'));
  assert.doesNotMatch(personal, /settings-backend-panel/);
  // One basemap (OpenStreetMap): Settings offers no map provider at all (owner review 2026-11-26).
  assert.doesNotMatch(settings, /map_tile|MAP_TILE/);
});

test("every group string exists in English and Chinese", () => {
  const keys = [
    "settings.groups",
    "settings.group.personal",
    "settings.group.workspace",
    "settings.group.organisation",
    "settings.group.connection",
    "settings.group.reset",
    "settings.group.workspace_title",
    "settings.group.workspace_help",
    "settings.group.advanced",
    "settings.group.advanced_help",
  ];
  for (const language of ["en", "zh"]) {
    const strings = JSON.parse(read(`i18n/${language}.json`)) as Record<string, string>;
    for (const key of keys) assert.ok(strings[key], `${language}: ${key}`);
  }
});

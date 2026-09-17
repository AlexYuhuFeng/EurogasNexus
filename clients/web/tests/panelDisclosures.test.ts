/**
 * Panel-taxonomy disclosure audit (Architecture V2 Wave 9).
 *
 * The taxonomy states, per panel kind, which disclosures a panel of that kind owes when it
 * presents a material value ("a figure without its time basis, units, provenance or
 * entitlement state is not decision evidence"). The Wave 1 conformance test checks that the
 * *rules* are well formed. What nothing checked was whether the panels that claim to exist
 * can actually carry what they owe.
 *
 * This audit answers that per panel kind with live evidence: for each owed disclosure it
 * names the slot in the owning primitive, or records the disclosure as the caller's duty.
 * A claim whose marker disappears fails here, so the table cannot rot into aspiration.
 */

import assert from "node:assert/strict";
import { existsSync, readFileSync } from "node:fs";
import test from "node:test";

import {
  DISCLOSURE_KINDS,
  panelTaxonomy,
  type DisclosureKind,
} from "../src/app/experience/panelTaxonomy.ts";

const ROOT = new URL("../", import.meta.url);

function readWebSource(relativePath: string): string {
  return readFileSync(new URL(`src/${relativePath}`, ROOT), "utf8");
}

function webSourceExists(relativePath: string): boolean {
  return existsSync(new URL(`src/${relativePath}`, ROOT));
}

/** Where a disclosure is actually carried, per panel kind. */
interface DisclosureEvidence {
  /** Slot in the owning primitive, matched live against its source. */
  readonly marker: string;
  readonly file: string;
}

/**
 * Panel kinds whose owner carries the disclosure in a named slot. A kind absent from this
 * table owes its disclosures to its *callers* - the primitive offers no slot, which is
 * recorded in `CALLER_DUTY` below rather than left unsaid.
 */
const PROVIDED_BY_PRIMITIVE: Readonly<Record<string, Partial<Record<DisclosureKind, DisclosureEvidence>>>> = {
  "metric-strip": {
    "as-of": { file: "components/ui/MetricStrip.tsx", marker: 'data-disclosure="as-of"' },
    "time-basis": { file: "components/ui/MetricStrip.tsx", marker: 'data-disclosure="time-basis"' },
    units: { file: "components/ui/MetricStrip.tsx", marker: "metric-strip-unit" },
  },
  warnings: {
    warning: { file: "components/ui/StatusBadge.tsx", marker: "StatusBadgeVariant" },
  },
  map: {
    provenance: { file: "components/GasNetworkMap.tsx", marker: "map.node_popup_source" },
  },
  "time-series": {
    units: { file: "components/strategy/StrategyLabCharts.tsx", marker: "unit" },
  },
};

/**
 * Disclosures a panel kind owes to its callers rather than to its primitive, with the reason.
 * These are not gaps in the taxonomy - a layout primitive cannot invent a time basis - but
 * they are the parts of the contract a surface must satisfy itself, so they are named.
 */
const CALLER_DUTY: Readonly<Record<string, readonly DisclosureKind[]>> = {
  "context-summary": ["as-of", "time-basis"],
  table: ["as-of", "units", "provenance"],
  assumptions: ["assumption", "as-of", "time-basis"],
  "run-result": ["as-of", "correlation-id", "warning"],
  comparison: ["assumption", "as-of", "units"],
  "decision-history": ["provenance", "correlation-id"],
  "ai-explanation": ["provenance", "entitlement"],
  evidence: ["provenance", "entitlement", "as-of"],
  "metric-strip": [],
  "time-series": ["as-of", "time-basis", "provenance"],
  map: ["as-of"],
  warnings: ["provenance"],
};

test("every disclosure a panel owes is either carried by its primitive or the caller's duty", () => {
  const unexplained: string[] = [];

  for (const contract of panelTaxonomy) {
    for (const disclosure of contract.disclosures) {
      const provided = PROVIDED_BY_PRIMITIVE[contract.kind]?.[disclosure];
      const duty = CALLER_DUTY[contract.kind]?.includes(disclosure) ?? false;
      if (!provided && !duty) unexplained.push(`${contract.kind}:${disclosure}`);
    }
  }

  assert.deepEqual(
    unexplained,
    [],
    "a disclosure is neither carried by the primitive nor recorded as the caller's duty",
  );
});

test("a primitive claim that names a slot is live, and names a file that exists", () => {
  const stale: string[] = [];

  for (const [kind, entries] of Object.entries(PROVIDED_BY_PRIMITIVE)) {
    for (const [disclosure, evidence] of Object.entries(entries) as Array<
      [DisclosureKind, DisclosureEvidence]
    >) {
      if (!DISCLOSURE_KINDS.includes(disclosure)) stale.push(`${kind}: unknown disclosure`);
      if (!webSourceExists(evidence.file)) {
        stale.push(`${kind}:${disclosure} names a missing file`);
        continue;
      }
      if (!readWebSource(evidence.file).includes(evidence.marker)) {
        stale.push(`${kind}:${disclosure} marker '${evidence.marker}' is gone`);
      }
    }
  }

  assert.deepEqual(stale, [], "a disclosure claim rotted");
});

test("the metric strip carries the disclosures its kind owes", () => {
  const contract = panelTaxonomy.find((item) => item.kind === "metric-strip");
  assert.ok(contract);
  // The kind owes exactly these, and each has a live slot rather than a caller convention.
  assert.deepEqual([...contract.disclosures].sort(), ["as-of", "time-basis", "units"]);
  const strip = readWebSource("components/ui/MetricStrip.tsx");
  for (const disclosure of contract.disclosures) {
    const evidence = PROVIDED_BY_PRIMITIVE["metric-strip"]?.[disclosure];
    assert.ok(evidence, disclosure);
    assert.ok(strip.includes(evidence.marker), `${disclosure}: ${evidence.marker}`);
  }
  // An omitted disclosure renders nothing rather than an invented value.
  assert.match(strip, /showsAsOf \? <span data-disclosure="as-of">\{asOf\}<\/span> : null/);
  assert.match(strip, /\{item\.unit \? <small className="metric-strip-unit">\{item\.unit\}<\/small> : null\}/);
});

test("the agents replay strip discloses when its numbers were taken", () => {
  const agents = readWebSource("components/AgentsWorkspace.tsx");
  const en = JSON.parse(readWebSource("i18n/en.json")) as Record<string, string>;
  const zh = JSON.parse(readWebSource("i18n/zh.json")) as Record<string, string>;

  // The strip showed run counts with no instant, which the taxonomy calls out: a figure
  // without its as-of is not decision evidence.
  assert.match(agents, /asOf=\{/);
  assert.match(agents, /formatAgentTimestamp\(selectedRun\.created_at\)/);
  assert.ok(en["agents.run_as_of"]?.trim());
  assert.ok(zh["agents.run_as_of"]?.trim());
  assert.notEqual(en["agents.run_as_of"], zh["agents.run_as_of"]);
});

/**
 * Panel taxonomy (Architecture V2 Wave 1).
 *
 * Architecture V2 section 5 of
 * `docs/engineering/Architecture-V2/04_PRODUCT_EXPERIENCE_ARCHITECTURE.md` fixes a
 * reusable panel vocabulary and asks every new capability to answer "which existing
 * pattern and panel does this belong to?" before inventing a surface.
 *
 * This registry records that vocabulary together with two honest facts per panel:
 * which shared primitive owns it today (or none), and which disclosures a panel of
 * that kind must show when it presents a material number. Disclosures are the
 * client-side projection of the UI content standards: a figure without its time
 * basis, units, provenance or entitlement state is not decision evidence.
 *
 * The taxonomy is descriptive metadata. It does not render, does not fetch and does
 * not create a second implementation of any existing primitive.
 */

import type { PanelKind, WorkspacePattern } from "./vocabulary.ts";

/** Disclosures a panel must carry when it presents material values. */
export const DISCLOSURE_KINDS = [
  "as-of",
  "time-basis",
  "units",
  "provenance",
  "entitlement",
  "assumption",
  "warning",
  "correlation-id",
] as const;

export type DisclosureKind = (typeof DISCLOSURE_KINDS)[number];

export type PanelImplementation = "present" | "partial" | "absent";

export interface PanelContract {
  readonly kind: PanelKind;
  /** What the panel is for. */
  readonly purpose: string;
  /** Shared primitive that owns the panel today, or an empty list when none exists. */
  readonly owners: readonly string[];
  readonly implementation: PanelImplementation;
  /** Disclosures this panel kind owes when it shows material values. */
  readonly disclosures: readonly DisclosureKind[];
  /** Patterns that normally compose this panel. */
  readonly patterns: readonly WorkspacePattern[];
}

export const panelTaxonomy: readonly PanelContract[] = [
  {
    kind: "context-summary",
    purpose: "Restates the Active Context (gas day, product, hub, portfolio) the surface is working in.",
    owners: [],
    implementation: "absent",
    disclosures: ["as-of", "time-basis"],
    patterns: ["EXPLORE", "ANALYSE", "CONFIGURE", "REVIEW"],
  },
  {
    kind: "metric-strip",
    purpose: "A compact row of headline metrics for the current scope.",
    owners: ["clients/web/src/components/ui/MetricStrip.tsx"],
    implementation: "present",
    disclosures: ["as-of", "units", "time-basis"],
    patterns: ["MONITOR", "ANALYSE"],
  },
  {
    kind: "time-series",
    purpose: "A price, volume, exposure or PnL series over the active time basis.",
    owners: ["clients/web/src/components/strategy/StrategyLabCharts.tsx"],
    implementation: "partial",
    disclosures: ["as-of", "units", "time-basis", "provenance"],
    patterns: ["MONITOR", "ANALYSE", "COMPARE"],
  },
  {
    kind: "table",
    purpose: "Row-oriented working detail with right-aligned numerics and explicit units.",
    owners: [],
    implementation: "partial",
    disclosures: ["as-of", "units", "provenance"],
    patterns: ["MONITOR", "EXPLORE", "ANALYSE", "CONFIGURE", "REVIEW"],
  },
  {
    kind: "map",
    purpose: "Physical/commercial graph exploration: nodes, edges, capacity, routes and pool paths.",
    owners: ["clients/web/src/components/GasNetworkMap.tsx"],
    implementation: "present",
    disclosures: ["as-of", "provenance"],
    patterns: ["EXPLORE", "MONITOR"],
  },
  {
    kind: "assumptions",
    purpose: "The bounded inputs a deterministic run consumed, so the result can be reproduced.",
    owners: [],
    implementation: "absent",
    disclosures: ["assumption", "as-of", "time-basis"],
    patterns: ["CONFIGURE", "ANALYSE"],
  },
  {
    kind: "warnings",
    purpose: "Degraded, stale, blocked or incomplete state that qualifies the surface's values.",
    owners: [
      "clients/web/src/app/warningLabel.ts",
      "clients/web/src/components/ui/StatusBadge.tsx",
    ],
    implementation: "partial",
    disclosures: ["warning", "provenance"],
    patterns: ["MONITOR", "EXPLORE", "ANALYSE", "COMPARE", "CONFIGURE", "REVIEW"],
  },
  {
    kind: "evidence",
    purpose: "Provenance and lineage for a result or artifact: source, version, hash and rights state.",
    owners: [
      "clients/web/src/components/agents/AgentArtifactChain.tsx",
      "clients/web/src/components/agents/AgentReviewGate.tsx",
    ],
    implementation: "partial",
    disclosures: ["provenance", "entitlement", "as-of"],
    patterns: ["REVIEW", "ANALYSE"],
  },
  {
    kind: "run-result",
    purpose: "The outcome of a deterministic run: status, blockers, warnings and output references.",
    owners: [],
    implementation: "partial",
    disclosures: ["as-of", "correlation-id", "warning"],
    patterns: ["ANALYSE", "COMPARE", "MONITOR"],
  },
  {
    kind: "comparison",
    purpose: "Two or more alternatives, scenarios or routes side by side on one time basis.",
    owners: ["clients/web/src/components/strategy/StrategyCompareWorkspace.tsx"],
    implementation: "partial",
    disclosures: ["assumption", "as-of", "units"],
    patterns: ["COMPARE"],
  },
  {
    kind: "decision-history",
    purpose: "What was decided, by whom, when, and against which evidence - never execution approval.",
    owners: ["clients/web/src/components/agents/AgentReviewGate.tsx"],
    implementation: "partial",
    disclosures: ["provenance", "correlation-id"],
    patterns: ["REVIEW"],
  },
  {
    kind: "ai-explanation",
    purpose: "AI interpretation, comparison or challenge of deterministic results, with its own boundary visible.",
    owners: ["clients/web/src/components/agents/AgentArtifactChain.tsx"],
    implementation: "partial",
    disclosures: ["provenance", "entitlement"],
    patterns: ["REVIEW", "ANALYSE", "MONITOR"],
  },
];

const byKind = new Map<PanelKind, PanelContract>(
  panelTaxonomy.map((contract) => [contract.kind, contract]),
);

export function panelContract(kind: PanelKind): PanelContract {
  const contract = byKind.get(kind);
  if (!contract) throw new Error(`No panel contract declared for kind '${kind}'.`);
  return contract;
}

/**
 * Disclosures a panel composition owes for a pattern: the union of the
 * disclosures of the panels it uses. Wave 9 renders them; Wave 1 records them so a
 * surface cannot quietly ship a material number without its time basis.
 */
export function requiredDisclosures(panels: readonly PanelKind[]): DisclosureKind[] {
  const required = new Set<DisclosureKind>();
  for (const kind of panels) {
    for (const disclosure of panelContract(kind).disclosures) required.add(disclosure);
  }
  return DISCLOSURE_KINDS.filter((kind) => required.has(kind));
}

export function panelKindsForPattern(pattern: WorkspacePattern): PanelKind[] {
  return panelTaxonomy
    .filter((contract) => contract.patterns.includes(pattern))
    .map((contract) => contract.kind);
}

export function panelsWithSharedOwner(): PanelKind[] {
  return panelTaxonomy
    .filter((contract) => contract.owners.length > 0)
    .map((contract) => contract.kind);
}

export function unownedPanelKinds(): PanelKind[] {
  return panelTaxonomy
    .filter((contract) => contract.owners.length === 0)
    .map((contract) => contract.kind);
}

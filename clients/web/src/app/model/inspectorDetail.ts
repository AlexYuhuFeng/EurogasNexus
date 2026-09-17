/**
 * Canonical Inspector detail resolution (Architecture V2 Wave 9).
 *
 * Wave 1 fixed the Inspector *contract* (`experience/inspectorContract.ts`) and Wave 9
 * mounted the shell surfaces. This module is the missing middle: turning a subject
 * reference into the detail the Inspector shows.
 *
 * The rules it keeps:
 *
 * - it reads only what the calling identity already received, from the state the
 *   surfaces already hold: it never fetches, and it never resolves detail the
 *   backend withheld;
 * - it presents, it does not compute. Values are formatted for reading (a timestamp
 *   is rendered as a timestamp), and no field is derived, aggregated or restated as
 *   an authority;
 * - a kind this build cannot resolve says so, instead of rendering an empty panel
 *   that looks like "this object has no detail";
 * - a field the record does not carry is omitted rather than shown as a zero, and a
 *   field the record explicitly reports as absent is shown as absent.
 */

import type {
  IntradayOpportunityDTO,
  MarketQuoteDTO,
  MonitoringAlertDTO,
  NodeDTO,
  NormalizedMarketObsDTO,
  PortfolioResourceDTO,
  ResourcePoolOptionsDTO,
  RouteCandidateDTO,
  StrategyRunDTO,
  UpstreamContractDTO,
} from "@/api/client";
import { canOpenInspector, type InspectorSubject } from "../experience/inspectorContract.ts";
import type { InspectorSubjectKind } from "../experience/vocabulary.ts";
import { formatUtcTimestamp } from "./evidencePresentation.ts";

/** The state the Inspector may read detail from. The api store satisfies it. */
export interface InspectorDetailSource {
  readonly nodes: readonly NodeDTO[];
  readonly marketQuotes: readonly MarketQuoteDTO[];
  readonly normalizedMarkets: readonly NormalizedMarketObsDTO[];
  readonly monitoringAlerts: readonly MonitoringAlertDTO[];
  readonly intradayOpportunities: readonly IntradayOpportunityDTO[];
  readonly upstreamContracts: readonly UpstreamContractDTO[];
  readonly routeCandidates: readonly RouteCandidateDTO[];
  readonly resourcePoolOptions: ResourcePoolOptionsDTO | null;
  readonly strategyRuns: readonly StrategyRunDTO[];
}

export interface InspectorFact {
  readonly labelKey: string;
  readonly value: string;
}

export interface InspectorDetail {
  /** Whether this build can resolve detail for the subject's kind. */
  readonly resolved: boolean;
  /** The subject's display label, when the record carries a better one than the ref. */
  readonly label: string | null;
  readonly facts: readonly InspectorFact[];
  /** Provenance and evidence references the record names, in the order it names them. */
  readonly evidenceRefs: readonly string[];
}

const UNRESOLVED: InspectorDetail = { resolved: false, label: null, facts: [], evidenceRefs: [] };

interface FieldSpec {
  readonly field: string;
  readonly labelKey: string;
  readonly format?: "timestamp" | "quantity";
}

interface Candidate {
  readonly rows: readonly unknown[];
}

function asRecord(row: unknown): Record<string, unknown> {
  return row as Record<string, unknown>;
}

function stringField(record: Record<string, unknown>, field: string): string | null {
  const value = record[field];
  return typeof value === "string" && value.length > 0 ? value : null;
}

/** Records the Inspector may look a ref up in, per subject kind. */
function candidatesFor(
  kind: InspectorSubjectKind,
  source: InspectorDetailSource,
  ref: string,
): Candidate[] {
  const byId = (rows: readonly unknown[], field: string): Candidate | null => {
    const match = rows.find((row) => asRecord(row)[field] === ref);
    return match ? { rows: [match] } : null;
  };
  const collect = (items: Array<Candidate | null>): Candidate[] =>
    items.filter((item): item is Candidate => item !== null);

  switch (kind) {
    case "market-observation":
      return collect([
        byId(source.marketQuotes, "quote_id"),
        byId(source.normalizedMarkets, "observation_id"),
        byId(source.monitoringAlerts, "alert_id"),
        byId(source.intradayOpportunities, "opportunity_id"),
      ]);
    case "contract":
      return collect([byId(source.upstreamContracts, "contract_id")]);
    case "route":
      return collect([byId(source.routeCandidates, "route_id")]);
    case "resource":
      return collect([
        byId(source.resourcePoolOptions?.portfolio_resources ?? [], "resource_id"),
      ]);
    case "strategy-run":
      return collect([byId(source.strategyRuns, "run_id")]);
    case "network-node":
      return collect([byId(source.nodes, "id")]);
    default:
      return [];
  }
}

const QUOTE_FIELDS: readonly FieldSpec[] = [
  { field: "hub", labelKey: "experience.inspector.fact.hub" },
  { field: "product", labelKey: "experience.inspector.fact.product" },
  { field: "venue", labelKey: "experience.inspector.fact.venue" },
  { field: "bid_price", labelKey: "experience.inspector.fact.bid" },
  { field: "ask_price", labelKey: "experience.inspector.fact.ask" },
  { field: "last_price", labelKey: "experience.inspector.fact.last" },
  { field: "unit", labelKey: "experience.inspector.fact.unit" },
  { field: "observed_at_utc", labelKey: "experience.inspector.fact.observed_at", format: "timestamp" },
  { field: "source_system", labelKey: "experience.inspector.fact.source" },
  { field: "source_reference", labelKey: "experience.inspector.fact.source_reference" },
  { field: "freshness", labelKey: "experience.inspector.fact.freshness" },
  { field: "quality_score", labelKey: "experience.inspector.fact.quality" },
  { field: "simulated", labelKey: "experience.inspector.fact.simulated" },
];

const OBSERVATION_FIELDS: readonly FieldSpec[] = [
  { field: "hub", labelKey: "experience.inspector.fact.hub" },
  { field: "market_venue", labelKey: "experience.inspector.fact.venue" },
  { field: "tenor", labelKey: "experience.inspector.fact.tenor" },
  { field: "price", labelKey: "experience.inspector.fact.price" },
  { field: "price_gbp_mwh", labelKey: "experience.inspector.fact.price_gbp" },
  { field: "unit", labelKey: "experience.inspector.fact.unit" },
  { field: "period_start_utc", labelKey: "experience.inspector.fact.period_start", format: "timestamp" },
  { field: "period_end_utc", labelKey: "experience.inspector.fact.period_end", format: "timestamp" },
  { field: "observed_at_utc", labelKey: "experience.inspector.fact.observed_at", format: "timestamp" },
  { field: "source_system", labelKey: "experience.inspector.fact.source" },
  { field: "freshness", labelKey: "experience.inspector.fact.freshness" },
  { field: "quality_score", labelKey: "experience.inspector.fact.quality" },
];

const ALERT_FIELDS: readonly FieldSpec[] = [
  { field: "severity", labelKey: "experience.inspector.fact.severity" },
  { field: "status", labelKey: "experience.inspector.fact.status" },
  { field: "category", labelKey: "experience.inspector.fact.category" },
  { field: "alert_type", labelKey: "experience.inspector.fact.alert_type" },
  { field: "entity_type", labelKey: "experience.inspector.fact.entity_type" },
  { field: "entity_id", labelKey: "experience.inspector.fact.entity_ref" },
  { field: "occurrence_count", labelKey: "experience.inspector.fact.occurrences" },
  { field: "event_time_utc", labelKey: "experience.inspector.fact.event_time", format: "timestamp" },
  { field: "detected_at_utc", labelKey: "experience.inspector.fact.detected_at", format: "timestamp" },
  { field: "llm_status", labelKey: "experience.inspector.fact.ai_status" },
];

const OPPORTUNITY_FIELDS: readonly FieldSpec[] = [
  { field: "opportunity_type", labelKey: "experience.inspector.fact.opportunity_type" },
  { field: "status", labelKey: "experience.inspector.fact.status" },
  { field: "buy_hub", labelKey: "experience.inspector.fact.buy_hub" },
  { field: "sell_hub", labelKey: "experience.inspector.fact.sell_hub" },
  { field: "product", labelKey: "experience.inspector.fact.product" },
  { field: "gross_spread", labelKey: "experience.inspector.fact.gross_spread" },
  { field: "trading_cost", labelKey: "experience.inspector.fact.trading_cost" },
  { field: "net_margin", labelKey: "experience.inspector.fact.net_margin" },
  { field: "detected_at_utc", labelKey: "experience.inspector.fact.detected_at", format: "timestamp" },
  { field: "valid_until_utc", labelKey: "experience.inspector.fact.valid_until", format: "timestamp" },
  { field: "quote_age_seconds", labelKey: "experience.inspector.fact.quote_age" },
  { field: "confidence_score", labelKey: "experience.inspector.fact.confidence" },
];

const CONTRACT_FIELDS: readonly FieldSpec[] = [
  { field: "resource_type", labelKey: "experience.inspector.fact.resource_type" },
  { field: "delivery_point_name", labelKey: "experience.inspector.fact.delivery_point" },
  { field: "gas_year", labelKey: "experience.inspector.fact.gas_year" },
  { field: "delivery_quantity_mwh_per_day", labelKey: "experience.inspector.fact.delivery_quantity" },
  { field: "contract_price_gbp_mwh", labelKey: "experience.inspector.fact.contract_price" },
  { field: "variable_cost_gbp_mwh", labelKey: "experience.inspector.fact.variable_cost" },
  { field: "settlement_frequency", labelKey: "experience.inspector.fact.settlement_frequency" },
  { field: "allowed_exit_points", labelKey: "experience.inspector.fact.allowed_exit_points" },
  { field: "eligible_sale_modes", labelKey: "experience.inspector.fact.eligible_sale_modes" },
  { field: "updated_at_utc", labelKey: "experience.inspector.fact.updated_at", format: "timestamp" },
];

const ROUTE_FIELDS: readonly FieldSpec[] = [
  { field: "start_point_name", labelKey: "experience.inspector.fact.start_point" },
  { field: "target_point_name", labelKey: "experience.inspector.fact.target_point" },
  { field: "business_model", labelKey: "experience.inspector.fact.business_model" },
  { field: "required_entry_point_name", labelKey: "experience.inspector.fact.required_entry" },
  { field: "required_exit_point_name", labelKey: "experience.inspector.fact.required_exit" },
  { field: "required_tso_access", labelKey: "experience.inspector.fact.required_tso_access" },
  { field: "source_systems", labelKey: "experience.inspector.fact.source" },
];

const RESOURCE_FIELDS: readonly FieldSpec[] = [
  { field: "resource_type", labelKey: "experience.inspector.fact.resource_type" },
  { field: "delivery_mode", labelKey: "experience.inspector.fact.delivery_mode" },
  { field: "location_point_name", labelKey: "experience.inspector.fact.location" },
  { field: "available_quantity_mwh_per_day", labelKey: "experience.inspector.fact.available_quantity" },
  { field: "contract_cost_gbp_mwh", labelKey: "experience.inspector.fact.contract_cost" },
  { field: "variable_cost_gbp_mwh", labelKey: "experience.inspector.fact.variable_cost" },
  { field: "accessible_tsos", labelKey: "experience.inspector.fact.accessible_tsos" },
];

const STRATEGY_RUN_FIELDS: readonly FieldSpec[] = [
  { field: "strategy_id", labelKey: "experience.inspector.fact.strategy" },
  { field: "strategy_version_id", labelKey: "experience.inspector.fact.strategy_version" },
  { field: "run_type", labelKey: "experience.inspector.fact.run_type" },
  { field: "run_mode", labelKey: "experience.inspector.fact.run_mode" },
  { field: "status", labelKey: "experience.inspector.fact.status" },
  { field: "started_at_utc", labelKey: "experience.inspector.fact.started_at", format: "timestamp" },
  { field: "finished_at_utc", labelKey: "experience.inspector.fact.finished_at", format: "timestamp" },
  { field: "data_cutoff_utc", labelKey: "experience.inspector.fact.data_cutoff", format: "timestamp" },
  { field: "dataset_snapshot_id", labelKey: "experience.inspector.fact.dataset_snapshot" },
  { field: "manifest_hash", labelKey: "experience.inspector.fact.manifest_hash" },
];

const NODE_FIELDS: readonly FieldSpec[] = [
  { field: "node_type", labelKey: "experience.inspector.fact.node_type" },
  { field: "country", labelKey: "experience.inspector.fact.country" },
  { field: "capacity_boe_d", labelKey: "experience.inspector.fact.capacity" },
  { field: "source_system", labelKey: "experience.inspector.fact.source" },
  { field: "source_dataset", labelKey: "experience.inspector.fact.source_dataset" },
  { field: "data_quality", labelKey: "experience.inspector.fact.data_quality" },
];

/**
 * Field specs per kind. A kind with several record shapes (an alert reads as an
 * alert, a quote as a quote) declares its specs per recognised shape, keyed by the
 * id field the record carries.
 */
const FIELDS_BY_ID_FIELD: Readonly<Record<string, readonly FieldSpec[]>> = {
  quote_id: QUOTE_FIELDS,
  observation_id: OBSERVATION_FIELDS,
  alert_id: ALERT_FIELDS,
  opportunity_id: OPPORTUNITY_FIELDS,
  contract_id: CONTRACT_FIELDS,
  route_id: ROUTE_FIELDS,
  resource_id: RESOURCE_FIELDS,
  run_id: STRATEGY_RUN_FIELDS,
  id: NODE_FIELDS,
};

/** The ref fields a kind is looked up by, in the order the resolver tries them. */
const ID_FIELDS_BY_KIND: Partial<Record<InspectorSubjectKind, readonly string[]>> = {
  "market-observation": ["quote_id", "observation_id", "alert_id", "opportunity_id"],
  contract: ["contract_id"],
  route: ["route_id"],
  resource: ["resource_id"],
  "strategy-run": ["run_id"],
  "network-node": ["id"],
};

/**
 * The record's own name for the object, when it carries one. These are proper nouns
 * the backend supplies (a hub, a venue, a contract name), not product copy, so the
 * Inspector shows them as data rather than inventing a translated label.
 */
const LABEL_BY_ID_FIELD: Readonly<
  Record<string, (record: Record<string, unknown>) => string | null>
> = {
  quote_id: (record) => joinParts([stringField(record, "hub"), stringField(record, "product")]),
  observation_id: (record) =>
    joinParts([stringField(record, "hub"), stringField(record, "tenor")]),
  alert_id: (record) =>
    joinParts([stringField(record, "category"), stringField(record, "alert_type")]),
  opportunity_id: (record) => stringField(record, "route_name"),
  contract_id: (record) => stringField(record, "contract_name"),
  route_id: (record) => stringField(record, "route_name"),
  resource_id: (record) => stringField(record, "resource_name"),
  run_id: (record) => stringField(record, "strategy_name") ?? stringField(record, "strategy_id"),
  id: (record) => stringField(record, "name"),
};

function joinParts(parts: Array<string | null>): string | null {
  const present = parts.filter((part): part is string => part !== null);
  return present.length > 0 ? present.join(" · ") : null;
}

/** The evidence/provenance fields a record names, in presentation order. */
const EVIDENCE_FIELDS = [
  "source_reference",
  "source_refs",
  "source_systems",
  "source_system",
  "evidence_refs",
  "required_tso_access",
] as const;

function formatValue(value: unknown, format: FieldSpec["format"]): string | null {
  if (value === null || value === undefined || value === "") return null;
  if (Array.isArray(value)) {
    return value.length === 0 ? null : value.map((item) => String(item)).join(", ");
  }
  if (typeof value === "boolean") return String(value);
  if (typeof value === "number") return Number.isFinite(value) ? String(value) : null;
  if (typeof value === "string") {
    return format === "timestamp" ? formatUtcTimestamp(value, value) : value;
  }
  return null;
}

function evidenceRefs(record: Record<string, unknown>): string[] {
  const refs: string[] = [];
  for (const field of EVIDENCE_FIELDS) {
    const value = record[field];
    const values = Array.isArray(value) ? value : [value];
    for (const item of values) {
      if (typeof item === "string" && item.length > 0 && !refs.includes(item)) refs.push(item);
    }
  }
  return refs;
}

/**
 * Resolve the detail the Inspector shows for a subject from state the surface
 * already holds.
 *
 * Returns an explicitly unresolved detail when the kind has no resolver in this
 * build, when the ref is not in the loaded data, or when the subject is not a legal
 * hand-over for its origin page. An unresolved subject still renders its reference:
 * the Inspector says it cannot show the detail, rather than implying there is none.
 */
export function inspectorDetailFor(
  source: InspectorDetailSource | null | undefined,
  subject: InspectorSubject | null | undefined,
): InspectorDetail {
  if (!subject || !source) return UNRESOLVED;
  if (!canOpenInspector(subject.kind, subject.originPage)) return UNRESOLVED;
  const idFields = ID_FIELDS_BY_KIND[subject.kind];
  if (!idFields) return UNRESOLVED;

  for (const candidate of candidatesFor(subject.kind, source, subject.ref)) {
    const record = asRecord(candidate.rows[0]);
    const idField = idFields.find((field) => record[field] === subject.ref);
    if (!idField) continue;
    const specs = FIELDS_BY_ID_FIELD[idField] ?? [];
    const facts: InspectorFact[] = [];
    for (const spec of specs) {
      const value = formatValue(record[spec.field], spec.format);
      if (value !== null) facts.push({ labelKey: spec.labelKey, value });
    }
    const label = LABEL_BY_ID_FIELD[idField]?.(record) ?? null;
    return { resolved: true, label, facts, evidenceRefs: evidenceRefs(record) };
  }
  return UNRESOLVED;
}

/** The subject kinds this build can resolve detail for. Used by tests and docs. */
export function resolvableInspectorKinds(): InspectorSubjectKind[] {
  return Object.keys(ID_FIELDS_BY_KIND) as InspectorSubjectKind[];
}

/**
 * Build a subject for a hand-over, or `null` when the page may not hand that kind over.
 *
 * Every surface uses this rather than constructing a subject literal, so the Wave 1
 * composition rule (a page may only inspect the subject kinds it declares) is enforced
 * at the hand-over itself and not only inside the resolver.
 */
export function inspectorSubjectFor(
  kind: InspectorSubjectKind,
  ref: string | null | undefined,
  label: string,
  originPage: InspectorSubject["originPage"],
): InspectorSubject | null {
  if (!ref) return null;
  if (!canOpenInspector(kind, originPage)) return null;
  return { kind, ref, label, originPage };
}

/**
 * Build a `market-observation` subject for a hub observation. Returns `null` when the
 * page may not hand that kind over, so a surface cannot promise detail it has no
 * contract for (the Wave 1 rule).
 */
export function marketObservationSubject(
  observation: { readonly observation_id?: string; readonly quote_id?: string } | null | undefined,
  originPage: InspectorSubject["originPage"],
  label: string,
): InspectorSubject | null {
  return inspectorSubjectFor(
    "market-observation",
    observation?.observation_id ?? observation?.quote_id ?? null,
    label,
    originPage,
  );
}

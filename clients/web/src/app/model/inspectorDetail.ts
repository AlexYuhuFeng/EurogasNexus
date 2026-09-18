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
  CapacityObsDTO,
  DataProductCatalogueDTO,
  IntradayOpportunityDTO,
  JobDTO,
  MarketQuoteDTO,
  MonitoringAlertDTO,
  NodeDTO,
  NormalizedMarketObsDTO,
  PortfolioResourceDTO,
  ResourcePoolOptionsDTO,
  ReviewContextProjectionDTO,
  RouteCandidateDTO,
  SourceSystemDTO,
  StrategyRunDTO,
  UpstreamContractDTO,
} from "@/api/client";
import { canOpenInspector, type InspectorSubject } from "../experience/inspectorContract.ts";
import type { InspectorSubjectKind } from "../experience/vocabulary.ts";
import { reviewEvidence } from "./reviewContextModel.ts";
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
  /** Capacity observations, for a selected network point. */
  readonly capacity?: readonly CapacityObsDTO[];
  /** The review projection, for evidence a review decision was taken on. */
  readonly reviewContext?: ReviewContextProjectionDTO | null;
  /** The activity timeline's most recent job rows, for a tracked operation. */
  readonly jobs?: readonly JobDTO[];
  /** The source registry, for a provider connection's posture. */
  readonly sources?: readonly SourceSystemDTO[];
  /** The Data Product catalogue the research surface read, for a catalogue entry. */
  readonly dataProducts?: DataProductCatalogueDTO | null;
}

export interface InspectorFact {
  readonly labelKey: string;
  /**
   * A record's own field name, when the fact comes from a resolver-specific artifact.
   * Data keys are shown as they are rather than given invented product copy.
   */
  readonly label?: string;
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
    case "capacity":
      return collect([byId(source.capacity ?? [], "observation_id")]);
    case "job":
      return collect([byId(source.jobs ?? [], "job_id")]);
    case "provider-connection":
      return collect([byId(source.sources ?? [], "source_id")]);
    case "data-product":
      return collect([byId(source.dataProducts?.products ?? [], "product_id")]);
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

const CAPACITY_FIELDS: readonly FieldSpec[] = [
  { field: "point_id", labelKey: "experience.inspector.fact.point_ref" },
  { field: "direction", labelKey: "experience.inspector.fact.direction" },
  { field: "capacity_type", labelKey: "experience.inspector.fact.capacity_type" },
  { field: "capacity_mcm_d", labelKey: "experience.inspector.fact.capacity_mcm" },
  { field: "original_value", labelKey: "experience.inspector.fact.original_value" },
  { field: "original_unit", labelKey: "experience.inspector.fact.original_unit" },
  { field: "period_start_utc", labelKey: "experience.inspector.fact.period_start", format: "timestamp" },
  { field: "period_end_utc", labelKey: "experience.inspector.fact.period_end", format: "timestamp" },
  { field: "observed_at_utc", labelKey: "experience.inspector.fact.observed_at", format: "timestamp" },
  { field: "source_system", labelKey: "experience.inspector.fact.source" },
  { field: "source_reference", labelKey: "experience.inspector.fact.source_reference" },
  { field: "freshness", labelKey: "experience.inspector.fact.freshness" },
];

/**
 * A tracked operation's own record.
 *
 * The job row is bookkeeping about work, so the Inspector shows what it records - the operation,
 * who it is attributed to, its scope, its progress and timings, the artefacts it names and the
 * failure code if it has one - and never the work's results, which live in their own records.
 */
const JOB_FIELDS: readonly FieldSpec[] = [
  { field: "kind", labelKey: "experience.inspector.fact.job_kind" },
  { field: "status", labelKey: "experience.inspector.fact.status" },
  { field: "principal", labelKey: "experience.inspector.fact.job_principal" },
  { field: "scope_refs", labelKey: "experience.inspector.fact.job_scope" },
  { field: "progress", labelKey: "experience.inspector.fact.job_progress" },
  { field: "created_at_utc", labelKey: "experience.inspector.fact.observed_at", format: "timestamp" },
  { field: "started_at_utc", labelKey: "experience.inspector.fact.started_at", format: "timestamp" },
  { field: "finished_at_utc", labelKey: "experience.inspector.fact.finished_at", format: "timestamp" },
  { field: "output_refs", labelKey: "experience.inspector.fact.job_outputs" },
  { field: "error_code", labelKey: "experience.inspector.fact.job_error" },
  { field: "correlation_id", labelKey: "experience.inspector.fact.job_correlation" },
  { field: "snapshot_id", labelKey: "experience.inspector.fact.job_snapshot" },
  { field: "input_hash", labelKey: "experience.inspector.fact.job_input_hash" },
  { field: "provenance", labelKey: "experience.inspector.fact.job_provenance" },
];

/**
 * A provider connection's own record.
 *
 * A source row is a connection, not commercial data: the Inspector shows its posture - the
 * provider, the entitlement scope, credential and connectivity state, certification stage,
 * freshness and the last run outcome - which is exactly what an operator asks about it. Record
 * counts are shown as the row reports them, including the preview-substitute pair, so a substitute
 * is never mistaken for live data.
 */
const PROVIDER_CONNECTION_FIELDS: readonly FieldSpec[] = [
  { field: "source_system", labelKey: "experience.inspector.fact.source" },
  { field: "category", labelKey: "experience.inspector.fact.provider_category" },
  { field: "entitlement_scope", labelKey: "experience.inspector.fact.entitlement_scope" },
  { field: "credential_state", labelKey: "experience.inspector.fact.credential_state" },
  { field: "credential_provider_id", labelKey: "experience.inspector.fact.credential_provider" },
  {
    field: "credential_last_tested_at_utc",
    labelKey: "experience.inspector.fact.credential_tested_at",
    format: "timestamp",
  },
  { field: "connectivity_status", labelKey: "experience.inspector.fact.connectivity" },
  { field: "freshness_state", labelKey: "experience.inspector.fact.freshness" },
  { field: "last_success_at_utc", labelKey: "experience.inspector.fact.last_success", format: "timestamp" },
  { field: "last_failure_at_utc", labelKey: "experience.inspector.fact.last_failure", format: "timestamp" },
  { field: "consecutive_failures", labelKey: "experience.inspector.fact.consecutive_failures" },
  { field: "circuit_state", labelKey: "experience.inspector.fact.circuit_state" },
  { field: "certification_stage", labelKey: "experience.inspector.fact.certification_stage" },
  { field: "certification_allows_live", labelKey: "experience.inspector.fact.certification_allows_live" },
  { field: "scheduler_enabled", labelKey: "experience.inspector.fact.scheduler_enabled" },
  { field: "next_run_at_utc", labelKey: "experience.inspector.fact.next_run", format: "timestamp" },
  { field: "live_record_count", labelKey: "experience.inspector.fact.live_records" },
  { field: "preview_substitute_record_count", labelKey: "experience.inspector.fact.preview_records" },
  { field: "last_ingestion_status", labelKey: "experience.inspector.fact.last_ingestion" },
];

/**
 * A Data Product catalogue entry's own record.
 *
 * The catalogue is the platform's declared read model, so the Inspector shows the declaration
 * rather than a measurement: what the product is, its time basis, the source families behind it
 * and this identity's entitlement verdict. A product whose provenance the backend withheld carries
 * no measurement here either - the row reports the entitlement reason instead of a zero.
 */
const DATA_PRODUCT_FIELDS: readonly FieldSpec[] = [
  { field: "business_name", labelKey: "experience.inspector.fact.business_name" },
  { field: "domain", labelKey: "experience.inspector.fact.domain" },
  { field: "availability.state", labelKey: "experience.inspector.fact.availability" },
  { field: "availability.note", labelKey: "experience.inspector.fact.availability_note" },
  { field: "time_basis.basis", labelKey: "experience.inspector.fact.time_basis" },
  { field: "time_basis.gas_day_calendar", labelKey: "experience.inspector.fact.gas_day_calendar" },
  { field: "source_families", labelKey: "experience.inspector.fact.source_families" },
  { field: "simulated_families", labelKey: "experience.inspector.fact.simulated_families" },
  { field: "entitlement.status", labelKey: "experience.inspector.fact.entitlement" },
  { field: "entitlement.reason", labelKey: "experience.inspector.fact.entitlement_reason" },
  { field: "provenance.freshness.status", labelKey: "experience.inspector.fact.freshness" },
  { field: "provenance.row_count", labelKey: "experience.inspector.fact.provenance_rows" },
  { field: "provenance.confidence", labelKey: "experience.inspector.fact.confidence" },
  {
    field: "provenance.as_of_utc",
    labelKey: "experience.inspector.fact.observed_at",
    format: "timestamp",
  },
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
  job_id: JOB_FIELDS,
  source_id: PROVIDER_CONNECTION_FIELDS,
  product_id: DATA_PRODUCT_FIELDS,
};

/**
 * Kinds whose record shape is chosen by the kind rather than by the id field it carries.
 *
 * A capacity observation and a market observation are both keyed by `observation_id` but
 * carry different fields, so the shape cannot be inferred from the key alone.
 */
const FIELDS_BY_KIND: Partial<Record<InspectorSubjectKind, readonly FieldSpec[]>> = {
  capacity: CAPACITY_FIELDS,
};

/** The ref fields a kind is looked up by, in the order the resolver tries them. */
const ID_FIELDS_BY_KIND: Partial<Record<InspectorSubjectKind, readonly string[]>> = {
  "market-observation": ["quote_id", "observation_id", "alert_id", "opportunity_id"],
  contract: ["contract_id"],
  route: ["route_id"],
  resource: ["resource_id"],
  "strategy-run": ["run_id"],
  "network-node": ["id"],
  capacity: ["observation_id"],
  job: ["job_id"],
  "provider-connection": ["source_id"],
  "data-product": ["product_id"],
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
    stringField(record, "point_name") ??
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

/**
 * Read one field out of a record, following a dotted path when the spec names one.
 *
 * Records the surfaces hold are mostly flat, but a catalogue entry nests its posture
 * (`availability.state`, `provenance.freshness.status`). Walking the path keeps the spec honest:
 * a field that does not resolve is omitted by the caller exactly like a flat one the record does
 * not carry, rather than being read as present and undefined.
 */
function fieldValue(record: Record<string, unknown>, path: string): unknown {
  if (!path.includes(".")) return record[path];
  let current: unknown = record;
  for (const segment of path.split(".")) {
    if (current === null || typeof current !== "object") return undefined;
    current = (current as Record<string, unknown>)[segment];
  }
  return current;
}

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
  // What a record produced is evidence of what it did: a tracked operation names its artefacts
  // here, and the Inspector links them rather than treating them as decoration.
  "output_refs",
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
  if (subject.kind === "decision-evidence") {
    return decisionEvidenceDetail(source, subject.ref);
  }
  const idFields = ID_FIELDS_BY_KIND[subject.kind];
  if (!idFields) return UNRESOLVED;

  for (const candidate of candidatesFor(subject.kind, source, subject.ref)) {
    const record = asRecord(candidate.rows[0]);
    const idField = idFields.find((field) => record[field] === subject.ref);
    if (!idField) continue;
    const specs = FIELDS_BY_KIND[subject.kind] ?? FIELDS_BY_ID_FIELD[idField] ?? [];
    const facts: InspectorFact[] = [];
    for (const spec of specs) {
      const value = formatValue(fieldValue(record, spec.field), spec.format);
      if (value !== null) facts.push({ labelKey: spec.labelKey, value });
    }
    const label = LABEL_BY_ID_FIELD[idField]?.(record) ?? null;
    return { resolved: true, label, facts, evidenceRefs: evidenceRefs(record) };
  }
  return UNRESOLVED;
}

/**
 * Resolve the evidence a review decision was taken on.
 *
 * The ref is the review entity the decision names, ``"<entity_type>:<entity_id>"`` - the
 * same pair the decision history renders. The detail comes from the review projection's
 * evidence slice, which is where the backend reports what it could and could not retrieve,
 * so an entry it could not resolve is shown as unavailable *with its reason* rather than as
 * an empty artifact.
 */
function decisionEvidenceDetail(
  source: InspectorDetailSource,
  ref: string,
): InspectorDetail {
  const separator = ref.indexOf(":");
  if (separator <= 0) return UNRESOLVED;
  const entityType = ref.slice(0, separator);
  const entityId = ref.slice(separator + 1);
  const entry = reviewEvidence(source.reviewContext).find(
    (item) => item.entity_type === entityType && item.entity_id === entityId,
  );
  if (!entry) return UNRESOLVED;

  const facts: InspectorFact[] = [
    { labelKey: "experience.inspector.fact.entity_type", value: entry.entity_type },
    { labelKey: "experience.inspector.fact.entity_ref", value: entry.entity_id },
    {
      labelKey: "experience.inspector.fact.evidence_state",
      value: entry.available
        ? "available"
        : (entry.unavailable_reason ?? "unavailable"),
    },
  ];
  if (entry.resolver) {
    facts.push({ labelKey: "experience.inspector.fact.evidence_resolver", value: entry.resolver });
  }
  // A resolver's artifact is its own shape, so its flat scalar fields are presented under
  // their own names: inventing product copy for data keys would misdescribe them.
  for (const [key, value] of Object.entries(entry.artifact ?? {}).slice(0, 8)) {
    const formatted = formatValue(value, undefined);
    if (formatted !== null) facts.push({ labelKey: key, label: key, value: formatted });
  }

  const artifactRefs = evidenceRefs(asRecord(entry.artifact ?? {}));
  return {
    resolved: true,
    label: `${entry.entity_type}: ${entry.entity_id}`,
    facts,
    evidenceRefs: entry.resolver ? [entry.resolver, ...artifactRefs] : artifactRefs,
  };
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

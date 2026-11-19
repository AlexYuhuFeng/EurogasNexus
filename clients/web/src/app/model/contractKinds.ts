/**
 * Contract kinds (docs/product/CONTRACT_TYPES.md): the type-first form's model.
 *
 * The person chooses the kind first (cards), then sees only that kind's terms, grouped as the
 * desk reads a contract: parties and master, quantity, delivery, price, flexibility, credit.
 * Parties, points, terminals, ports, masters and indices are chosen from records
 * (UX_REFERENCE rule 25); the server validates the terms (`domain/contracts/kinds.py`) and
 * derives the columns positions, credit and the evaluators read, so this module only shapes
 * the form and the request. Pure: no React, no fetch.
 */

export const CONTRACT_KINDS = [
  "SUPPLY_GSA",
  "UPSTREAM_TENDER",
  "LNG_MSPA",
  "LNG_CARGO",
] as const;
export type AuthorableKind = (typeof CONTRACT_KINDS)[number];
/** Kinds whose terms are typed (the rest use the supply-agreement editor). */
export const TYPED_KINDS: ReadonlySet<string> = new Set(["UPSTREAM_TENDER", "LNG_MSPA", "LNG_CARGO"]);

export type KindGroup = "parties" | "quantity" | "delivery" | "price" | "flexibility" | "credit";
export const KIND_GROUPS: readonly KindGroup[] = ["parties", "quantity", "delivery", "price", "flexibility", "credit"];

/** Where a picked value comes from (each a register the firm holds). */
export type PickerSource = "counterparty" | "point" | "terminal" | "port" | "master" | "hub" | "index";

export interface KindField {
  key: string;
  group: KindGroup;
  input: "text" | "number" | "date" | "month" | "choice" | "bool" | "multi" | "picker" | "pickers";
  /** For `choice`/`multi`: the closed options (labels are `contracts.kind_option.<value>`). */
  options?: readonly string[];
  picker?: PickerSource;
  /** Native unit shown beside a number. */
  unit?: string;
  /** The unit is another field's value (a quantity in the contract's own unit). */
  unitFrom?: string;
  required?: boolean;
  /** Shown only when the draft matches (another field's value). */
  when?: (draft: KindDraft) => boolean;
  /** A picker may also take a value entered by hand (named as such in the result). */
  manual?: boolean;
}

/** The form as typed: text for every input (a cleared field stays cleared), arrays for multi. */
export type KindDraft = Record<string, string | string[] | boolean>;

const PRICE_UNITS = ["GBp/th", "EUR/MWh", "GBP/MWh", "USD/MMBtu"] as const;
const isIndex = (draft: KindDraft) => draft.price_type === "index";
const isFixed = (draft: KindDraft) => draft.price_type === "fixed";
const isDes = (draft: KindDraft) => draft.delivery_term === "DES";
const formula = (...values: string[]) => (draft: KindDraft) => values.includes(String(draft.price_formula));

export const KIND_FIELDS: Record<Exclude<AuthorableKind, "SUPPLY_GSA">, readonly KindField[]> = {
  UPSTREAM_TENDER: [
    { key: "seller_name", group: "parties", input: "picker", picker: "counterparty", required: true, manual: true },
    { key: "field_name", group: "parties", input: "text" },
    { key: "tender_reference", group: "parties", input: "text" },
    { key: "quantity_unit", group: "quantity", input: "choice", options: ["th/d", "MWh/d", "kWh/h"], required: true },
    { key: "dcq", group: "quantity", input: "number", unitFrom: "quantity_unit", required: true },
    { key: "offtake_obligation_pct", group: "quantity", input: "number", unit: "%" },
    { key: "delivery_point", group: "delivery", input: "picker", picker: "point", required: true },
    { key: "period_start", group: "delivery", input: "date", required: true },
    { key: "period_end", group: "delivery", input: "date", required: true },
    { key: "nomination", group: "delivery", input: "choice", options: ["day_ahead", "within_day"], required: true },
    { key: "allowed_exit_points", group: "delivery", input: "pickers", picker: "point" },
    { key: "price_type", group: "price", input: "choice", options: ["index", "fixed"], required: true },
    { key: "index", group: "price", input: "picker", picker: "index", required: true, when: isIndex },
    { key: "differential", group: "price", input: "number", when: isIndex },
    { key: "fixed_price", group: "price", input: "number", required: true, when: isFixed },
    { key: "price_unit", group: "price", input: "choice", options: PRICE_UNITS, required: true },
    { key: "entry_cost_per_mwh", group: "price", input: "number" },
    { key: "min_dcq", group: "flexibility", input: "number", unitFrom: "quantity_unit", required: true },
    { key: "max_dcq", group: "flexibility", input: "number", unitFrom: "quantity_unit", required: true },
    { key: "field_outage_force_majeure", group: "flexibility", input: "bool" },
    { key: "payment_lag_days", group: "credit", input: "number", unit: "d", required: true },
    { key: "financing_rate_pct", group: "credit", input: "number", unit: "%", required: true },
  ],
  LNG_MSPA: [
    { key: "counterparty_name", group: "parties", input: "picker", picker: "counterparty", required: true, manual: true },
    { key: "our_side", group: "parties", input: "choice", options: ["buyer", "seller"], required: true },
    { key: "master_reference", group: "parties", input: "text" },
    { key: "signed_on", group: "parties", input: "date" },
    { key: "governing_law", group: "parties", input: "choice", options: ["English law", "New York law", "French law", "Dutch law", "German law"] },
    { key: "gcv_min_mj_m3", group: "quantity", input: "number", unit: "MJ/m³" },
    { key: "gcv_max_mj_m3", group: "quantity", input: "number", unit: "MJ/m³" },
    { key: "term_start", group: "delivery", input: "date", required: true },
    { key: "term_end", group: "delivery", input: "date" },
    { key: "delivery_terms", group: "delivery", input: "multi", options: ["FOB", "DES"], required: true },
    { key: "laytime_hours", group: "delivery", input: "number", unit: "h" },
    { key: "demurrage_usd_per_day", group: "delivery", input: "number", unit: "USD/d" },
    { key: "diversion_allowed", group: "flexibility", input: "bool" },
    { key: "credit_support", group: "credit", input: "choice", options: ["none", "parent_guarantee", "letter_of_credit", "cash"], required: true },
    { key: "credit_support_amount", group: "credit", input: "number", when: (draft) => draft.credit_support !== "none" },
    { key: "credit_support_currency", group: "credit", input: "choice", options: ["USD", "EUR", "GBP"], when: (draft) => draft.credit_support !== "none" },
    { key: "payment_lag_days", group: "credit", input: "number", unit: "d", required: true },
  ],
  LNG_CARGO: [
    { key: "master_contract_id", group: "parties", input: "picker", picker: "master", required: true },
    { key: "cargo_reference", group: "parties", input: "text" },
    { key: "quantity_mmbtu", group: "quantity", input: "number", unit: "MMBtu", required: true },
    { key: "tolerance_pct", group: "quantity", input: "number", unit: "%", required: true },
    { key: "delivery_term", group: "delivery", input: "choice", options: ["DES", "FOB"], required: true },
    { key: "load_port", group: "delivery", input: "picker", picker: "port", manual: true, required: true, when: (draft) => !isDes(draft) },
    { key: "discharge_terminal", group: "delivery", input: "picker", picker: "terminal", required: true, manual: true, when: isDes },
    { key: "terminal_hub", group: "delivery", input: "picker", picker: "hub", required: true, when: isDes },
    { key: "window_start", group: "delivery", input: "date", required: true },
    { key: "window_end", group: "delivery", input: "date", required: true },
    { key: "narrowed_start", group: "delivery", input: "date" },
    { key: "narrowed_end", group: "delivery", input: "date" },
    { key: "vessel_name", group: "delivery", input: "text" },
    { key: "price_formula", group: "price", input: "choice", options: ["hh", "brent", "hub", "fixed"], required: true },
    { key: "slope", group: "price", input: "number", required: true, when: formula("hh", "brent") },
    { key: "hub_index", group: "price", input: "picker", picker: "index", required: true, when: formula("hub") },
    { key: "constant", group: "price", input: "number", required: true, when: formula("hh", "brent", "hub") },
    { key: "fixed_price", group: "price", input: "number", required: true, when: formula("fixed") },
    { key: "price_unit", group: "price", input: "choice", options: PRICE_UNITS, required: true },
    { key: "pricing_month", group: "price", input: "month", required: true },
    { key: "boil_off_pct_per_day", group: "flexibility", input: "number", unit: "%/d" },
  ],
};

/** Fields the form shows for a draft (a field whose condition is not met is hidden). */
export function visibleFields(kind: AuthorableKind, draft: KindDraft): KindField[] {
  if (kind === "SUPPLY_GSA") return [];
  return KIND_FIELDS[kind].filter((field) => !field.when || field.when(draft));
}

/** The entry template of a new contract: desk conventions only, never a fact of the deal. */
export function newKindDraft(kind: AuthorableKind): KindDraft {
  switch (kind) {
    case "UPSTREAM_TENDER":
      // An NBP tender is written in therms per day and pence per therm.
      return { nomination: "day_ahead", price_type: "index", price_unit: "GBp/th", quantity_unit: "th/d", differential: "0", payment_lag_days: "20", field_outage_force_majeure: true, allowed_exit_points: [] };
    case "LNG_MSPA":
      return { our_side: "buyer", delivery_terms: ["DES"], credit_support: "none", payment_lag_days: "20", diversion_allowed: false };
    case "LNG_CARGO":
      return { delivery_term: "DES", price_formula: "hh", price_unit: "USD/MMBtu", tolerance_pct: "5" };
    default:
      return {};
  }
}

const NUMBER_KEYS = new Set(
  Object.values(KIND_FIELDS).flatMap((fields) => fields.filter((field) => field.input === "number").map((field) => field.key)),
);
const INTEGER_KEYS = new Set(["payment_lag_days"]);

function text(value: unknown): string {
  return typeof value === "string" ? value.trim() : "";
}

export interface KindTermsResult {
  terms: Record<string, unknown> | null;
  /** Keys of required fields that are empty or not numbers (`contracts.kind_field.<key>`). */
  missing: string[];
}

/**
 * The typed terms the write sends, from the draft; `missing` names what blocks a save. The
 * server validates the rest (ranges, swing order, windows) and says what is wrong in words.
 */
export function kindTermsFromDraft(kind: AuthorableKind, draft: KindDraft): KindTermsResult {
  if (kind === "SUPPLY_GSA") return { terms: null, missing: [] };
  const fields = visibleFields(kind, draft);
  const missing: string[] = [];
  const terms: Record<string, unknown> = {
    schema: kind === "UPSTREAM_TENDER" ? "upstream-tender/v2" : kind === "LNG_MSPA" ? "lng-mspa/v1" : "lng-cargo/v1",
  };
  for (const field of fields) {
    if (field.key === "master_contract_id") {
      if (!text(draft[field.key])) missing.push(field.key);
      continue;
    }
    const raw = draft[field.key];
    if (field.input === "bool") {
      terms[field.key] = raw === true;
      continue;
    }
    if (field.input === "multi" || field.input === "pickers") {
      const values = Array.isArray(raw) ? raw : [];
      if (field.required && values.length === 0) missing.push(field.key);
      terms[field.key] = values;
      continue;
    }
    const value = text(raw);
    if (!value) {
      if (field.required) missing.push(field.key);
      continue;
    }
    if (NUMBER_KEYS.has(field.key)) {
      const number = Number(value);
      if (!Number.isFinite(number)) {
        missing.push(field.key);
        continue;
      }
      terms[field.key] = INTEGER_KEYS.has(field.key) ? Math.round(number) : number;
      continue;
    }
    terms[field.key] = value;
  }
  // The credit line a picked counterparty has (a name typed by hand has none).
  if (kind !== "LNG_CARGO" && text(draft.counterparty_id)) terms.counterparty_id = text(draft.counterparty_id);
  return { terms: missing.length ? null : terms, missing };
}

/** A stored contract's terms back into the form (numbers as text). */
export function draftFromTerms(kind: AuthorableKind, terms: Record<string, unknown> | null | undefined, masterId?: string | null): KindDraft {
  const draft: KindDraft = newKindDraft(kind);
  if (kind === "SUPPLY_GSA" || !terms) return draft;
  if (terms.schema === "upstream-tender/v1") {
    // A tender stored before quantities were written in their own unit: MWh/d.
    terms = {
      ...terms,
      quantity_unit: "MWh/d",
      dcq: terms.dcq_mwh_per_day,
      min_dcq: terms.min_dcq_mwh_per_day,
      max_dcq: terms.max_dcq_mwh_per_day,
    };
  }
  for (const field of KIND_FIELDS[kind]) {
    const value = terms[field.key];
    if (value === null || value === undefined) continue;
    if (field.input === "bool") draft[field.key] = value === true;
    else if (Array.isArray(value)) draft[field.key] = value.map(String);
    else draft[field.key] = String(value);
  }
  if (typeof terms.counterparty_id === "string") draft.counterparty_id = terms.counterparty_id;
  if (masterId) draft.master_contract_id = masterId;
  return draft;
}

/** Fields of a PDF intake's partial proposal that this kind holds (the rest stay in the table). */
export function draftWithProposal(kind: AuthorableKind, draft: KindDraft, proposal: Record<string, unknown> | null | undefined): KindDraft {
  if (kind === "SUPPLY_GSA" || !proposal) return draft;
  const known = new Set(KIND_FIELDS[kind].map((field) => field.key));
  const next = { ...draft };
  for (const [key, value] of Object.entries(proposal)) {
    if (!known.has(key) || value === null || value === undefined) continue;
    next[key] = Array.isArray(value) ? value.map(String) : typeof value === "boolean" ? value : String(value);
  }
  return next;
}

/** One-line headline of a stored contract for the list: the figure that matters for its kind. */
export interface KindHeadline {
  key: "swing" | "cargo" | "master" | "dcq";
  text: string;
}

interface StoredLike {
  contract_id: string;
  contract_kind?: string;
  delivery_point_name?: string;
  delivery_quantity_mwh_per_day: number;
  headline?: { key: string; value: number; min?: number; max?: number; unit: string; term?: string; window?: string[] } | null;
}

function figure(value: number, digits = 0): string {
  return value.toLocaleString("en-GB", { maximumFractionDigits: digits, minimumFractionDigits: digits });
}

export function kindHeadline(contract: StoredLike, all: readonly StoredLike[] = [], masterOf: (id: string) => string | null = () => null): KindHeadline {
  const head = contract.headline;
  if (contract.contract_kind === "UPSTREAM_TENDER" && head) {
    return { key: "swing", text: `${figure(head.value)} MWh/d (${figure(head.min ?? 0)}–${figure(head.max ?? 0)})` };
  }
  if (contract.contract_kind === "LNG_CARGO" && head) {
    return { key: "cargo", text: `${head.term ?? ""} ${figure(head.value, 2)} TBtu`.trim() };
  }
  if (contract.contract_kind === "LNG_MSPA") {
    const count = all.filter((item) => item.contract_kind === "LNG_CARGO" && masterOf(item.contract_id) === contract.contract_id).length;
    return { key: "master", text: String(count) };
  }
  if (head && head.key === "dcq") return { key: "dcq", text: `${figure(head.value)} ${head.unit}` };
  // An NBP contract reads in therms per day (exact unit factor from the recorded MWh/d).
  if (/\bNBP\b/i.test(contract.delivery_point_name ?? "")) {
    return { key: "dcq", text: `${figure(contract.delivery_quantity_mwh_per_day / MWH_PER_THERM)} th/d` };
  }
  return { key: "dcq", text: `${figure(contract.delivery_quantity_mwh_per_day)} MWh/d` };
}

/** One therm in MWh (100,000 BTU of 1,055.05585262 J: the units authority's factor). */
export const MWH_PER_THERM = (100_000 * 1055.05585262) / 3.6e9;

/** The request the governed write takes for a typed kind (base columns are derived there). */
export function typedContractBody(input: {
  contractId: string;
  contractName: string;
  kind: AuthorableKind;
  terms: Record<string, unknown>;
  masterId?: string | null;
  unmodelled: string;
  notes?: string | null;
  editToken?: string | null;
}): Record<string, unknown> {
  return {
    contract_id: input.contractId,
    contract_name: input.contractName.trim(),
    contract_kind: input.kind,
    kind_terms: input.terms,
    master_contract_id: input.masterId || null,
    unmodelled_terms: input.unmodelled.trim() || null,
    notes: input.notes ?? null,
    expected_edit_token: input.editToken ?? null,
  };
}

/** Where a contract stands today: the list sorts in this order (in execution first). */
export type ContractStatus = "in_execution" | "upcoming" | "expired" | "retired";
export const STATUS_ORDER: readonly ContractStatus[] = ["in_execution", "upcoming", "expired", "retired"];

/**
 * A contract's period from its stored label: a gas year (`2026/27`, `GY-26`, `2026`), an
 * open-ended one (`2025+`) or a typed contract's months (`2026-12..2027-02`). `end` is null
 * for an open-ended contract; null altogether when the label is not understood.
 */
export function contractPeriod(label: string): { start: string; end: string | null } | null {
  const text = (label || "").trim();
  const months = /^(\d{4})-(\d{2})\.\.(\d{4})-(\d{2})$/.exec(text);
  if (months) {
    const endYear = Number(months[3]);
    const endMonth = Number(months[4]);
    const lastDay = new Date(Date.UTC(endYear, endMonth, 0)).getUTCDate();
    return { start: `${months[1]}-${months[2]}-01`, end: `${months[3]}-${months[4]}-${String(lastDay).padStart(2, "0")}` };
  }
  const year = /(\d{4})|GY-?(\d{2})/i.exec(text);
  if (!year) return null;
  const first = year[1] ? Number(year[1]) : 2000 + Number(year[2]);
  return { start: `${first}-10-01`, end: text.endsWith("+") ? null : `${first + 1}-09-30` };
}

export function contractStatus(
  contract: { gas_year: string; retired_at_utc?: string | null },
  today: string,
): ContractStatus {
  if (contract.retired_at_utc) return "retired";
  const period = contractPeriod(contract.gas_year);
  if (!period) return "in_execution";
  if (period.end && period.end < today) return "expired";
  if (period.start > today) return "upcoming";
  return "in_execution";
}

/** The period as the desk writes it: `Dec-26 – Feb-27`, `GY 2026/27`, `from Oct-25`. */
export function periodText(label: string, monthName: (iso: string) => string): string {
  const period = contractPeriod(label);
  if (!period) return label;
  if (/^\d{4}\/\d{2}$/.test(label.trim())) return `GY ${label.trim()}`;
  return period.end ? `${monthName(period.start)} – ${monthName(period.end)}` : `${monthName(period.start)} →`;
}

interface Listable {
  contract_id: string;
  contract_name: string;
  contract_kind?: string;
  gas_year: string;
  delivery_point_name: string;
  retired_at_utc?: string | null;
  notes?: string | null;
}

/** The list's search: name, counterparty, point and kind; the type filter; in-execution first. */
export function listedContracts<T extends Listable>(
  contracts: readonly T[],
  input: { query: string; kind: string; today: string; counterpartyOf: (row: T) => string },
): T[] {
  const query = input.query.trim().toLowerCase();
  return contracts
    .filter((row) => !input.kind || (row.contract_kind ?? "SUPPLY_GSA") === input.kind)
    .filter((row) => !query || [row.contract_name, row.delivery_point_name, input.counterpartyOf(row), row.contract_id]
      .some((value) => value.toLowerCase().includes(query)))
    .map((row) => ({ row, status: STATUS_ORDER.indexOf(contractStatus(row, input.today)) }))
    .sort((a, b) => a.status - b.status || a.row.contract_name.localeCompare(b.row.contract_name))
    .map((item) => item.row)
    .reduce<T[]>((out, row, _index, all) => {
      // The hierarchy is visible in the list: each confirmation sits under its master (when the
      // master is listed), in the master's place, whatever the confirmation's own status.
      const master = (row as Listable & { master_contract_id?: string | null }).master_contract_id;
      if (master && all.some((item) => item.contract_id === master)) return out;
      out.push(row);
      for (const child of all) {
        if ((child as Listable & { master_contract_id?: string | null }).master_contract_id === row.contract_id) out.push(child);
      }
      return out;
    }, []);
}

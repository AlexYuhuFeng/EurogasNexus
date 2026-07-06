import type { ContractDraft } from "./defaultContractDraft";

export function stringFromRecord(record: Record<string, unknown>, key: string, fallback: string): string {
  const value = record[key];
  return typeof value === "string" && value.trim() ? value.trim() : fallback;
}

export function numberFromRecord(record: Record<string, unknown>, key: string, fallback: number): number {
  const value = record[key];
  if (typeof value === "number" && Number.isFinite(value)) return value;
  if (typeof value === "string" && value.trim() && Number.isFinite(Number(value))) return Number(value);
  return fallback;
}

export function nullableNumberFromRecord(
  record: Record<string, unknown>,
  key: string,
  fallback: number | null,
): number | null {
  const value = record[key];
  if (value == null || value === "") return fallback;
  if (typeof value === "number" && Number.isFinite(value)) return value;
  if (typeof value === "string" && Number.isFinite(Number(value))) return Number(value);
  return fallback;
}

export function stringArrayFromRecord(record: Record<string, unknown>, key: string, fallback: string[]): string[] {
  const value = record[key];
  if (Array.isArray(value)) {
    const items = value.filter((item): item is string => typeof item === "string" && item.trim().length > 0);
    return items.length > 0 ? items : fallback;
  }
  if (typeof value === "string" && value.trim()) {
    return value.split(",").map((item) => item.trim()).filter(Boolean);
  }
  return fallback;
}

export function notesRecordFromRecord(record: Record<string, unknown>): Record<string, unknown> {
  const notes = record.notes;
  if (notes && typeof notes === "object" && !Array.isArray(notes)) return notes as Record<string, unknown>;
  if (typeof notes !== "string" || !notes.trim()) return {};
  try {
    const parsed = JSON.parse(notes) as unknown;
    return parsed && typeof parsed === "object" && !Array.isArray(parsed) ? parsed as Record<string, unknown> : {};
  } catch {
    return {};
  }
}

export function contractDraftFromRecord(record: Record<string, unknown>, current: ContractDraft): ContractDraft {
  const mergedRecord = { ...notesRecordFromRecord(record), ...record };
  return {
    ...current,
    contract_id: stringFromRecord(mergedRecord, "contract_id", current.contract_id),
    contract_name: stringFromRecord(mergedRecord, "contract_name", current.contract_name),
    counterparty: stringFromRecord(mergedRecord, "counterparty", current.counterparty),
    contract_type: stringFromRecord(mergedRecord, "contract_type", current.contract_type),
    delivery_point_name: stringFromRecord(mergedRecord, "delivery_point_name", current.delivery_point_name),
    physical_exit_point_name: stringFromRecord(mergedRecord, "physical_exit_point_name", current.physical_exit_point_name),
    title_transfer_point: stringFromRecord(mergedRecord, "title_transfer_point", current.title_transfer_point),
    beach_delivery_point: stringFromRecord(mergedRecord, "beach_delivery_point", current.beach_delivery_point),
    index_basis: stringFromRecord(mergedRecord, "index_basis", current.index_basis),
    terminal_access: stringFromRecord(mergedRecord, "terminal_access", current.terminal_access),
    capacity_expiry: stringFromRecord(mergedRecord, "capacity_expiry", current.capacity_expiry),
    document_name: stringFromRecord(mergedRecord, "document_name", current.document_name),
    document_status: stringFromRecord(mergedRecord, "document_status", current.document_status),
    source_reference: stringFromRecord(mergedRecord, "source_reference", current.source_reference),
    governing_law: stringFromRecord(mergedRecord, "governing_law", current.governing_law),
    gas_year: stringFromRecord(mergedRecord, "gas_year", current.gas_year),
    delivery_quantity_mwh_per_day: numberFromRecord(
      mergedRecord,
      "delivery_quantity_mwh_per_day",
      current.delivery_quantity_mwh_per_day,
    ),
    contract_price_gbp_mwh: numberFromRecord(mergedRecord, "contract_price_gbp_mwh", current.contract_price_gbp_mwh),
    delivery_tolerance_pct: numberFromRecord(mergedRecord, "delivery_tolerance_pct", current.delivery_tolerance_pct),
    nomination_tolerance_pct: numberFromRecord(mergedRecord, "nomination_tolerance_pct", current.nomination_tolerance_pct),
    tolerance_risk_allowance_gbp_mwh: numberFromRecord(
      mergedRecord,
      "tolerance_risk_allowance_gbp_mwh",
      current.tolerance_risk_allowance_gbp_mwh,
    ),
    variable_cost_gbp_mwh: numberFromRecord(mergedRecord, "variable_cost_gbp_mwh", current.variable_cost_gbp_mwh),
    regas_fee_gbp_mwh: numberFromRecord(mergedRecord, "regas_fee_gbp_mwh", current.regas_fee_gbp_mwh),
    fuel_loss_allowance_pct: numberFromRecord(mergedRecord, "fuel_loss_allowance_pct", current.fuel_loss_allowance_pct),
    settlement_frequency: stringFromRecord(mergedRecord, "settlement_frequency", current.settlement_frequency),
    upstream_payment_lag_days: numberFromRecord(
      mergedRecord,
      "upstream_payment_lag_days",
      current.upstream_payment_lag_days,
    ),
    screen_sale_cash_lag_days: numberFromRecord(
      mergedRecord,
      "screen_sale_cash_lag_days",
      current.screen_sale_cash_lag_days,
    ),
    annual_financing_rate_pct: numberFromRecord(
      mergedRecord,
      "annual_financing_rate_pct",
      current.annual_financing_rate_pct,
    ),
    owned_entry_capacity_mwh_per_day: nullableNumberFromRecord(
      mergedRecord,
      "owned_entry_capacity_mwh_per_day",
      current.owned_entry_capacity_mwh_per_day,
    ),
    owned_exit_capacity_mwh_per_day: nullableNumberFromRecord(
      mergedRecord,
      "owned_exit_capacity_mwh_per_day",
      current.owned_exit_capacity_mwh_per_day,
    ),
    allowed_exit_points: stringArrayFromRecord(mergedRecord, "allowed_exit_points", current.allowed_exit_points),
    eligible_sale_modes: stringArrayFromRecord(mergedRecord, "eligible_sale_modes", current.eligible_sale_modes),
  };
}

export function contractRecordFromParsedJson(parsed: unknown): Record<string, unknown> | null {
  if (Array.isArray(parsed)) {
    return parsed.find((item): item is Record<string, unknown> => Boolean(item) && typeof item === "object") ?? null;
  }
  if (parsed && typeof parsed === "object") {
    const record = parsed as Record<string, unknown>;
    const wrapped = record.contract;
    if (wrapped && typeof wrapped === "object" && !Array.isArray(wrapped)) {
      return wrapped as Record<string, unknown>;
    }
    return record;
  }
  return null;
}

export function parseContractTextDraft(fileName: string, text: string): Record<string, unknown> {
  const record: Record<string, unknown> = {
    document_name: fileName,
    document_status: "STAGED_REVIEW_REQUIRED",
    source_reference: fileName,
  };
  const captureText = (key: string, labels: string[]) => {
    const pattern = new RegExp(`(?:^|\\n)\\s*(?:${labels.join("|")})\\s*[:\\-]\\s*([^\\r\\n]+)`, "i");
    const value = text.match(pattern)?.[1]?.trim();
    if (value) record[key] = value;
  };
  const captureNumber = (key: string, labels: string[]) => {
    const pattern = new RegExp(`(?:^|\\n)\\s*(?:${labels.join("|")})\\s*[:\\-]\\s*([0-9]+(?:\\.[0-9]+)?)`, "i");
    const value = text.match(pattern)?.[1];
    if (value !== undefined && Number.isFinite(Number(value))) record[key] = Number(value);
  };

  captureText("contract_id", ["contract id", "agreement id", "confirmation id"]);
  captureText("contract_name", ["contract name", "agreement", "confirmation"]);
  captureText("counterparty", ["counterparty", "seller", "buyer"]);
  captureText("contract_type", ["contract type", "agreement type"]);
  captureText("gas_year", ["gas year", "term"]);
  captureText("delivery_point_name", ["delivery point", "delivery hub"]);
  captureText("title_transfer_point", ["title transfer point", "title-transfer point", "transfer point"]);
  captureText("beach_delivery_point", ["beach delivery point", "beach", "landing point"]);
  captureText("index_basis", ["index basis", "price index", "pricing basis"]);
  captureText("terminal_access", ["terminal access", "terminal", "tso access"]);
  captureText("capacity_expiry", ["capacity expiry", "capacity end", "expiry"]);
  captureText("governing_law", ["governing law", "law"]);
  captureNumber("delivery_quantity_mwh_per_day", ["quantity", "daily quantity", "mwh per day", "mwh/d"]);
  captureNumber("contract_price_gbp_mwh", ["contract price", "price", "gbp/mwh"]);
  captureNumber("delivery_tolerance_pct", ["delivery tolerance", "tolerance"]);
  captureNumber("nomination_tolerance_pct", ["nomination tolerance"]);
  captureNumber("variable_cost_gbp_mwh", ["variable cost"]);
  captureNumber("regas_fee_gbp_mwh", ["regas fee", "regasification fee"]);
  captureNumber("fuel_loss_allowance_pct", ["fuel loss", "shrinkage"]);

  return record;
}

export function contractRecordFromImportedFile(fileName: string, text: string): Record<string, unknown> | null {
  try {
    const parsed = JSON.parse(text) as unknown;
    const record = contractRecordFromParsedJson(parsed);
    return record ? { document_name: fileName, document_status: "IMPORTED_JSON_DRAFT", ...record } : null;
  } catch {
    return parseContractTextDraft(fileName, text);
  }
}

/**
 * Records as picker options (UX_REFERENCE rule 25): each kind of record the firm holds, named
 * in words, with its id searchable and on hover. One builder per kind, so every form offers
 * the same choice the same way.
 */
import type { RecordOption } from "../../components/ui/recordPickerModel.ts";
import { GAS_HUBS } from "../contractChoices.ts";

interface ContractLike {
  contract_id: string;
  contract_name: string;
  delivery_point_name?: string;
  gas_year?: string;
  retired_at_utc?: string | null;
}

/** Contracts in execution; a retired one is listed only when already chosen, and not choosable. */
export function contractOptions(contracts: readonly ContractLike[], keep: readonly string[] = []): RecordOption[] {
  return contracts
    .filter((contract) => !contract.retired_at_utc || keep.includes(contract.contract_id))
    .map((contract) => ({
      id: contract.contract_id,
      label: contract.contract_name || contract.contract_id,
      detail: [contract.delivery_point_name, contract.gas_year].filter(Boolean).join(" · ") || undefined,
      keywords: [contract.delivery_point_name ?? "", contract.gas_year ?? ""],
      disabled: Boolean(contract.retired_at_utc),
    }));
}

interface BookLike {
  book_id: string;
  name: string;
  legal_entity?: string;
  region?: string;
  active?: boolean;
}

export function bookOptions(books: readonly BookLike[]): RecordOption[] {
  return books
    .filter((book) => book.active !== false)
    .map((book) => ({
      id: book.book_id,
      label: book.name || book.book_id,
      detail: [book.legal_entity, book.region].filter(Boolean).join(" · ") || undefined,
    }));
}

/** The European hubs in desk order; a named label where the code alone is ambiguous. */
export function hubOptions(nameOf: (code: string) => string | null = () => null): RecordOption[] {
  return GAS_HUBS.map((code) => ({ id: code, label: code, detail: nameOf(code) ?? undefined }));
}

interface CounterpartyLike {
  counterparty_id: string;
  counterparty: string;
  rating?: string | null;
}

/** Counterparties with a credit line; each once. */
export function counterpartyOptions(rows: readonly CounterpartyLike[]): RecordOption[] {
  const seen = new Map<string, RecordOption>();
  for (const row of rows) {
    if (seen.has(row.counterparty_id)) continue;
    seen.set(row.counterparty_id, {
      id: row.counterparty_id,
      label: row.counterparty || row.counterparty_id,
      detail: row.rating ?? undefined,
    });
  }
  return [...seen.values()];
}

interface PersonLike {
  /** The principal ("demo.nl.trader"). */
  id: string;
  /** The person's name, when known. */
  name?: string | null;
  detail?: string | null;
}

/** People (traders, reviewers) by name; the principal is searchable and on hover. */
export function personOptions(people: readonly PersonLike[]): RecordOption[] {
  const seen = new Map<string, RecordOption>();
  for (const person of people) {
    if (!person.id || seen.has(person.id)) continue;
    seen.set(person.id, { id: person.id, label: person.name || person.id, detail: person.detail ?? undefined });
  }
  return [...seen.values()].sort((a, b) => a.label.localeCompare(b.label));
}

/**
 * Gas years a contract can run in ("2026/27"), from last year to five ahead of `today`'s gas
 * year (a gas year starts on 1 October).
 */
export function gasYearOptions(today: Date = new Date()): string[] {
  const start = today.getUTCMonth() >= 9 ? today.getUTCFullYear() : today.getUTCFullYear() - 1;
  return Array.from({ length: 7 }, (_, index) => {
    const year = start - 1 + index;
    return `${year}/${String((year + 1) % 100).padStart(2, "0")}`;
  });
}

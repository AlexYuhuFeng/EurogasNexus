/**
 * SCHED-1, the gas day's reconciliation: presentation rules only. Every figure, break and
 * explanation is the server's (`application/gas_day_reconciliation.py`); this file picks the
 * tone of a chip, the words of a countdown and the order of the filters.
 */
import type {
  GasDayReconciliationDTO,
  ReconciliationBreakDTO,
  ReconciliationBreakKind,
  ReconciliationGroupDTO,
  ReconciliationUrgency,
} from "@/api/client";
import type { StatusTone } from "@/components/ui";

/** A break's chip: red when no renomination is left or the cut-off is within the hour. */
export function breakTone(item: Pick<ReconciliationBreakDTO, "severity" | "urgency" | "kind">): StatusTone {
  if (item.kind === "not_confirmed") return "info";
  if (item.severity === "critical" || item.urgency === "passed") return "breach";
  if (item.severity === "warning" || item.urgency === "due_soon") return "watch";
  return "neutral";
}

/** The countdown's colour, as the checklist's: amber within 3 h, red within the hour or past. */
export function countdownUrgency(urgency: ReconciliationUrgency, minutesLeft: number | null): "open" | "soon" | "imminent" | "none" {
  if (urgency === "passed") return "imminent";
  if (urgency === "closed" || minutesLeft === null) return "none";
  if (minutesLeft <= 60) return "imminent";
  if (minutesLeft <= 180) return "soon";
  return "open";
}

/** Whole hours and minutes left, recomputed from the cut-off so the countdown moves. */
export function minutesUntil(atUtc: string | null | undefined, nowMs: number): number | null {
  if (!atUtc) return null;
  const at = Date.parse(atUtc);
  if (!Number.isFinite(at)) return null;
  return Math.max(0, Math.floor((at - nowMs) / 60_000));
}

/** A group's breaks, in the server's order (time to cut-off, then MWh at risk). */
export function breaksOf(group: ReconciliationGroupDTO, breaks: readonly ReconciliationBreakDTO[]): ReconciliationBreakDTO[] {
  const ids = new Set(group.break_ids);
  return breaks.filter((item) => ids.has(item.id));
}

/** A group's stable key: hub, point and counterparty. */
export function groupKey(group: Pick<ReconciliationGroupDTO, "hub" | "point" | "counterparty">): string {
  return `${group.hub}|${group.point ?? ""}|${group.counterparty}`;
}

/** The hubs to filter on: those the read holds, in its order. */
export function hubOptions(payload: GasDayReconciliationDTO | null | undefined): string[] {
  return [...new Set((payload?.hubs ?? []).map((hub) => hub.hub))];
}

/** The break kinds to filter on: those found first (with their count), then the rest. */
export function kindOptions(payload: GasDayReconciliationDTO | null | undefined): { kind: ReconciliationBreakKind; count: number }[] {
  const kinds = payload?.kinds ?? [];
  const counted = kinds.map((kind) => ({ kind, count: payload?.counts[kind] ?? 0 }));
  return [...counted.filter((item) => item.count > 0), ...counted.filter((item) => item.count === 0)];
}

/** A signed quantity as the desk writes it ("−204,728"), or a dash when not held. */
export function signedQuantity(quantity: { value: number } | null | undefined): string {
  if (!quantity) return "—";
  const rounded = Math.round(Math.abs(quantity.value));
  if (rounded === 0) return "0";
  return `${quantity.value < 0 ? "−" : "+"}${rounded.toLocaleString("en-GB")}`;
}

/** The indicative cash-out in words' figures ("1,440 GBP"), or null when there is none. */
export function cashOutText(item: Pick<ReconciliationBreakDTO, "cash_out">): string | null {
  const cash = item.cash_out;
  if (cash.basis !== "indicative" || cash.value == null) return null;
  return `${Math.round(cash.value).toLocaleString("en-GB")} ${cash.currency ?? ""}`.trim();
}

/** The explanation and next step in the reader's language. */
export function breakWords(item: ReconciliationBreakDTO, language: string): { explanation: string; next: string } {
  const zh = language.toLowerCase().startsWith("zh");
  return {
    explanation: zh && item.explanation_zh ? item.explanation_zh : item.explanation,
    next: zh && item.next_step_zh ? item.next_step_zh : item.next_step,
  };
}

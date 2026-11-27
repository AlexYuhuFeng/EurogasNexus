/**
 * Deal capture on screen (Book → Blotter): the pure helpers the blotter and the end-of-day panel
 * share. The server sends money and volume as exact decimal text; these only format it for
 * display in the app's language and never add figures together.
 */
import type { DealPositionKindDTO, DealSourceDTO, EodDifferenceDTO } from "../../api/deals.ts";
import { formatAmount } from "../time/valueFormat.ts";

type Translate = (key: string, options?: Record<string, unknown>) => string;

/** Today's trade date in UTC (the server's default too). */
export function todayIso(now: Date = new Date()): string {
  return now.toISOString().slice(0, 10);
}

/** An exact decimal from the server, shown in the app's language (display only). */
export function shownDecimal(text: string | null | undefined, language: string, digits: number): string {
  if (text === null || text === undefined || text === "") return "–";
  const value = Number(text);
  return Number.isFinite(value) ? formatAmount(value, language, digits) : text;
}

/** Where a deal came from, in one short phrase: the file and line, or by hand and by whom. */
export function dealSourceText(row: { source: DealSourceDTO }, t: Translate): string {
  if (row.source.kind === "manual") return t("deals.source_manual", { who: row.source.entered_by ?? "" });
  return t("deals.source_file", { file: row.source.file_name ?? "", line: row.source.line ?? "" });
}

/** Why a deal counts as physical or financial: chosen by hand (by whom), stated, or the rule. */
export function positionKindText(kind: DealPositionKindDTO | null | undefined, t: Translate): string {
  if (!kind) return "";
  switch (kind.basis) {
    case "entered_by_hand":
      return t("deals.kind_basis.entered_by_hand", { who: kind.rule ?? "" });
    case "stated_on_deal":
      return t("deals.kind_basis.stated_on_deal");
    case "rule":
      return kind.rule_kind === "financial_until_delivery"
        ? t("deals.kind_basis.until_delivery", { rule: kind.rule ?? "" })
        : t("deals.kind_basis.rule", { rule: kind.rule ?? "" });
    default:
      return t("deals.kind_basis.default");
  }
}

/** One line for an end-of-day difference: what each side holds (from the check's detail). */
export function differenceText(item: EodDifferenceDTO, t: Translate): string {
  const detail = item.detail ?? {};
  switch (item.kind) {
    case "volume":
      return t("eod.detail.volume", { captured: detail.captured_mwh, etrm: detail.etrm_mwh });
    case "price":
      return t("eod.detail.price", { captured: detail.captured, etrm: detail.etrm, currency: detail.currency });
    case "period":
    case "side":
    case "hub":
    case "counterparty":
      return t("eod.detail.pair", { captured: detail.captured, etrm: detail.etrm });
    case "etrm_unreadable":
      return t("eod.detail.unreadable", { line: detail.line, message: detail.message });
    default:
      return "";
  }
}

/** Differences still without a note: the close is offered only at zero. */
export function unacknowledged(differences: readonly EodDifferenceDTO[], notes: Record<string, string>): number {
  return differences.filter((item) => !(notes[item.id] ?? "").trim()).length;
}

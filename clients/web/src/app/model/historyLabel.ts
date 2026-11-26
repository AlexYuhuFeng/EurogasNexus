/**
 * The history behind a fundamentals figure in the reader's language. The server states it as an
 * English label ("History from 12 Oct 2026: no complete prior year held"); the same facts come
 * with it (`mode`, `years`, `history_from`), so the words are written here from those, through the
 * chart's own keys (`chart.history.*`, the F.2 rule in seasonModel.ts).
 */
import i18n from "i18next";

import { formatGasDay } from "../time/timeFormat.ts";
import { historyPlan } from "../../components/ui/charts/seasonModel.ts";

type Translate = (key: string, options?: Record<string, unknown>) => string;

export interface HistoryFacts {
  mode?: "none" | "lines" | "band";
  years?: string[];
  label: string;
  history_from?: string | null;
}

export function historyLabel(history: HistoryFacts | null | undefined, t: Translate, language = i18n.language ?? "en"): string {
  if (!history) return "";
  if (!history.mode) return history.label;
  const from = history.history_from ? formatGasDay(history.history_from.slice(0, 10), language, true) : "";
  const plan = historyPlan(history.mode === "none" ? [] : history.years ?? [], from);
  const key = plan.label.key;
  const said = t(key, plan.label.values);
  return said === key ? history.label : said;
}

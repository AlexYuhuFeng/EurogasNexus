/**
 * A spread study typed into the answer bar ("forward spread net of tariff between TTF and NBP",
 * "NBP vs TTF front month", "英国和荷兰之间的价差"): two hubs and a spread word. The bar does not
 * interpret it; it offers to open Research → Spreads with the text, where the server reads it
 * into a StrategySpec and the engine computes every figure.
 */

import { HUBS } from "./intent.ts";

const ZH_HUBS: Record<string, string> = {
  荷兰: "TTF", 英国: "NBP", 德国: "THE", 法国: "PEG", 比利时: "ZTP", 意大利: "PSV", 奥地利: "CEGH", 西班牙: "PVB", 丹麦: "ETF",
};
const SPREAD_WORD = /\b(?:spread|spreads|vs\.?|versus|minus|between|net of|tariff|arb|arbitrage|transport)\b|价差|之间|扣除|运输费|对/i;

/** The hubs a line names, in order, each once (`THE` only in capitals). */
export function hubsNamed(text: string): string[] {
  const found: Array<[number, string]> = [];
  for (const match of text.matchAll(/[A-Za-z]+/g)) {
    const word = match[0];
    const upper = word.toUpperCase();
    if (upper === "THE" && word !== "THE") continue;
    if ((HUBS as readonly string[]).includes(upper)) found.push([match.index ?? 0, upper]);
  }
  for (const [word, hub] of Object.entries(ZH_HUBS)) {
    let at = text.indexOf(word);
    while (at >= 0) {
      found.push([at, hub]);
      at = text.indexOf(word, at + word.length);
    }
  }
  const out: string[] = [];
  for (const [, hub] of found.sort((a, b) => a[0] - b[0])) if (!out.includes(hub)) out.push(hub);
  return out;
}

/** The description to open in Spreads, or null when the line is not a spread study. */
export function spreadStudy(text: string): string | null {
  const clean = text.trim();
  if (clean.length < 7 || clean.length > 500) return null;
  if (hubsNamed(clean).length < 2 || !SPREAD_WORD.test(clean)) return null;
  return clean;
}

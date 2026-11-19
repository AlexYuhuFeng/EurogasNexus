/**
 * The first-use hints each page declares (design basis H.1): at most three, each anchored to a
 * real control by a selector, its sentence in the locale files (`hints.<id>`).
 */
import type { FirstUseHint } from "../../components/ui/firstUseHintsModel.ts";

const hint = (id: string, anchor: string): FirstUseHint => ({ id, anchor, textKey: `hints.${id}` });

export const FIRST_USE_HINTS: Readonly<Record<string, readonly FirstUseHint[]>> = {
  "desk.today": [
    hint("desk.today.name", ".today-figure-name"),
    hint("desk.today.feeds", ".projection-context-trigger"),
    hint("desk.today.brief", '[data-hint-anchor="desk-brief"]'),
  ],
  "deals.contracts": [
    hint("deals.contracts.find", '[data-hint-anchor="contract-kind-filter"]'),
    hint("deals.contracts.new", '[data-page-action="contract-new"]'),
    hint("deals.contracts.import", '[data-hint-anchor="contract-import"]'),
  ],
};

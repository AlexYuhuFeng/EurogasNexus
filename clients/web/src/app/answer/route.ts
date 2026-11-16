/**
 * Which tier answers a query: deterministic, cheapest and most certain first.
 *
 * 1. `?` in front asks (tier 3). `=` in front forces the calculator: a conversion, a gas-day
 *    answer or an arithmetic result, or a "not a calculation" line, never anything else.
 * 2. Instant (tier 1, synchronous, no network): a unit or price conversion, arithmetic, a
 *    gas-day/date answer, or a definition question whose subject is a glossary term
 *    ("what is TTF", "TTF 是什么"), which goes to the glossary and never to the model.
 * 3. Looked up (tier 2): a price, storage, LNG, Norway, outages or, with `portfolio.read`, a
 *    book look-up (`intent.ts`).
 * 4. A bare glossary term ("hedge ratio", "UMM") shows its definition.
 * 5. A question ("why …", "what's going on …", "…?", "为什么…") or a definition question with
 *    no glossary hit offers Ask (tier 3), which runs only on Enter.
 * Anything else gets no answer row: the navigation results below are the answer.
 */

import { calculate, type Calculation } from "./expression.ts";
import { gasDayAnswer, type GasDayAnswer } from "./gasDay.ts";
import { definitionSubject, findTerm, glossaryAnswer, type GlossaryAnswer, type GlossaryEntry } from "./glossary.ts";
import { lookupIntent, type LookupIntent } from "./intent.ts";
import { convertQuery, type Conversion, type FxHeld } from "./units.ts";
import type { UnitsReferenceDTO } from "../../api/client.ts";

export type Route =
  | { tier: 1; kind: "calc"; calc: Calculation }
  | { tier: 1; kind: "convert"; conversion: Conversion }
  | { tier: 1; kind: "gasday"; answer: GasDayAnswer }
  | { tier: 1; kind: "glossary"; answer: GlossaryAnswer }
  | { tier: 1; kind: "not-calc"; text: string }
  | { tier: 2; kind: "lookup"; intent: LookupIntent }
  | { tier: 3; kind: "ask"; question: string; forced: boolean }
  | { tier: 0; kind: "none" };

export interface RouteContext {
  units: UnitsReferenceDTO | null;
  fx: FxHeld | null;
  glossary: readonly GlossaryEntry[];
  bookAllowed: boolean;
  zh: boolean;
  now?: Date;
}

const QUESTION_EN = /^(?:what|what's|whats|why|how|when|which|where|who|is|are|was|were|did|does|do|has|have|can|could|should|will|would|explain|summari[sz]e|summary|tell\s+me|give\s+me|show\s+me|compare|any)\b/i;
const QUESTION_ZH = /(为什么|为何|什么|怎么|怎样|如何|是否|吗|呢|哪些|哪个|多少|总结|概括|解释|分析)/;

/** Whether a query reads as a question someone would ask (not a name being typed). */
export function looksLikeQuestion(text: string): boolean {
  const trimmed = text.trim();
  if (trimmed.length < 4) return false;
  if (/[?？]$/.test(trimmed)) return true;
  if (QUESTION_EN.test(trimmed) && trimmed.split(/\s+/).length >= 3) return true;
  if (QUESTION_ZH.test(trimmed) && trimmed.length >= 4) return true;
  return false;
}

export function routeQuery(raw: string, context: RouteContext): Route {
  const text = raw.trim();
  if (!text) return { tier: 0, kind: "none" };
  if (text.startsWith("?") || text.startsWith("？")) {
    const question = text.slice(1).trim();
    return question.length >= 3 ? { tier: 3, kind: "ask", question, forced: true } : { tier: 0, kind: "none" };
  }
  const forced = text.startsWith("=");
  const body = forced ? text.slice(1).trim() : text;

  const conversion = convertQuery(body, context.units, context.fx);
  if (conversion) return { tier: 1, kind: "convert", conversion };
  const calc = calculate(body, forced);
  if (calc) return { tier: 1, kind: "calc", calc };
  const day = gasDayAnswer(body, context.now);
  if (day) return { tier: 1, kind: "gasday", answer: day };
  if (forced) return body ? { tier: 1, kind: "not-calc", text: body } : { tier: 0, kind: "none" };

  const subject = definitionSubject(body);
  if (subject) {
    const entry = findTerm(subject, context.glossary);
    if (entry) return { tier: 1, kind: "glossary", answer: glossaryAnswer(entry, context.zh) };
  }
  const intent = lookupIntent(body, { bookAllowed: context.bookAllowed, now: context.now });
  if (intent) return { tier: 2, kind: "lookup", intent };
  const bare = findTerm(body, context.glossary);
  if (bare) return { tier: 1, kind: "glossary", answer: glossaryAnswer(bare, context.zh) };
  if (subject || looksLikeQuestion(body)) return { tier: 3, kind: "ask", question: body, forced: false };
  return { tier: 0, kind: "none" };
}

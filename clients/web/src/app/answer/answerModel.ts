/**
 * What the answer row shows, whichever tier produced it. Pure data: strings that depend on
 * the reader's language travel as translation keys with values, and the row translates them.
 */

export interface AnswerText {
  key: string;
  values?: Record<string, string | number>;
}

/** Where Enter takes the reader: a mode's task, or a glossary entry. */
export type AnswerTarget =
  | { kind: "task"; mode: "desk" | "deals" | "book" | "research"; task: string }
  | { kind: "glossary"; term: string };

export type AnswerKind =
  | "calc" | "convert" | "gasday" | "glossary" | "not-calc"
  | "price" | "storage" | "lng" | "norway" | "outages" | "position" | "credit" | "contract";

export interface AnswerView {
  kind: AnswerKind;
  /** What was answered, as the desk names it: `TTF Dec-26`, `(42.5 − 39.8) × 30`. */
  label: string | AnswerText;
  /** The value, formatted; null for an answer that is a sentence or says what is missing. */
  value: string | null;
  unit?: string | AnswerText | null;
  /** The day change or comparison, formatted and signed, with its sign for colour. */
  delta?: { text: string; value: number } | null;
  /** A simulated figure is said beside the number, as the hub board does. */
  simulated?: boolean;
  /** A sentence instead of a value (a definition, "No sourced price"). */
  sentence?: string | AnswerText | null;
  /** Second-line facts: FX rate, calorific value, as-of and source, the reason for a gap. */
  lines: AnswerText[];
  asOf?: string | null;
  /** The number alone for the clipboard, and with its unit. */
  copy?: { value: string; withUnit: string } | null;
  target?: AnswerTarget | null;
}

/** The tier 2 state the bar shows while a look-up runs or after it failed. */
export type LookupState =
  | { status: "idle" }
  | { status: "loading"; key: string }
  | { status: "done"; key: string; answer: AnswerView }
  | { status: "error"; key: string };

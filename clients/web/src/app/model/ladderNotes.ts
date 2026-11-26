/** The position ladder's notes (server `notes`, or an older server's `warnings` sentences). */
import type { PositionLadderDTO } from "../../api/client.ts";

type Translate = (key: string, options?: Record<string, unknown>) => string;

/**
 * The ladder's notes in the reader's language: the server's codes (`notes`) through
 * `position.note.<code>`, its English sentence where a code is unknown or an older server sent
 * none.
 */
export function ladderNotes(ladder: Pick<PositionLadderDTO, "warnings" | "notes">, t: Translate): string[] {
  const notes = ladder.notes?.length ? ladder.notes : (ladder.warnings ?? []).map(noteFromSentence);
  return notes.map((note, index) => {
    if (!note.code) return ladder.warnings?.[index] ?? "";
    const key = `position.note.${note.code.toLowerCase()}`;
    const text = t(key, note.params ?? {});
    return text === key ? ladder.warnings?.[index] ?? note.code : text;
  });
}

/** An older server's sentence as its code, so it is still said in the reader's language. */
const LADDER_SENTENCES: readonly [RegExp, string, (match: RegExpExecArray) => Record<string, unknown>][] = [
  [/^Indicative: price risk on the open position only/, "INDICATIVE_PRICE_RISK_ONLY", () => ({})],
  [/^(\d+) leg-months have no mark or no price/, "LEG_MONTHS_NOT_VALUED", (m) => ({ count: Number(m[1]) })],
  [/^VaR unavailable: offsetting delivery months at (.+?) require/, "VAR_OFFSETTING_MONTHS", (m) => ({ hubs: m[1] })],
  [/^VaR needs at least 20 daily price changes on every hub held; (\d+) available/, "VAR_SHORT_HISTORY", (m) => ({ count: Number(m[1]) })],
];

function noteFromSentence(sentence: string): { code: string; params?: Record<string, unknown> } {
  for (const [pattern, code, params] of LADDER_SENTENCES) {
    const match = pattern.exec(sentence);
    if (match) return { code, params: params(match) };
  }
  return { code: "" };
}


/**
 * The logic of RecordPicker (UX_REFERENCE rule 25, the live principle): choose from records that
 * exist (a contract in execution, a counterparty, a book, a trader, a point, a terminal) instead
 * of typing an identifier. Pure, so it is tested without a browser.
 *
 * - A record is shown by its name; its id is searchable and shown on hover, never as the label.
 * - Search matches the name's start first, then a word's start, then anywhere, then the id and
 *   keywords (other names, a hub, a counterparty).
 * - With no query, recent picks lead, then the records in the order given.
 * - At most `MAX_VISIBLE` options are listed; the rest are reached by typing.
 * - Manual entry, where a form allows it, is an explicit last option ("Use 'X', entered by
 *   hand"), so the result can say which inputs were typed.
 */

export const MAX_VISIBLE = 12;
export const MAX_RECENT = 5;

export interface RecordOption {
  /** What is stored: a contract id, a principal, a hub code. */
  id: string;
  /** What a person reads: "Rhinmark Handel GmbH", "Demo TTF desk trader". */
  label: string;
  /** A quiet second line: "BBB · NWG-NL", "in execution to Sep-27". */
  detail?: string;
  /** Other words that find it: aliases, its hub, its counterparty. */
  keywords?: readonly string[];
  /** Shown but not choosable, with the reason in `detail` (a contract not in execution). */
  disabled?: boolean;
}

export type PickerEntry =
  | { type: "record"; option: RecordOption; recent: boolean }
  | { type: "manual"; text: string };

const fold = (text: string) => text.normalize("NFKD").replace(/[̀-ͯ]/g, "").toLowerCase();

/** 0 = name starts with the query; 1 = a word starts with it; 2 = name contains it; 3 = id or a
 * keyword contains it; null = no match. */
export function matchRank(option: RecordOption, query: string): number | null {
  const q = fold(query.trim());
  if (!q) return 0;
  const label = fold(option.label);
  if (label.startsWith(q)) return 0;
  if (label.split(/[\s·,/()-]+/).some((word) => word.startsWith(q))) return 1;
  if (label.includes(q)) return 2;
  if (fold(option.id).includes(q)) return 3;
  if ((option.keywords ?? []).some((word) => fold(word).includes(q))) return 3;
  return null;
}

export interface EntriesResult {
  entries: PickerEntry[];
  /** Matches not listed (reach them by typing more). */
  hidden: number;
}

/** What the list shows for `query`. */
export function pickerEntries(
  options: readonly RecordOption[],
  query: string,
  { recent = [], allowManual = false }: { recent?: readonly string[]; allowManual?: boolean } = {},
): EntriesResult {
  const trimmed = query.trim();
  let ordered: Array<{ option: RecordOption; recent: boolean }>;
  if (!trimmed) {
    const byId = new Map(options.map((option) => [option.id, option]));
    const recents = recent.map((id) => byId.get(id)).filter((option): option is RecordOption => Boolean(option));
    const recentIds = new Set(recents.map((option) => option.id));
    ordered = [
      ...recents.map((option) => ({ option, recent: true })),
      ...options.filter((option) => !recentIds.has(option.id)).map((option) => ({ option, recent: false })),
    ];
  } else {
    ordered = options
      .map((option, index) => ({ option, rank: matchRank(option, trimmed), index }))
      .filter((item): item is { option: RecordOption; rank: number; index: number } => item.rank !== null)
      .sort((a, b) => a.rank - b.rank || a.index - b.index)
      .map(({ option }) => ({ option, recent: false }));
  }
  const visible = ordered.slice(0, MAX_VISIBLE);
  const entries: PickerEntry[] = visible.map((item) => ({ type: "record", ...item }));
  const exact = options.some((option) => fold(option.label) === fold(trimmed) || fold(option.id) === fold(trimmed));
  if (allowManual && trimmed && !exact) entries.push({ type: "manual", text: trimmed });
  return { entries, hidden: Math.max(0, ordered.length - visible.length) };
}

/** The next active row for a key, or null when the key is not the list's. */
export function moveActive(active: number, key: string, count: number): number | null {
  if (count === 0) return null;
  if (key === "ArrowDown") return (active + 1) % count;
  if (key === "ArrowUp") return (active - 1 + count) % count;
  if (key === "Home") return 0;
  if (key === "End") return count - 1;
  return null;
}

export function withRecent(recent: readonly string[], id: string): string[] {
  return [id, ...recent.filter((item) => item !== id)].slice(0, MAX_RECENT);
}

export function readRecent(storage: Pick<Storage, "getItem"> | null | undefined, key: string): string[] {
  try {
    const parsed = JSON.parse(storage?.getItem(key) ?? "[]");
    return Array.isArray(parsed) ? parsed.filter((item): item is string => typeof item === "string").slice(0, MAX_RECENT) : [];
  } catch {
    return [];
  }
}

export function writeRecent(storage: Pick<Storage, "setItem"> | null | undefined, key: string, recent: readonly string[]): void {
  try {
    storage?.setItem(key, JSON.stringify(recent.slice(0, MAX_RECENT)));
  } catch {
    // Private window: recents hold for this page only.
  }
}

/**
 * A stable id for a new record from its name, for forms that used to ask for one
 * ("Rhinmark Handel GmbH" → "rhinmark-handel-gmbh"; "-2", "-3" when taken).
 */
export function idFromName(name: string, taken: Iterable<string> = []): string {
  const base =
    fold(name)
      .replace(/[^a-z0-9]+/g, "-")
      .replace(/^-+|-+$/g, "")
      .slice(0, 48) || "item";
  const used = new Set(taken);
  if (!used.has(base)) return base;
  for (let n = 2; ; n += 1) if (!used.has(`${base}-${n}`)) return `${base}-${n}`;
}

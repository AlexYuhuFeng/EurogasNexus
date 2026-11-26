/**
 * Limit and mandate breaches in the reader's language (AGENTS rule 17; UX_REFERENCE rule 21).
 *
 * The risk engine (`domain/risk/limits.py`) states a breach as an English sentence
 * ("TTF is outside the mandate (demo-kestrel-uk-6)", "2027-01 hedged 0%, under the approved
 * 60%"). The server's own Chinese table (`application/desk_text.py`) covers alerts and briefs;
 * the screens read the same sentences, so this module recognises each template, says it through
 * `limits.breach.<kind>` with its parameters, and names the contract a reference points at. A
 * sentence no template matches is shown as sent. tests/limitBreaches.test.ts keeps every template
 * in limits.py matched here.
 */

type Translate = (key: string, options?: Record<string, unknown>) => string;

export interface ParsedBreach {
  kind: string;
  params: Record<string, string>;
  /** The sentence as the server sent it. */
  text: string;
}

const TEMPLATES: readonly [string, RegExp, readonly string[]][] = [
  ["outside_mandate", /^(\S+) is outside the mandate \((.+)\)$/, ["hub", "ref"]],
  ["physical_not_allowed", /^physical supply is not allowed \((.+)\)$/, ["ref"]],
  ["financial_not_allowed", /^financial trades are not allowed \((.+)\)$/, ["ref"]],
  ["instrument_not_allowed", /^(\S+) is not an allowed instrument \((.+)\)$/, ["instrument", "ref"]],
  ["beyond_tenor", /^delivery to (.+) is beyond (\d+) months \((.+)\)$/, ["month", "months", "ref"]],
  ["net_over", /^net (-?[\d,]+) MWh in (.+) is over ([\d,]+) MWh$/, ["net", "at", "limit"]],
  ["hedged_above", /^(.+) hedged (-?\d+)%, above (\d+)%$/, ["at", "pct", "limit"]],
  ["hedged_below", /^(.+) hedged (-?\d+)%, below (\d+)%$/, ["at", "pct", "limit"]],
  ["approved_over", /^(\S+) hedged (-?\d+)%, over the approved (\d+)%$/, ["at", "pct", "limit"]],
  ["approved_under", /^(\S+) hedged (-?\d+)%, under the approved (\d+)%$/, ["at", "pct", "limit"]],
];

/** One breach sentence as its kind and parameters; kind "" when no template matches. */
export function parseBreach(text: string): ParsedBreach {
  const sentence = text.trim();
  for (const [kind, pattern, names] of TEMPLATES) {
    const match = pattern.exec(sentence);
    if (match) {
      const params = Object.fromEntries(names.map((name, index) => [name, match[index + 1] ?? ""]));
      // "-0%" is a rounding artefact of a zero hedge.
      if (params.pct === "-0") params.pct = "0";
      return { kind, params, text: sentence };
    }
  }
  return { kind: "", params: {}, text: sentence };
}

/** The `"; "`-joined breaches of a mandate, or a list of them, as separate sentences. */
export function splitBreaches(breaches: string | readonly string[] | null | undefined): string[] {
  if (!breaches) return [];
  const list = typeof breaches === "string" ? breaches.split(/;\s+/) : [...breaches];
  return list.map((item) => item.trim()).filter(Boolean);
}

/** One breach in words; a contract reference is said by its name when the page holds it. */
export function breachText(text: string, t: Translate, names?: ReadonlyMap<string, string>): string {
  const parsed = parseBreach(text);
  if (!parsed.kind) return parsed.text;
  const params: Record<string, string> = { ...parsed.params };
  if (params.ref) params.ref = names?.get(params.ref) ?? params.ref;
  const key = `limits.breach.${parsed.kind}`;
  const said = t(key, params);
  return said === key ? parsed.text : said;
}

/**
 * Several breaches as few lines: the months of one approval band breached the same way are one
 * line ("26 months under the approved 60%: Nov-26 to Jan-29"), every other breach its own.
 */
export function breachSummary(
  breaches: string | readonly string[] | null | undefined,
  t: Translate,
  names?: ReadonlyMap<string, string>,
): string[] {
  const BANDED = new Set(["approved_under", "approved_over", "hedged_below", "hedged_above"]);
  const lines: { group?: string; text: string }[] = [];
  const groups = new Map<string, { kind: string; limit: string; texts: string[]; months: string[] }>();
  for (const text of splitBreaches(breaches)) {
    const parsed = parseBreach(text);
    if (BANDED.has(parsed.kind)) {
      const key = `${parsed.kind}|${parsed.params.limit}`;
      const group = groups.get(key);
      if (group) {
        group.texts.push(text);
        group.months.push(parsed.params.at ?? "");
      } else {
        groups.set(key, { kind: parsed.kind, limit: parsed.params.limit ?? "", texts: [text], months: [parsed.params.at ?? ""] });
        lines.push({ group: key, text });
      }
      continue;
    }
    lines.push({ text });
  }
  return lines.map(({ group, text }) => {
    const banded = group ? groups.get(group) : undefined;
    if (!banded || banded.texts.length === 1) return breachText(text, t, names);
    return t(`limits.breach.${banded.kind}_many`, {
      count: banded.months.length,
      limit: banded.limit,
      first: banded.months[0],
      last: banded.months[banded.months.length - 1],
    });
  });
}

/** "12% to 87%" (`limits.py` `_pct_range`) in the reader's language; anything else as sent. */
export function pctRangeText(text: string | null | undefined, t: Translate): string {
  const match = /^(-?\d+)% to (-?\d+)%$/.exec(String(text ?? "").trim());
  if (!match) return String(text ?? "");
  const key = "limits.pct_range";
  const said = t(key, { low: match[1], high: match[2] });
  return said === key ? String(text) : said;
}

/**
 * Server sentences said in the reader's language (AGENTS rule 17; UX_REFERENCE rule 21).
 *
 * Some server notes are still English sentences, not codes: the position inputs
 * (`application/position_inputs.py`) and the delivery flags (`domain/risk/delivery.py`). Until
 * they travel as codes, each template is recognised here and said through `server.sentence.<kind>`
 * with its parameters; a contract or cargo id is said by its name where the page holds it. A
 * sentence no template matches is shown as sent. tests/serverSentences.test.ts keeps the server's
 * templates and this table in step.
 */

type Translate = (key: string, options?: Record<string, unknown>) => string;

const TEMPLATES: readonly [string, RegExp, readonly string[]][] = [
  ["simulated_marks", /^(?:DEMO: marks are simulated demo prices, not market prices\.?|Marks are simulated prices, not market prices\.?)$/, []],
  ["contract_floating", /^contract (\S+): price floats with (.+); volume only on the ladder$/, ["contract", "index"]],
  ["contract_indexed", /^contract (\S+): price floats with (.+); volume on the ladder, its price exposure on that index$/, ["contract", "index"]],
  ["contract_fob", /^contract (\S+): an FOB cargo is not on a European hub until it is sold or discharged$/, ["contract"]],
  ["contract_gas_year", /^contract (\S+): gas year '?(.+?)'? not understood$/, ["contract", "year"]],
  ["contract_no_hub", /^contract (\S+): delivery point '?(.+?)'? does not name a hub; .+$/, ["contract", "point"]],
  ["cargo_on_ladder", /^cargo (\S+): on the ladder as contract (\S+); its plan's send-out is not added again$/, ["cargo", "contract"]],
  ["cargo_no_sendout", /^cargo (\S+): no send-out on the ladder \((.+)\)$/, ["cargo", "reason"]],
  ["cargo_hedge_on_ladder", /^cargo (\S+): hedge (\S+) is a trade already on the ladder; not added again$/, ["cargo", "hedge"]],
  ["cargoes_volume_only", /^(\d+) cargo\(es\) on the ladder from their plans and recorded hedges; volume only, not valued$/, ["count"]],
  ["delivery_deviates", /^deviates from nominations on more than 1 day in 5$/, []],
  ["delivery_trend", /^last 7 days ([+-]?[\d.]+)% against DCQ$/, ["pct"]],
  ["delivery_volatile", /^volatile delivery \(CV above 15%\)$/, []],
  // FX basis notes (domain/market/fx_forward.py `label`, application/valuation_snapshot.py).
  ["fx_derived_dated", /^FX: derived \(interest parity from (.+), flat rate\), value date (\S+)$/, ["names", "date"]],
  ["fx_derived", /^(?:FX: )?derived \(interest parity from (.+), flat rate\)$/, ["names"]],
  ["fx_spot", /^FX: spot \(ECB reference rate of (\S+)\)$/, ["date"]],
  ["fx_reference", /^(?:FX: )?ECB reference rate (\S+?)(?:, value date \S+)?$/, ["date"]],
  ["fx_simulated", /^(?:FX: )?simulated reference rate (\S+?)(?:, value date \S+)?$/, ["date"]],
  ["fx_sourced", /^(?:FX: )?sourced \((.+)\)(?:, value date (\S+))?$/, ["source", "date"]],
  ["spreads_simulated", /^Simulated inputs: these spreads are not market prices\.?$/, []],
];

/** A server sentence in words, or null when no template matches. */
export function serverSentence(text: string, t: Translate, names?: ReadonlyMap<string, string>): string | null {
  const sentence = text.trim();
  for (const [kind, pattern, params] of TEMPLATES) {
    const match = pattern.exec(sentence);
    if (!match) continue;
    const values: Record<string, string> = {};
    params.forEach((name, index) => {
      const value = match[index + 1] ?? "";
      values[name] = name === "contract" || name === "cargo" ? names?.get(value) ?? value : value;
    });
    const key = `server.sentence.${kind}`;
    const said = t(key, values);
    return said === key ? null : said;
  }
  return null;
}

export interface FxRateLike {
  pair: string;
  base_currency?: string;
  quote_currency?: string;
  rate: number;
  observed_at_utc?: string;
}

export interface MarketObservationLike {
  market_venue: string;
  product: string;
  price: number;
  currency: string;
  unit?: string;
  observed_at_utc?: string;
  period_start_utc?: string;
  metadata_json?: Record<string, unknown>;
}

interface CurrencyEdge {
  to: string;
  multiplier: number;
}

function normalizedCurrency(value: string | null | undefined): string {
  return (value ?? "").trim().toUpperCase();
}

function timestampMs(value: string | null | undefined): number {
  if (!value) return 0;
  const parsed = Date.parse(value);
  return Number.isFinite(parsed) ? parsed : 0;
}

function rateCurrencies(rate: FxRateLike): [string, string] | null {
  const pair = rate.pair.replace(/[^A-Za-z]/g, "").toUpperCase();
  const base = normalizedCurrency(rate.base_currency) || pair.slice(0, 3);
  const quote = normalizedCurrency(rate.quote_currency) || pair.slice(3, 6);
  return base.length === 3 && quote.length === 3 ? [base, quote] : null;
}

function buildLatestCurrencyGraph(rates: FxRateLike[]): Map<string, CurrencyEdge[]> {
  const latestRates = new Map<string, FxRateLike>();
  rates.forEach((rate) => {
    const currencies = rateCurrencies(rate);
    if (!currencies || !Number.isFinite(rate.rate) || rate.rate <= 0) return;
    const key = currencies.join(":");
    const current = latestRates.get(key);
    if (!current || timestampMs(rate.observed_at_utc) > timestampMs(current.observed_at_utc)) {
      latestRates.set(key, rate);
    }
  });

  const graph = new Map<string, CurrencyEdge[]>();
  latestRates.forEach((rate) => {
    const currencies = rateCurrencies(rate);
    if (!currencies) return;
    const [base, quote] = currencies;
    graph.set(base, [...(graph.get(base) ?? []), { to: quote, multiplier: rate.rate }]);
    graph.set(quote, [...(graph.get(quote) ?? []), { to: base, multiplier: 1 / rate.rate }]);
  });
  return graph;
}

export function convertCurrency(
  value: number,
  sourceCurrency: string,
  targetCurrency: string,
  rates: FxRateLike[],
): number | null {
  if (!Number.isFinite(value)) return null;
  const source = normalizedCurrency(sourceCurrency);
  const target = normalizedCurrency(targetCurrency);
  if (!source || !target) return null;
  if (source === target) return value;

  const graph = buildLatestCurrencyGraph(rates);
  const queue: Array<{ currency: string; value: number; depth: number }> = [
    { currency: source, value, depth: 0 },
  ];
  const visited = new Set([source]);
  while (queue.length > 0) {
    const current = queue.shift();
    if (!current || current.depth >= 3) continue;
    for (const edge of graph.get(current.currency) ?? []) {
      const converted = current.value * edge.multiplier;
      if (edge.to === target) return converted;
      if (visited.has(edge.to)) continue;
      visited.add(edge.to);
      queue.push({ currency: edge.to, value: converted, depth: current.depth + 1 });
    }
  }
  return null;
}

export function marketPriceGbpMwh(
  observation: Pick<MarketObservationLike, "price" | "currency">,
  rates: FxRateLike[],
): number | null {
  return convertCurrency(observation.price, observation.currency, "GBP", rates);
}

export function marketObservationHub(observation: MarketObservationLike): string {
  const metadataHub = observation.metadata_json?.hub;
  if (typeof metadataHub === "string" && metadataHub.trim()) return metadataHub.trim();
  const productHub = observation.product.trim().split(/\s+/)[0];
  return productHub || observation.market_venue;
}

export function marketObservationTenor(observation: MarketObservationLike): string {
  const metadataTenor = observation.metadata_json?.tenor;
  if (typeof metadataTenor === "string" && metadataTenor.trim()) {
    return metadataTenor.trim().toLowerCase();
  }
  return observation.product.trim().toLowerCase();
}

export function isGasPriceObservation(observation: MarketObservationLike): boolean {
  const unit = (observation.unit ?? "").toUpperCase();
  return unit.includes("MWH") && normalizedCurrency(observation.currency).length === 3;
}

export function newestObservation<T extends MarketObservationLike>(rows: T[]): T | null {
  return rows.reduce<T | null>((latest, row) => {
    if (!latest) return row;
    const rowTime = timestampMs(row.observed_at_utc ?? row.period_start_utc);
    const latestTime = timestampMs(latest.observed_at_utc ?? latest.period_start_utc);
    return rowTime > latestTime ? row : latest;
  }, null);
}

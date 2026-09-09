import type { IntradayOpportunityDTO, MarketQuoteDTO } from "@/api/client";

export interface MarketOverviewComparison {
  hub: string;
  quote: MarketQuoteDTO | null;
  bid: number | null;
  ask: number | null;
  mid: number | null;
  priceUnit: string | null;
  spread: number | null;
  spreadUnit: string | null;
  opportunity: IntradayOpportunityDTO | null;
  contextTitle: string;
}

function normalized(value: string | null | undefined): string {
  return value?.trim().toLowerCase().replace(/\s+/g, " ") ?? "";
}

function normalizedUnit(value: string | null | undefined): string {
  return normalized(value).replace(/\s*\/\s*/g, "/");
}

function finiteNumber(value: number | null | undefined): number | null {
  return value != null && Number.isFinite(value) ? value : null;
}

function timestamp(value: string | null | undefined): number | null {
  if (!value) return null;
  const parsed = Date.parse(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function sameTimestamp(left: string | null | undefined, right: string | null | undefined): boolean {
  const leftMs = timestamp(left);
  const rightMs = timestamp(right);
  return leftMs !== null && rightMs !== null && leftMs === rightMs;
}

function latestQuoteByHub(quotes: readonly MarketQuoteDTO[]): Map<string, MarketQuoteDTO> {
  const latest = new Map<string, MarketQuoteDTO>();
  [...quotes]
    .sort((left, right) => (timestamp(right.observed_at_utc) ?? 0) - (timestamp(left.observed_at_utc) ?? 0))
    .forEach((quote) => {
      const hub = normalized(quote.hub).toUpperCase();
      if (hub && !latest.has(hub)) latest.set(hub, quote);
    });
  return latest;
}

function basisOf(quote: MarketQuoteDTO | null): string | null {
  if (!quote?.metadata_json) return null;
  for (const key of ["price_basis", "basis", "price_level"]) {
    const value = quote.metadata_json[key];
    if (typeof value === "string" && value.trim()) return value.trim();
  }
  return null;
}

function quotePriceUnit(quote: MarketQuoteDTO | null): string | null {
  if (!quote) return null;
  const currency = quote.currency.trim().toUpperCase();
  const unit = quote.unit.trim();
  if (!currency || !unit) return null;
  if (unit.includes("/")) {
    const [unitCurrency, quantity] = unit.split("/").map((part) => part.trim());
    if (unit.split("/").length !== 2 || !unitCurrency || !quantity || unitCurrency.toUpperCase() !== currency) {
      return null;
    }
    return `${currency}/${quantity}`;
  }
  return `${currency}/${unit}`;
}

function comparisonUnit(opportunity: IntradayOpportunityDTO): string | null {
  const currency = opportunity.comparison_currency.trim().toUpperCase();
  const unit = opportunity.comparison_unit.trim();
  if (!currency || !unit) return null;
  if (unit.includes("/")) {
    const [unitCurrency, quantity] = unit.split("/").map((part) => part.trim());
    if (unit.split("/").length !== 2 || !unitCurrency || !quantity || unitCurrency.toUpperCase() !== currency) {
      return null;
    }
    return `${currency}/${quantity}`;
  }
  return `${currency}/${unit}`;
}

function opportunityIsCurrent(opportunity: IntradayOpportunityDTO, nowMs: number): boolean {
  if (normalized(opportunity.status) === "expired") return false;
  const validUntilMs = timestamp(opportunity.valid_until_utc);
  return validUntilMs !== null && validUntilMs > nowMs;
}

export function nextMarketOverviewExpiryMs(
  opportunities: readonly IntradayOpportunityDTO[],
  nowMs: number,
): number | null {
  const futureExpiries = opportunities
    .filter((opportunity) => normalized(opportunity.status) !== "expired")
    .map((opportunity) => timestamp(opportunity.valid_until_utc))
    .filter((expiryMs): expiryMs is number => expiryMs !== null && expiryMs > nowMs);
  return futureExpiries.length > 0 ? Math.min(...futureExpiries) : null;
}

function opportunityMatchesCurrentQuotes(
  opportunity: IntradayOpportunityDTO,
  hub: string,
  quote: MarketQuoteDTO | null,
  ttfQuote: MarketQuoteDTO | null,
  nowMs: number,
): boolean {
  if (!quote || !ttfQuote || !opportunityIsCurrent(opportunity, nowMs)) return false;
  if (opportunity.buy_hub.trim().toUpperCase() !== hub) return false;
  if (opportunity.sell_hub.trim().toUpperCase() !== "TTF") return false;
  if (opportunity.buy_quote_id !== quote.quote_id || opportunity.sell_quote_id !== ttfQuote.quote_id) {
    return false;
  }
  if (normalized(opportunity.product) !== normalized(quote.product)) return false;
  if (normalized(opportunity.product) !== normalized(ttfQuote.product)) return false;
  if (!sameTimestamp(opportunity.delivery_start_utc, quote.delivery_start_utc)) return false;
  if (!sameTimestamp(opportunity.delivery_start_utc, ttfQuote.delivery_start_utc)) return false;
  if (!sameTimestamp(opportunity.delivery_end_utc, quote.delivery_end_utc)) return false;
  if (!sameTimestamp(opportunity.delivery_end_utc, ttfQuote.delivery_end_utc)) return false;
  if (normalizedUnit(quote.unit) !== normalizedUnit(ttfQuote.unit)) return false;
  // Native currencies may differ only on this backend-proven path; the
  // opportunity carries the normalized comparison currency and unit.
  if (!quotePriceUnit(quote) || !quotePriceUnit(ttfQuote)) return false;
  if (!comparisonUnit(opportunity) || finiteNumber(opportunity.gross_spread) === null) return false;

  const quoteBasis = basisOf(quote);
  const ttfBasis = basisOf(ttfQuote);
  if ((quoteBasis === null) !== (ttfBasis === null)) return false;
  return quoteBasis === null || normalized(quoteBasis) === normalized(ttfBasis);
}

function contextTitle(
  quote: MarketQuoteDTO | null,
  opportunity: IntradayOpportunityDTO | null,
): string {
  const product = opportunity?.product ?? quote?.product ?? "unavailable";
  const deliveryStart = opportunity?.delivery_start_utc ?? quote?.delivery_start_utc ?? "unavailable";
  const deliveryEnd = opportunity?.delivery_end_utc ?? quote?.delivery_end_utc ?? "unavailable";
  const basis = basisOf(quote) ?? "unavailable";
  const priceUnit = quotePriceUnit(quote) ?? "unavailable";
  const spreadBasis = opportunity
    ? comparisonUnit(opportunity) ?? "unavailable"
    : "unavailable";
  const provenance = opportunity
    ? `${opportunity.opportunity_id}; ${opportunity.source_refs.join(", ") || "source unavailable"}`
    : "unavailable";
  return [
    `product=${product}`,
    `delivery=${deliveryStart}/${deliveryEnd}`,
    `basis=${basis}`,
    `quote_unit=${priceUnit}`,
    `spread_basis=${spreadBasis}`,
    `spread_source=${provenance}`,
  ].join("; ");
}

export function marketQuoteMid(quote: MarketQuoteDTO | null): number | null {
  if (!quote) return null;
  const bid = finiteNumber(quote.bid_price);
  const ask = finiteNumber(quote.ask_price);
  return bid !== null && ask !== null ? (bid + ask) / 2 : null;
}

export function formatQuoteBidAsk(
  bid: number | null,
  ask: number | null,
  unit: string | null,
): string {
  const bidText = bid === null ? "n/a" : bid.toFixed(2);
  const askText = ask === null ? "n/a" : ask.toFixed(2);
  return unit ? `${bidText} / ${askText} ${unit}` : `${bidText} / ${askText}`;
}

export function buildMarketOverviewComparisons(
  hubs: readonly string[],
  quotes: readonly MarketQuoteDTO[],
  opportunities: readonly IntradayOpportunityDTO[],
  nowMs: number = Date.now(),
): MarketOverviewComparison[] {
  const latestQuotes = latestQuoteByHub(quotes);
  const ttfQuote = latestQuotes.get("TTF") ?? null;

  return hubs.map((hub) => {
    const quote = latestQuotes.get(hub.toUpperCase()) ?? null;
    const opportunity = hub.toUpperCase() === "TTF"
      ? null
      : opportunities.find((candidate) => opportunityMatchesCurrentQuotes(
        candidate,
        hub.toUpperCase(),
        quote,
        ttfQuote,
        nowMs,
      )) ?? null;
    return {
      hub,
      quote,
      bid: finiteNumber(quote?.bid_price),
      ask: finiteNumber(quote?.ask_price),
      mid: marketQuoteMid(quote),
      priceUnit: quotePriceUnit(quote),
      spread: opportunity?.gross_spread ?? null,
      spreadUnit: opportunity ? comparisonUnit(opportunity) : null,
      opportunity,
      contextTitle: contextTitle(quote, opportunity),
    };
  });
}

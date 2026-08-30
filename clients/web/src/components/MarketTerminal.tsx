import { useMemo, useState } from "react";
import type {
  FxRateDTO,
  IntradayOpportunityDTO,
  MarketQuoteDTO,
  MarketSpreadDTO,
  NormalizedMarketObsDTO,
  SourceSystemDTO,
} from "@/api/client";
import { IntradayDecisionFeed } from "@/components/IntradayDecisionFeed";

type Translate = (key: string) => string;

interface MarketTerminalProps {
  markets: NormalizedMarketObsDTO[];
  marketSpreads: MarketSpreadDTO[];
  marketQuotes: MarketQuoteDTO[];
  intradayOpportunities: IntradayOpportunityDTO[];
  fxRates: FxRateDTO[];
  sources: SourceSystemDTO[];
  lastUpdatedAtUtc: string | null;
  onRefresh: () => Promise<void>;
  t: Translate;
}

interface HubDefinition {
  hub: string;
  region: string;
  label: string;
}

interface HubTerminalRow extends HubDefinition {
  latest: NormalizedMarketObsDTO | null;
  history: NormalizedMarketObsDTO[];
  spreadToTtf: number | null;
  tenor: string;
  sourceLabel: string;
  simulated: boolean;
}

interface SourceMatrixRow {
  sourceSystem: string;
  latestObservedAtUtc: string | null;
  hubs: string[];
  priceTiming: string;
  updateIntervalSeconds: number | null;
  simulated: boolean;
}

const marketMajorHubs: HubDefinition[] = [
  { hub: "TTF", region: "Netherlands", label: "TTF" },
  { hub: "NBP", region: "Great Britain", label: "NBP" },
  { hub: "THE", region: "Germany", label: "THE" },
  { hub: "PEG", region: "France", label: "PEG" },
  { hub: "ZTP", region: "Belgium", label: "ZTP" },
  { hub: "PSV", region: "Italy", label: "PSV" },
];

const marketTenorOrder = ["within-day", "day-ahead", "weekend", "month-ahead"];
const simulatedPriceSourceSystems = ["EEX_Sim", "ICE_OCM_Sim", "Trayport_Sim", "ICIS_Sim"];
const marketSourceOrder = [
  "ICE_OCM_Sim",
  "EEX_Sim",
  "Trayport_Sim",
  "ICIS_Sim",
  "ICE_OCM",
  "EEX",
  "TRAYPORT",
  "ICIS",
];

const gasPriceSources = new Set([
  "EEX",
  "ICE_OCM",
  "TRAYPORT",
  "PLATTS",
  "ICIS",
  "ARGUS",
  "KPLER",
  ...simulatedPriceSourceSystems.map((source) => source.toUpperCase()),
]);

const compareObservedDesc = (
  left: { observed_at_utc: string },
  right: { observed_at_utc: string },
): number => Date.parse(right.observed_at_utc) - Date.parse(left.observed_at_utc);

const isLaterTimestamp = (candidate: string, current: string | null | undefined): boolean => (
  !current || Date.parse(candidate) > Date.parse(current)
);

const formatPrice = (row: NormalizedMarketObsDTO | null): string => {
  if (!row) return "n/a";
  const unit = row.unit.toUpperCase().includes(row.currency.toUpperCase())
    ? row.unit
    : `${row.currency}/${row.unit}`;
  return `${row.price.toFixed(2)} ${unit}`;
};

const formatSpread = (value: number | null, unit?: string): string => {
  if (value == null) return "n/a";
  const prefix = value > 0 ? "+" : "";
  return `${prefix}${value.toFixed(2)} ${unit ?? "MWh"}`;
};

const getObservedTime = (row: NormalizedMarketObsDTO): string =>
  row.observed_at_utc ?? row.period_end_utc ?? row.period_start_utc;

const metadataValue = (row: NormalizedMarketObsDTO, key: string): string | null => {
  const value = row.metadata_json?.[key];
  return typeof value === "string" && value.trim() ? value.trim() : null;
};

const metadataNumber = (row: NormalizedMarketObsDTO, key: string): number | null => {
  const value = row.metadata_json?.[key];
  if (typeof value === "number" && Number.isFinite(value)) return value;
  if (typeof value === "string" && Number.isFinite(Number(value))) return Number(value);
  return null;
};

const tenorLabel = (tenor: string, t: Translate): string => {
  if (tenor === "within-day") return t("market.tenor_within_day");
  if (tenor === "weekend") return t("market.tenor_weekend");
  if (tenor === "month-ahead") return t("market.tenor_month_ahead");
  return t("market.tenor_day_ahead");
};

const formatTimestamp = (value: string | null | undefined): string => {
  if (!value) return "n/a";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
};

const formatCadence = (seconds: number | null): string => {
  if (seconds == null) return "n/a";
  if (seconds < 60) return `${seconds.toFixed(0)}s`;
  if (seconds < 3600) return `${Math.round(seconds / 60)}m`;
  return `${Math.round(seconds / 3600)}h`;
};

const sourceLabel = (row: NormalizedMarketObsDTO | null): string => {
  if (!row) return "n/a";
  return row.source_system ?? row.market_venue;
};

const sourceSystemRank = (sourceSystem: string): number => {
  const index = marketSourceOrder.indexOf(sourceSystem);
  return index === -1 ? marketSourceOrder.length : index;
};

const isSimulatedSource = (row: NormalizedMarketObsDTO | null): boolean => {
  if (!row) return false;
  return row.source_system?.toLowerCase().includes("_sim") === true || row.metadata_json?.simulated === true;
};

const sortNewestFirst = (left: NormalizedMarketObsDTO, right: NormalizedMarketObsDTO): number =>
  Date.parse(getObservedTime(right)) - Date.parse(getObservedTime(left));

function MarketSparkline({ values, label }: { values: number[]; label: string }) {
  if (values.length < 2) {
    return <div className="market-sparkline empty" aria-label={label} />;
  }

  const min = Math.min(...values);
  const max = Math.max(...values);
  const span = Math.max(max - min, 0.01);
  const points = values.map((value, index) => {
    const x = (index / Math.max(values.length - 1, 1)) * 100;
    const y = 28 - ((value - min) / span) * 24;
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  }).join(" ");

  return (
    <svg className="market-sparkline" viewBox="0 0 100 32" role="img" aria-label={label}>
      <polyline points={points} />
    </svg>
  );
}

const quoteMid = (quote: MarketQuoteDTO | null | undefined): number | null => {
  if (!quote) return null;
  if (quote.last_price != null && Number.isFinite(quote.last_price)) return quote.last_price;
  if (
    quote.bid_price != null && Number.isFinite(quote.bid_price) &&
    quote.ask_price != null && Number.isFinite(quote.ask_price)
  ) {
    return (quote.bid_price + quote.ask_price) / 2;
  }
  if (quote.bid_price != null && Number.isFinite(quote.bid_price)) return quote.bid_price;
  if (quote.ask_price != null && Number.isFinite(quote.ask_price)) return quote.ask_price;
  return null;
};

const quoteIdentityKey = (quote: MarketQuoteDTO): string => [
  quote.source_system,
  quote.venue,
  quote.instrument_id,
  quote.hub.toUpperCase(),
  quote.product.toLowerCase(),
  quote.currency,
  quote.unit,
].join(":");

const quoteAgeSeconds = (quote: MarketQuoteDTO | null | undefined): number | null => {
  if (!quote) return null;
  const observedAtMs = new Date(quote.observed_at_utc).getTime();
  if (!Number.isFinite(observedAtMs)) return null;
  return Math.max((Date.now() - observedAtMs) / 1_000, 0);
};

const formatAge = (seconds: number | null): string => {
  if (seconds == null) return "n/a";
  if (seconds < 60) return `${Math.round(seconds)}s`;
  if (seconds < 3_600) return `${Math.round(seconds / 60)}m`;
  if (seconds < 86_400) return `${Math.round(seconds / 3_600)}h`;
  return `${Math.round(seconds / 86_400)}d`;
};

const quoteHistoryValues = (quotes: MarketQuoteDTO[]): number[] => quotes
  .slice()
  .sort((left, right) => Date.parse(left.observed_at_utc) - Date.parse(right.observed_at_utc))
  .map(quoteMid)
  .filter((price): price is number => price !== null)
  .slice(-40);

const observationHistoryValues = (rows: NormalizedMarketObsDTO[]): number[] => rows
  .slice()
  .sort((left, right) => Date.parse(getObservedTime(left)) - Date.parse(getObservedTime(right)))
  .map((row) => row.price)
  .filter((price) => Number.isFinite(price))
  .slice(-40);

const quoteDelta = (quotes: MarketQuoteDTO[]): number | null => {
  const values = quoteHistoryValues(quotes);
  if (values.length < 2) return null;
  return values[values.length - 1] - values[values.length - 2];
};

const formatDelta = (value: number | null): string => {
  if (value == null) return "n/a";
  return `${value > 0 ? "+" : ""}${value.toFixed(3)}`;
};

export function MarketTerminal({
  markets,
  marketSpreads,
  marketQuotes,
  intradayOpportunities,
  fxRates,
  sources,
  lastUpdatedAtUtc,
  onRefresh,
  t,
}: MarketTerminalProps) {
  const [activeTenor, setActiveTenor] = useState("day-ahead");

  const quoteHistoryByIdentity = useMemo(() => {
    const result = new Map<string, MarketQuoteDTO[]>();
    marketQuotes.forEach((quote) => {
      const key = quoteIdentityKey(quote);
      result.set(key, [...(result.get(key) ?? []), quote]);
    });
    result.forEach((quotes) => quotes.sort(compareObservedDesc));
    return result;
  }, [marketQuotes]);

  const quoteHistoryByHubTenor = useMemo(() => {
    const result = new Map<string, MarketQuoteDTO[]>();
    marketQuotes.forEach((quote) => {
      const key = `${quote.hub.toUpperCase()}:${quote.product.toLowerCase()}`;
      result.set(key, [...(result.get(key) ?? []), quote]);
    });
    result.forEach((quotes) => quotes.sort(compareObservedDesc));
    return result;
  }, [marketQuotes]);

  const latestQuoteByHubTenor = useMemo(() => new Map(
    Array.from(quoteHistoryByHubTenor.entries()).map(([key, quotes]) => [key, quotes[0]]),
  ), [quoteHistoryByHubTenor]);

  const sourceQuoteRows = useMemo(() => Array.from(quoteHistoryByIdentity.entries())
    .filter(([, quotes]) => quotes[0]?.product.toLowerCase() === activeTenor)
    .map(([key, history]) => ({ key, history, latest: history[0] }))
    .filter((row): row is { key: string; history: MarketQuoteDTO[]; latest: MarketQuoteDTO } => (
      Boolean(row.latest)
    ))
    .sort((left, right) => {
      const leftHubRank = marketMajorHubs.findIndex((hub) => hub.hub === left.latest.hub);
      const rightHubRank = marketMajorHubs.findIndex((hub) => hub.hub === right.latest.hub);
      const hubDelta = (leftHubRank < 0 ? marketMajorHubs.length : leftHubRank)
        - (rightHubRank < 0 ? marketMajorHubs.length : rightHubRank);
      if (hubDelta !== 0) return hubDelta;
      const sourceDelta = sourceSystemRank(left.latest.source_system)
        - sourceSystemRank(right.latest.source_system);
      if (sourceDelta !== 0) return sourceDelta;
      return compareObservedDesc(left.latest, right.latest);
    }), [activeTenor, quoteHistoryByIdentity]);

  const spreadToTtfByHubTenor = useMemo(() => {
    const direct = new Map<string, number>();
    const reverse = new Map<string, number>();
    marketSpreads.forEach((row) => {
      direct.set(`${row.from_hub}:${row.to_hub}:${row.period}`, row.spread_eur_mwh);
      reverse.set(`${row.to_hub}:${row.from_hub}:${row.period}`, row.spread_eur_mwh);
    });
    return { direct, reverse };
  }, [marketSpreads]);

  const groupedByTenor = useMemo(() => {
    const grouped = new Map<string, NormalizedMarketObsDTO[]>();
    markets
      .filter((row) => row.is_gas_price && Boolean(row.hub))
      .forEach((row) => {
        const key = `${row.hub}:${row.tenor}`;
        grouped.set(key, [...(grouped.get(key) ?? []), row]);
      });
    return grouped;
  }, [markets]);

  const spreadToTtfFor = (hub: string, tenor: string): number | null => {
    if (hub.toUpperCase() === "TTF") return null;
    const key = `${hub.toUpperCase()}:TTF:${tenor}`;
    const direct = spreadToTtfByHubTenor.direct.get(key);
    if (direct !== undefined) return direct;
    const reverse = spreadToTtfByHubTenor.reverse.get(key);
    return reverse !== undefined ? -reverse : null;
  };

  const marketRowsByTenor = useMemo(() => {
    const result = new Map<string, HubTerminalRow[]>();
    marketTenorOrder.forEach((tenor) => {
      result.set(tenor, marketMajorHubs.map((definition): HubTerminalRow => {
        const history = (groupedByTenor.get(`${definition.hub}:${tenor}`) ?? []).slice().sort(sortNewestFirst);
        const latest = history[0] ?? null;
        return {
          ...definition,
          latest,
          history,
          spreadToTtf: spreadToTtfFor(definition.hub, tenor),
          tenor,
          sourceLabel: sourceLabel(latest),
          simulated: isSimulatedSource(latest),
        };
      }));
    });
    return result;
  }, [groupedByTenor, spreadToTtfByHubTenor]);

  const marketRows = marketRowsByTenor.get(activeTenor) ?? [];
  const curveLanes = marketMajorHubs.map((definition) => {
    const tenorRows = marketTenorOrder.map((tenor) => marketRowsByTenor.get(tenor)?.find((row) => row.hub === definition.hub));
    return {
      ...definition,
      tenorRows,
    };
  });

  const allTenorRows = Array.from(marketRowsByTenor.values()).flat();
  const terminalRows = marketRows.length > 0 ? marketRows : allTenorRows;
  const priceRowsForStrip = terminalRows.length > 0
    ? terminalRows
    : marketMajorHubs.map((definition): HubTerminalRow => ({
        ...definition,
        latest: null,
        history: [],
        spreadToTtf: null,
        tenor: "day-ahead",
        sourceLabel: "n/a",
        simulated: false,
      }));

  const sourceMatrixRows = useMemo<SourceMatrixRow[]>(() => {
    const grouped = new Map<string, SourceMatrixRow>();
    markets
      .filter((row) => row.is_gas_price && Boolean(row.hub))
      .forEach((row) => {
        if (row.tenor !== activeTenor) return;
        const sourceSystem = row.source_system ?? row.market_venue;
        const current = grouped.get(sourceSystem);
        const observedAt = getObservedTime(row);
        const isNewer = isLaterTimestamp(observedAt, current?.latestObservedAtUtc);
        grouped.set(sourceSystem, {
          sourceSystem,
          latestObservedAtUtc: isNewer ? observedAt : current?.latestObservedAtUtc ?? observedAt,
          hubs: Array.from(new Set([...(current?.hubs ?? []), row.hub])).sort(),
          priceTiming: isNewer
            ? metadataValue(row, "price_timing") ?? row.tenor
            : current?.priceTiming ?? row.tenor,
          updateIntervalSeconds: isNewer
            ? metadataNumber(row, "update_interval_seconds")
            : current?.updateIntervalSeconds ?? null,
          simulated: (current?.simulated ?? false) || isSimulatedSource(row),
        });
      });
    marketQuotes.forEach((quote) => {
      if (quote.product.toLowerCase() !== activeTenor) return;
      const sourceSystem = quote.source_system || quote.venue;
      const current = grouped.get(sourceSystem);
      const isNewer = isLaterTimestamp(quote.observed_at_utc, current?.latestObservedAtUtc);
      grouped.set(sourceSystem, {
        sourceSystem,
        latestObservedAtUtc: isNewer
          ? quote.observed_at_utc
          : current?.latestObservedAtUtc ?? quote.observed_at_utc,
        hubs: Array.from(new Set([...(current?.hubs ?? []), quote.hub])).sort(),
        priceTiming: isNewer
          ? String(quote.metadata_json?.price_level ?? "L1 bid/ask")
          : current?.priceTiming ?? "L1 bid/ask",
        updateIntervalSeconds: isNewer
          ? Number(quote.metadata_json?.update_interval_seconds ?? 0) || null
          : current?.updateIntervalSeconds ?? null,
        simulated: (current?.simulated ?? false) || quote.simulated,
      });
    });
    return Array.from(grouped.values())
      .sort((left, right) => {
        const rankDelta = sourceSystemRank(left.sourceSystem) - sourceSystemRank(right.sourceSystem);
        if (rankDelta !== 0) return rankDelta;
        return left.sourceSystem.localeCompare(right.sourceSystem);
      });
  }, [activeTenor, marketQuotes, markets]);

  const priceSourceSummary = useMemo(() => {
    const priceSources = sources.filter((source) => source.category === "price");
    return {
      registered: priceSources.length,
      active: priceSources.filter((source) => source.connectivity_status === "active").length,
      missingCredentials: priceSources.filter((source) => source.credential_state === "missing").length,
      runtimeRecords: priceSources.reduce((total, source) => total + source.live_record_count, 0),
      feeds: priceSources.filter((source) => gasPriceSources.has(source.source_system.toUpperCase())),
    };
  }, [sources]);

  const marketUnavailableRows = priceRowsForStrip.filter((row) => (
    row.latest === null && !latestQuoteByHubTenor.has(`${row.hub}:${row.tenor}`)
  ));
  const activeFeedLabels = priceSourceSummary.feeds
    .filter((source) => source.connectivity_status === "active")
    .map((source) => source.source_system);
  const displayFeeds = activeFeedLabels.length > 0
    ? activeFeedLabels.join(" / ")
    : priceSourceSummary.feeds.slice(0, 4).map((source) => source.source_system).join(" / ");

  return (
    <div className="workspace-grid market-page market-terminal-board">
      <div className="workspace-panel span-3 market-terminal-hero">
        <div className="section-heading">
          <span className="eyebrow">{t("panel.market")}</span>
          <strong>{t("market.terminal")}</strong>
        </div>
        <p className="panel-copy">{t("market.live_exchange_prices")}</p>
        <div className="market-live-status">
          <span>{t("market.live_polling")}</span>
          <strong>{formatTimestamp(lastUpdatedAtUtc)}</strong>
          <button
            type="button"
            onClick={() => {
              void onRefresh();
            }}
          >
            {t("market.refresh")}
          </button>
        </div>
        <div className="market-tenor-tabs" aria-label={t("market.tenor_tabs")}>
          {marketTenorOrder.map((tenor) => (
            <button
              key={`market-tenor-${tenor}`}
              type="button"
              className={activeTenor === tenor ? "market-tenor-tab active" : "market-tenor-tab"}
              aria-pressed={activeTenor === tenor}
              onClick={() => setActiveTenor(tenor)}
            >
              {tenorLabel(tenor, t)}
            </button>
          ))}
        </div>
        <div className="market-terminal-strip" aria-label={t("market.terminal")}>
          {priceRowsForStrip.map((row) => {
            const quote = latestQuoteByHubTenor.get(`${row.hub}:${row.tenor}`);
            const history = quoteHistoryByHubTenor.get(`${row.hub}:${row.tenor}`) ?? [];
            const delta = quoteDelta(history);
            const simulated = quote?.simulated || row.simulated;
            const sourceLabel = quote?.source_system ?? row.sourceLabel;
            const sourceDescription = simulated
              ? `${sourceLabel} · ${t("market.simulated_source")}`
              : sourceLabel;
            return (
            <div
              key={`ticker-${row.hub}-${row.tenor}`}
              className={`market-price-ticker ${quote || row.latest ? "is-live" : "is-waiting"}`}
            >
              <span>{row.hub}</span>
              <strong>
                {quote
                  ? `${formatPriceValue(quote.bid_price)} / ${formatPriceValue(quote.ask_price)}`
                  : formatPrice(row.latest)}
              </strong>
              <small>
                {quote ? t("market.bid_ask") : tenorLabel(row.tenor, t)} · {t("market.quote_age")} {formatAge(quoteAgeSeconds(quote))}
              </small>
              <div className="market-ticker-meta">
                <em
                  className={`market-source-pill ${simulated ? "simulated" : ""}`}
                  aria-label={sourceDescription}
                  title={sourceDescription}
                >
                  {sourceLabel}
                </em>
                <span className={`market-price-delta ${delta === null ? "flat" : delta > 0 ? "up" : delta < 0 ? "down" : "flat"}`}>
                  {t("market.tick_change")} {formatDelta(delta)}
                </span>
              </div>
            </div>
          );})}
        </div>
        <div className="market-curve-lanes">
          {curveLanes.map((lane) => (
            <div key={`curve-lane-${lane.hub}`}>
              <strong>{lane.hub}</strong>
              {lane.tenorRows.map((row, index) => {
                const tenor = marketTenorOrder[index];
                const quote = latestQuoteByHubTenor.get(`${lane.hub}:${tenor}`);
                const price = quoteMid(quote) ?? row?.latest?.price ?? null;
                return (
                  <span key={`curve-lane-${lane.hub}-${tenor}`}>
                    {tenorLabel(tenor, t)} {price === null ? "n/a" : price.toFixed(2)}
                  </span>
                );
              })}
            </div>
          ))}
        </div>
        <div className="market-source-matrix-title">
          <strong>{t("market.source_matrix")}</strong>
          <span>{tenorLabel(activeTenor, t)}</span>
        </div>
        <div className="market-source-matrix" role="table" aria-label={t("market.source_matrix")}>
          <div className="market-source-matrix-row header" role="row">
            <span role="columnheader">{t("panel.source")}</span>
            <span role="columnheader">{t("market.timing")}</span>
            <span role="columnheader">{t("market.hubs")}</span>
            <span role="columnheader">{t("market.cadence")}</span>
          </div>
          {sourceMatrixRows.map((row) => (
            <div key={`source-matrix-${row.sourceSystem}`} className="market-source-matrix-row" role="row">
              <strong role="rowheader">{row.sourceSystem}</strong>
              <span role="cell">{row.priceTiming}</span>
              <span role="cell">{row.hubs.length > 0 ? row.hubs.join(" / ") : "n/a"}</span>
              <span role="cell">
                {formatCadence(row.updateIntervalSeconds)}
                {row.simulated ? ` / ${t("market.simulated_source")}` : ""}
              </span>
            </div>
          ))}
          {sourceMatrixRows.length === 0 && (
            <div className="market-source-matrix-row" role="row">
              <strong role="rowheader">{t("data.unavailable")}</strong>
              <span role="cell">{activeTenor}</span>
              <span role="cell">n/a</span>
              <span role="cell">{t("market.awaiting_feed")}</span>
            </div>
          )}
        </div>
      </div>

      <div className="workspace-panel span-3 market-opportunity-panel">
        <IntradayDecisionFeed
          opportunities={intradayOpportunities}
          lastUpdatedAtUtc={lastUpdatedAtUtc}
          t={t}
        />
      </div>

      <div className="workspace-panel span-2">
        <div className="section-heading">
          <span className="eyebrow">{t("market.latest")}</span>
          <strong>{t("market.title")}</strong>
        </div>
        <div className="market-terminal-table" role="table" aria-label={t("market.title")}>
          <div className="market-terminal-row header" role="row">
            <span role="columnheader">{t("market.hub")}</span>
            <span role="columnheader">{t("market.venue_product")}</span>
            <span role="columnheader">{t("market.price")}</span>
            <span role="columnheader">{t("market.freshness")}</span>
            <span role="columnheader">{t("market.trend")}</span>
          </div>
          {sourceQuoteRows.map(({ key, latest, history }) => (
            <div key={`market-terminal-${key}`} className="market-terminal-row" role="row">
              <strong data-label={t("market.hub")} role="rowheader">{latest.hub}</strong>
              <span data-label={t("market.venue_product")} role="cell">
                {latest.venue} {latest.product} · {latest.source_system}
              </span>
              <span data-label={t("market.price")} role="cell">
                {formatPriceValue(latest.bid_price)} / {formatPriceValue(latest.ask_price)} {latest.currency}/{latest.unit}
              </span>
              <span data-label={t("market.freshness")} role="cell">
                {formatAge(quoteAgeSeconds(latest))} · {latest.freshness}
              </span>
              <span className="market-sparkline-cell" data-label={t("market.trend")} role="cell">
                <MarketSparkline
                  values={quoteHistoryValues(history)}
                  label={`${latest.hub} ${latest.source_system} ${tenorLabel(activeTenor, t)} ${t("market.trend")}`}
                />
              </span>
            </div>
          ))}
          {priceRowsForStrip
            .filter((row) => !sourceQuoteRows.some(({ latest }) => latest.hub === row.hub))
            .map((row) => (
              <div key={`market-terminal-fallback-${row.hub}`} className="market-terminal-row" role="row">
                <strong data-label={t("market.hub")} role="rowheader">{row.hub}</strong>
                <span data-label={t("market.venue_product")} role="cell">
                  {row.latest
                    ? `${row.latest.market_venue} ${row.latest.product} · ${row.sourceLabel}`
                    : row.region}
                </span>
                <span data-label={t("market.price")} role="cell">{formatPrice(row.latest)}</span>
                <span data-label={t("market.freshness")} role="cell">
                  {row.latest
                    ? `${row.latest.freshness ?? "n/a"} · ${metadataValue(row.latest, "price_timing") ?? row.tenor}`
                    : t("market.awaiting_feed")}
                </span>
                <span className="market-sparkline-cell" data-label={t("market.trend")} role="cell">
                  <MarketSparkline
                    values={observationHistoryValues(row.history)}
                    label={`${row.hub} ${tenorLabel(row.tenor, t)} ${t("market.trend")}`}
                  />
                </span>
              </div>
            ))}
        </div>
        {marketUnavailableRows.length > 0 && (
          <p className="market-terminal-note">
            {t("market.no_price_rows")}: {marketUnavailableRows.map((row) => row.hub).join(", ")}
          </p>
        )}
      </div>

      <div className="workspace-panel market-region-comparison">
        <h3>{t("market.region_comparison")}</h3>
        <div className="market-region-list">
          {priceRowsForStrip.map((row) => (
            <div key={`region-${row.hub}`}>
              <span>{row.label}</span>
              <strong>{(() => {
                const quote = latestQuoteByHubTenor.get(`${row.hub}:${row.tenor}`);
                const ttfQuote = latestQuoteByHubTenor.get(`TTF:${row.tenor}`);
                const liveMid = quoteMid(quote);
                const ttfMid = quoteMid(ttfQuote);
                const liveSpread = row.hub === "TTF"
                  ? 0
                  : liveMid !== null && ttfMid !== null
                    ? liveMid - ttfMid
                    : null;
                return formatSpread(
                  row.spreadToTtf ?? liveSpread,
                  quote ? `${quote.currency}/${quote.unit}` : row.latest?.unit,
                );
              })()}</strong>
              <small>{t("market.spread_to_ttf")}</small>
            </div>
          ))}
        </div>
      </div>

      <div className="workspace-panel market-source-quality">
        <h3>{t("market.source_quality")}</h3>
        <div className="metric-grid two-column">
          <div><span>{t("sources.total_sources")}</span><strong>{priceSourceSummary.registered}</strong></div>
          <div><span>{t("sources.active_sources")}</span><strong>{priceSourceSummary.active}</strong></div>
          <div><span>{t("sources.missing_credentials")}</span><strong>{priceSourceSummary.missingCredentials}</strong></div>
          <div><span>{t("sources.runtime_records")}</span><strong>{priceSourceSummary.runtimeRecords}</strong></div>
        </div>
        <p className="market-terminal-note">{displayFeeds || t("data.unavailable")}</p>
      </div>

      <div className="workspace-panel">
        <h3>{t("market.fx")}</h3>
        <div className="data-table market-fx-table">
          <div className="data-table-row header"><span>{t("market.pair")}</span><span>{t("market.rate")}</span><span>{t("market.observed")}</span><span>{t("panel.source")}</span></div>
          {fxRates.slice(0, 6).map((rate) => (
            <div key={`fx-row-${rate.pair}-${rate.observed_at_utc}`} className="data-table-row">
              <strong>{rate.pair}</strong>
              <span>{rate.rate.toFixed(4)}</span>
              <span>{formatTimestamp(rate.observed_at_utc)}</span>
              <span>{rate.source_system ?? t("market.ecb_source")}</span>
            </div>
          ))}
          {fxRates.length === 0 && (
            <div className="data-table-row"><strong>n/a</strong><span>n/a</span><span>n/a</span><span>{t("data.unavailable")}</span></div>
          )}
        </div>
      </div>
    </div>
  );
}

function formatPriceValue(value: number | null | undefined): string {
  return value == null || !Number.isFinite(value) ? "n/a" : value.toFixed(3);
}

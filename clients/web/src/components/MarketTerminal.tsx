import { useMemo, useState } from "react";
import type {
  FxRateDTO,
  IntradayOpportunityDTO,
  MarketObsDTO,
  MarketQuoteDTO,
  SourceSystemDTO,
} from "@/api/client";
import { IntradayDecisionFeed } from "@/components/IntradayDecisionFeed";

type Translate = (key: string) => string;

interface MarketTerminalProps {
  markets: MarketObsDTO[];
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
  latest: MarketObsDTO | null;
  history: MarketObsDTO[];
  spreadToTtf: number | null;
  tenor: string;
  sourceLabel: string;
  simulated: boolean;
}

interface SourceMatrixRow {
  sourceSystem: string;
  latest: MarketObsDTO | null;
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

const marketTenorOrder = ["within-day", "day-ahead", "month-ahead"];
const simulatedPriceSourceSystems = ["EEX_Sim", "ICE_OCM_Sim", "ICIS_Sim"];
const marketSourceOrder = [
  "ICE_OCM_Sim",
  "EEX_Sim",
  "ICIS_Sim",
  "ICE_OCM",
  "EEX",
  "ICIS",
  "TRAYPORT",
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

const formatPrice = (row: MarketObsDTO | null): string => {
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

const getObservedTime = (row: MarketObsDTO): string =>
  row.observed_at_utc ?? row.period_end_utc ?? row.period_start_utc;

const metadataValue = (row: MarketObsDTO, key: string): string | null => {
  const value = row.metadata_json?.[key];
  return typeof value === "string" && value.trim() ? value.trim() : null;
};

const metadataNumber = (row: MarketObsDTO, key: string): number | null => {
  const value = row.metadata_json?.[key];
  if (typeof value === "number" && Number.isFinite(value)) return value;
  if (typeof value === "string" && Number.isFinite(Number(value))) return Number(value);
  return null;
};

const tenorLabel = (tenor: string, t: Translate): string => {
  if (tenor === "within-day") return t("market.tenor_within_day");
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

const marketTenor = (row: MarketObsDTO): string => {
  const metadataTenor = metadataValue(row, "tenor");
  if (metadataTenor) return metadataTenor;
  const product = row.product.toLowerCase();
  if (product.includes("within")) return "within-day";
  if (product.includes("month")) return "month-ahead";
  if (product.includes("weekend")) return "weekend";
  return "day-ahead";
};

const sourceLabel = (row: MarketObsDTO | null): string => {
  if (!row) return "n/a";
  return row.source_system ?? row.market_venue;
};

const sourceSystemRank = (sourceSystem: string): number => {
  const index = marketSourceOrder.indexOf(sourceSystem);
  return index === -1 ? marketSourceOrder.length : index;
};

const isSimulatedSource = (row: MarketObsDTO | null): boolean => {
  if (!row) return false;
  return row.source_system?.toLowerCase().includes("_sim") === true || row.metadata_json?.simulated === true;
};

const isGasMarketObservation = (row: MarketObsDTO): boolean => {
  const source = row.source_system?.toUpperCase();
  const venue = row.market_venue.toUpperCase();
  const product = row.product.toUpperCase();
  if (source === "ECB" || venue === "ECB" || product.includes("/")) return false;
  return marketMajorHubs.some(({ hub }) => product.includes(hub) || venue.includes(hub));
};

const hubForObservation = (row: MarketObsDTO): string | null => {
  const text = `${row.market_venue} ${row.product}`.toUpperCase();
  return marketMajorHubs.find(({ hub }) => text.includes(hub))?.hub ?? null;
};

const sortNewestFirst = (left: MarketObsDTO, right: MarketObsDTO): number =>
  getObservedTime(right).localeCompare(getObservedTime(left));

function MarketSparkline({ rows }: { rows: MarketObsDTO[] }) {
  const values = rows
    .slice()
    .sort((left, right) => getObservedTime(left).localeCompare(getObservedTime(right)))
    .map((row) => row.price)
    .filter((price) => Number.isFinite(price));

  if (values.length < 2) {
    return <div className="market-sparkline empty" aria-label="n/a" />;
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
    <svg className="market-sparkline" viewBox="0 0 100 32" role="img" aria-label="price trend">
      <polyline points={points} />
    </svg>
  );
}

export function MarketTerminal({
  markets,
  marketQuotes,
  intradayOpportunities,
  fxRates,
  sources,
  lastUpdatedAtUtc,
  onRefresh,
  t,
}: MarketTerminalProps) {
  const [activeTenor, setActiveTenor] = useState("day-ahead");

  const latestQuoteByHubTenor = useMemo(() => {
    const result = new Map<string, MarketQuoteDTO>();
    [...marketQuotes]
      .sort((left, right) => right.observed_at_utc.localeCompare(left.observed_at_utc))
      .forEach((quote) => {
        const key = `${quote.hub.toUpperCase()}:${quote.product.toLowerCase()}`;
        if (!result.has(key)) result.set(key, quote);
      });
    return result;
  }, [marketQuotes]);

  const groupedByTenor = useMemo(() => {
    const grouped = new Map<string, MarketObsDTO[]>();
    markets.filter(isGasMarketObservation).forEach((row) => {
      const hub = hubForObservation(row);
      if (!hub) return;
      const key = `${hub}:${marketTenor(row)}`;
      grouped.set(key, [...(grouped.get(key) ?? []), row]);
    });
    return grouped;
  }, [markets]);

  const marketRowsByTenor = useMemo(() => {
    const result = new Map<string, HubTerminalRow[]>();
    marketTenorOrder.forEach((tenor) => {
      const ttfLatest = groupedByTenor.get(`TTF:${tenor}`)?.slice().sort(sortNewestFirst)[0] ?? null;
      result.set(tenor, marketMajorHubs.map((definition): HubTerminalRow => {
        const history = (groupedByTenor.get(`${definition.hub}:${tenor}`) ?? []).slice().sort(sortNewestFirst);
        const latest = history[0] ?? null;
        const spreadToTtf =
          latest && ttfLatest && latest.currency === ttfLatest.currency && latest.unit === ttfLatest.unit
            ? latest.price - ttfLatest.price
            : null;
        return {
          ...definition,
          latest,
          history,
          spreadToTtf,
          tenor,
          sourceLabel: sourceLabel(latest),
          simulated: isSimulatedSource(latest),
        };
      }));
    });
    return result;
  }, [groupedByTenor]);

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
    const grouped = new Map<string, MarketObsDTO[]>();
    markets.filter(isGasMarketObservation).forEach((row) => {
      if (marketTenor(row) !== activeTenor) return;
      const sourceSystem = row.source_system ?? row.market_venue;
      grouped.set(sourceSystem, [...(grouped.get(sourceSystem) ?? []), row]);
    });
    return Array.from(grouped.entries())
      .map(([sourceSystem, rows]) => {
        const sortedRows = rows.slice().sort(sortNewestFirst);
        const latest = sortedRows[0] ?? null;
        const hubs = Array.from(
          new Set(sortedRows.map(hubForObservation).filter((hub): hub is string => Boolean(hub))),
        ).sort();
        return {
          sourceSystem,
          latest,
          hubs,
          priceTiming: latest ? metadataValue(latest, "price_timing") ?? marketTenor(latest) : "n/a",
          updateIntervalSeconds: latest ? metadataNumber(latest, "update_interval_seconds") : null,
          simulated: isSimulatedSource(latest),
        };
      })
      .sort((left, right) => {
        const rankDelta = sourceSystemRank(left.sourceSystem) - sourceSystemRank(right.sourceSystem);
        if (rankDelta !== 0) return rankDelta;
        return left.sourceSystem.localeCompare(right.sourceSystem);
      });
  }, [activeTenor, markets]);

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

  const marketUnavailableRows = priceRowsForStrip.filter((row) => row.latest === null);
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
        <div className="market-tenor-tabs" aria-label="Price tenor">
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
            return (
            <div
              key={`ticker-${row.hub}-${row.tenor}-${quote?.observed_at_utc ?? "no-quote"}`}
              className={`market-price-ticker ${row.latest ? "is-live" : "is-waiting"}`}
            >
              <span>{row.hub}</span>
              <strong>
                {quote
                  ? `${formatPriceValue(quote.bid_price)} / ${formatPriceValue(quote.ask_price)}`
                  : formatPrice(row.latest)}
              </strong>
              <small>
                {quote ? "Bid / Ask" : row.tenor} / {quote?.freshness ?? row.latest?.freshness ?? t("market.awaiting_feed")}
              </small>
              <em className={`market-source-pill ${quote?.simulated || row.simulated ? "simulated" : ""}`}>
                {quote?.simulated || row.simulated ? t("market.simulated_source") : quote?.source_system ?? row.sourceLabel}
              </em>
            </div>
          );})}
        </div>
        <div className="market-curve-lanes">
          {curveLanes.map((lane) => (
            <div key={`curve-lane-${lane.hub}`}>
              <strong>{lane.hub}</strong>
              {lane.tenorRows.map((row, index) => (
                <span key={`curve-lane-${lane.hub}-${marketTenorOrder[index]}`}>
                  {tenorLabel(marketTenorOrder[index], t)} {row?.latest ? row.latest.price.toFixed(2) : "n/a"}
                </span>
              ))}
            </div>
          ))}
        </div>
        <div className="market-source-matrix-title">
          <strong>{t("market.source_matrix")}</strong>
          <span>{tenorLabel(activeTenor, t)}</span>
        </div>
        <div className="market-source-matrix" aria-label={t("market.source_matrix")}>
          <div className="market-source-matrix-row header">
            <span>{t("panel.source")}</span>
            <span>{t("market.timing")}</span>
            <span>{t("market.hubs")}</span>
            <span>{t("market.cadence")}</span>
          </div>
          {sourceMatrixRows.map((row) => (
            <div key={`source-matrix-${row.sourceSystem}`} className="market-source-matrix-row">
              <strong>{row.sourceSystem}</strong>
              <span>{row.priceTiming}</span>
              <span>{row.hubs.length > 0 ? row.hubs.join(" / ") : "n/a"}</span>
              <span>
                {formatCadence(row.updateIntervalSeconds)}
                {row.simulated ? ` / ${t("market.simulated_source")}` : ""}
              </span>
            </div>
          ))}
          {sourceMatrixRows.length === 0 && (
            <div className="market-source-matrix-row">
              <strong>{t("data.unavailable")}</strong>
              <span>{activeTenor}</span>
              <span>n/a</span>
              <span>{t("market.awaiting_feed")}</span>
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
        <div className="market-terminal-table">
          <div className="market-terminal-row header">
            <span>Hub</span>
            <span>Venue/Product</span>
            <span>{t("market.price")}</span>
            <span>{t("market.freshness")}</span>
            <span>Trend</span>
          </div>
          {priceRowsForStrip.map((row) => (
            <div key={`market-terminal-${row.hub}`} className="market-terminal-row">
              <strong data-label="Hub">{row.hub}</strong>
              <span data-label="Venue/Product">
                {row.latest ? `${row.latest.market_venue} ${row.latest.product}` : row.region}
              </span>
              <span data-label={t("market.price")}>{formatPrice(row.latest)}</span>
              <span data-label={t("market.freshness")}>
                {row.latest?.freshness ?? t("market.awaiting_feed")}
                {row.latest ? ` / ${metadataValue(row.latest, "price_timing") ?? row.tenor}` : ""}
              </span>
              <span className="market-sparkline-cell" data-label="Trend">
                <MarketSparkline rows={row.history} />
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
              <strong>{formatSpread(row.spreadToTtf, row.latest?.unit)}</strong>
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
        <div className="data-table">
          <div className="data-table-row header three"><span>Pair</span><span>Rate</span><span>{t("panel.source")}</span></div>
          {fxRates.slice(0, 6).map((rate) => (
            <div key={`fx-row-${rate.pair}-${rate.observed_at_utc}`} className="data-table-row three">
              <strong>{rate.pair}</strong>
              <span>{rate.rate.toFixed(4)}</span>
              <span>{rate.source_system ?? "ECB"}</span>
            </div>
          ))}
          {fxRates.length === 0 && (
            <div className="data-table-row three"><strong>n/a</strong><span>n/a</span><span>{t("data.unavailable")}</span></div>
          )}
        </div>
      </div>
    </div>
  );
}

function formatPriceValue(value: number | null | undefined): string {
  return value == null || !Number.isFinite(value) ? "n/a" : value.toFixed(3);
}

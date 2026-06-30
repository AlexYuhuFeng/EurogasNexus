import { useMemo } from "react";
import type { FxRateDTO, MarketObsDTO, SourceSystemDTO } from "@/api/client";

type Translate = (key: string) => string;

interface MarketTerminalProps {
  markets: MarketObsDTO[];
  fxRates: FxRateDTO[];
  sources: SourceSystemDTO[];
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
}

const marketMajorHubs: HubDefinition[] = [
  { hub: "TTF", region: "Netherlands", label: "TTF" },
  { hub: "NBP", region: "Great Britain", label: "NBP" },
  { hub: "THE", region: "Germany", label: "THE" },
  { hub: "PEG", region: "France", label: "PEG" },
  { hub: "ZTP", region: "Belgium", label: "ZTP" },
  { hub: "PSV", region: "Italy", label: "PSV" },
];

const gasPriceSources = new Set(["EEX", "ICE_OCM", "TRAYPORT", "PLATTS", "ICIS", "ARGUS", "KPLER"]);

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

export function MarketTerminal({ markets, fxRates, sources, t }: MarketTerminalProps) {
  const marketRows = useMemo(() => {
    const grouped = new Map<string, MarketObsDTO[]>();
    markets.filter(isGasMarketObservation).forEach((row) => {
      const hub = hubForObservation(row);
      if (!hub) return;
      grouped.set(hub, [...(grouped.get(hub) ?? []), row]);
    });

    const ttfLatest = grouped.get("TTF")?.slice().sort(sortNewestFirst)[0] ?? null;
    return marketMajorHubs.map((definition): HubTerminalRow => {
      const history = (grouped.get(definition.hub) ?? []).slice().sort(sortNewestFirst);
      const latest = history[0] ?? null;
      const spreadToTtf =
        latest && ttfLatest && latest.currency === ttfLatest.currency && latest.unit === ttfLatest.unit
          ? latest.price - ttfLatest.price
          : null;
      return { ...definition, latest, history, spreadToTtf };
    });
  }, [markets]);

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

  const marketUnavailableRows = marketRows.filter((row) => row.latest === null);
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
        <div className="market-terminal-strip" aria-label={t("market.terminal")}>
          {marketRows.map((row) => (
            <div
              key={`ticker-${row.hub}`}
              className={`market-price-ticker ${row.latest ? "is-live" : "is-waiting"}`}
            >
              <span>{row.hub}</span>
              <strong>{formatPrice(row.latest)}</strong>
              <small>{row.latest?.freshness ?? t("market.awaiting_feed")}</small>
            </div>
          ))}
        </div>
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
          {marketRows.map((row) => (
            <div key={`market-terminal-${row.hub}`} className="market-terminal-row">
              <strong data-label="Hub">{row.hub}</strong>
              <span data-label="Venue/Product">
                {row.latest ? `${row.latest.market_venue} ${row.latest.product}` : row.region}
              </span>
              <span data-label={t("market.price")}>{formatPrice(row.latest)}</span>
              <span data-label={t("market.freshness")}>{row.latest?.freshness ?? t("market.awaiting_feed")}</span>
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
          {marketRows.map((row) => (
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

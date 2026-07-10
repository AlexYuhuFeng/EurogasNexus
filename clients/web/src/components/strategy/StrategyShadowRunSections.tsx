type Translate = (key: string) => string;

export type PriceBasisId =
  | "WITHIN_DAY"
  | "DAY_AHEAD"
  | "MONTHLY"
  | "ICIS_ASSESSMENT"
  | "ICE_OCM_MARK"
  | "EEX_CURVE"
  | "FX";

export interface StrategyPriceBasisRow {
  basis: PriceBasisId;
  latestPrice: number | null;
  observationCount: number;
  sourceSystems: string[];
  simulatedCount: number;
  staleCount: number;
  latestObservedAtUtc: string | null;
}

export interface StrategyPnlCurveRow {
  basis: PriceBasisId;
  latestPrice: number | null;
  pnlGbpPerDay: number | null;
  marginGbpMwh: number | null;
  poolQuantityMwhPerDay: number;
  weightedPoolCostGbpMwh: number | null;
  sourceSystems: string[];
  simulatedCount: number;
  staleCount: number;
}

export interface StrategyBasisExposureRow {
  basis: PriceBasisId;
  latestPrice: number | null;
  basisMarginVsPoolCost: number | null;
  poolPnlAtRiskGbpPerDay: number | null;
  poolQuantityMwhPerDay: number;
  weightedPoolCostGbpMwh: number | null;
  observationCount: number;
  sourceSystems: string[];
  simulatedCount: number;
  staleCount: number;
}

export interface StrategyContractPnlRow {
  resourceId: string;
  resourceName: string;
  quantityMwhPerDay: number;
  costGbpMwh: number;
  marginGbpMwh: number | null;
  dailyPnlGbp: number | null;
}

interface StrategyPriceBasisBoardProps {
  rows: StrategyPriceBasisRow[];
  activeBasis: PriceBasisId;
  simulatedBasisCount: number;
  staleBasisCount: number;
  unavailableBasisCount: number;
  language: string;
  t: Translate;
  onSelectBasis: (basis: PriceBasisId) => void;
}

interface StrategyBasisExposureLadderProps {
  rows: StrategyBasisExposureRow[];
  t: Translate;
}

interface StrategyPnlCurvePanelProps {
  rows: StrategyPnlCurveRow[];
  maxAbsPnl: number;
  weightedPoolCostGbpMwh: number | null;
  totalPoolQuantityMwhPerDay: number;
  t: Translate;
}

interface StrategyContractPnlAttributionProps {
  rows: StrategyContractPnlRow[];
  t: Translate;
}

function basisLabelKey(basis: PriceBasisId): string {
  return `strategy.basis.${basis.toLowerCase()}`;
}

function formatMoney(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "n/a";
  return value.toFixed(2);
}

function formatQuantity(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "n/a";
  return `${Math.round(value).toLocaleString()} MWh/d`;
}

function formatSignedMoney(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "n/a";
  const sign = value > 0 ? "+" : "";
  return `${sign}${Math.round(value).toLocaleString()}`;
}

function formatTimestamp(value: string | null | undefined, language: string): string {
  if (!value) return "n/a";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return "n/a";
  return new Intl.DateTimeFormat(language.startsWith("zh") ? "zh-CN" : "en-GB", {
    month: "short",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).format(parsed);
}

export function StrategyPriceBasisBoard({
  rows,
  activeBasis,
  simulatedBasisCount,
  staleBasisCount,
  unavailableBasisCount,
  language,
  t,
  onSelectBasis,
}: StrategyPriceBasisBoardProps) {
  return (
    <section className="workspace-panel span-3 strategy-price-basis-board">
      <div className="panel-title-row">
        <h3>{t("strategy.price_basis_board")}</h3>
        <span>{rows.reduce((total, row) => total + row.observationCount, 0)} {t("panel.records")}</span>
      </div>
      <div className="strategy-data-quality-banner">
        <div>
          <span>{t("strategy.simulated_basis_count")}</span>
          <strong>{simulatedBasisCount}</strong>
        </div>
        <div>
          <span>{t("strategy.stale_basis_count")}</span>
          <strong>{staleBasisCount}</strong>
        </div>
        <div>
          <span>{t("strategy.unavailable_basis_count")}</span>
          <strong>{unavailableBasisCount}</strong>
        </div>
      </div>
      <div className="strategy-price-basis-selector" aria-label={t("strategy.selected_price_basis")}>
        {rows.map((row) => (
          <button
            key={`strategy-basis-option-${row.basis}`}
            type="button"
            className={`strategy-basis-option${activeBasis === row.basis ? " active" : ""}`}
            aria-pressed={activeBasis === row.basis}
            onClick={() => onSelectBasis(row.basis)}
          >
            {t(basisLabelKey(row.basis))}
          </button>
        ))}
      </div>
      <div className="strategy-price-basis-grid">
        {rows.map((row) => (
          <div key={`strategy-basis-${row.basis}`} className="strategy-price-basis-card">
            <span>{t(basisLabelKey(row.basis))}</span>
            <strong>
              {row.basis === "FX"
                ? formatMoney(row.latestPrice)
                : `${formatMoney(row.latestPrice)} GBP/MWh`}
            </strong>
            <div className="strategy-basis-meta">
              <small>{t("strategy.observations")}: {row.observationCount}</small>
              <small>{t("strategy.latest_price")}: {formatTimestamp(row.latestObservedAtUtc, language)}</small>
              <small>{row.sourceSystems.join(", ") || t("data.unavailable")}</small>
            </div>
            <div className="strategy-data-quality-chip-row">
              {row.simulatedCount > 0 && (
                <span className="strategy-data-quality-chip simulated">{t("strategy.simulated_data")}</span>
              )}
              {row.staleCount > 0 && (
                <span className="strategy-data-quality-chip stale">{t("strategy.stale_data")}</span>
              )}
              {row.observationCount === 0 && (
                <span className="strategy-data-quality-chip unavailable">{t("data.unavailable")}</span>
              )}
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}

export function StrategyBasisExposureLadder({ rows, t }: StrategyBasisExposureLadderProps) {
  return (
    <section className="workspace-panel span-2 strategy-basis-exposure-ladder">
      <div className="panel-title-row">
        <h3>{t("strategy.basis_exposure_ladder")}</h3>
        <span>{t("strategy.pool_pnl_at_risk")}</span>
      </div>
      <div className="strategy-basis-exposure-list">
        {rows.map((row) => {
          const isNegative = (row.poolPnlAtRiskGbpPerDay ?? 0) < 0;
          return (
            <div
              key={`strategy-exposure-${row.basis}`}
              className={`strategy-basis-exposure-row${isNegative ? " negative" : ""}`}
            >
              <div>
                <strong>{t(basisLabelKey(row.basis))}</strong>
                <span>{row.sourceSystems.join(", ") || t("data.unavailable")}</span>
              </div>
              <div>
                <span>{t("strategy.latest_price")}</span>
                <strong>{formatMoney(row.latestPrice)} GBP/MWh</strong>
              </div>
              <div>
                <span>{t("strategy.margin_vs_pool_cost")}</span>
                <strong>{formatMoney(row.basisMarginVsPoolCost)} GBP/MWh</strong>
              </div>
              <div>
                <span>{t("strategy.pool_pnl_at_risk")}</span>
                <strong>{formatSignedMoney(row.poolPnlAtRiskGbpPerDay)} GBP/d</strong>
              </div>
              <small>
                {formatQuantity(row.poolQuantityMwhPerDay)} / {formatMoney(row.weightedPoolCostGbpMwh)} GBP/MWh
              </small>
            </div>
          );
        })}
      </div>
    </section>
  );
}

export function StrategyPnlCurvePanel({
  rows,
  maxAbsPnl,
  weightedPoolCostGbpMwh,
  totalPoolQuantityMwhPerDay,
  t,
}: StrategyPnlCurvePanelProps) {
  return (
    <section className="workspace-panel span-2 strategy-pnl-curve">
      <div className="panel-title-row">
        <h3>{t("strategy.pnl_curve")}</h3>
        <span>{t("home.resource_pool")}</span>
      </div>
      <div className="strategy-pool-baseline">
        <div>
          <span>{t("strategy.weighted_pool_cost")}</span>
          <strong>{formatMoney(weightedPoolCostGbpMwh)} GBP/MWh</strong>
        </div>
        <div>
          <span>{t("strategy.pool_volume")}</span>
          <strong>{formatQuantity(totalPoolQuantityMwhPerDay)}</strong>
        </div>
      </div>
      <div className="strategy-pnl-curve-list">
        {rows.map((row) => {
          const width = Math.max(
            row.pnlGbpPerDay === null ? 0 : 4,
            Math.round((Math.abs(row.pnlGbpPerDay ?? 0) / maxAbsPnl) * 100),
          );
          const isNegative = (row.pnlGbpPerDay ?? 0) < 0;
          return (
            <div key={`strategy-pnl-${row.basis}`} className="strategy-pnl-curve-row">
              <div className="strategy-pnl-row-header">
                <strong>{t(basisLabelKey(row.basis))}</strong>
                <span>{formatSignedMoney(row.pnlGbpPerDay)} GBP/d</span>
              </div>
              <div className="strategy-pnl-track">
                <span
                  className={`strategy-pnl-bar${isNegative ? " negative" : ""}`}
                  style={{ width: `${width}%` }}
                />
              </div>
              <small>
                {formatMoney(row.latestPrice)} GBP/MWh / {formatMoney(row.marginGbpMwh)} GBP/MWh
              </small>
            </div>
          );
        })}
      </div>
    </section>
  );
}

export function StrategyContractPnlAttribution({ rows, t }: StrategyContractPnlAttributionProps) {
  return (
    <div className="strategy-contract-pnl-attribution">
      {rows.slice(0, 6).map((resource) => {
        const isNegative = (resource.dailyPnlGbp ?? 0) < 0;
        return (
          <div
            key={`strategy-contract-pnl-${resource.resourceId}`}
            className={`strategy-contract-pnl-row${isNegative ? " negative" : ""}`}
          >
            <div>
              <strong>{resource.resourceName}</strong>
              <span>{formatQuantity(resource.quantityMwhPerDay)} / {formatMoney(resource.costGbpMwh)} GBP/MWh</span>
            </div>
            <div>
              <strong>{formatSignedMoney(resource.dailyPnlGbp)} GBP/d</strong>
              <span>{formatMoney(resource.marginGbpMwh)} GBP/MWh</span>
            </div>
          </div>
        );
      })}
      {rows.length === 0 && <p className="panel-copy">{t("data.unavailable")}</p>}
    </div>
  );
}

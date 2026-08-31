import type { StrategyRunDTO, StrategySummaryDTO } from "@/api/client";

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

interface StrategyPerformancePanelProps {
  runs: StrategyRunDTO[];
  summary: StrategySummaryDTO | null;
  language: string;
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
    <section className="workspace-panel strategy-pnl-curve">
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

export function StrategyPerformancePanel({
  runs,
  summary,
  language,
  t,
}: StrategyPerformancePanelProps) {
  const plottedRuns = runs
    .filter((run) => run.cumulative_pnl_gbp !== null)
    .slice()
    .sort((left, right) => Date.parse(left.started_at_utc) - Date.parse(right.started_at_utc))
    .slice(-30);
  const values = plottedRuns.map((run) => run.cumulative_pnl_gbp ?? 0);
  const minimum = Math.min(0, ...values);
  const maximum = Math.max(0, ...values);
  const range = Math.max(maximum - minimum, 1);
  const plotLeft = 8;
  const plotRight = 96;
  const plotTop = 12;
  const plotBottom = 84;
  const xForIndex = (index: number) => (
    plottedRuns.length <= 1
      ? (plotLeft + plotRight) / 2
      : plotLeft + (index / (plottedRuns.length - 1)) * (plotRight - plotLeft)
  );
  const yForValue = (value: number) => plotBottom - ((value - minimum) / range) * (plotBottom - plotTop);
  const pointList = values.map((value, index) => `${xForIndex(index)},${yForValue(value)}`).join(" ");
  const latestRun = plottedRuns.at(-1) ?? null;

  return (
    <section className="workspace-panel span-2 strategy-performance-chart">
      <div className="panel-title-row">
        <h3>{t("strategy.cumulative_paper_pnl")}</h3>
        <span>{plottedRuns.length} {t("panel.records")}</span>
      </div>
      <div className="strategy-performance-plot">
        {plottedRuns.length > 0 ? (
          <svg
            viewBox="0 0 104 96"
            role="img"
            aria-label={t("strategy.cumulative_paper_pnl")}
            preserveAspectRatio="none"
          >
            {[30, 48, 66].map((y) => (
              <line key={`strategy-grid-${y}`} className="strategy-chart-grid" x1="8" x2="96" y1={y} y2={y} />
            ))}
            <line
              className="strategy-chart-zero"
              x1="8"
              x2="96"
              y1={yForValue(0)}
              y2={yForValue(0)}
            />
            <polyline className="strategy-chart-line" points={pointList} />
          </svg>
        ) : (
          <div className="strategy-performance-empty">
            <strong>{t("strategy.awaiting_shadow_run")}</strong>
            <span>{t("strategy.no_execution")}</span>
          </div>
        )}
        {plottedRuns.length > 0 && (
          <span
            className="strategy-chart-point"
            style={{
              left: `${(xForIndex(plottedRuns.length - 1) / 104) * 100}%`,
              top: `${(yForValue(values.at(-1) ?? 0) / 96) * 100}%`,
            }}
          />
        )}
      </div>
      <div className="strategy-performance-summary">
        <div>
          <span>{t("strategy.cumulative_pnl")}</span>
          <strong>{formatSignedMoney(summary?.cumulative_pnl_gbp)} GBP</strong>
        </div>
        <div>
          <span>{t("strategy.hit_rate")}</span>
          <strong>{((summary?.hit_rate ?? 0) * 100).toFixed(1)}%</strong>
        </div>
        <div>
          <span>{t("strategy.max_drawdown")}</span>
          <strong>{formatSignedMoney(summary?.max_drawdown_gbp)} GBP</strong>
        </div>
        <div>
          <span>{t("strategy.run_count")}</span>
          <strong>{summary?.run_count ?? runs.length}</strong>
        </div>
        <div>
          <span>{t("context.updated")}</span>
          <strong>{formatTimestamp(latestRun?.started_at_utc, language)}</strong>
        </div>
      </div>
    </section>
  );
}

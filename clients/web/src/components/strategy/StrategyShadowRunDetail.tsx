import { useMemo, useState } from "react";

import { EvidenceBlock, MetricStrip, PanelHeader } from "@/components/ui";
import { formatUtcTimestamp } from "@/app/model/evidencePresentation";
import {
  StrategyBasisExposureLadder,
  StrategyContractPnlAttribution,
  StrategyPerformancePanel,
  StrategyPnlCurvePanel,
  StrategyPriceBasisBoard,
} from "@/components/strategy/StrategyShadowRunSections";
import {
  STALE_HOURS_BY_BASIS,
  basisCounts,
  basisExposureRows,
  basisLabelKey,
  classifyPriceBasis,
  contractPnlRows,
  isSimulatedSource,
  isStaleObservation,
  maxAbsPnl,
  pnlCurveRows,
  poolQuantity,
  poolRows,
  priceBasisRows,
  priceTape,
  shadowRunProvenance,
  strategyWarningLabel,
  weightedPoolCost,
  type PriceBasisId,
} from "@/app/model/shadowRunPresentation";
import { useApiStore } from "@/stores/api";

type Translate = (key: string) => string;

interface StrategyShadowRunDetailProps {
  language: string;
  t: Translate;
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

function formatInstant(value: string | null | undefined): string {
  return formatUtcTimestamp(value);
}

/**
 * What a shadow run's economics rest on, inside the shadow task (owner decision on the unmounted
 * terminal, completing slice B of the D3 decision).
 *
 * The task's monitor management answers what is happening; this answers what the figures rest on:
 * the price basis each comes from and whether that basis is simulated or stale, the pool's volume
 * and weighted cost, the daily PnL each basis puts at risk, each contract's contribution, the
 * persisted run's cumulative paper PnL, and the engine, dataset and commit behind the run.
 *
 * It reads only what the identity already received (`stores/api`), plus the strategy summary the
 * client already fetches. Nothing is computed that the platform did not measure:
 *
 * - a basis with no observation keeps `null` and is counted as unavailable rather than dropped;
 * - a margin against an unknown pool cost stays `null` instead of defaulting to the latest price;
 * - a summary the surface does not hold shows `n/a` for the hit rate, not `0.0%`;
 * - staleness is measured against one instant taken when the panel renders, and the strip states
 *   the observation time basis it is measured on.
 *
 * There is no run control here. Running a shadow evaluation is the task's own compute and lives in
 * the workspace header's primary slot; this panel reports what the last evaluation and the
 * persisted runs say.
 */
export function StrategyShadowRunDetail({ language, t }: StrategyShadowRunDetailProps) {
  const normalizedMarkets = useApiStore((state) => state.normalizedMarkets);
  const fxRates = useApiStore((state) => state.fxRates);
  const resourcePoolOptions = useApiStore((state) => state.resourcePoolOptions);
  const runs = useApiStore((state) => state.strategyRuns);
  const summary = useApiStore((state) => state.strategySummary);
  const result = useApiStore((state) => state.strategyResult);
  const [activeBasis, setActiveBasis] = useState<PriceBasisId>("WITHIN_DAY");

  const presentation = useMemo(() => {
    // One instant for the whole render, so two rows cannot disagree about what "now" was.
    const nowMs = Date.now();
    const tape = priceTape([], normalizedMarkets);
    const basis = priceBasisRows({ tape, fxRates, nowMs });
    const pool = poolRows(resourcePoolOptions?.portfolio_resources ?? []);
    const quantity = poolQuantity(pool);
    const weightedCost = weightedPoolCost(pool);
    const pnl = pnlCurveRows(basis, {
      quantityMwhPerDay: quantity,
      weightedCostGbpMwh: weightedCost,
    });
    return {
      nowMs,
      tape,
      basis,
      pool,
      quantity,
      weightedCost,
      pnl,
      exposure: basisExposureRows(pnl, basis),
      counts: basisCounts(basis),
      maxAbs: maxAbsPnl(pnl),
      provenance: shadowRunProvenance({ result, runs }),
    };
  }, [fxRates, normalizedMarkets, resourcePoolOptions, result, runs]);

  const activeBasisRow =
    presentation.basis.find((row) => row.basis === activeBasis) ?? presentation.basis[0];
  const activePnlRow =
    activeBasis === "FX"
      ? null
      : (presentation.pnl.find((row) => row.basis === activeBasis) ?? null);
  const contracts = contractPnlRows(
    presentation.pool,
    activePnlRow?.latestPrice ?? null,
  );
  const latestObservation = presentation.basis.reduce<string | null>((latest, row) => {
    if (!row.latestObservedAtUtc) return latest;
    if (!latest) return row.latestObservedAtUtc;
    return Date.parse(row.latestObservedAtUtc) > Date.parse(latest)
      ? row.latestObservedAtUtc
      : latest;
  }, null);
  const provenance = presentation.provenance;
  const tape = presentation.tape;
  const nowMs = presentation.nowMs;
  const allocations = provenance.run?.allocation_targets ?? [];

  return (
    <>
      <section className="workspace-panel span-3 strategy-shadow-detail-header">
        <PanelHeader
          title={t("strategy.selected_price_basis")}
          meta={
            activeBasisRow ? t(basisLabelKey(activeBasisRow.basis)) : t("data.unavailable")
          }
        />
        <MetricStrip
          asOf={formatInstant(latestObservation)}
          timeBasis={t("strategy.observation_time_basis")}
          items={[
            {
              label: t("strategy.latest_price"),
              value: formatMoney(activeBasisRow?.latestPrice),
              unit: activeBasis === "FX" ? "" : "GBP/MWh",
            },
            {
              label: t("strategy.weighted_pool_cost"),
              value: formatMoney(presentation.weightedCost),
              unit: "GBP/MWh",
            },
            {
              label: t("strategy.pool_volume"),
              value: formatQuantity(presentation.quantity),
            },
            {
              label: t("strategy.unavailable_basis_count"),
              value: String(presentation.counts.unavailable),
            },
            {
              label: t("strategy.stale_basis_count"),
              value: String(presentation.counts.stale),
            },
            {
              label: t("strategy.simulated_basis_count"),
              value: String(presentation.counts.simulated),
            },
          ]}
        />
        <p className="panel-copy">{t("strategy.shadow_detail_note")}</p>
      </section>

      <StrategyPriceBasisBoard
        rows={presentation.basis}
        activeBasis={activeBasis}
        simulatedBasisCount={presentation.counts.simulated}
        staleBasisCount={presentation.counts.stale}
        unavailableBasisCount={presentation.counts.unavailable}
        language={language}
        t={t}
        onSelectBasis={setActiveBasis}
      />

      <StrategyPnlCurvePanel
        rows={presentation.pnl}
        maxAbsPnl={presentation.maxAbs}
        weightedPoolCostGbpMwh={presentation.weightedCost}
        totalPoolQuantityMwhPerDay={presentation.quantity}
        t={t}
      />

      <StrategyBasisExposureLadder rows={presentation.exposure} t={t} />

      <section className="workspace-panel span-2 strategy-contract-pnl-panel">
        <PanelHeader
          title={t("strategy.contract_pnl_attribution")}
          meta={
            activePnlRow?.latestPrice !== null && activePnlRow !== null
              ? `${formatMoney(activePnlRow.latestPrice)} GBP/MWh`
              : t("data.unavailable")
          }
        />
        <p className="panel-copy">{t("strategy.contract_pnl_note")}</p>
        <StrategyContractPnlAttribution rows={contracts} t={t} />
      </section>

      <section className="workspace-panel strategy-market-tape">
        <PanelHeader title={t("strategy.market_tape")} meta={`${tape.length} ${t("panel.records")}`} />
        <p className="panel-copy">{t("strategy.market_tape_note")}</p>
        {tape.length === 0 ? (
          <p className="muted">{t("data.unavailable")}</p>
        ) : (
          <div className="research-table data-table" tabIndex={0}>
            <div className="data-table-row header five">
              <span>{t("strategy.selected_price_basis")}</span>
              <span>{t("strategy.reference")}</span>
              <span>{t("strategy.latest_price")}</span>
              <span>{t("evidence.observed")}</span>
              <span>{t("strategy.source_evidence")}</span>
            </div>
            {tape.slice(0, 12).map((price) => (
              <div key={`${price.observation_id}-${price.source_system}`} className="data-table-row five">
                <span className="status-badge">
                  {t(basisLabelKey(classifyPriceBasis(price)))}
                </span>
                <span>
                  {[price.hub, price.venue, price.product].filter(Boolean).join(" · ") ||
                    t("data.unavailable")}
                </span>
                <span>{formatMoney(price.price_gbp_mwh)} GBP/MWh</span>
                <span>{formatInstant(price.observed_at_utc)}</span>
                <span className="muted">
                  {price.source_system}
                  {isSimulatedSource(price.source_system)
                    ? ` · ${t("strategy.simulated_data")}`
                    : ""}
                  {isStaleObservation(
                    price.observed_at_utc,
                    STALE_HOURS_BY_BASIS[classifyPriceBasis(price)],
                    nowMs,
                  )
                    ? ` · ${t("strategy.stale_data")}`
                    : ""}
                </span>
              </div>
            ))}
          </div>
        )}
      </section>

      <section className="workspace-panel span-2 strategy-allocation-ladder">
        <PanelHeader
          title={t("strategy.allocation_targets")}
          meta={`${allocations.length} ${t("panel.records")}`}
        />
        <p className="panel-copy">{t("strategy.allocation_note")}</p>
        {allocations.length === 0 ? (
          <p className="muted">{t("strategy.awaiting_shadow_run")}</p>
        ) : (
          <div className="research-table data-table" tabIndex={0}>
            <div className="data-table-row header four">
              <span>{t("strategy.bucket")}</span>
              <span>{t("strategy.quantity")}</span>
              <span>{t("strategy.target")}</span>
              <span>{t("strategy.margin_vs_pool_cost")}</span>
            </div>
            {allocations.map((target, index) => (
              <div key={`${target.market_bucket}-${index}`} className="data-table-row four">
                <strong>{target.market_bucket}</strong>
                <span>{formatQuantity(target.target_quantity_mwh_per_day)}</span>
                <span>{`${(target.target_allocation_pct * 100).toFixed(1)}%`}</span>
                <span>{formatMoney(target.expected_margin_gbp_mwh)} GBP/MWh</span>
              </div>
            ))}
          </div>
        )}
      </section>

      <section className="workspace-panel strategy-paper-state">
        <PanelHeader
          title={t("strategy.paper_state")}
          meta={provenance.run ? provenance.run.status : t("strategy.awaiting_shadow_run")}
        />
        <p className="panel-copy">{t("strategy.paper_state_note")}</p>
        <div className="strategy-provenance-facts">
          <div>
            <span>{t("strategy.paper_pnl")}</span>
            <strong>{formatSignedMoney(provenance.run?.paper_pnl_gbp)} GBP</strong>
          </div>
          <div>
            <span>{t("strategy.cumulative_pnl")}</span>
            <strong>{formatSignedMoney(provenance.run?.cumulative_pnl_gbp)} GBP</strong>
          </div>
          <div>
            {/* A run that recorded no hit is not a loss: the field is nullable, and the panel says
                which of the two it is looking at. */}
            <span>{t("strategy.hit_rate")}</span>
            <strong>
              {provenance.run?.hit === null || provenance.run?.hit === undefined
                ? t("data.unavailable")
                : provenance.run.hit
                  ? t("strategy.win")
                  : t("strategy.loss")}
            </strong>
          </div>
          <div>
            <span>{t("strategy.no_execution")}</span>
            <strong>{t("strategy.no_execution")}</strong>
          </div>
        </div>
      </section>

      <StrategyPerformancePanel
        runs={runs}
        summary={summary}
        language={language}
        t={t}
      />

      <section className="workspace-panel span-3 strategy-run-provenance">
        <PanelHeader
          title={t("strategy.run_provenance")}
          meta={provenance.run ? provenance.run.status : t("data.unavailable")}
        />
        <p className="panel-copy">{t("strategy.run_provenance_note")}</p>
        {/* The evidence behind the figures, in the shared block: where the run says its data came
            from, the instant it read to, and the review boundary it carries. */}
        <EvidenceBlock
          ariaLabel={t("strategy.source_evidence")}
          items={[
            {
              label: t("strategy.source_evidence"),
              value: provenance.sourceRefs.join(", ") || t("data.unavailable"),
              detail: `${t("strategy.data_cutoff")}: ${formatInstant(provenance.run?.data_cutoff_utc)}`,
              wide: true,
            },
            {
              label: t("evidence.review_boundary"),
              value: provenance.humanReviewRequired
                ? t("strategy.warning.human_review_required")
                : t("strategy.no_execution"),
              detail: t("strategy.no_execution"),
            },
            {
              label: t("strategy.reproducible"),
              value: provenance.run?.manifest_hash
                ? t("strategy.reproducible_yes")
                : t("strategy.no_registry_provenance"),
              detail: provenance.run?.manifest_hash ?? t("data.unavailable"),
            },
            {
              label: t("context.updated"),
              value: formatInstant(provenance.run?.started_at_utc),
              detail: t("evidence.utc"),
            },
          ]}
        />
        <div className="data-table strategy-provenance-table" tabIndex={0}>
          <div className="data-table-row header four">
            <span>{t("strategy.run_type")}</span>
            <span>{t("strategy.engine_version")}</span>
            <span>{t("strategy.git_commit")}</span>
            <span>{t("strategy.dataset_snapshot")}</span>
          </div>
          <div className="data-table-row four">
            <span>{provenance.run?.run_type ?? t("data.unavailable")}</span>
            <span>{provenance.run?.engine_version ?? t("data.unavailable")}</span>
            <span>{provenance.run?.git_commit_sha ?? t("data.unavailable")}</span>
            <span>{provenance.run?.dataset_snapshot_id ?? t("data.unavailable")}</span>
          </div>
          <div className="data-table-row header four">
            <span>{t("strategy.data_cutoff")}</span>
            <span>{t("strategy.manifest_hash")}</span>
            <span>{t("strategy.application_version")}</span>
            <span>{t("strategy.run_time")}</span>
          </div>
          <div className="data-table-row four">
            <span>{formatInstant(provenance.run?.data_cutoff_utc)}</span>
            <span>{provenance.run?.manifest_hash ?? t("data.unavailable")}</span>
            <span>{provenance.run?.application_version ?? t("data.unavailable")}</span>
            <span>{formatInstant(provenance.run?.started_at_utc)}</span>
          </div>
        </div>
        <div className="strategy-provenance-facts">
          <div>
            <span>{t("strategy.current_candidate_action")}</span>
            <strong>{provenance.candidateAction ?? t("strategy.awaiting_shadow_run")}</strong>
          </div>
          <div>
            <span>{t("strategy.run_count")}</span>
            <strong>{runs.length}</strong>
          </div>
          <div>
            <span>{t("strategy.latest_persisted_run")}</span>
            <strong>{provenance.run?.status ?? t("data.unavailable")}</strong>
          </div>
        </div>
        <div className="strategy-warning-stack">
          <span className="eyebrow">{t("strategy.warning_stack")}</span>
          {provenance.warnings.length === 0 ? (
            <p className="muted">{t("review.no_warnings")}</p>
          ) : (
            <ul>
              {provenance.warnings.map((warning) => (
                <li key={warning}>{strategyWarningLabel(warning, t)}</li>
              ))}
            </ul>
          )}
        </div>
        <div className="strategy-provenance-facts">
          <div>
            <span>{t("strategy.paper_pnl")}</span>
            <strong>{formatSignedMoney(provenance.run?.paper_pnl_gbp)} GBP</strong>
          </div>
          <div>
            <span>{t("strategy.cumulative_pnl")}</span>
            <strong>{formatSignedMoney(provenance.run?.cumulative_pnl_gbp)} GBP</strong>
          </div>
          <div>
            <span>{t("strategy.day_ahead")}</span>
            <strong>{formatMoney(provenance.run?.day_ahead_average_gbp_mwh)} GBP/MWh</strong>
          </div>
          <div>
            <span>{t("strategy.intraday")}</span>
            <strong>{formatMoney(provenance.run?.intraday_average_gbp_mwh)} GBP/MWh</strong>
          </div>
        </div>
        <p className="muted">{t("strategy.no_execution")}</p>
      </section>
    </>
  );
}

import { useState } from "react";

import { api, type FinancingRateDTO } from "@/api/client";
import { apiErrorDetailCode, describeFailure, presentError } from "@/app/experience/errorPresentation";
import "./trader-desk.css";

type Translate = (key: string) => string;

const BENCHMARK_OPTIONS = ["SONIA", "ESTR", "SOFR"] as const;

interface FinancingRateHelperProps {
  t: Translate;
  /** Receives the all-in rate restated on ACT/365F, the basis the early-cash term accrues on. */
  onApply: (allInAct365Pct: number) => void;
}

/**
 * Builds a contract financing rate the way contracts state it: overnight benchmark + spread.
 *
 * The backend resolves the fixing (latest value date on or before the chosen date) and the
 * day-count restatement; this helper only shows the answer and, on request, writes the all-in
 * rate into the contract's financing-rate field. Nothing is applied automatically.
 */
export function FinancingRateHelper({ t, onApply }: FinancingRateHelperProps) {
  const [benchmark, setBenchmark] = useState<string>("SONIA");
  const [spreadText, setSpreadText] = useState("0");
  const [asOf, setAsOf] = useState("");
  const [result, setResult] = useState<FinancingRateDTO | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);

  const resolve = () => {
    const spread = Number(spreadText);
    if (!Number.isFinite(spread)) return;
    setBusy(true);
    api.financingRate(benchmark, spread, asOf || undefined)
      .then((response) => {
        setResult(response.data);
        setError(null);
      })
      .catch((cause: unknown) => {
        setResult(null);
        setError(cause);
      })
      .finally(() => setBusy(false));
  };

  const failure = error
    ? apiErrorDetailCode(error) === "financing_rate_unavailable"
      ? t("financing.unavailable")
      : presentError(t, describeFailure(error)).title
    : null;

  return (
    <div className="financing-rate-helper span-2" aria-label={t("financing.title")}>
      <strong>{t("financing.title")}</strong>
      <div className="financing-rate-inputs">
        <select value={benchmark} aria-label={t("financing.benchmark")} onChange={(event) => setBenchmark(event.target.value)}>
          {BENCHMARK_OPTIONS.map((item) => (
            <option key={item} value={item}>{t(`financing.benchmark.${item}`)}</option>
          ))}
        </select>
        <label>
          {t("financing.spread_bps")}
          <input type="number" step="1" value={spreadText} onChange={(event) => setSpreadText(event.target.value)} />
        </label>
        <label>
          {t("financing.as_of")}
          <input type="date" value={asOf} onChange={(event) => setAsOf(event.target.value)} />
        </label>
        <button type="button" onClick={resolve} disabled={busy}>{t("financing.resolve")}</button>
      </div>
      {failure && <p className="financing-rate-note issue">{failure}</p>}
      {result && (
        <div className="financing-rate-result">
          <span>
            {result.benchmark_id} {result.benchmark_rate_pct.toFixed(4)}% ({result.fixing_date})
            {" + "}{result.spread_bps} bp = <strong>{result.all_in_pct.toFixed(4)}%</strong> {result.day_count}
            {result.day_count !== "ACT/365F" && <> → {result.all_in_act365_pct.toFixed(4)}% ACT/365F</>}
          </span>
          <button type="button" onClick={() => onApply(Number(result.all_in_act365_pct.toFixed(4)))}>
            {t("financing.apply")}
          </button>
          <small>{result.attribution}</small>
        </div>
      )}
    </div>
  );
}

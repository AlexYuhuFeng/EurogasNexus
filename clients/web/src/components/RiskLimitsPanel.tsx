import { useCallback, useEffect, useState } from "react";

import {
  api,
  type CreditExposureRowDTO,
  type CreditLineInput,
  type MandateInput,
  type MandateUsageRowDTO,
} from "@/api/client";
import { formatMoney, formatQuantity, splitList } from "@/app/model/riskLimitsModel";
import { ReportExport } from "./ReportExport";

type Translate = (key: string, options?: Record<string, unknown>) => string;

function LimitBadge({ status, t }: { status: string; t: Translate }) {
  return (
    <span className="limit-badge" data-status={status}>
      {t(`limits.status_${status}`)}
    </span>
  );
}

function Utilisation({ pct }: { pct: number | null }) {
  if (pct === null) return <span className="muted">-</span>;
  const width = Math.max(0, Math.min(100, pct));
  return (
    <span className="limit-meter" title={`${pct.toFixed(1)}%`}>
      <span className="limit-meter-bar" style={{ width: `${width}%` }} data-over={pct > 100 ? "true" : undefined} />
      <span className="limit-meter-value">{pct.toFixed(0)}%</span>
    </span>
  );
}

const EMPTY_LINE = {
  counterparty_id: "",
  name: "",
  aliases: "",
  limit_amount: "",
  currency: "EUR",
  collateral_amount: "0",
  rating: "",
  contract_ids: "",
  receivable_days: "50",
  valid_until: "",
};

const EMPTY_MANDATE = {
  mandate_id: "",
  trader: "",
  display_name: "",
  book_ids: "",
  hubs: "",
  max_net_mwh_per_month: "",
  max_tenor_months: "",
  valid_until: "",
};

/**
 * Credit and mandates: counterparty exposure against approved lines, and each trader's open
 * positions against their mandate. Risk (REVIEWER) maintains both; everyone in the book sees
 * the utilisation, so a breach is visible to the trader and the desk head at the same time.
 */
export function RiskLimitsPanel({ t }: { t: Translate }) {
  const [credit, setCredit] = useState<CreditExposureRowDTO[] | null>(null);
  const [mandates, setMandates] = useState<MandateUsageRowDTO[] | null>(null);
  const [warnings, setWarnings] = useState<string[]>([]);
  const [line, setLine] = useState(EMPTY_LINE);
  const [mandate, setMandate] = useState(EMPTY_MANDATE);
  const [editing, setEditing] = useState<"none" | "credit" | "mandate">("none");
  const [message, setMessage] = useState<string | null>(null);

  const load = useCallback(() => {
    api.creditExposure()
      .then((response) => {
        setCredit(response.data.rows);
        setWarnings(response.meta?.warnings ?? []);
      })
      .catch(() => setCredit(null));
    api.mandateUsage().then((response) => setMandates(response.data.rows)).catch(() => setMandates(null));
  }, []);
  useEffect(load, [load]);

  const fail = (caught: unknown) => setMessage(caught instanceof Error ? caught.message : String(caught));

  const saveLine = () => {
    const body: CreditLineInput = {
      name: line.name.trim(),
      aliases: splitList(line.aliases),
      limit_amount: Number(line.limit_amount),
      currency: line.currency.trim().toUpperCase(),
      collateral_amount: Number(line.collateral_amount || 0),
      rating: line.rating.trim() || null,
      contract_ids: splitList(line.contract_ids),
      receivable_days: Number(line.receivable_days || 50),
      valid_until: line.valid_until || null,
    };
    api.saveCreditLine(line.counterparty_id.trim(), body)
      .then(() => {
        setMessage(t("limits.saved"));
        setLine(EMPTY_LINE);
        setEditing("none");
        load();
      })
      .catch(fail);
  };

  const saveMandate = () => {
    const body: MandateInput = {
      trader: mandate.trader.trim(),
      display_name: mandate.display_name.trim(),
      book_ids: splitList(mandate.book_ids),
      hubs: splitList(mandate.hubs).map((hub) => hub.toUpperCase()),
      max_net_mwh_per_month: mandate.max_net_mwh_per_month ? Number(mandate.max_net_mwh_per_month) : null,
      max_tenor_months: mandate.max_tenor_months ? Number(mandate.max_tenor_months) : null,
      physical_allowed: true,
      financial_allowed: true,
      valid_until: mandate.valid_until || null,
    };
    api.saveTraderMandate(mandate.mandate_id.trim(), body)
      .then(() => {
        setMessage(t("limits.saved"));
        setMandate(EMPTY_MANDATE);
        setEditing("none");
        load();
      })
      .catch(fail);
  };

  const lineField = (key: keyof typeof EMPTY_LINE) => (event: { target: { value: string } }) =>
    setLine({ ...line, [key]: event.target.value });
  const mandateField = (key: keyof typeof EMPTY_MANDATE) => (event: { target: { value: string } }) =>
    setMandate({ ...mandate, [key]: event.target.value });
  const breaches = [...(credit ?? []), ...(mandates ?? [])].filter((row) => row.status === "breach" || row.status === "expired").length;

  return (
    <section className="workspace-panel span-3 risk-limits-panel" aria-labelledby="risk-limits-title">
      <div className="panel-title-row">
        <h2 id="risk-limits-title">{t("limits.title")}</h2>
        {breaches > 0 && <span className="limit-badge" data-status="breach">{t("limits.breaches", { count: breaches })}</span>}
      </div>

      <div className="panel-title-row">
        <h3>{t("limits.credit_title")}</h3>
        <ReportExport t={t} path="/portfolio/credit-exposure" />
      </div>
      {credit && credit.length === 0 && <p className="muted">{t("limits.credit_empty")}</p>}
      {credit && credit.length > 0 && (
        <table className="position-ladder" data-credit-exposure="true">
          <thead>
            <tr>
              <th scope="col">{t("limits.counterparty")}</th>
              <th scope="col" className="num">{t("limits.limit")}</th>
              <th scope="col" className="num">{t("limits.replacement")}</th>
              <th scope="col" className="num">{t("limits.receivable")}</th>
              <th scope="col" className="num">{t("limits.collateral")}</th>
              <th scope="col" className="num">{t("limits.net")}</th>
              <th scope="col">{t("limits.used")}</th>
              <th scope="col">{t("limits.status")}</th>
            </tr>
          </thead>
          <tbody>
            {credit.map((row) => (
              <tr key={row.counterparty_id} data-status={row.status}>
                <td>
                  <strong>{row.counterparty}</strong>{" "}
                  <small>{[row.rating, row.legal_entity, t("limits.legs", { count: row.legs })].filter(Boolean).join(" · ")}</small>
                </td>
                <td className="num">{formatMoney(row.limit, row.currency)}</td>
                <td className="num">{formatMoney(row.replacement_exposure, row.currency)}</td>
                <td className="num">{formatMoney(row.receivable_exposure, row.currency)}</td>
                <td className="num">{formatMoney(row.collateral, row.currency)}</td>
                <td className="num"><strong>{formatMoney(row.net_exposure, row.currency)}</strong></td>
                <td><Utilisation pct={row.utilisation_pct} /></td>
                <td>
                  <LimitBadge status={row.status} t={t} />
                  {row.unvalued_legs > 0 && <small> {t("limits.unvalued", { count: row.unvalued_legs })}</small>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      <div className="panel-title-row">
        <h3>{t("limits.mandate_title")}</h3>
        <ReportExport t={t} path="/portfolio/mandate-usage" />
      </div>
      {mandates && mandates.length === 0 && <p className="muted">{t("limits.mandate_empty")}</p>}
      {mandates && mandates.length > 0 && (
        <table className="position-ladder" data-mandate-usage="true">
          <thead>
            <tr>
              <th scope="col">{t("limits.trader")}</th>
              <th scope="col">{t("limits.scope")}</th>
              <th scope="col" className="num">{t("limits.largest_net")}</th>
              <th scope="col">{t("limits.used")}</th>
              <th scope="col">{t("limits.tenor")}</th>
              <th scope="col">{t("limits.status")}</th>
            </tr>
          </thead>
          <tbody>
            {mandates.map((row) => (
              <tr key={row.mandate_id} data-status={row.status}>
                <td><strong>{row.name}</strong> <small>{row.trader}</small></td>
                <td><small>{row.books} · {row.hubs}</small></td>
                <td className="num">
                  {formatQuantity(row.largest_net_mwh)} <small>{row.largest_at}</small>
                </td>
                <td><Utilisation pct={row.utilisation_pct} /></td>
                <td>
                  {row.furthest_month || "-"}
                  {row.max_tenor_months !== null && <small> / {t("limits.months", { count: row.max_tenor_months })}</small>}
                </td>
                <td>
                  <LimitBadge status={row.status} t={t} />
                  {row.breaches && <div className="limit-breaches">{row.breaches}</div>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {warnings.length > 0 && (
        <details className="limit-warnings">
          <summary>{t("limits.notes", { count: warnings.length })}</summary>
          <ul>{warnings.map((warning) => <li key={warning}>{warning}</li>)}</ul>
        </details>
      )}

      <div className="limit-actions">
        <button type="button" className="secondary-button" onClick={() => setEditing(editing === "credit" ? "none" : "credit")}>
          {t("limits.edit_credit")}
        </button>
        <button type="button" className="secondary-button" onClick={() => setEditing(editing === "mandate" ? "none" : "mandate")}>
          {t("limits.edit_mandate")}
        </button>
        <small className="muted">{t("limits.who_edits")}</small>
      </div>
      {editing === "credit" && (
        <div className="licence-form">
          <label><span>{t("limits.counterparty_id")}</span><input value={line.counterparty_id} onChange={lineField("counterparty_id")} /></label>
          <label><span>{t("limits.counterparty")}</span><input value={line.name} onChange={lineField("name")} /></label>
          <label><span>{t("limits.aliases")}</span><input value={line.aliases} onChange={lineField("aliases")} /></label>
          <label><span>{t("limits.limit")}</span><input inputMode="decimal" value={line.limit_amount} onChange={lineField("limit_amount")} /></label>
          <label><span>{t("limits.currency")}</span><input value={line.currency} maxLength={3} onChange={lineField("currency")} /></label>
          <label><span>{t("limits.collateral")}</span><input inputMode="decimal" value={line.collateral_amount} onChange={lineField("collateral_amount")} /></label>
          <label><span>{t("limits.rating")}</span><input value={line.rating} onChange={lineField("rating")} /></label>
          <label><span>{t("limits.contracts")}</span><input value={line.contract_ids} onChange={lineField("contract_ids")} /></label>
          <label><span>{t("limits.receivable_days")}</span><input inputMode="numeric" value={line.receivable_days} onChange={lineField("receivable_days")} /></label>
          <label><span>{t("limits.valid_until")}</span><input type="date" value={line.valid_until} onChange={lineField("valid_until")} /></label>
          <button
            type="button"
            disabled={!line.counterparty_id.trim() || !line.name.trim() || !(Number(line.limit_amount) >= 0) || !line.limit_amount}
            onClick={saveLine}
          >
            {t("limits.save")}
          </button>
        </div>
      )}
      {editing === "mandate" && (
        <div className="licence-form">
          <label><span>{t("limits.mandate_id")}</span><input value={mandate.mandate_id} onChange={mandateField("mandate_id")} /></label>
          <label><span>{t("limits.trader")}</span><input value={mandate.trader} onChange={mandateField("trader")} /></label>
          <label><span>{t("limits.display_name")}</span><input value={mandate.display_name} onChange={mandateField("display_name")} /></label>
          <label><span>{t("limits.books")}</span><input value={mandate.book_ids} onChange={mandateField("book_ids")} /></label>
          <label><span>{t("limits.hubs")}</span><input value={mandate.hubs} onChange={mandateField("hubs")} /></label>
          <label><span>{t("limits.max_net")}</span><input inputMode="decimal" value={mandate.max_net_mwh_per_month} onChange={mandateField("max_net_mwh_per_month")} /></label>
          <label><span>{t("limits.max_tenor")}</span><input inputMode="numeric" value={mandate.max_tenor_months} onChange={mandateField("max_tenor_months")} /></label>
          <label><span>{t("limits.valid_until")}</span><input type="date" value={mandate.valid_until} onChange={mandateField("valid_until")} /></label>
          <button
            type="button"
            disabled={!mandate.mandate_id.trim() || !mandate.trader.trim() || !mandate.display_name.trim()}
            onClick={saveMandate}
          >
            {t("limits.save")}
          </button>
        </div>
      )}
      {message && <p role="status">{message}</p>}
    </section>
  );
}

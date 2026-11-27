import { useCallback, useMemo, useState } from "react";
import { useCachedRead } from "@/app/data/readCache";

import {
  api,
  type CreditExposureRowDTO,
  type CreditLineInput,
  type GovernedSaveDTO,
  type MandateInput,
  type MandateUsageRowDTO,
} from "@/api/client";
import { formatMoney, formatQuantity, splitList } from "@/app/model/riskLimitsModel";
import { pendingByTarget, saveOutcome } from "@/app/model/makerCheckerModel";
import { FigureProvenance } from "./FigureProvenance";
import { PENDING_CHANGES_KEY } from "./PendingChangesPanel";
import { ReportExport } from "./ReportExport";
import { WhyButton } from "./WhyButton";
import { MethodNote } from "./MethodNote";
import { MarksAsOf, marksRowAttributes } from "./MarksAsOf";
import { DataGrid, StatusBadge, type DataGridColumn, type StatusTone, PeriodPicker, RecordPicker, UpdatingMark } from "@/components/ui";
import { idFromName } from "@/components/ui/recordPickerModel";
import { bookOptions, contractOptions, counterpartyOptions, hubOptions, personOptions } from "@/app/model/recordOptions";
import { REPORTING_CURRENCIES, formatMeasure } from "@/app/time/valueFormat";
import { deskMonthsIn, formatDeliveryMonth } from "@/app/time/timeFormat";
import { useConvertedAmount } from "@/app/time/useConversion";
import { ConvertedValue } from "@/components/ui/ConvertedValue";
import { useApiStore } from "@/stores/api";
import { serverWarningText } from "@/app/warningLabel";
import { useLineageLookup } from "./CommercialWarningList";
import { breachSummary, pctRangeText } from "@/app/model/limitBreaches";

type Translate = (key: string, options?: Record<string, unknown>) => string;

const STATUS_TONE: Record<string, StatusTone> = {
  ok: "ok",
  watch: "watch",
  breach: "breach",
  expired: "breach",
  incomplete: "stale",
};

function LimitBadge({ status, t }: { status: string; t: Translate }) {
  return (
    <StatusBadge tone={STATUS_TONE[status] ?? "neutral"}>
      {t(`limits.status_${status}`)}
    </StatusBadge>
  );
}

function Utilisation({ pct }: { pct: number | null }) {
  if (pct === null) return <span className="muted">-</span>;
  const width = Math.max(0, Math.min(100, pct));
  return (
    <span className="limit-meter" title={formatMeasure("percent", pct)}>
      <span className="limit-meter-bar" style={{ width: `${width}%` }} data-over={pct > 100 ? "true" : undefined} />
      <span className="limit-meter-value">{formatMeasure("percent", pct, { decimals: 0 })}</span>
    </span>
  );
}

/** An amount in another currency than the reader reports in: the converted figure under it. */
function InReportingCurrency({ amount, currency }: { amount: number; currency: string }) {
  const converted = useConvertedAmount({ amount, currency, subject: "limit" });
  return <ConvertedValue converted={converted} mode="line" compact />;
}

const EMPTY_LINE = {
  counterparty_id: "",
  name: "",
  aliases: "",
  limit_amount: "",
  currency: "EUR",
  collateral_amount: "0",
  guarantee_amount: "",
  guarantee_expiry: "",
  rating: "",
  contract_ids: "",
  receivable_days: "50",
  valid_until: "",
  legal_entity: "",
  change_reason: "",
};

const EMPTY_MANDATE = {
  mandate_id: "",
  trader: "",
  display_name: "",
  book_ids: "",
  hubs: "",
  max_net_mwh_per_month: "",
  max_tenor_months: "",
  min_hedge: "",
  max_hedge: "",
  instruments: "",
  valid_until: "",
  change_reason: "",
};

/**
 * Credit and mandates: counterparty exposure against approved lines, and each trader's open
 * positions against their mandate. Risk (REVIEWER) maintains both; everyone in the book sees
 * the utilisation, so a breach is visible to the trader and the desk head at the same time.
 */
export function RiskLimitsPanel({ t, canMaintainRisk }: { t: Translate; canMaintainRisk: boolean }) {
  // Kept across task switches (app/data/readCache.ts): the last answer shows at once.
  const creditRead = useCachedRead("/portfolio/credit-exposure", () => api.creditExposure());
  const mandateRead = useCachedRead("/portfolio/mandate-usage", () => api.mandateUsage());
  const credit: CreditExposureRowDTO[] | null = creditRead.data?.data.rows ?? null;
  const mandates: MandateUsageRowDTO[] | null = mandateRead.data?.data.rows ?? null;
  const warnings: string[] = creditRead.data?.meta?.warnings ?? [];
  // P-17: a limit change waits for a second person; the rows it would change say so.
  const pendingRead = useCachedRead(PENDING_CHANGES_KEY, () => api.changeRequests("pending"));
  const pendingLines = useMemo(() => pendingByTarget(pendingRead.data?.data.changes, "credit_line"), [pendingRead.data]);
  const pendingMandates = useMemo(
    () => pendingByTarget(pendingRead.data?.data.changes, "trader_mandate"),
    [pendingRead.data],
  );
  const [line, setLine] = useState(EMPTY_LINE);
  const [mandate, setMandate] = useState(EMPTY_MANDATE);
  const [editing, setEditing] = useState<"none" | "credit" | "mandate">("none");
  // The deals the stored line had when the form read it, and whether the form has read it yet:
  // a save before the read would send its links empty and clear the breach (QA-R-01).
  const [linkedOnLoad, setLinkedOnLoad] = useState(0);
  const [lineLoading, setLineLoading] = useState(false);
  const [confirmUnlink, setConfirmUnlink] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  // The live principle (UX_REFERENCE rule 25): every choice below is a record the firm holds.
  const contracts = useApiStore((state) => state.upstreamContracts);
  const booksRead = useCachedRead("/portfolio/books", () => api.tradingBooks());
  const bookNames = useMemo(() => new Map((booksRead.data?.data.books ?? []).map((book) => [book.book_id, book.name])), [booksRead.data]);
  const counterparties = useMemo(() => counterpartyOptions(credit ?? []), [credit]);
  const contractChoices = useMemo(() => contractOptions(contracts, splitList(line.contract_ids)), [contracts, line.contract_ids]);
  const bookChoices = useMemo(() => bookOptions(booksRead.data?.data.books ?? []), [booksRead.data]);
  const hubChoices = useMemo(() => hubOptions(), []);
  const mandateChoices = useMemo(
    () => (mandates ?? []).map((row) => ({ id: row.mandate_id, label: row.name || row.mandate_id, detail: row.trader })),
    [mandates],
  );
  const traderChoices = useMemo(() => personOptions((mandates ?? []).map((row) => ({ id: row.trader }))), [mandates]);
  const instrumentChoices = useMemo(
    () => ["physical", "future", "forward", "swap", "option"].map((id) => ({ id, label: t(`limits.instrument.${id}`) })),
    [t],
  );
  const listOf = (value: string) => splitList(value);
  const joined = (ids: readonly string[]) => ids.join(", ");
  const pickCounterparty = (choice: { id: string; manual: boolean } | null) => {
    if (!choice) return;
    if (choice.manual) {
      // A counterparty not yet in any record: its id is made from the name, never typed.
      const id = idFromName(choice.id, counterparties.map((item) => item.id));
      setLine((current) => ({ ...current, counterparty_id: id, name: choice.id }));
      return;
    }
    const row = credit?.find((item) => item.counterparty_id === choice.id);
    setLinkedOnLoad(0);
    setConfirmUnlink(false);
    setLineLoading(true);
    // Every stored field, so saving one changed field sends the others as they are.
    api.creditLine(choice.id)
      .then((response) => {
        const stored = response.data;
        setLinkedOnLoad(stored.contract_ids.length);
        setLine((current) => current.counterparty_id !== choice.id ? current : ({
          ...current,
          name: stored.name,
          aliases: stored.aliases.join(", "),
          legal_entity: stored.legal_entity ?? "",
          limit_amount: String(stored.limit_amount),
          currency: stored.currency,
          collateral_amount: String(stored.collateral_amount),
          guarantee_amount: stored.guarantee_amount ?? "",
          guarantee_expiry: stored.guarantee_expiry ?? "",
          rating: stored.rating ?? "",
          contract_ids: stored.contract_ids.join(", "),
          receivable_days: String(stored.receivable_days),
          valid_until: stored.valid_until ?? "",
        }));
      })
      .catch(fail)
      .finally(() => setLineLoading(false));
    setLine((current) => ({
      ...current,
      counterparty_id: choice.id,
      name: row?.counterparty ?? current.name,
      limit_amount: row ? String(row.limit) : current.limit_amount,
      currency: row?.currency ?? current.currency,
      collateral_amount: row ? String(row.collateral) : current.collateral_amount,
      rating: row?.rating ?? current.rating,
      valid_until: row?.valid_until ?? current.valid_until,
    }));
  };
  const pickMandate = (choice: { id: string; manual: boolean } | null) => {
    if (!choice) return;
    if (choice.manual) {
      const id = idFromName(choice.id, mandateChoices.map((item) => item.id));
      setMandate((current) => ({ ...current, mandate_id: id, display_name: choice.id }));
      return;
    }
    const row = mandates?.find((item) => item.mandate_id === choice.id);
    setMandate((current) => ({
      ...current,
      mandate_id: choice.id,
      trader: row?.trader ?? current.trader,
      display_name: row?.name ?? current.display_name,
      book_ids: row?.books ?? current.book_ids,
      hubs: row?.hubs ?? current.hubs,
      max_net_mwh_per_month: row?.max_net_mwh_per_month != null ? String(row.max_net_mwh_per_month) : current.max_net_mwh_per_month,
      max_tenor_months: row?.max_tenor_months != null ? String(row.max_tenor_months) : current.max_tenor_months,
      instruments: row?.instruments ?? current.instruments,
      valid_until: row?.valid_until ?? current.valid_until,
    }));
  };

  const load = useCallback(() => {
    creditRead.refresh();
    mandateRead.refresh();
    pendingRead.refresh();
  }, [creditRead.refresh, mandateRead.refresh, pendingRead.refresh]);

  // Saved at once, or proposed and waiting for a second person (P-17): the message says which.
  const savedMessage = (answer: GovernedSaveDTO | undefined, subject: string) => {
    const outcome = saveOutcome(answer);
    if (outcome === "proposed") return t("changes.proposed", { subject });
    if (outcome === "unchanged") return t("changes.unchanged");
    return t("limits.saved");
  };

  const fail = (caught: unknown) => setMessage(caught instanceof Error ? caught.message : String(caught));

  const unlinkingAll = linkedOnLoad > 0 && splitList(line.contract_ids).length === 0;
  const saveLine = () => {
    const body: CreditLineInput = {
      name: line.name.trim(),
      aliases: splitList(line.aliases),
      limit_amount: Number(line.limit_amount),
      currency: line.currency.trim().toUpperCase(),
      collateral_amount: Number(line.collateral_amount || 0),
      // Exact: the guarantee travels as decimal text, never through a float.
      guarantee_amount: line.guarantee_amount.trim() || null,
      guarantee_expiry: line.guarantee_expiry || null,
      rating: line.rating.trim() || null,
      contract_ids: splitList(line.contract_ids),
      receivable_days: Number(line.receivable_days || 50),
      valid_until: line.valid_until || null,
      legal_entity: line.legal_entity.trim() || null,
      ...(unlinkingAll && confirmUnlink ? { unlink_contracts: true } : {}),
      ...(line.change_reason.trim() ? { change_reason: line.change_reason.trim() } : {}),
    };
    api.saveCreditLine(line.counterparty_id.trim(), body)
      .then((response) => {
        setMessage(savedMessage(response.data, body.name));
        setLine(EMPTY_LINE);
        setLinkedOnLoad(0);
        setConfirmUnlink(false);
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
      min_hedge_ratio_pct: mandate.min_hedge ? Number(mandate.min_hedge) : null,
      max_hedge_ratio_pct: mandate.max_hedge ? Number(mandate.max_hedge) : null,
      instruments: splitList(mandate.instruments).map((item) => item.toLowerCase()),
      physical_allowed: true,
      financial_allowed: true,
      valid_until: mandate.valid_until || null,
      ...(mandate.change_reason.trim() ? { change_reason: mandate.change_reason.trim() } : {}),
    };
    api.saveTraderMandate(mandate.mandate_id.trim(), body)
      .then((response) => {
        setMessage(savedMessage(response.data, body.display_name));
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
  const creditColumns = useMemo<DataGridColumn<CreditExposureRowDTO>[]>(() => [
    {
      id: "counterparty",
      header: t("limits.counterparty"),
      rowHeader: true,
      sortable: true,
      value: (row) => row.counterparty,
      render: (row) => (
        <>
          <strong>{row.counterparty}</strong>{" "}
          <small className="muted">{[row.rating, row.legal_entity, t("limits.legs", { count: row.legs })].filter(Boolean).join(" · ")}</small>
        </>
      ),
    },
    // Each line is in its own currency, so the amounts carry it per row and are not sortable
    // against each other: £31m is not "more" than €4.5m. Utilisation is the comparable figure.
    { id: "limit", header: t("limits.limit"), type: "number", value: (row) => row.limit, format: (_, row) => formatMoney(row.limit, row.currency) },
    { id: "replacement", header: t("limits.replacement"), type: "number", value: (row) => row.replacement_exposure, format: (_, row) => formatMoney(row.replacement_exposure, row.currency) },
    { id: "receivable", header: t("limits.receivable"), type: "number", value: (row) => row.receivable_exposure, format: (_, row) => formatMoney(row.receivable_exposure, row.currency) },
    { id: "collateral", header: t("limits.collateral"), type: "number", value: (row) => row.collateral, format: (_, row) => formatMoney(row.collateral, row.currency) },
    // Tested in the currency the line was approved in (G7); the reporting currency is a second
    // line when it differs, at the latest held ECB rate, named on hover (G3).
    { id: "net", header: t("limits.net"), type: "number", value: (row) => row.net_exposure, render: (row) => <><strong>{formatMoney(row.net_exposure, row.currency)}</strong><InReportingCurrency amount={row.net_exposure} currency={row.currency} /></> },
    { id: "used", header: t("limits.used"), type: "number", sortable: true, value: (row) => row.utilisation_pct, render: (row) => <Utilisation pct={row.utilisation_pct} /> },
    {
      id: "status",
      header: t("limits.status"),
      render: (row) => (
        <span className="limit-status-cell">
          <LimitBadge status={row.status} t={t} />
          {row.status !== "ok" && <WhyButton subject="credit" id={row.counterparty_id} label={row.counterparty} t={t} />}
          {row.unvalued_legs > 0 && <small>{t("limits.unvalued", { count: row.unvalued_legs })}</small>}
          {/* QA-R-07: the marks' day on every line; late or stale in words, the row greyed. */}
          <MarksAsOf row={row} t={t} />
          {(row.open_ended_legs ?? 0) > 0 && (
            <small title={t("limits.open_ended_help")}>{t("limits.open_ended", { count: row.open_ended_legs })}</small>
          )}
          {pendingLines.has(row.counterparty_id) && (
            <StatusBadge tone="watch">{t("changes.awaiting")}</StatusBadge>
          )}
          <FigureProvenance provenance={row.provenance} t={t} />
        </span>
      ),
    },
  ], [pendingLines, t]);

  const names = useLineageLookup();
  const mandateColumns = useMemo<DataGridColumn<MandateUsageRowDTO>[]>(() => [
    // Names in words; the principal and the book ids are on hover (owner: no internal ids on screen).
    { id: "trader", header: t("limits.trader"), rowHeader: true, sortable: true, value: (row) => row.name, render: (row) => <strong title={row.trader}>{row.name || row.trader}</strong> },
    {
      id: "scope",
      header: t("limits.scope"),
      render: (row) => {
        const ids = splitList(row.books);
        const names = ids.map((id) => bookNames.get(id) ?? id);
        return <small title={row.books}>{[names.join(", "), row.hubs].filter(Boolean).join(" · ")}</small>;
      },
    },
    { id: "largest", header: t("limits.largest_net"), type: "number", sortable: true, value: (row) => row.largest_net_mwh, render: (row) => <>{formatQuantity(row.largest_net_mwh)} <small className="muted">{deskMonthsIn(row.largest_at)}</small></> },
    { id: "used", header: t("limits.used"), type: "number", sortable: true, value: (row) => row.utilisation_pct, render: (row) => <Utilisation pct={row.utilisation_pct} /> },
    {
      id: "tenor",
      header: t("limits.tenor"),
      render: (row) => <>{row.furthest_month ? formatDeliveryMonth(row.furthest_month) : "–"}{row.max_tenor_months !== null && <small className="muted"> / {t("limits.months", { count: row.max_tenor_months })}</small>}</>,
    },
    {
      id: "hedge",
      header: t("limits.hedge"),
      render: (row) => (
        <>
          {row.hedge_ratio_range ? pctRangeText(row.hedge_ratio_range, t) : "–"}
          {row.hedge_policy && <small className="muted"> / {row.hedge_policy}</small>}
          {row.hedge_room_mwh !== null && <small className="muted"> · {t("limits.hedge_room", { room: formatQuantity(row.hedge_room_mwh) })}</small>}
          {row.instruments !== "any" && <small className="muted"> · {row.instruments}</small>}
        </>
      ),
    },
    {
      id: "status",
      header: t("limits.status"),
      render: (row) => (
        <span className="limit-status-cell">
          <LimitBadge status={row.status} t={t} />
          {row.status !== "ok" && <WhyButton subject="mandate" id={row.mandate_id} label={row.name} t={t} />}
          {row.breaches && <small className="limit-breaches" title={row.breaches}>{breachSummary(row.breach_notes?.length ? row.breach_notes : row.breaches, t, names.resources).join("; ")}</small>}
          {/* A mandate is measured in MWh, not priced: shown only if the server ever dates it. */}
          <MarksAsOf row={row} t={t} quietWhenCurrent />
          {pendingMandates.has(row.mandate_id) && (
            <StatusBadge tone="watch">{t("changes.awaiting")}</StatusBadge>
          )}
          <FigureProvenance provenance={row.provenance} t={t} />
        </span>
      ),
    },
  ], [bookNames, names, pendingMandates, t]);

  const breaches = [...(credit ?? []), ...(mandates ?? [])].filter((row) => row.status === "breach" || row.status === "expired").length;

  return (
    <section className="workspace-panel span-3 risk-limits-panel desk-panel" aria-labelledby="risk-limits-title">
      <div className="panel-title-row">
        <h2 id="risk-limits-title">{t("limits.title")}</h2>
        {breaches > 0 && <StatusBadge tone="breach">{t("limits.breaches", { count: breaches })}</StatusBadge>}
        <UpdatingMark active={creditRead.updating || mandateRead.updating} label={t("status.updating")} />
      </div>

      <div className="panel-title-row">
        <h3>{t("limits.credit_title")}</h3>
        <MethodNote method={credit?.[0]?.method} subject={t("limits.credit_title")} t={t} />
        <ReportExport t={t} path="/portfolio/credit-exposure" />
      </div>
      {credit && credit.length === 0 && <p className="muted">{t("limits.credit_empty")}</p>}
      {credit && credit.length > 0 && (
        <DataGrid
          id="credit-exposure"
          label={t("limits.credit_title")}
          columns={creditColumns}
          rows={credit}
          rowKey={(row) => row.counterparty_id}
          defaultSort={{ columnId: "used", direction: "descending" }}
          rowAttributes={(row) => ({ "data-status": row.status, ...marksRowAttributes(row) })}
          tableAttributes={{ "data-credit-exposure": "true" }}
        />
      )}

      <div className="panel-title-row">
        <h3>{t("limits.mandate_title")}</h3>
        <MethodNote method={mandates?.[0]?.method} subject={t("limits.mandate_title")} t={t} />
        <ReportExport t={t} path="/portfolio/mandate-usage" />
      </div>
      {mandates && mandates.length === 0 && <p className="muted">{t("limits.mandate_empty")}</p>}
      {mandates && mandates.length > 0 && (
        <DataGrid
          id="mandate-usage"
          label={t("limits.mandate_title")}
          columns={mandateColumns}
          rows={mandates}
          rowKey={(row) => row.mandate_id}
          defaultSort={{ columnId: "used", direction: "descending" }}
          rowAttributes={(row) => ({ "data-status": row.status, ...marksRowAttributes(row) })}
          tableAttributes={{ "data-mandate-usage": "true" }}
        />
      )}
      {warnings.length > 0 && (
        <details className="limit-warnings">
          <summary>{t("limits.notes", { count: warnings.length })}</summary>
          <ul>{warnings.map((warning) => <li key={warning}>{serverWarningText(warning, t)}</li>)}</ul>
        </details>
      )}

      <div className="limit-actions">
        {canMaintainRisk && (<>
          <button type="button" className="secondary-button" onClick={() => setEditing(editing === "credit" ? "none" : "credit")}>
            {t("limits.edit_credit")}
          </button>
          <button type="button" className="secondary-button" onClick={() => setEditing(editing === "mandate" ? "none" : "mandate")}>
            {t("limits.edit_mandate")}
          </button>
        </>)}
        <small className="muted">{t("limits.who_edits")}</small>
      </div>
      {canMaintainRisk && editing === "credit" && (
        <div className="licence-form">
          <RecordPicker
            id="credit-counterparty"
            label={t("limits.counterparty")}
            options={credit ? counterparties : null}
            value={line.counterparty_id || null}
            recentKey="counterparty"
            allowManual
            onChange={pickCounterparty}
          />
          <label><span>{t("limits.display_name")}</span><input value={line.name} onChange={lineField("name")} /></label>
          <label><span>{t("limits.aliases")}</span><input value={line.aliases} onChange={lineField("aliases")} /></label>
          <label><span>{t("limits.limit")}</span><input inputMode="decimal" value={line.limit_amount} onChange={lineField("limit_amount")} /></label>
          <label><span>{t("limits.currency")}</span>
            <select value={line.currency} onChange={lineField("currency")}>
              {REPORTING_CURRENCIES.map((code) => <option key={code} value={code}>{code}</option>)}
            </select>
          </label>
          <label><span>{t("limits.collateral")}</span><input inputMode="decimal" value={line.collateral_amount} onChange={lineField("collateral_amount")} /></label>
          <label><span>{t("limits.guarantee_amount")}</span><input inputMode="decimal" value={line.guarantee_amount} onChange={lineField("guarantee_amount")} /></label>
          <label><span>{t("limits.guarantee_expiry")}</span><PeriodPicker label={t("limits.guarantee_expiry")} value={line.guarantee_expiry} clearable onChange={(value) => setLine((current) => ({ ...current, guarantee_expiry: value }))} /></label>
          <label><span>{t("limits.rating")}</span><input value={line.rating} onChange={lineField("rating")} /></label>
          <RecordPicker
            id="credit-contracts"
            label={t("limits.contracts")}
            multiple
            options={contractChoices}
            value={listOf(line.contract_ids)}
            emptyText={t("limits.no_contracts")}
            onChange={(ids) => setLine((current) => ({ ...current, contract_ids: joined(ids) }))}
          />
          {unlinkingAll && (
            <label className="limits-unlink-confirm">
              <input type="checkbox" checked={confirmUnlink} onChange={(event) => setConfirmUnlink(event.target.checked)} />
              <span>{t("limits.unlink_confirm", { count: linkedOnLoad })}</span>
            </label>
          )}
          <label><span>{t("limits.receivable_days")}</span><input inputMode="numeric" value={line.receivable_days} onChange={lineField("receivable_days")} /></label>
          <label><span>{t("limits.valid_until")}</span><PeriodPicker label={t("limits.valid_until")} value={line.valid_until} clearable onChange={(value) => lineField("valid_until")({ target: { value } } as never)} /></label>
          <label><span>{t("changes.why")}</span><input maxLength={500} placeholder={t("changes.why_hint")} value={line.change_reason} onChange={lineField("change_reason")} /></label>
          <button
            type="button"
            aria-busy={lineLoading || undefined}
            disabled={lineLoading || (unlinkingAll && !confirmUnlink) || !line.counterparty_id.trim() || !line.name.trim() || !(Number(line.limit_amount) >= 0) || !line.limit_amount}
            onClick={saveLine}
          >
            {t("limits.save")}
          </button>
        </div>
      )}
      {canMaintainRisk && editing === "mandate" && (
        <div className="licence-form">
          <RecordPicker
            id="mandate"
            label={t("limits.mandate")}
            options={mandates ? mandateChoices : null}
            value={mandate.mandate_id || null}
            allowManual
            onChange={pickMandate}
          />
          <RecordPicker
            id="mandate-trader"
            label={t("limits.trader")}
            options={mandates ? traderChoices : null}
            value={mandate.trader || null}
            recentKey="trader"
            allowManual
            onChange={(choice) => choice && setMandate((current) => ({ ...current, trader: choice.id }))}
          />
          <label><span>{t("limits.display_name")}</span><input value={mandate.display_name} onChange={mandateField("display_name")} /></label>
          <RecordPicker
            id="mandate-books"
            label={t("limits.books")}
            multiple
            options={booksRead.data ? bookChoices : null}
            value={listOf(mandate.book_ids)}
            onChange={(ids) => setMandate((current) => ({ ...current, book_ids: joined(ids) }))}
          />
          <RecordPicker
            id="mandate-hubs"
            label={t("limits.hubs")}
            multiple
            options={hubChoices}
            value={listOf(mandate.hubs)}
            placeholder={t("limits.any_hub")}
            onChange={(ids) => setMandate((current) => ({ ...current, hubs: joined(ids) }))}
          />
          <label><span>{t("limits.max_net")}</span><input inputMode="decimal" value={mandate.max_net_mwh_per_month} onChange={mandateField("max_net_mwh_per_month")} /></label>
          <label><span>{t("limits.max_tenor")}</span><input inputMode="numeric" value={mandate.max_tenor_months} onChange={mandateField("max_tenor_months")} /></label>
          <label><span>{t("limits.min_hedge")}</span><input inputMode="decimal" value={mandate.min_hedge} onChange={mandateField("min_hedge")} /></label>
          <label><span>{t("limits.max_hedge")}</span><input inputMode="decimal" value={mandate.max_hedge} onChange={mandateField("max_hedge")} /></label>
          <RecordPicker
            id="mandate-instruments"
            label={t("limits.instruments")}
            multiple
            options={instrumentChoices}
            value={listOf(mandate.instruments)}
            onChange={(ids) => setMandate((current) => ({ ...current, instruments: joined(ids) }))}
          />
          <label><span>{t("limits.valid_until")}</span><PeriodPicker label={t("limits.valid_until")} value={mandate.valid_until} clearable onChange={(value) => mandateField("valid_until")({ target: { value } } as never)} /></label>
          <label><span>{t("changes.why")}</span><input maxLength={500} placeholder={t("changes.why_hint")} value={mandate.change_reason} onChange={mandateField("change_reason")} /></label>
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

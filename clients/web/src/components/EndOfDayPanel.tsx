import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";

import { api } from "@/api/client";
import type { DealPnlRowDTO, EodCheckDTO, EodDifferenceDTO, PackScheduleDTO } from "@/api/deals";
import { readKey, useCachedRead } from "@/app/data/readCache";
import { DataGrid, Field, PeriodPicker, Select, type DataGridColumn } from "@/components/ui";

import { differenceText, shownDecimal, todayIso, unacknowledged } from "@/app/model/dealCaptureModel";

type Translate = (key: string, options?: Record<string, unknown>) => string;

/** The times a scheduled pack may go, every half hour from 16:00 to 22:00. */
const SCHEDULE_TIMES = Array.from({ length: 13 }, (_, index) => `${String(16 + Math.floor(index / 2)).padStart(2, "0")}:${index % 2 ? "30" : "00"}`);

/**
 * Book → Blotter, second part: the end-of-day check against the ETRM's own export, closing the
 * day with every difference acknowledged by the signed-in person, the day's P&L as a desk
 * estimate, and the daily pack (download, send by e-mail, or on the desk's schedule).
 */
export function EndOfDayPanel({ t, canWrite, canReadLimits }: { t: Translate; canWrite: boolean; canReadLimits: boolean }) {
  const { i18n } = useTranslation();
  const language = i18n.language;
  const [day, setDay] = useState(todayIso);
  const [etrmFile, setEtrmFile] = useState<File | null>(null);
  const [check, setCheck] = useState<EodCheckDTO | null>(null);
  const [notes, setNotes] = useState<Record<string, string>>({});
  const [closeNote, setCloseNote] = useState("");
  const [message, setMessage] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [packLanguages, setPackLanguages] = useState<string[]>(["en", "zh-CN"]);
  const pnl = useCachedRead(readKey("/desk/deals/pnl", { day }), (signal) => api.dealPnl(day, { signal }).then((response) => response.data));
  const schedule = useCachedRead(readKey("/desk/deals/pack-schedule"), (signal) =>
    api.dailyPackSchedule({ signal }).then((response) => response.data),
  );
  const fail = (caught: unknown) => setMessage(caught instanceof Error ? caught.message : String(caught));

  const runCheck = (file: File | null) => {
    setEtrmFile(file);
    setCheck(null);
    if (!file) return;
    setBusy(true);
    setMessage(null);
    api
      .dealEodCheck(file, day)
      .then((response) => {
        setCheck(response.data);
        setNotes({});
      })
      .catch(fail)
      .finally(() => setBusy(false));
  };

  const missing = unacknowledged(check?.differences ?? [], notes);

  const close = async () => {
    if (!check || !etrmFile) return;
    setBusy(true);
    try {
      const text = await etrmFile.text();
      const response = await api.closeDealDay({
        day,
        etrm_file_name: etrmFile.name,
        etrm_csv: text,
        acknowledgements: notes,
        note: closeNote || undefined,
      });
      setMessage(t("eod.closed_message", { who: response.data.closed_by, count: response.data.differences }));
      pnl.refresh();
    } catch (caught) {
      fail(caught);
    } finally {
      setBusy(false);
    }
  };

  const send = (kinds: string[]) => {
    setBusy(true);
    setMessage(null);
    api
      .sendDailyPack({ day, kinds, languages: packLanguages })
      .then((response) => setMessage(t("eod.pack_queued", { count: response.data.queued.length })))
      .catch(fail)
      .finally(() => setBusy(false));
  };

  const saveSchedule = (next: PackScheduleDTO) => {
    api
      .saveDailyPackSchedule({ enabled: next.enabled, at_local: next.at_local, timezone: next.timezone, weekdays: next.weekdays, kinds: next.kinds, languages: next.languages })
      .then(() => schedule.refresh())
      .catch(fail);
  };

  const diffColumns = useMemo<DataGridColumn<EodDifferenceDTO>[]>(() => [
    { id: "kind", header: t("eod.col.kind"), value: (row) => row.kind, render: (row) => <span className="limit-badge" data-status={row.kind.startsWith("missing") ? "breach" : "watch"}>{t(`eod.kind.${row.kind}`)}</span>, rowHeader: true },
    { id: "hub", header: t("deals.col.hub"), value: (row) => row.hub ?? "" },
    { id: "period", header: t("deals.col.period"), value: (row) => row.product ?? "" },
    { id: "deal", header: t("eod.col.deal"), value: (row) => row.deal_key ?? "", render: (row) => <>{row.deal_key ?? "–"}{row.matched_by === "terms" && <small className="muted"> {t("eod.matched_by_terms")}</small>}</> },
    { id: "etrm", header: t("eod.col.etrm"), value: (row) => row.etrm_trade_id ?? "" },
    { id: "detail", header: t("eod.col.detail"), value: (row) => differenceText(row, t) },
    {
      id: "ack",
      header: t("eod.col.acknowledge"),
      value: (row) => notes[row.id] ?? "",
      render: (row) => (
        <input
          aria-label={t("eod.ack_label", { kind: t(`eod.kind.${row.kind}`) })}
          value={notes[row.id] ?? ""}
          disabled={!canWrite}
          data-eod-ack={row.id}
          onChange={(event) => setNotes((current) => ({ ...current, [row.id]: event.target.value }))}
        />
      ),
      keepWhenEmpty: true,
    },
  ], [t, notes, canWrite]);

  const pnlColumns = useMemo<DataGridColumn<DealPnlRowDTO>[]>(() => [
    { id: "trader", header: t("deals.col.trader"), value: (row) => row.trader, rowHeader: true, span: true },
    { id: "hub", header: t("deals.col.hub"), value: (row) => row.hub },
    { id: "day", header: t("eod.col.day"), type: "number", value: (row) => Number(row.day), format: (_v, row) => shownDecimal(row.day, language, 0) },
    { id: "mtd", header: t("eod.col.mtd"), type: "number", value: (row) => Number(row.mtd), format: (_v, row) => shownDecimal(row.mtd, language, 0) },
    { id: "ytd", header: t("eod.col.ytd"), type: "number", value: (row) => Number(row.ytd), format: (_v, row) => shownDecimal(row.ytd, language, 0) },
    { id: "currency", header: t("eod.col.currency"), value: (row) => row.currency },
  ], [t, language]);

  const status = pnl.data?.status;
  const current = schedule.data;
  const download = (kind: "management" | "risk", lang: "en" | "zh-CN", format: "pdf" | "xlsx") =>
    api.downloadDailyPack(day, kind, lang, format).catch(fail);

  return (
    <section className="workspace-panel span-3" aria-labelledby="eod-title" data-end-of-day="true">
      <h2 id="eod-title">{t("eod.title")}</h2>
      <div className="ds-form-grid">
        <Field label={t("deals.day")}>
          <PeriodPicker label={t("deals.day")} value={day} onChange={(value) => { setDay(value || todayIso()); setCheck(null); }} />
        </Field>
        <Field label={t("eod.etrm_file")} hint={t("eod.etrm_file_hint")}>
          <input type="file" accept=".csv,text/csv" data-eod-file="true" disabled={busy} onChange={(event) => runCheck(event.target.files?.[0] ?? null)} />
        </Field>
      </div>
      <p className="muted" data-day-status={status?.closed ? "closed" : "estimate"}>
        {status?.closed && status.closes.length
          ? t("deals.status_closed", { who: status.closes[status.closes.length - 1].closed_by })
          : t("deals.status_estimate")}
      </p>

      {check && (
        <div data-eod-result="true">
          <p>
            {t("eod.summary", { captured: check.captured_deals, etrm: check.etrm_trades, matched: check.matched, differences: check.differences.length })}
            {check.reference_column ? "" : ` ${t("eod.no_reference")}`}
          </p>
          <DataGrid
            id="eod-differences"
            label={t("eod.differences")}
            columns={diffColumns}
            rows={check.differences}
            rowKey={(row) => row.id}
            density="compact"
            empty={t("eod.no_differences")}
            rowAttributes={(row) => ({ "data-record": "eod-difference", "data-kind": row.kind })}
          />
          {canWrite && (
            <div className="ds-form-grid">
              <Field label={t("eod.close_note")}>
                <input value={closeNote} onChange={(event) => setCloseNote(event.target.value)} />
              </Field>
              <div className="ds-form-grid-action">
                <button type="button" data-eod-close="true" disabled={busy || missing > 0} onClick={() => void close()}>
                  {missing > 0 ? t("eod.close_missing", { count: missing }) : t("eod.close")}
                </button>
              </div>
            </div>
          )}
        </div>
      )}

      <h3>{t("eod.pnl_title")}</h3>
      <p className="muted">{t("eod.pnl_method")}</p>
      {pnl.data?.simulated_marks && <p className="limit-badge" data-status="breach">{t("eod.simulated")}</p>}
      <DataGrid id="deal-pnl" label={t("eod.pnl_title")} columns={pnlColumns} rows={pnl.data?.by_trader_hub ?? []} rowKey={(row) => `${row.book_id}:${row.trader}:${row.hub}:${row.currency}`} density="compact" empty={t("eod.pnl_empty")} />
      {(pnl.data?.not_valued.length ?? 0) > 0 && <p className="muted">{t("eod.not_valued", { count: pnl.data?.not_valued.length })}</p>}

      <h3>{t("eod.pack_title")}</h3>
      <p className="muted">{t("eod.pack_hint")}</p>
      <div className="ds-form-grid" role="group" aria-label={t("eod.pack_title")}>
        {(["management", "risk"] as const).filter((kind) => kind === "management" || canReadLimits).map((kind) => (
          <div key={kind} className="ds-form-grid-action" data-pack-kind={kind}>
            <strong>{t(`eod.pack.${kind}`)}</strong>{" "}
            {(["en", "zh-CN"] as const).map((lang) => (
              <span key={lang}>
                <button type="button" onClick={() => void download(kind, lang, "pdf")}>{t(`eod.pack_pdf_${lang === "en" ? "en" : "zh"}`)}</button>{" "}
                <button type="button" onClick={() => void download(kind, lang, "xlsx")}>{t(`eod.pack_xlsx_${lang === "en" ? "en" : "zh"}`)}</button>{" "}
              </span>
            ))}
          </div>
        ))}
      </div>
      {canWrite && (
        <div className="ds-form-grid">
          <Field label={t("eod.pack_languages")}>
            <Select
              value={packLanguages.join(",")}
              onChange={(value) => setPackLanguages(value.split(","))}
              options={[
                { value: "en,zh-CN", label: t("eod.lang_both") },
                { value: "en", label: t("eod.lang_en") },
                { value: "zh-CN", label: t("eod.lang_zh") },
              ]}
            />
          </Field>
          <div className="ds-form-grid-action">
            <button type="button" disabled={busy} data-pack-send="management" onClick={() => send(["management"])}>{t("eod.send_management")}</button>{" "}
            {canReadLimits && <button type="button" disabled={busy} data-pack-send="risk" onClick={() => send(["management", "risk"])}>{t("eod.send_both")}</button>}
          </div>
          {current && Object.values(current.recipients ?? {}).every((count) => count === 0) && (
            <p className="muted">{t("eod.no_recipients")}</p>
          )}
        </div>
      )}
      {canWrite && current && (
        <details className="scope-fold" data-pack-schedule="true">
          <summary>{current.enabled ? t("eod.schedule_on", { at: current.at_local, zone: current.timezone }) : t("eod.schedule_off")}</summary>
          <div className="ds-form-grid">
            <Field label={t("eod.schedule_enabled")}>
              <Select value={current.enabled ? "on" : "off"} onChange={(value) => saveSchedule({ ...current, enabled: value === "on" })} options={[{ value: "off", label: t("eod.off") }, { value: "on", label: t("eod.on") }]} />
            </Field>
            <Field label={t("eod.schedule_time")}>
              <Select value={current.at_local} onChange={(value) => saveSchedule({ ...current, at_local: value })} options={SCHEDULE_TIMES.map((time) => ({ value: time, label: time }))} />
            </Field>
            <Field label={t("eod.schedule_zone")}>
              <Select value={current.timezone} onChange={(value) => saveSchedule({ ...current, timezone: value })} options={["Europe/London", "Europe/Amsterdam", "Europe/Berlin", "Asia/Shanghai", "UTC"].map((zone) => ({ value: zone, label: zone }))} />
            </Field>
          </div>
        </details>
      )}
      {busy && <p role="status">{t("deals.working")}</p>}
      {message && <p role="status">{message}</p>}
    </section>
  );
}

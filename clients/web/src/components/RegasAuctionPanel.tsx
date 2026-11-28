/**
 * Desk → Cargoes → Regas auctions: "bid at most X for this slot", live, with what drives it.
 *
 * - The list: the desk's auction cases, open first, each with its countdown to the close.
 * - The case: the most to bid in the auction's own quotation and as a total, the auction's
 *   current level and the headroom with its state (room to bid, at the limit, stop); the
 *   countdowns to the close and to the cargo offer's expiry; what drives it (from hub revenue to
 *   the maximum bid), the sensitivities and the break-even hub price; the residual exposure and
 *   the hedges that lock the margin if the slot is won; a read-only what-if on position and
 *   limits; every input with where it came from, and the ones entered by hand marked so.
 * - Live: the answer is re-read when a price, FX rate, mark or limit changes (the session's one
 *   live stream; `REGAS_LIVE_TOPICS`), and the countdowns tick every second.
 *
 * Rule 8: nothing here bids, orders or nominates. "Prepare hedge orders" is disabled with its
 * note; a trader acts in the execution tool and on the terminal's platform.
 */
import { useEffect, useMemo, useState } from "react";

import { api } from "@/api/client";
import type {
  RegasAnswerDTO,
  RegasCaseAnswerDTO,
  RegasCaseDTO,
  RegasCasesDTO,
  RegasCostLineDTO,
  RegasDayDTO,
  RegasExposureDTO,
  RegasHedgeDTO,
  RegasSnapshotDTO,
  RegasWhatIfDTO,
} from "@/api/regasAuction";
import { useNow } from "@/app/data/connection";
import { readKey, useCachedRead } from "@/app/data/readCache";
import { useLiveTopics } from "@/app/hooks/useLive";
import { shownDecimal } from "@/app/model/dealCaptureModel";
import {
  REGAS_LIVE_MS,
  REGAS_LIVE_TOPICS,
  bodyFromInputs,
  countdownText,
  deadlineTone,
  draftFromNotice,
  draftGaps,
  draftToBody,
  emptyDraft,
  isBidLevel,
  inputLabel,
  missingSummary,
  quotedUnit,
  secondsUntil,
  stateTone,
  withCost,
  withHandPrice,
  withLevel,
  withRate,
  type RegasDraft,
} from "@/app/model/regasAuctionModel";
import { Button, DataGrid, Field, Instant, PeriodPicker, Select, Skeleton, StatusBadge, UpdatingMark, type DataGridColumn } from "@/components/ui";

type Translate = (key: string, options?: Record<string, unknown>) => string;

/** The sim mark beside a simulated value (UX rule 10), as on the board. */
function SimMark({ t }: { t: Translate }) {
  return (
    <span className="ds-cell-mark" data-state="simulated" title={t("board.sim_long")}>
      <span aria-hidden="true">{t("board.sim")}</span>
      <span className="ds-visually-hidden">{t("board.sim_long")}</span>
    </span>
  );
}

/** The case open beside the list: the `auction` URL parameter (a link, an alert, Back). */
function useOpenCase(): [string | null, (caseId: string | null) => void] {
  const read = () => new URLSearchParams(window.location.search).get("auction");
  const [open, setOpen] = useState<string | null>(read);
  useEffect(() => {
    const follow = () => setOpen(read());
    window.addEventListener("popstate", follow);
    return () => window.removeEventListener("popstate", follow);
  }, []);
  const choose = (caseId: string | null) => {
    const url = new URL(window.location.href);
    if (caseId) url.searchParams.set("auction", caseId);
    else url.searchParams.delete("auction");
    window.history.replaceState(window.history.state, "", url);
    setOpen(caseId);
  };
  return [open, choose];
}

function failText(caught: unknown): string {
  if (caught instanceof Error) return caught.message;
  return String(caught);
}

export function RegasAuctionPanel({ t, language, canWrite }: { t: Translate; language: string; canWrite: boolean }) {
  const list = useCachedRead(readKey("/desk/regas-auctions"), (signal) => api.regasAuctions({ signal }).then((r) => r.data));
  const [openId, setOpenId] = useOpenCase();
  const [creating, setCreating] = useState(false);
  const nowMs = useNow(1_000);
  const data: RegasCasesDTO | undefined = list.data;
  const cases = data?.cases ?? [];
  const selected = openId ?? (creating ? null : cases.find((item) => item.state === "open")?.case_id ?? cases[0]?.case_id ?? null);

  return (
    <div className="regas-desk" data-regas-desk="">
      <section className="trader-panel regas-list" aria-labelledby="regas-list-title">
        <div className="trader-panel-head">
          <h2 id="regas-list-title">{t("regas.list.title")}</h2>
          {canWrite && (
            <Button size="sm" variant="secondary" data-regas-new="" onClick={() => { setCreating(true); setOpenId(null); }}>
              {t("regas.list.new")}
            </Button>
          )}
        </div>
        <div className="trader-panel-body">
          {list.loading && !data ? (
            <Skeleton rows={4} label={t("regas.loading")} />
          ) : cases.length === 0 ? (
            <p className="trader-muted">{t("regas.list.empty")}</p>
          ) : (
            <ul className="regas-case-list">
              {cases.map((item) => {
                const left = secondsUntil(item.auction_closes_at_utc, nowMs);
                return (
                  <li key={item.case_id}>
                    <button
                      type="button"
                      className="regas-case-row"
                      aria-current={selected === item.case_id ? "true" : undefined}
                      data-record="regas-case"
                      data-regas-case-state={item.state}
                      onClick={() => { setCreating(false); setOpenId(item.case_id); }}
                    >
                      <span className="regas-case-name">{item.title}</span>
                      <span className="trader-meta">{item.terminal_name} · {item.hub} · {item.counterparty_name}</span>
                      {item.state === "open" ? (
                        <StatusBadge tone={deadlineTone(left)}>{t("regas.closes_in", { time: countdownText(left, t("regas.closed_word")) })}</StatusBadge>
                      ) : (
                        <StatusBadge tone={item.state === "won" ? "ok" : "neutral"}>{t(`regas.outcome.${item.state}`)}</StatusBadge>
                      )}
                    </button>
                  </li>
                );
              })}
            </ul>
          )}
        </div>
      </section>
      <div className="regas-main">
        {creating || (!selected && canWrite) ? (
          data ? (
            <RegasCaseForm
              t={t}
              choices={data.choices}
              onCancel={() => setCreating(false)}
              onOpened={(item) => {
                setCreating(false);
                list.refresh();
                setOpenId(item.case_id);
              }}
            />
          ) : (
            <Skeleton rows={6} label={t("regas.loading")} />
          )
        ) : selected ? (
          <RegasCaseView key={selected} caseId={selected} t={t} language={language} canWrite={canWrite} nowMs={nowMs} onChanged={list.refresh} />
        ) : (
          <p className="trader-muted">{t("regas.list.empty")}</p>
        )}
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ the case */

function RegasCaseView({ caseId, t, language, canWrite, nowMs, onChanged }: { caseId: string; t: Translate; language: string; canWrite: boolean; nowMs: number; onChanged: () => void }) {
  const read = useCachedRead(readKey(`/desk/regas-auctions/${caseId}`), (signal) => api.regasAuction(caseId, { signal }).then((r) => r.data));
  const snaps = useCachedRead(readKey(`/desk/regas-auctions/${caseId}/snapshots`), (signal) => api.regasAuctionSnapshots(caseId, { signal }).then((r) => r.data.snapshots));
  // Live: a price, FX rate, mark or limit change re-reads the answer (bursts read once).
  useLiveTopics(REGAS_LIVE_TOPICS, read.refresh, { minIntervalMs: REGAS_LIVE_MS });
  const [message, setMessage] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [level, setLevel] = useState("");
  const [note, setNote] = useState("");
  const [whatIf, setWhatIf] = useState<RegasWhatIfDTO | null>(null);
  const [outcome, setOutcome] = useState<"won" | "lost" | "lapsed">("lost");
  const [closeNote, setCloseNote] = useState("");
  const data: RegasCaseAnswerDTO | undefined = read.data;

  useEffect(() => {
    setLevel(data?.case.inputs?.auction.level?.value ?? "");
  }, [data?.case.inputs?.auction.level?.value]);

  if (!data) {
    if (read.error) return <p className="trader-degraded" role="alert">{failText(read.error)}</p>;
    return <Skeleton rows={8} label={t("regas.loading")} />;
  }
  const { case: item, answer } = data;
  const open = item.state === "open";
  const editable = canWrite && open && item.inputs !== undefined;

  const run = (work: () => Promise<unknown>, done?: string) => {
    setBusy(true);
    setMessage(null);
    work()
      .then(() => {
        if (done) setMessage(done);
        read.refresh();
        snaps.refresh();
        onChanged();
      })
      .catch((caught) => setMessage(failText(caught)))
      .finally(() => setBusy(false));
  };
  const save = (change: (body: ReturnType<typeof bodyFromInputs>) => ReturnType<typeof bodyFromInputs>) => {
    if (!item.inputs) return;
    run(() => api.saveRegasAuction(caseId, change(bodyFromInputs(item.inputs!, item.version))));
  };

  const closes = secondsUntil(item.auction_closes_at_utc, nowMs);
  const expires = secondsUntil(item.offer_expires_at_utc, nowMs);
  const unit = quotedUnit(answer);
  const zone = item.inputs?.auction.time_zone ?? "";
  const costLabels = Object.fromEntries(answer.cost_lines.map((line) => [line.key, t(`regas.cost.${line.key}`, { defaultValue: line.label })]));

  return (
    <div className="regas-case" data-regas-case={item.case_id} data-regas-state={answer.state} aria-busy={read.updating || undefined}>
      <header className="trader-panel regas-head">
        <div className="trader-panel-head">
          <h2>{item.title}</h2>
          <span className="trader-meta">{item.terminal_name} · {item.hub} · {t("regas.owner")}: {item.counterparty_name}</span>
          <UpdatingMark active={read.updating} label={t("regas.updating")} />
        </div>
        <div className="regas-deadlines">
          <span data-regas-deadline="close">
            <StatusBadge tone={open ? deadlineTone(closes) : "neutral"}>
              {open ? t("regas.closes_in", { time: countdownText(closes, t("regas.closed_word")) }) : t(`regas.outcome.${item.state}`)}
            </StatusBadge>{" "}
            <span className="trader-meta">{t("regas.closes_at")} <Instant value={item.auction_closes_at_utc} date="always" /> · {t("regas.window_zone", { zone })}</span>
          </span>
          {item.offer_expires_at_utc && (
            <span data-regas-deadline="offer">
              <StatusBadge tone={open ? deadlineTone(expires) : "neutral"}>{t("regas.offer_in", { time: countdownText(expires, t("regas.lapsed_word")) })}</StatusBadge>{" "}
              <span className="trader-meta">{t("regas.offer_at")} <Instant value={item.offer_expires_at_utc} date="always" /></span>
            </span>
          )}
          {answer.offer_lapses_before_close && <span className="trader-degraded">{t("regas.offer_before_close")}</span>}
        </div>
      </header>

      <section className="trader-panel regas-answer" aria-label={t("regas.answer.title")} data-regas-answer={answer.state}>
        {answer.computed ? (
          <div className="regas-figures">
            <div className="regas-figure regas-figure-main" data-regas-max-bid={answer.max_bid_quoted}>
              <span className="regas-figure-label">{isBidLevel(answer) ? t("regas.answer.bid_at_most") : t("regas.answer.illustration")}</span>
              <span className="regas-figure-value">
                {shownDecimal(answer.max_bid_quoted, language, answer.quotation === "per_mwh" ? 3 : 0)}
                {answer.simulated ? <SimMark t={t} /> : null}
              </span>
              <span className="regas-figure-unit">{unit}</span>
              <span className="trader-meta">{t("regas.answer.total", { total: shownDecimal(answer.max_bid_total, language, 0), currency: answer.currency, energy: shownDecimal(answer.energy_unloaded_mwh, language, 0) })}</span>
              {answer.quoted_low && answer.quoted_high && (
                <span className="trader-meta">{t("regas.answer.tolerance", { low: shownDecimal(answer.quoted_low, language, 3), high: shownDecimal(answer.quoted_high, language, 3) })}</span>
              )}
            </div>
            <div className="regas-figure">
              <span className="regas-figure-label">{t("regas.answer.level")}</span>
              <span className="regas-figure-value">{answer.level ? shownDecimal(answer.level, language, answer.quotation === "per_mwh" ? 3 : 0) : "–"}</span>
              <span className="regas-figure-unit">{unit}</span>
              {editable && (
                <span className="regas-inline">
                  <input aria-label={t("regas.answer.level_input")} inputMode="decimal" value={level} onChange={(event) => setLevel(event.target.value)} data-regas-level-input="" />
                  <Button size="sm" variant="secondary" disabled={busy} onClick={() => save((body) => withLevel(body, level))} data-regas-level-save="">{t("regas.answer.level_save")}</Button>
                </span>
              )}
              {item.inputs?.auction.level && <span className="trader-meta">{t("regas.entered_by", { who: item.inputs.auction.level.by ?? "", at: (item.inputs.auction.level.at ?? "").slice(11, 16) })}</span>}
            </div>
            <div className="regas-figure" data-regas-headroom={answer.headroom ?? ""}>
              <span className="regas-figure-label">{t("regas.answer.headroom")}</span>
              <span className="regas-figure-value">{answer.headroom ? shownDecimal(answer.headroom, language, answer.quotation === "per_mwh" ? 3 : 0) : "–"}</span>
              <span className="regas-figure-unit">{unit}</span>
              <span data-regas-state-badge={answer.state}><StatusBadge tone={stateTone(answer.state)}>{t(`regas.state.${answer.state}`)}</StatusBadge></span>
            </div>
            <div className="regas-figure">
              <span className="regas-figure-label">{t("regas.answer.break_even")}</span>
              <span className="regas-figure-value">{answer.break_even_hub_price ? shownDecimal(answer.break_even_hub_price, language, 3) : "–"}</span>
              <span className="regas-figure-unit">{answer.currency}/MWh</span>
              <span className="trader-meta">{answer.break_even_note ? t("regas.answer.price_does_not_decide") : t("regas.answer.break_even_note", { hub: item.hub })}</span>
            </div>
          </div>
        ) : (
          <div className="regas-missing" data-regas-missing={answer.missing.length}>
            <p><StatusBadge tone="watch">{t("regas.state.missing_inputs")}</StatusBadge> {t("regas.missing.lead")}</p>
            <ul>
              {missingSummary(answer.missing).map((gap) => (
                <li key={`${gap.kind}:${gap.what}`}>{t(`regas.missing.${gap.kind}`, { what: gap.what, count: gap.count, defaultValue: gap.what })}</li>
              ))}
            </ul>
          </div>
        )}
        {answer.simulated && <p className="trader-foot" data-regas-illustration="">{t("regas.illustration_note")}</p>}
        {answer.hand_entered.length > 0 && (
          <p className="trader-foot" data-regas-hand={answer.hand_entered.length}>{t("regas.hand_entered", { count: answer.hand_entered.length, items: [...new Set(answer.hand_entered.map((key) => inputLabel(key.startsWith("price:") ? key.split(":").slice(0, 2).join(":") : key, costLabels, t)))].join(", ") })}</p>
        )}
        <div className="regas-actions">
          {canWrite && open && (
            <span className="regas-inline">
              <input aria-label={t("regas.snapshot.note")} placeholder={t("regas.snapshot.note")} value={note} onChange={(event) => setNote(event.target.value)} />
              <Button size="sm" variant="primary" disabled={busy} data-regas-snapshot="" onClick={() => run(() => api.saveRegasSnapshot(caseId, note).then(() => setNote("")), t("regas.snapshot.saved"))}>{t("regas.snapshot.save")}</Button>
            </span>
          )}
          <span className="regas-inline" aria-label={t("regas.report.title")} role="group">
            <span className="trader-meta">{t("regas.report.title")}</span>
            {(["en", "zh-CN"] as const).map((lang) =>
              (["pdf", "xlsx"] as const).map((format) => (
                <Button key={`${lang}-${format}`} size="sm" variant="quiet" onClick={() => api.downloadRegasReport(caseId, lang, format).catch((caught) => setMessage(failText(caught)))}>
                  {t(`regas.report.${format}`)} {lang === "en" ? "EN" : "中文"}
                </Button>
              )),
            )}
          </span>
          <span className="trader-meta"><Instant value={answer.as_of_utc} prefix={t("regas.as_of")} seconds /></span>
        </div>
        {message && <p className="trader-foot" role="status">{message}</p>}
      </section>

      {answer.computed && (
        <div className="regas-grid">
          <section className="trader-panel" aria-labelledby={`regas-drivers-${caseId}`}>
            <div className="trader-panel-head"><h2 id={`regas-drivers-${caseId}`}>{t("regas.drivers.title")}</h2></div>
            <div className="trader-panel-body">
              <Waterfall answer={answer} t={t} language={language} />
            </div>
          </section>
          <section className="trader-panel" aria-labelledby={`regas-sens-${caseId}`}>
            <div className="trader-panel-head"><h2 id={`regas-sens-${caseId}`}>{t("regas.sens.title")}</h2></div>
            <div className="trader-panel-body">
              <Sensitivities answer={answer} t={t} language={language} />
              <h3>{t("regas.exposure.title")}</h3>
              <Exposure rows={answer.exposure ?? []} t={t} language={language} />
            </div>
          </section>
          <section className="trader-panel" aria-labelledby={`regas-hedges-${caseId}`}>
            <div className="trader-panel-head"><h2 id={`regas-hedges-${caseId}`}>{t("regas.hedges.title")}</h2></div>
            <div className="trader-panel-body">
              <Hedges rows={answer.hedges ?? []} t={t} language={language} />
              <div className="trader-order-row">
                <span className="trader-muted">{t("regas.hedges.note")}</span>
                <Button size="sm" disabled title={answer.prepare_hedge_orders.note} data-regas-prepare-orders="">{t("regas.hedges.prepare")}</Button>
              </div>
              <Button size="sm" variant="secondary" disabled={busy} data-regas-what-if="" onClick={() => api.regasAuctionWhatIf(caseId).then((r) => setWhatIf(r.data)).catch((caught) => setMessage(failText(caught)))}>
                {t("regas.whatif.run")}
              </Button>
              {whatIf && <WhatIf data={whatIf} t={t} language={language} />}
            </div>
          </section>
        </div>
      )}

      <section className="trader-panel regas-inputs" aria-labelledby={`regas-inputs-${caseId}`}>
        <div className="trader-panel-head">
          <h2 id={`regas-inputs-${caseId}`}>{t("regas.inputs.title")}</h2>
          <span className="trader-meta">{t("regas.inputs.slot", { energy: shownDecimal(answer.slot.energy_mwh, language, 0), days: answer.slot.days, count: answer.slot.days })}</span>
        </div>
        <div className="trader-panel-body">
          <CostLines lines={answer.cost_lines} t={t} language={language} editable={editable} busy={busy} onSave={(key, value, link) => save((body) => withCost(body, key, value, link))} />
          <HandInputs answer={answer} hub={item.hub} t={t} editable={editable} busy={busy} onPrice={(value) => save((body) => withHandPrice(body, item.hub, value))} onRate={(value) => save((body) => withRate(body, value))} />
          <details className="scope-fold" data-regas-provenance="">
            <summary>{t("regas.inputs.prices", { count: answer.days?.length ?? 0 })}</summary>
            <Days rows={answer.days ?? []} t={t} language={language} />
            <ul className="regas-assumptions">
              {answer.assumptions.map((line) => <li key={line.key}>{line.text}</li>)}
            </ul>
          </details>
          <Snapshots rows={snaps.data ?? []} t={t} language={language} />
          {canWrite && open && (
            <div className="ds-form-grid regas-close" role="group" aria-label={t("regas.close.title")}>
              <Field label={t("regas.close.outcome")}>
                <Select value={outcome} onChange={(value) => setOutcome(value as typeof outcome)} options={(["won", "lost", "lapsed"] as const).map((value) => ({ value, label: t(`regas.outcome.${value}`) }))} />
              </Field>
              <Field label={t("regas.close.note")}>
                <input value={closeNote} onChange={(event) => setCloseNote(event.target.value)} />
              </Field>
              <div className="ds-form-grid-action desk-actions">
                <Button size="sm" variant="secondary" disabled={busy || closeNote.trim().length < 3} onClick={() => run(() => api.closeRegasAuction(caseId, outcome, closeNote.trim()), t("regas.close.done"))}>{t("regas.close.save")}</Button>
              </div>
            </div>
          )}
          {!open && item.close_note && <p className="trader-foot">{t("regas.close.closed", { outcome: t(`regas.outcome.${item.state}`), who: item.closed_by ?? "", note: item.close_note })}</p>}
        </div>
      </section>
    </div>
  );
}

function Waterfall({ answer, t, language }: { answer: RegasAnswerDTO; t: Translate; language: string }) {
  const columns = useMemo<DataGridColumn<NonNullable<RegasAnswerDTO["waterfall"]>[number]>[]>(() => [
    { id: "item", header: t("regas.col.item"), value: (row) => row.label, rowHeader: true, render: (row) => (row.key === "max_bid" ? <strong>{t("regas.cost.max_bid")}</strong> : t(`regas.cost.${row.key}`, { defaultValue: row.label })) },
    { id: "total", header: t("regas.col.total"), unit: answer.currency, type: "number", value: (row) => Number(row.total), format: (_v, row) => shownDecimal(row.total, language, 0) },
    { id: "per", header: t("regas.col.per_mwh"), unit: `${answer.currency}/MWh`, type: "number", value: (row) => Number(row.per_mwh), format: (_v, row) => shownDecimal(row.per_mwh, language, 3) },
  ], [t, language, answer.currency]);
  return <DataGrid id="regas-waterfall" label={t("regas.drivers.title")} columns={columns} rows={answer.waterfall ?? []} rowKey={(row) => row.key} density="compact" rowAttributes={(row) => ({ "data-record": "regas-step", "data-step": row.key })} />;
}

function Sensitivities({ answer, t, language }: { answer: RegasAnswerDTO; t: Translate; language: string }) {
  const unit = quotedUnit(answer);
  const columns = useMemo<DataGridColumn<NonNullable<RegasAnswerDTO["sensitivities"]>[number]>[]>(() => [
    { id: "what", header: t("regas.col.move"), value: (row) => row.label, rowHeader: true, render: (row) => t(`regas.sens.${row.key.split(":")[0]}`, { what: row.label, per: row.per, defaultValue: `${row.label} ${row.per}` }) },
    { id: "quoted", header: t("regas.col.change"), unit, type: "number", value: (row) => Number(row.max_bid_quoted ?? NaN), format: (_v, row) => (row.max_bid_quoted === null ? t("regas.no_price_for_day") : shownDecimal(row.max_bid_quoted, language, 3)) },
    { id: "total", header: t("regas.col.total"), unit: answer.currency, type: "number", value: (row) => Number(row.max_bid_total ?? NaN), format: (_v, row) => shownDecimal(row.max_bid_total, language, 0), priority: "secondary" },
  ], [t, language, unit, answer.currency]);
  return <DataGrid id="regas-sensitivities" label={t("regas.sens.title")} columns={columns} rows={answer.sensitivities ?? []} rowKey={(row) => row.key} density="compact" />;
}

function Exposure({ rows, t, language }: { rows: RegasExposureDTO[]; t: Translate; language: string }) {
  const columns = useMemo<DataGridColumn<RegasExposureDTO>[]>(() => [
    { id: "hub", header: t("regas.col.hub"), value: (row) => `${row.hub} ${row.month}`, rowHeader: true },
    { id: "long", header: t("regas.col.revenue_long"), unit: "MWh", type: "number", value: (row) => Number(row.long_mwh), format: (_v, row) => shownDecimal(row.long_mwh, language, 0) },
    { id: "formula", header: t("regas.col.formula"), unit: "MWh", type: "number", value: (row) => Number(row.formula_mwh), format: (_v, row) => shownDecimal(row.formula_mwh, language, 0) },
    { id: "covered", header: t("regas.col.covered"), unit: "MWh", type: "number", value: (row) => Number(row.covered_mwh), format: (_v, row) => shownDecimal(row.covered_mwh, language, 0), priority: "secondary" },
    { id: "residual", header: t("regas.col.residual"), unit: "MWh", type: "number", value: (row) => Number(row.residual_mwh), format: (_v, row) => shownDecimal(row.residual_mwh, language, 0) },
  ], [t, language]);
  return <DataGrid id="regas-exposure" label={t("regas.exposure.title")} columns={columns} rows={rows} rowKey={(row) => `${row.hub}:${row.month}`} density="compact" />;
}

function Hedges({ rows, t, language }: { rows: RegasHedgeDTO[]; t: Translate; language: string }) {
  const columns = useMemo<DataGridColumn<RegasHedgeDTO>[]>(() => [
    { id: "contract", header: t("regas.col.contract"), value: (row) => `${row.hub} ${row.contract}`, rowHeader: true, cellTitle: (row) => t("regas.hedges.last_trading", { day: row.last_trading_day }) },
    { id: "side", header: t("regas.col.side"), value: (row) => row.side, render: (row) => <span data-deal-side={row.side}>{t(`regas.side.${row.side}`)}</span> },
    { id: "volume", header: t("regas.col.volume"), type: "number", value: (row) => Number(row.desk_volume ?? row.mwh), render: (row) => (row.desk_volume ? <>{shownDecimal(row.desk_volume, language, row.desk_unit === "MW" ? 1 : 0)} <small className="ds-grid-unit">{row.desk_unit}</small></> : "–") },
    { id: "mwh", header: t("regas.col.energy"), unit: "MWh", type: "number", value: (row) => Number(row.mwh), format: (_v, row) => shownDecimal(row.mwh, language, 0), priority: "secondary" },
    { id: "cost", header: t("regas.col.cost"), type: "number", value: (row) => Number(row.cost), format: (_v, row) => shownDecimal(row.cost, language, 0), cellTitle: (row) => row.half_spread_source },
  ], [t, language]);
  return <DataGrid id="regas-hedges" label={t("regas.hedges.title")} columns={columns} rows={rows} rowKey={(row) => `${row.hub}:${row.month}`} density="compact" empty={t("regas.hedges.none")} rowAttributes={(row) => ({ "data-record": "regas-hedge", "data-instrument": row.instrument })} />;
}

function WhatIf({ data, t, language }: { data: RegasWhatIfDTO; t: Translate; language: string }) {
  if (!data.computed) return <p className="trader-muted">{t("regas.whatif.missing")}</p>;
  return (
    <div className="regas-whatif" data-regas-whatif="" data-booked={String(data.booked)}>
      <p className="trader-foot">{t("regas.whatif.note")}</p>
      <ul>
        {(data.added ?? []).map((row) => (
          <li key={`${row.hub}:${row.month}`}>{t("regas.whatif.position", { hub: row.hub, month: row.month, mwh: shownDecimal(row.net_mwh, language, 0) })}</li>
        ))}
        {(data.mandates ?? []).map((row) => (
          <li key={row.mandate_id}>{t("regas.whatif.mandate", { name: row.name, before: String(row.before.status ?? ""), after: String(row.after.status ?? ""), breaches: String(row.after.breaches ?? "") || "–" })}</li>
        ))}
        {data.credit && (
          <li>{t("regas.whatif.credit", { before: shownDecimal(String(data.credit.before.utilisation_pct ?? ""), language, 1), after: shownDecimal(String(data.credit.after.utilisation_pct ?? ""), language, 1) })}</li>
        )}
      </ul>
    </div>
  );
}

function CostLines({ lines, t, language, editable, busy, onSave }: { lines: RegasCostLineDTO[]; t: Translate; language: string; editable: boolean; busy: boolean; onSave: (key: string, value: string, link: string) => void }) {
  const [editing, setEditing] = useState<{ key: string; value: string; link: string } | null>(null);
  const columns = useMemo<DataGridColumn<RegasCostLineDTO>[]>(() => [
    { id: "line", header: t("regas.col.item"), value: (row) => row.label, rowHeader: true, render: (row) => t(`regas.cost.${row.key}`, { defaultValue: row.label }) },
    { id: "value", header: t("regas.col.value"), type: "number", value: (row) => Number(row.value ?? NaN), render: (row) => (row.held ? <>{shownDecimal(row.value, language, row.basis === "per_slot" ? 0 : 3)} <small className="ds-grid-unit">{t(`regas.basis.${row.basis}`)}</small></> : <span className="trader-degraded">{t("regas.not_held")}</span>) },
    { id: "total", header: t("regas.col.total"), type: "number", value: (row) => Number(row.total ?? NaN), format: (_v, row) => shownDecimal(row.total, language, 0) },
    {
      id: "source",
      header: t("regas.col.source"),
      value: (row) => row.origin,
      cellTitle: (row) => row.source,
      render: (row) => (
        <span data-origin={row.origin}>
          {row.origin === "hand" ? t("regas.origin.hand", { who: row.entered_by ?? "", at: (row.entered_at ?? "").slice(0, 10) }) : t(`regas.origin.${row.origin}`)}
          {row.link ? <> · <a href={row.link} target="_blank" rel="noreferrer">{t("regas.tariff_link")}</a></> : null}
        </span>
      ),
    },
    {
      id: "edit",
      header: t("regas.col.enter"),
      value: () => "",
      render: (row) =>
        editable && row.basis !== "financing" && row.basis !== "hedge_spread" ? (
          <button type="button" className="link-button" onClick={() => setEditing({ key: row.key, value: row.origin === "hand" ? row.value ?? "" : "", link: row.link ?? "" })}>{t("regas.enter_by_hand")}</button>
        ) : null,
      priority: "secondary",
    },
  ], [t, language, editable]);
  return (
    <>
      <DataGrid id="regas-costs" label={t("regas.inputs.costs")} columns={columns} rows={lines} rowKey={(row) => row.key} density="compact" rowAttributes={(row) => ({ "data-record": "regas-cost", "data-held": String(row.held), "data-origin": row.origin })} />
      {editing && (
        <div className="ds-form-grid" role="group" aria-label={t("regas.enter_by_hand")}>
          <Field label={lines.find((row) => row.key === editing.key)?.label ?? editing.key}>
            <input inputMode="decimal" value={editing.value} onChange={(event) => setEditing({ ...editing, value: event.target.value })} />
          </Field>
          <Field label={t("regas.tariff_link")} hint={t("regas.tariff_link_hint")}>
            <input type="url" value={editing.link} onChange={(event) => setEditing({ ...editing, link: event.target.value })} />
          </Field>
          <div className="ds-form-grid-action desk-actions">
            <Button size="sm" variant="secondary" disabled={busy} onClick={() => { onSave(editing.key, editing.value, editing.link); setEditing(null); }}>{t("regas.save")}</Button>
            <Button size="sm" variant="quiet" onClick={() => setEditing(null)}>{t("regas.cancel")}</Button>
          </div>
        </div>
      )}
    </>
  );
}

function HandInputs({ answer, hub, t, editable, busy, onPrice, onRate }: { answer: RegasAnswerDTO; hub: string; t: Translate; editable: boolean; busy: boolean; onPrice: (value: string) => void; onRate: (value: string) => void }) {
  const [price, setPrice] = useState("");
  const [rate, setRate] = useState("");
  const pricesMissing = answer.missing.some((key) => key.startsWith(`price:${hub}:`));
  const rateMissing = answer.missing.includes("financing_rate");
  if (!editable || (!pricesMissing && !rateMissing)) return null;
  return (
    <div className="ds-form-grid" role="group" aria-label={t("regas.enter_by_hand")} data-regas-hand-inputs="">
      {pricesMissing && (
        <>
          <Field label={t("regas.hand.price", { hub })} hint={t("regas.hand.price_hint")}>
            <input inputMode="decimal" value={price} onChange={(event) => setPrice(event.target.value)} />
          </Field>
          <div className="ds-form-grid-action desk-actions">
            <Button size="sm" variant="secondary" disabled={busy || !price.trim()} onClick={() => onPrice(price)}>{t("regas.save")}</Button>
          </div>
        </>
      )}
      {rateMissing && (
        <>
          <Field label={t("regas.hand.rate", { currency: answer.currency })}>
            <input inputMode="decimal" value={rate} onChange={(event) => setRate(event.target.value)} />
          </Field>
          <div className="ds-form-grid-action desk-actions">
            <Button size="sm" variant="secondary" disabled={busy || !rate.trim()} onClick={() => onRate(rate)}>{t("regas.save")}</Button>
          </div>
        </>
      )}
    </div>
  );
}

function Days({ rows, t, language }: { rows: RegasDayDTO[]; t: Translate; language: string }) {
  const columns = useMemo<DataGridColumn<RegasDayDTO>[]>(() => [
    { id: "day", header: t("regas.col.day"), value: (row) => row.day, rowHeader: true },
    { id: "price", header: t("regas.col.price"), type: "number", value: (row) => Number(row.native_value ?? row.price), render: (row) => <>{shownDecimal(row.native_value ?? row.price, language, 3)} <small className="ds-grid-unit">{row.native_unit ?? "/MWh"}</small>{row.class === "simulated" ? <SimMark t={t} /> : null}</> },
    { id: "sent", header: t("regas.col.sent_out"), unit: "MWh", type: "number", value: (row) => Number(row.sent_out_mwh), format: (_v, row) => shownDecimal(row.sent_out_mwh, language, 0) },
    { id: "source", header: t("regas.col.source"), value: (row) => row.source ?? "", render: (row) => <span title={row.source ?? ""}>{row.source ?? "–"}{row.as_of_utc ? <> · <Instant value={row.as_of_utc} /></> : null}</span>, priority: "secondary" },
  ], [t, language]);
  return <DataGrid id="regas-days" label={t("regas.inputs.prices", { count: rows.length })} columns={columns} rows={rows} rowKey={(row) => row.day} density="compact" />;
}

function Snapshots({ rows, t, language }: { rows: RegasSnapshotDTO[]; t: Translate; language: string }) {
  const columns = useMemo<DataGridColumn<RegasSnapshotDTO>[]>(() => [
    { id: "saved", header: t("regas.col.saved"), value: (row) => row.saved_at_utc, render: (row) => <Instant value={row.saved_at_utc} />, rowHeader: true },
    { id: "by", header: t("regas.col.by"), value: (row) => row.saved_by },
    { id: "bid", header: t("regas.answer.bid_at_most"), type: "number", value: (row) => Number(row.max_bid_quoted ?? NaN), format: (_v, row) => shownDecimal(row.max_bid_quoted, language, 3) },
    { id: "level", header: t("regas.answer.level"), type: "number", value: (row) => Number(row.level ?? NaN), format: (_v, row) => shownDecimal(row.level, language, 3) },
    { id: "state", header: t("regas.col.state"), value: (row) => row.state, render: (row) => <StatusBadge tone={stateTone(row.state)}>{t(`regas.state.${row.state}`)}</StatusBadge> },
    { id: "note", header: t("regas.col.note"), value: (row) => row.note, priority: "secondary" },
  ], [t, language]);
  return (
    <>
      <h3>{t("regas.snapshot.title")}</h3>
      <DataGrid id="regas-snapshots" label={t("regas.snapshot.title")} columns={columns} rows={rows} rowKey={(row) => row.snapshot_id} density="compact" empty={t("regas.snapshot.none")} />
    </>
  );
}

/* ------------------------------------------------------------------ a new case */

function RegasCaseForm({ t, choices, onOpened, onCancel }: { t: Translate; choices: RegasCasesDTO["choices"]; onOpened: (item: RegasCaseDTO) => void; onCancel: () => void }) {
  const [draft, setDraft] = useState<RegasDraft>(() => emptyDraft(choices));
  const [message, setMessage] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const set = (patch: Partial<RegasDraft>) => setDraft((current) => ({ ...current, ...patch }));
  const text = (key: keyof RegasDraft) => ({ value: String(draft[key] ?? ""), onChange: (event: { target: { value: string } }) => set({ [key]: event.target.value } as Partial<RegasDraft>) });
  const gaps = draftGaps(draft);
  const [handTerminal, setHandTerminal] = useState(false);
  const [handOwner, setHandOwner] = useState(false);
  const submit = () => {
    setBusy(true);
    setMessage(null);
    api
      .openRegasAuction(draftToBody(draft))
      .then((response) => onOpened(response.data))
      .catch((caught) => setMessage(failText(caught)))
      .finally(() => setBusy(false));
  };
  const terminalOptions = [
    { value: "", label: t("regas.form.choose") },
    ...choices.terminals.map((item) => ({ value: item.terminal_id, label: `${item.name} (${item.hub})` })),
    { value: "__hand", label: t("regas.form.terminal_by_hand") },
  ];
  const ownerOptions = [
    { value: "", label: t("regas.form.choose") },
    ...choices.owners.map((item) => ({ value: item.counterparty_id, label: item.name })),
    { value: "__hand", label: t("regas.form.owner_by_hand") },
  ];
  return (
    <section className="trader-panel regas-form" aria-labelledby="regas-form-title" data-regas-form="">
      <div className="trader-panel-head">
        <h2 id="regas-form-title">{t("regas.form.title")}</h2>
        <span className="trader-meta">{t("regas.form.lead")}</span>
      </div>
      <div className="trader-panel-body">
        {choices.notices.length > 0 && (
          <Field label={t("regas.form.notice")}>
            <Select value={draft.notice_key} onChange={(value) => { const notice = choices.notices.find((item) => item.notice_key === value); setDraft(notice ? draftFromNotice(draft, notice) : { ...draft, notice_key: "" }); }} options={[{ value: "", label: t("regas.form.no_notice") }, ...choices.notices.map((item) => ({ value: item.notice_key, label: item.title }))]} />
          </Field>
        )}
        <h3>{t("regas.form.slot")}</h3>
        <div className="ds-form-grid">
          <Field label={t("regas.form.book")}>
            <Select value={draft.book_id} onChange={(value) => set({ book_id: value })} options={choices.books.map((item) => ({ value: item.book_id, label: item.name }))} />
          </Field>
          <Field label={t("regas.form.terminal")}>
            <Select value={draft.terminal_id || (handTerminal ? "__hand" : "")} onChange={(value) => { const found = choices.terminals.find((item) => item.terminal_id === value); setHandTerminal(value === "__hand"); set(found ? { terminal_id: found.terminal_id, terminal_name: found.name, hub: found.hub } : { terminal_id: "", terminal_name: "" }); }} options={terminalOptions} />
          </Field>
          {handTerminal && (
            <>
              <Field label={t("regas.form.terminal_name")}><input {...text("terminal_name")} /></Field>
              <Field label={t("regas.form.hub")}><Select value={draft.hub} onChange={(value) => set({ hub: value })} options={["NBP", "TTF", "ZTP", "THE", "PEG", "PVB"].map((hub) => ({ value: hub, label: hub }))} /></Field>
            </>
          )}
          <Field label={t("regas.form.title_field")}><input {...text("title")} /></Field>
          <Field label={t("regas.form.first_day")}><PeriodPicker label={t("regas.form.first_day")} value={draft.first_day} onChange={(value) => set({ first_day: value })} /></Field>
          <Field label={t("regas.form.last_day")}><PeriodPicker label={t("regas.form.last_day")} value={draft.last_day} min={draft.first_day || undefined} onChange={(value) => set({ last_day: value })} /></Field>
          <Field label={t("regas.form.quantity")}><input inputMode="decimal" {...text("quantity")} /></Field>
          <Field label={t("regas.form.unit")}>
            <Select value={draft.unit} onChange={(value) => set({ unit: value })} options={["GWh", "MWh", "MMBtu", "therm", "m3_lng"].map((unit) => ({ value: unit, label: t(`regas.unit.${unit}`, { defaultValue: unit }) }))} />
          </Field>
          {draft.unit === "m3_lng" && (
            <Field label={t("regas.form.factor")} hint={t("regas.form.factor_hint")}><input inputMode="decimal" placeholder="6.5" {...text("factor")} /></Field>
          )}
        </div>
        <h3>{t("regas.form.auction")}</h3>
        <div className="ds-form-grid">
          <Field label={t("regas.form.format")}>
            <Select value={draft.format} onChange={(value) => set({ format: value })} options={choices.definition.formats.map((value) => ({ value, label: t(`regas.format.${value}`, { defaultValue: value }) }))} />
          </Field>
          <Field label={t("regas.form.time_zone")}><input {...text("time_zone")} /></Field>
          <Field label={t("regas.form.opens")}><PeriodPicker kind="datetime" label={t("regas.form.opens")} value={draft.opens_local} clearable onChange={(value) => set({ opens_local: value })} /></Field>
          <Field label={t("regas.form.closes")}><PeriodPicker kind="datetime" label={t("regas.form.closes")} value={draft.closes_local} clearable onChange={(value) => set({ closes_local: value })} /></Field>
          <Field label={t("regas.form.quotation")}>
            <Select value={draft.quotation} onChange={(value) => set({ quotation: value as RegasDraft["quotation"] })} options={[{ value: "per_mwh", label: t("regas.quotation.per_mwh") }, { value: "per_slot", label: t("regas.quotation.per_slot") }]} />
          </Field>
          <Field label={t("regas.answer.level")}><input inputMode="decimal" {...text("level")} /></Field>
        </div>
        <h3>{t("regas.form.offer")}</h3>
        <div className="ds-form-grid">
          <Field label={t("regas.form.owner")}>
            <Select value={draft.owner_id || (handOwner ? "__hand" : "")} onChange={(value) => { const found = choices.owners.find((item) => item.counterparty_id === value); setHandOwner(value === "__hand"); set(found ? { owner_id: found.counterparty_id, owner_name: found.name } : { owner_id: "", owner_name: "" }); }} options={ownerOptions} />
          </Field>
          {handOwner && <Field label={t("regas.form.owner_name")}><input {...text("owner_name")} /></Field>}
          <Field label={t("regas.form.kind")}>
            <Select value={draft.kind} onChange={(value) => set({ kind: value as RegasDraft["kind"] })} options={choices.definition.offer_kinds.map((value) => ({ value, label: t(`regas.kind.${value}`) }))} />
          </Field>
          {draft.kind === "fixed" ? (
            <>
              <Field label={t("regas.form.price")}><input inputMode="decimal" {...text("price")} /></Field>
              <Field label={t("regas.form.price_unit")}>
                <Select value={draft.price_unit} onChange={(value) => set({ price_unit: value })} options={choices.definition.price_units.map((value) => ({ value, label: value }))} />
              </Field>
            </>
          ) : (
            <>
              <Field label={t("regas.form.index_hub")}><Select value={draft.index_hub || draft.hub} onChange={(value) => set({ index_hub: value })} options={["NBP", "TTF", "ZTP", "THE", "PEG", "PVB"].map((hub) => ({ value: hub, label: hub }))} /></Field>
              <Field label={t("regas.form.pricing")}>
                <Select value={draft.pricing} onChange={(value) => set({ pricing: value as RegasDraft["pricing"] })} options={choices.definition.pricing_periods.map((value) => ({ value, label: t(`regas.pricing.${value}`) }))} />
              </Field>
              {draft.pricing === "month" && <Field label={t("regas.form.pricing_month")}><PeriodPicker kind="month" label={t("regas.form.pricing_month")} value={draft.pricing_month} onChange={(value) => set({ pricing_month: value })} /></Field>}
              <Field label={t("regas.form.slope")}><input inputMode="decimal" {...text("slope")} /></Field>
              <Field label={t("regas.form.constant")}><input inputMode="decimal" {...text("constant")} /></Field>
            </>
          )}
          <Field label={t("regas.form.tolerance")}><input inputMode="decimal" {...text("tolerance_pct")} /></Field>
          <Field label={t("regas.form.expires")}><PeriodPicker kind="datetime" label={t("regas.form.expires")} value={draft.expires_local} clearable onChange={(value) => set({ expires_local: value })} /></Field>
        </div>
        <h3>{t("regas.form.costs")}</h3>
        <p className="trader-muted">{t("regas.form.costs_lead")}</p>
        <div className="ds-form-grid">
          {choices.definition.costs.filter((cost) => cost.basis !== "financing" && cost.basis !== "hedge_spread").map((cost) => (
            <Field key={cost.key} label={`${cost.label} (${t(`regas.basis.${cost.basis}`)})`} hint={cost.from === "register" ? t("regas.form.from_register") : cost.default !== null ? t("regas.form.default", { value: cost.default }) : t("regas.form.from_hand")}>
              <input inputMode="decimal" value={draft.costs[cost.key]?.value ?? ""} onChange={(event) => set({ costs: { ...draft.costs, [cost.key]: { value: event.target.value, link: draft.costs[cost.key]?.link ?? "" } } })} />
            </Field>
          ))}
          <Field label={t("regas.hand.price", { hub: draft.hub })} hint={t("regas.hand.price_hint")}><input inputMode="decimal" {...text("price_by_hand")} /></Field>
        </div>
        {message && <p className="trader-degraded" role="alert">{message}</p>}
        <div className="desk-actions">
          <Button variant="primary" size="sm" disabled={busy || gaps.length > 0} title={gaps.length ? t("regas.form.needs", { items: gaps.map((gap) => t(`regas.gap.${gap}`)).join(", ") }) : undefined} onClick={submit} data-regas-open="">{t("regas.form.open")}</Button>
          <Button variant="quiet" size="sm" onClick={onCancel}>{t("regas.cancel")}</Button>
          {gaps.length > 0 && <span className="trader-muted">{t("regas.form.needs", { items: gaps.map((gap) => t(`regas.gap.${gap}`)).join(", ") })}</span>}
        </div>
      </div>
    </section>
  );
}

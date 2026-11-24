/**
 * One cargo's plan (QA-L-05), in a sheet beside the cargo board: header, what changed, a
 * timeline, the energy waterfall, send-out by gas day, the hub × month grid with hedge cover,
 * suggestions by due time with their arithmetic, the inputs and their sources; then the what-if
 * (ETA, slot, berth delay: nothing is stored) and the hedge editor (`PUT .../hedges`, audited).
 *
 * Every figure is the plan the server built (`GET /api/lng/cargoes/{id}/plan`). Advice only:
 * nothing here executes, books or nominates.
 */
import { useEffect, useMemo, useState } from "react";

import {
  api,
  type CargoPlanChangeDTO,
  type CargoPlanDTO,
  type CargoPlanMonthDTO,
  type CargoPlanSuggestionDTO,
} from "@/api/client";
import { readKey, useCachedRead } from "@/app/data/readCache";
import { apiErrorDetailCode, describeFailure, presentError } from "@/app/experience/errorPresentation";
import { GAS_HUBS } from "@/app/contractChoices";
import {
  convertEnergy,
  coverTone,
  countdown,
  countdownText,
  daysToLastTrade,
  energyDigits,
  energyWaterfall,
  hedgeRowsCoveringPhysical,
  hedgeRowsFrom,
  sendOutByMonth,
  sendOutGap,
  slotChoices,
  statusTone,
  suggestionArithmetic,
  suggestionsByDue,
  validateHedges,
  whatIfRows,
  type EnergyDisplayUnit,
  type HedgeRow,
  type WhatIfRow,
} from "@/app/model/cargoBoardModel";
import { formatDeliveryMonth, formatInstant } from "@/app/time/timeFormat";
import { formatAmount, plainDecimal } from "@/app/time/valueFormat";
import { useInstantFormatter } from "@/app/time/useInstant";
import { Button, DataGrid, Field, Instant, Segmented, Select, Sheet, StatusBadge, type DataGridColumn } from "@/components/ui";
import { Chart, Waterfall } from "@/components/ui/charts";
import { PeriodPicker } from "@/components/ui/PeriodPicker";
import { withTime } from "@/components/ui/periodModel";
import "./cargo-board.css";
import type { ChartData } from "@/components/ui/charts";

type Translate = (key: string, options?: Record<string, unknown>) => string;

export type PlanSection = "plan" | "what_if" | "hedge";
const SECTIONS: readonly PlanSection[] = ["plan", "what_if", "hedge"];

function planKey(cargoId: string): string {
  return readKey(`/lng/cargoes/${cargoId}/plan`);
}

export function CargoPlanSheet({
  cargoId,
  section,
  onSection,
  onClose,
  t,
  language,
  unit,
  canRecordHedges,
  onSaved,
}: {
  cargoId: string | null;
  section: PlanSection;
  onSection: (section: PlanSection) => void;
  onClose: () => void;
  t: Translate;
  language: string;
  unit: EnergyDisplayUnit;
  canRecordHedges: boolean;
  onSaved: () => void;
}) {
  const read = useCachedRead(cargoId ? planKey(cargoId) : null, (signal) =>
    api.cargoPlan(cargoId!, undefined, { signal }).then((response) => response.data),
  );
  const plan = read.data ?? null;
  const failure = read.error ? presentError(t, describeFailure(read.error)) : null;
  const code = read.error ? apiErrorDetailCode(read.error) : null;
  return (
    <Sheet
      open={Boolean(cargoId)}
      onClose={onClose}
      side="end"
      id="cargo-plan"
      closeLabel={t("lng.cargo.close")}
      eyebrow={t("lng.cargo.plan_eyebrow")}
      title={cargoId ? `${cargoId}${plan?.cargo.vessel_name ? ` · ${plan.cargo.vessel_name}` : ""}` : ""}
      headerActions={
        <Segmented
          label={t("lng.cargo.section_label")}
          options={SECTIONS.map((value) => ({ value, label: t(`lng.cargo.section.${value}`) }))}
          value={section}
          onChange={onSection}
        />
      }
      className="cargo-plan-sheet"
    >
      {read.loading && !plan && <p className="muted" role="status">{t("lng.cargo.plan_loading")}</p>}
      {failure && (
        <div className="cargo-board-error" role="alert">
          <strong>{failure.title}</strong>
          <span>{code ? t(`lng.cargo.fix.${code}`, { defaultValue: failure.action }) : failure.action}</span>
          <Button variant="secondary" onClick={read.refresh}>{t("lng.cargo.retry")}</Button>
        </div>
      )}
      {plan && section === "plan" && <PlanBody plan={plan} t={t} language={language} unit={unit} onSection={onSection} />}
      {plan && section === "what_if" && <WhatIf plan={plan} t={t} language={language} />}
      {plan && section === "hedge" && (
        <HedgeEditor
          plan={plan}
          t={t}
          language={language}
          canRecord={canRecordHedges}
          onSaved={() => {
            read.refresh();
            onSaved();
          }}
        />
      )}
    </Sheet>
  );
}

/* ------------------------------------------------------------------ the plan */

function PlanBody({ plan, t, language, unit, onSection }: { plan: CargoPlanDTO; t: Translate; language: string; unit: EnergyDisplayUnit; onSection: (section: PlanSection) => void }) {
  const cargo = plan.cargo;
  const body = plan.plan;
  const format = useInstantFormatter();
  const nowMs = Date.now();
  const age = Math.max(0, (nowMs - Date.parse(plan.as_of_utc)) / 60_000);
  const mwh = (value: number) => formatAmount(value, language);
  const gap = sendOutGap(body);
  const waterfall = useMemo(
    () => energyWaterfall(cargo.loaded_mwh, body).map((step) => ({ id: step.id, label: t(step.labelKey), value: step.value, kind: step.kind })),
    [body, cargo.loaded_mwh, t],
  );
  const sendOut = useMemo<ChartData>(() => {
    const { days, series } = sendOutByMonth(body);
    return {
      axis: "gas-day",
      x: days,
      xTitle: t("lng.cargo.gas_day"),
      unit: "MWh",
      series: series.map((item, index) => ({ id: item.month, label: formatDeliveryMonth(item.month), values: item.values, style: "bar", stack: true, colour: index + 1, decimals: 0 })),
    };
  }, [body, t]);
  const assumed = (source: string) => /desk standard|no terminal terms|no gas-in-kind|mapped from/i.test(source);

  return (
    <div className="cargo-plan" data-cargo-plan={cargo.cargo_id}>
      {/* 1. Header */}
      <section className="cargo-plan-head" aria-label={t("lng.cargo.plan_header")}>
        <StatusBadge tone={statusTone({ slot_status: body.slot_status })}>{t(`lng.cargo.status.${body.slot_status}`)}</StatusBadge>
        {cargo.simulated && <StatusBadge tone="simulated" title={t("lng.cargo.simulated_title")}>{t("lng.cargo.simulated")}</StatusBadge>}
        <dl className="cargo-plan-facts">
          <div><dt>{t("lng.cargo.book")}</dt><dd>{cargo.book_id ?? "–"}</dd></div>
          <div><dt>{t("lng.cargo.source")}</dt><dd>{cargo.source_system ?? "–"}</dd></div>
          <div><dt>{t("lng.cargo.route")}</dt><dd>{cargo.load_port ?? "–"} → {cargo.slot?.terminal ?? cargo.destination_terminal ?? "–"} ({cargo.hub ?? t("lng.cargo.no_hub")})</dd></div>
          <div><dt>{t("lng.cargo.eta")}</dt><dd><Instant value={cargo.eta_utc} date="always" /></dd></div>
          <div><dt>{t("lng.cargo.as_of")}</dt><dd><Instant value={plan.as_of_utc} date="always" /> · {t("lng.cargo.age_minutes", { minutes: formatAmount(age, language) })}</dd></div>
        </dl>
        {plan.contract?.warning && <p className="cargo-plan-warning" role="note">{plan.contract.warning}</p>}
        <p className="cargo-board-advisory">{plan.advisory} {t("lng.cargo.advice_only")}</p>
      </section>

      {/* 2. What changed */}
      <section className="cargo-plan-section" aria-labelledby="cargo-plan-changed">
        <h3 id="cargo-plan-changed">{t("lng.cargo.what_changed")}</h3>
        {plan.last_change ? <p className="cargo-plan-headline">{plan.last_change.headline}</p> : <p className="muted">{t("lng.cargo.no_change_yet")}</p>}
        {cargo.changed && (
          <p className="cargo-board-sub">
            {cargo.changed.kinds.map((kind) => t(`lng.cargo.change_kind.${kind}`, { defaultValue: kind })).join(", ")} · {cargo.changed.by} · <Instant value={cargo.changed.at_utc} date="always" />
            {cargo.changed.eta_before_utc && <> · {t("lng.cargo.eta_was")} <Instant value={cargo.changed.eta_before_utc} date="always" /></>}
          </p>
        )}
        {plan.last_change?.months?.some((shift) => Math.abs(shift.change_mwh) >= 1) && (
          <DataGrid
            id="cargo-plan-shift"
            label={t("lng.cargo.what_changed")}
            density="compact"
            rows={plan.last_change.months.filter((shift) => Math.abs(shift.change_mwh) >= 1 || Math.abs(shift.physical_after_mwh) >= 1)}
            rowKey={(shift) => `${shift.hub}-${shift.month}`}
            columns={[
              { id: "month", header: t("lng.cargo.col.month"), rowHeader: true, value: (shift) => `${shift.hub} ${formatDeliveryMonth(shift.month)}` },
              { id: "before", header: t("lng.cargo.before"), unit: "MWh", type: "number", value: (shift) => shift.physical_before_mwh, format: (value) => mwh(value as number) },
              { id: "after", header: t("lng.cargo.after"), unit: "MWh", type: "number", value: (shift) => shift.physical_after_mwh, format: (value) => mwh(value as number) },
              { id: "change", header: t("lng.cargo.change"), unit: "MWh", type: "number", value: (shift) => shift.change_mwh, format: (value) => signed(value as number, language) },
            ]}
          />
        )}
      </section>

      {/* 3. Timeline */}
      <section className="cargo-plan-section" aria-labelledby="cargo-plan-timeline">
        <h3 id="cargo-plan-timeline">{t("lng.cargo.timeline")}</h3>
        <Timeline plan={plan} t={t} format={(value) => format(value, { date: "always" })?.text ?? "–"} />
        <a className="ds-inline-link" href="#cargo-plan-grid-title">{t("lng.cargo.to_grid")}</a>
      </section>

      {/* 4. Energy waterfall */}
      <section className="cargo-plan-section">
        <Waterfall
          id={`cargo-energy-${cargo.cargo_id}`}
          title={t("lng.cargo.waterfall_title")}
          unit="MWh"
          items={waterfall}
          t={t}
          decimals={0}
          simulated={Boolean(cargo.simulated)}
          note={cargo.loaded_mwh == null ? t("lng.cargo.waterfall_no_loaded") : t("lng.cargo.waterfall_note", { unit, delivered: formatAmount(convertEnergy(body.delivered_mwh, unit), language, energyDigits(unit)) })}
        />
      </section>

      {/* 5. Send-out by gas day */}
      <section className="cargo-plan-section">
        <Chart
          id={`cargo-send-out-${cargo.cargo_id}`}
          title={t("lng.cargo.send_out_title")}
          data={sendOut}
          t={t}
          height={180}
          asOf={plan.as_of_utc}
          simulated={Boolean(cargo.simulated)}
          empty={t("lng.cargo.send_out_none")}
          subtitle={t("lng.cargo.send_out_subtitle")}
          note={gap === 0 ? t("lng.cargo.send_out_reconciles") : t("lng.cargo.send_out_gap", { gap: signed(gap, language) })}
        />
      </section>

      {/* 6. Hub × month */}
      <section className="cargo-plan-section" aria-labelledby="cargo-plan-grid-title">
        <h3 id="cargo-plan-grid-title">{t("lng.cargo.grid_title")}</h3>
        <MonthGrid months={body.months} t={t} language={language} nowMs={nowMs} />
        <HedgeLegs plan={plan} t={t} language={language} />
        <Button variant="secondary" onClick={() => onSection("hedge")}>{t("lng.cargo.edit_hedges")}</Button>
      </section>

      {/* 7. Suggestions */}
      <section className="cargo-plan-section" aria-labelledby="cargo-plan-suggestions">
        <h3 id="cargo-plan-suggestions">{t("lng.cargo.suggestions")}</h3>
        <Suggestions plan={plan} t={t} language={language} />
        <Button variant="secondary" onClick={() => onSection("what_if")}>{t("lng.cargo.try_what_if")}</Button>
      </section>

      {/* 8. Inputs */}
      <section className="cargo-plan-section" aria-labelledby="cargo-plan-inputs">
        <h3 id="cargo-plan-inputs">{t("lng.cargo.inputs")}</h3>
        <ul className="cargo-plan-inputs">
          {plan.inputs.map((input) => (
            <li key={input.input}>
              <strong>{input.input}</strong>: {input.source}
              {assumed(input.source) && <StatusBadge tone="watch" title={t("lng.cargo.assumption_title")}>{t("lng.cargo.assumption")}</StatusBadge>}
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}

function signed(value: number, language: string): string {
  const text = formatAmount(Math.abs(value), language);
  return value > 0 ? `+${text}` : value < 0 ? `−${text}` : text;
}

/* ------------------------------------------------------------------ timeline */

interface Mark {
  id: string;
  at: number;
  labelKey: string;
  kind: "point" | "expiry";
  /** For a last trading day: the hub month it closes. */
  month?: string;
}

function Timeline({ plan, t, format }: { plan: CargoPlanDTO; t: Translate; format: (value: string) => string }) {
  const cargo = plan.cargo;
  const body = plan.plan;
  const at = (value: string | null | undefined) => (value ? Date.parse(value) : Number.NaN);
  const marks: Mark[] = [
    { id: "departed", at: at(cargo.departed_at_utc), labelKey: "lng.cargo.tl.departed", kind: "point" as const },
    { id: "eta", at: at(cargo.eta_utc), labelKey: "lng.cargo.tl.eta", kind: "point" as const },
    { id: "berth", at: at(body.berth_utc), labelKey: "lng.cargo.tl.berth", kind: "point" as const },
    { id: "send_out_end", at: at(body.send_out_end_utc), labelKey: "lng.cargo.tl.send_out_end", kind: "point" as const },
    ...body.months.map((month) => ({ id: `ltd-${month.hub}-${month.month}`, at: Date.parse(`${month.last_trading_day}T23:59:00Z`), labelKey: "lng.cargo.tl.expiry", kind: "expiry" as const, month: `${month.hub} ${formatDeliveryMonth(month.month)}` })),
  ].filter((mark) => Number.isFinite(mark.at));
  const windowStart = at(cargo.slot?.window_start_utc);
  const windowEnd = at(cargo.slot?.window_end_utc);
  const sendStart = body.send_out.length ? at(body.berth_utc) : Number.NaN;
  const sendEnd = at(body.send_out_end_utc);
  const instants = [...marks.map((mark) => mark.at), windowStart, windowEnd].filter(Number.isFinite);
  if (instants.length < 2) return <p className="muted">{t("lng.cargo.tl.empty")}</p>;
  const from = Math.min(...instants);
  const to = Math.max(...instants);
  const span = to - from || 1;
  const pct = (value: number) => `${plainDecimal(((value - from) / span) * 96 + 2, 2)}%`;
  const pctWidth = (start: number, end: number) => `${plainDecimal(((end - start) / span) * 96, 2)}%`;
  const describe = marks.map((mark) => `${t(mark.labelKey)} ${format(new Date(mark.at).toISOString())}`).join("; ");
  return (
    <div className="cargo-timeline" role="img" aria-label={describe}>
      <div className="cargo-timeline-track" aria-hidden="true">
        {Number.isFinite(windowStart) && Number.isFinite(windowEnd) && (
          <span className="cargo-timeline-window" style={{ left: pct(windowStart), width: pctWidth(windowStart, windowEnd) }} title={`${t("lng.cargo.tl.window")}: ${format(cargo.slot!.window_start_utc)} – ${format(cargo.slot!.window_end_utc)}`} />
        )}
        {Number.isFinite(sendStart) && Number.isFinite(sendEnd) && (
          <span className="cargo-timeline-sendout" style={{ left: pct(sendStart), width: pctWidth(sendStart, sendEnd) }} title={t("lng.cargo.tl.send_out")} />
        )}
        {marks.map((mark) => (
          <span key={mark.id} className={`cargo-timeline-mark is-${mark.kind}`} data-mark={mark.id} style={{ left: pct(mark.at) }} title={`${t(mark.labelKey)}: ${format(new Date(mark.at).toISOString())}`} />
        ))}
      </div>
      <ol className="cargo-timeline-legend">
        {[...marks].sort((left, right) => left.at - right.at).map((mark) => (
          <li key={mark.id} data-kind={mark.kind}>
            <span>{t(mark.labelKey)}{mark.month ? ` ${mark.month}` : ""}</span>
            <time dateTime={new Date(mark.at).toISOString()}>{format(new Date(mark.at).toISOString())}</time>
          </li>
        ))}
        {Number.isFinite(windowStart) && Number.isFinite(windowEnd) && (
          <li data-kind="window">
            <span>{t("lng.cargo.tl.window")}</span>
            <span>{format(cargo.slot!.window_start_utc)} – {format(cargo.slot!.window_end_utc)}</span>
          </li>
        )}
      </ol>
    </div>
  );
}

/* ------------------------------------------------------------------ hub × month */

function MonthGrid({ months, t, language, nowMs }: { months: readonly CargoPlanMonthDTO[]; t: Translate; language: string; nowMs: number }) {
  const mwh = (value: unknown) => formatAmount(Number(value), language);
  const columns: DataGridColumn<CargoPlanMonthDTO>[] = [
    { id: "hub", header: t("lng.cargo.col.hub"), value: (row) => row.hub },
    { id: "month", header: t("lng.cargo.col.month"), rowHeader: true, value: (row) => row.month, format: (value) => formatDeliveryMonth(String(value)) },
    { id: "physical", header: t("lng.cargo.col.physical"), unit: "MWh", type: "number", value: (row) => row.physical_mwh, format: mwh },
    { id: "hedge", header: t("lng.cargo.col.hedge"), unit: "MWh", type: "number", value: (row) => row.hedge_mwh, format: mwh },
    { id: "net", header: t("lng.cargo.col.net"), unit: "MWh", type: "number", value: (row) => row.net_mwh, format: mwh },
    {
      id: "cover",
      header: t("lng.cargo.col.cover_pct"),
      type: "number",
      value: (row) => row.cover_ratio,
      render: (row) => (
        <StatusBadge tone={coverTone(row)}>{row.cover_ratio === null ? "–" : `${formatAmount(row.cover_ratio * 100, language)} %`}</StatusBadge>
      ),
    },
    {
      id: "ltd",
      header: t("lng.cargo.col.last_trading"),
      value: (row) => row.last_trading_day,
      render: (row) => (
        <span className="cargo-board-id">
          <span>{row.last_trading_day}</span>
          <span className="cargo-board-sub">
            {row.trading ? t("lng.cargo.trading_days", { days: daysToLastTrade(row.last_trading_day, nowMs) }) : t("lng.cargo.stopped_trading")}
          </span>
        </span>
      ),
    },
  ];
  return (
    <DataGrid
      id="cargo-plan-months"
      label={t("lng.cargo.grid_title")}
      columns={columns}
      rows={months}
      rowKey={(row) => `${row.hub}-${row.month}`}
      density="compact"
      empty={t("lng.cargo.grid_empty")}
    />
  );
}

function HedgeLegs({ plan, t, language }: { plan: CargoPlanDTO; t: Translate; language: string }) {
  const legs = plan.hedges ?? [];
  if (!legs.length) return <p className="muted">{t("lng.cargo.no_hedges")}</p>;
  return (
    <ul className="cargo-plan-legs" aria-label={t("lng.cargo.hedge_legs")}>
      {legs.map((leg, index) => (
        <li key={`${leg.hub}-${leg.month}-${index}`}>
          {leg.hub} {formatDeliveryMonth(leg.month)} <strong>{signed(leg.mwh, language)} MWh</strong>
          {" · "}
          {leg.reference || t("lng.cargo.no_reference")}
          {" · "}
          {leg.created_by} · <Instant value={leg.created_at_utc} date="always" />
        </li>
      ))}
    </ul>
  );
}

/* ------------------------------------------------------------------ suggestions */

function Suggestions({ plan, t, language }: { plan: CargoPlanDTO; t: Translate; language: string }) {
  const items = suggestionsByDue(plan.plan.suggestions);
  if (!items.length) return <p className="muted">{t("lng.cargo.no_suggestions")}</p>;
  const inZone = (value: string, preference: "market" | "utc") => formatInstant(value, { language, preference, date: "always" })?.text ?? "–";
  const values = (arith: NonNullable<ReturnType<typeof suggestionArithmetic>>) =>
    Object.fromEntries(
      Object.entries(arith.values).map(([key, value]) => [
        key,
        typeof value === "number" ? formatAmount(value, language) : /^\d{4}-\d{2}$/.test(value) ? formatDeliveryMonth(value) : value,
      ]),
    );
  return (
    <ol className="cargo-plan-suggestions">
      {items.map((item: CargoPlanSuggestionDTO, index) => {
        const arith = suggestionArithmetic(item, plan.plan.months, plan.plan);
        return (
          <li key={`${item.kind}-${index}`} data-kind={item.kind}>
            <div className="cargo-plan-suggestion-head">
              <StatusBadge tone={item.kind === "find_slot" || item.kind === "short_notice" ? "breach" : item.kind === "deadline" ? "info" : "watch"}>
                {t(`lng.cargo.kind.${item.kind}`)}
              </StatusBadge>
              <span className="cargo-board-advisory">{t("lng.cargo.advice_only_short")}</span>
            </div>
            <p>{item.text}</p>
            {arith && <p className="cargo-plan-arith">{t(arith.key, values(arith))}</p>}
            {item.due_utc && (
              <p className="cargo-board-sub">
                {t("lng.cargo.due")} {inZone(item.due_utc, "market")} · {inZone(item.due_utc, "utc")}
              </p>
            )}
          </li>
        );
      })}
    </ol>
  );
}

/* ------------------------------------------------------------------ what-if */

/** "2026-11-27T20:00:00+00:00" -> "2026-11-27T20:00": the picker's value, read as UTC. */
function toUtcInput(value: string | null | undefined): string {
  if (!value) return "";
  const ms = Date.parse(value);
  if (!Number.isFinite(ms)) return "";
  const at = new Date(ms);
  const pad = (part: number) => String(part).padStart(2, "0");
  return withTime(`${at.getUTCFullYear()}-${pad(at.getUTCMonth() + 1)}-${pad(at.getUTCDate())}`, at.getUTCHours(), at.getUTCMinutes());
}

function WhatIf({ plan, t, language }: { plan: CargoPlanDTO; t: Translate; language: string }) {
  const cargo = plan.cargo;
  const mspa = plan.contract?.mspa ?? null;
  const [eta, setEta] = useState(toUtcInput(cargo.eta_utc));
  const [slot, setSlot] = useState(cargo.slot?.slot_id ?? "");
  const [delay, setDelay] = useState("0");
  const [laytime, setLaytime] = useState(String(mspa?.laytime_hours ?? 36));
  const [demurrage, setDemurrage] = useState(mspa?.demurrage_usd_per_day != null ? String(mspa.demurrage_usd_per_day) : "");
  const [result, setResult] = useState<CargoPlanChangeDTO | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const choices = slotChoices(plan.slot_options ?? []);
  const format = useInstantFormatter();
  useEffect(() => setResult(null), [eta, slot, delay, laytime, demurrage]);

  const run = () => {
    setBusy(true);
    setError(null);
    const body: Parameters<typeof api.cargoPlanWhatIf>[1] = {
      berth_delay_hours: Number(delay || 0),
      laytime_hours: Number(laytime || 36),
    };
    if (eta && eta !== toUtcInput(cargo.eta_utc)) body.eta_utc = `${eta}:00Z`;
    if (slot && slot !== cargo.slot?.slot_id) body.slot_id = slot;
    if (demurrage.trim()) body.demurrage_per_day = Number(demurrage);
    api.cargoPlanWhatIf(cargo.cargo_id, body)
      .then((response) => setResult(response.data.change))
      .catch((caught: unknown) => {
        const code = apiErrorDetailCode(caught);
        setError(code ? t(`lng.cargo.fix.${code}`, { defaultValue: presentError(t, describeFailure(caught)).action }) : presentError(t, describeFailure(caught)).action);
      })
      .finally(() => setBusy(false));
  };
  const invalid = Number.isNaN(Number(delay)) || Number(delay) < 0 || Number(delay) > 720 || Number.isNaN(Number(laytime)) || Number(laytime) < 0 || (demurrage.trim() !== "" && (Number.isNaN(Number(demurrage)) || Number(demurrage) < 0));
  const slotLabel = (option: { slot_id: string; terminal: string; window_start_utc: string; window_end_utc: string }) =>
    `${option.terminal} · ${format(option.window_start_utc, { date: "always" })?.text ?? ""} – ${format(option.window_end_utc, { date: "always" })?.text ?? ""}`;

  return (
    <div className="cargo-whatif" data-cargo-whatif="">
      <p className="cargo-plan-warning" role="note">{t("lng.cargo.whatif.nothing_stored")}</p>
      <div className="cargo-whatif-form ds-form-grid">
        <Field label={t("lng.cargo.whatif.eta")} hint={t("lng.cargo.whatif.eta_hint")}>
          <PeriodPicker kind="datetime" label={t("lng.cargo.whatif.eta")} value={eta} onChange={setEta} />
        </Field>
        <Field label={t("lng.cargo.whatif.slot")} hint={choices.held.length ? t("lng.cargo.whatif.held_hint", { count: choices.held.length }) : t("lng.cargo.whatif.slot_hint")}>
          <Select
            value={slot}
            onChange={setSlot}
            options={[
              ...(cargo.slot ? [] : [{ value: "", label: t("lng.cargo.whatif.no_slot") }]),
              ...choices.free.map((option) => ({ value: option.slot_id, label: slotLabel(option) })),
              ...choices.held.map((option) => ({ value: option.slot_id, label: `${slotLabel(option)} · ${t("lng.cargo.whatif.held_by", { cargo: option.held_by ?? "" })}`, disabled: true })),
            ]}
          />
        </Field>
        <Field label={t("lng.cargo.whatif.berth_delay")}>
          <input type="number" min={0} max={720} step={1} value={delay} onChange={(event) => setDelay(event.target.value)} />
        </Field>
        <Field label={t("lng.cargo.whatif.laytime")} hint={mspa?.laytime_hours != null ? t("lng.cargo.whatif.from_mspa", { contract: mspa.master_contract_id }) : t("lng.cargo.whatif.laytime_default")}>
          <input type="number" min={0} max={240} step={1} value={laytime} onChange={(event) => setLaytime(event.target.value)} />
        </Field>
        <Field label={t("lng.cargo.whatif.demurrage")} hint={mspa?.demurrage_usd_per_day != null ? t("lng.cargo.whatif.from_mspa", { contract: mspa.master_contract_id }) : t("lng.cargo.whatif.demurrage_none")}>
          <input type="number" min={0} step={1000} value={demurrage} onChange={(event) => setDemurrage(event.target.value)} />
        </Field>
      </div>
      <Button variant="primary" onClick={run} loading={busy} disabled={invalid}>{t("lng.cargo.whatif.run")}</Button>
      {error && <p className="ds-field-error" role="alert">{error}</p>}
      {result && <WhatIfResult change={result} t={t} language={language} />}
    </div>
  );
}

function WhatIfResult({ change, t, language }: { change: CargoPlanChangeDTO; t: Translate; language: string }) {
  const format = useInstantFormatter();
  const rows = whatIfRows(change);
  const show = (row: WhatIfRow, value: number | string | null) => {
    if (value === null) return "–";
    if (typeof value === "number") return formatAmount(value, language);
    if (row.id === "status") return t(`lng.cargo.status.${value}`);
    return format(value, { date: "always" })?.text ?? value;
  };
  return (
    <section className="cargo-plan-section" aria-labelledby="cargo-whatif-result">
      <h3 id="cargo-whatif-result">{t("lng.cargo.whatif.result")}</h3>
      <p className="cargo-plan-headline">{change.headline}</p>
      <DataGrid
        id="cargo-whatif-diff"
        label={t("lng.cargo.whatif.result")}
        density="compact"
        rows={rows}
        rowKey={(row) => row.id}
        columns={[
          {
            id: "figure",
            header: t("lng.cargo.whatif.figure"),
            rowHeader: true,
            value: (row) => row.id,
            render: (row) => (row.id.startsWith("month:") ? t(row.labelKey, { hub: row.id.split(":")[1], month: formatDeliveryMonth(row.id.split(":")[2]) }) : t(row.labelKey)),
          },
          { id: "before", header: t("lng.cargo.before"), type: "number", value: (row) => (typeof row.before === "number" ? row.before : null), render: (row) => show(row, row.before) },
          { id: "after", header: t("lng.cargo.after"), type: "number", value: (row) => (typeof row.after === "number" ? row.after : null), render: (row) => show(row, row.after) },
          { id: "change", header: t("lng.cargo.change"), type: "number", value: (row) => row.change, format: (value) => (value === null ? "" : signed(value as number, language)) },
        ]}
      />
      <p className="cargo-board-advisory">{t("lng.cargo.whatif.nothing_stored")}</p>
    </section>
  );
}

/* ------------------------------------------------------------------ hedge editor */

function HedgeEditor({ plan, t, language, canRecord, onSaved }: { plan: CargoPlanDTO; t: Translate; language: string; canRecord: boolean; onSaved: () => void }) {
  const [rows, setRows] = useState<HedgeRow[]>(() => hedgeRowsFrom(plan.hedges));
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [touched, setTouched] = useState(false);
  const validation = useMemo(() => validateHedges(rows.filter((row) => row.hub || row.month || row.mwh || row.reference), GAS_HUBS), [rows]);
  const filled = rows.filter((row) => row.hub || row.month || row.mwh || row.reference);
  const indexOfFilled = (row: HedgeRow) => filled.indexOf(row);
  const set = (index: number, patch: Partial<HedgeRow>) => {
    setTouched(true);
    setMessage(null);
    setRows((current) => current.map((row, position) => (position === index ? { ...row, ...patch } : row)));
  };
  const save = () => {
    if (!validation.legs) return;
    setBusy(true);
    setError(null);
    api.saveCargoHedges(plan.cargo.cargo_id, validation.legs)
      .then(() => {
        setMessage(t("lng.cargo.hedge.saved", { count: validation.legs!.length }));
        setTouched(false);
        onSaved();
      })
      .catch((caught: unknown) => {
        const code = apiErrorDetailCode(caught);
        setError(code ? t(`lng.cargo.hedge.error.${code}`, { defaultValue: presentError(t, describeFailure(caught)).action }) : presentError(t, describeFailure(caught)).action);
      })
      .finally(() => setBusy(false));
  };
  const hubOptions = [{ value: "", label: t("lng.cargo.hedge.choose_hub") }, ...GAS_HUBS.map((hub) => ({ value: hub, label: hub }))];
  const months = [...new Set([...plan.plan.months.map((month) => month.month), ...rows.map((row) => row.month).filter(Boolean)])].sort();

  return (
    <div className="cargo-hedge" data-cargo-hedge="">
      <p className="cargo-board-sub">{t("lng.cargo.hedge.intro")}</p>
      {!canRecord && <p className="cargo-plan-warning" role="note">{t("lng.cargo.hedge.read_only")}</p>}
      <table className="cargo-hedge-table">
        <caption className="visually-hidden">{t("lng.cargo.hedge.title")}</caption>
        <thead>
          <tr>
            <th scope="col">{t("lng.cargo.col.hub")}</th>
            <th scope="col">{t("lng.cargo.col.month")}</th>
            <th scope="col">{t("lng.cargo.hedge.mwh")}</th>
            <th scope="col">{t("lng.cargo.hedge.reference")}</th>
            <th scope="col"><span className="visually-hidden">{t("lng.cargo.hedge.remove")}</span></th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row, index) => {
            const errors = indexOfFilled(row) >= 0 ? validation.rows[indexOfFilled(row)] ?? [] : [];
            const showErrors = touched && errors.length > 0;
            return (
              <tr key={index} data-invalid={showErrors ? "true" : undefined}>
                <td>
                  <Select aria-label={t("lng.cargo.col.hub")} value={row.hub} onChange={(value) => set(index, { hub: value })} options={hubOptions} disabled={!canRecord} />
                </td>
                <td>
                  <input aria-label={t("lng.cargo.col.month")} list="cargo-hedge-months" placeholder="YYYY-MM" value={row.month} onChange={(event) => set(index, { month: event.target.value })} disabled={!canRecord} />
                </td>
                <td>
                  <input inputMode="decimal" aria-label={t("lng.cargo.hedge.mwh")} value={row.mwh} onChange={(event) => set(index, { mwh: event.target.value })} disabled={!canRecord} />
                </td>
                <td>
                  <input aria-label={t("lng.cargo.hedge.reference")} maxLength={160} value={row.reference} onChange={(event) => set(index, { reference: event.target.value })} disabled={!canRecord} />
                </td>
                <td>
                  <Button variant="quiet" onClick={() => { setTouched(true); setRows((current) => current.filter((_, position) => position !== index)); }} disabled={!canRecord}>{t("lng.cargo.hedge.remove")}</Button>
                  {showErrors && <span className="ds-field-error" role="alert">{errors.map((code) => t(`lng.cargo.hedge.invalid.${code}`)).join(" ")}</span>}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
      <datalist id="cargo-hedge-months">
        {months.map((month) => <option key={month} value={month}>{formatDeliveryMonth(month)}</option>)}
      </datalist>
      <div className="cargo-hedge-actions">
        <Button variant="secondary" onClick={() => setRows((current) => [...current, { hub: plan.cargo.hub ?? "", month: "", mwh: "", reference: "" }])} disabled={!canRecord}>{t("lng.cargo.hedge.add")}</Button>
        <Button variant="quiet" onClick={() => { setTouched(true); setRows(hedgeRowsCoveringPhysical(plan.plan.months)); }} disabled={!canRecord || !plan.plan.months.length}>{t("lng.cargo.hedge.from_physical")}</Button>
        <Button variant="primary" onClick={save} loading={busy} disabled={!canRecord || !touched || !validation.legs}>{t("lng.cargo.hedge.save")}</Button>
      </div>
      {validation.tooMany && <p className="ds-field-error" role="alert">{t("lng.cargo.hedge.too_many")}</p>}
      {message && <p role="status">{message}</p>}
      {error && <p className="ds-field-error" role="alert">{error}</p>}
      <p className="cargo-board-sub">{t("lng.cargo.hedge.audit")}</p>
      {validation.legs && (
        <p className="cargo-board-sub">
          {t("lng.cargo.hedge.total", { total: signed(validation.legs.reduce((sum, leg) => sum + leg.mwh, 0), language) })}
        </p>
      )}
    </div>
  );
}

/**
 * Today row 7, the gas day checklist (owner, 2026-11-19): per source the nomination status as
 * recorded, by whom and when, the agent the contract names, expected against nominated, and the
 * LNG terminal steps of the day. Status tracking only (AGENTS.md rule 8): a status entered here
 * is labelled "entered by hand" and audited server-side; nothing is nominated or sent.
 * One server read (`rows[6]`, `application/gas_day_checklist.py`).
 */
import { useState } from "react";

import { api, type GasDayChecklistItemDTO, type GasDayTargetDTO, type TodayChecklistRowDTO } from "@/api/client";
import { cutoffUrgency, formatQuantity, timeLeft } from "@/app/model/gasDayModel";
import { formatGasDay } from "@/app/time/timeFormat";
import { useInstantFormatter } from "@/app/time/useInstant";
import { Button, EmptyState, Segmented, StatusBadge, type StatusTone } from "@/components/ui";

type Translate = (key: string, options?: Record<string, unknown>) => string;

export interface ChecklistRowProps {
  row: TodayChecklistRowDTO;
  t: Translate;
  language: string;
  nowMs: number;
  /** Whether the reader may record a status (`gas_day.record`); the server checks again. */
  canRecord?: boolean;
  onOpen?: (target: GasDayTargetDTO) => void;
  /** Read Today again after a status is recorded. */
  onRecorded?: () => void;
}

const STATUS_TONE: Record<string, StatusTone> = {
  to_send: "watch",
  sent: "info",
  confirmed: "ok",
  renominated: "ok",
  done: "ok",
  mismatch_queried: "watch",
  scheduled: "neutral",
  not_held: "neutral",
};

/** The statuses a person may record for a step. */
const RECORDABLE: Record<string, readonly string[]> = {
  nomination: ["sent", "confirmed", "renominated", "mismatch_queried"],
  renomination: ["sent", "confirmed", "renominated", "mismatch_queried"],
  lng_send_out: ["sent", "confirmed", "renominated"],
  lng_unloading: ["done"],
};

function Record({ item, gasDay, t, onRecorded }: { item: GasDayChecklistItemDTO; gasDay: string; t: Translate; onRecorded?: () => void }) {
  const options = RECORDABLE[item.step] ?? [];
  const [status, setStatus] = useState(options[0] ?? "");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  if (options.length === 0) return null;
  const step = item.step === "renomination" ? "renomination" : item.step;
  return (
    <span className="checklist-record">
      <label className="ds-visually-hidden" htmlFor={`rec-${gasDay}-${item.ref}-${item.step}`}>{t("today.checklist.record_label", { label: item.label })}</label>
      <select
        id={`rec-${gasDay}-${item.ref}-${item.step}`}
        className="checklist-select"
        value={status}
        onChange={(event) => setStatus(event.target.value)}
      >
        {options.map((value) => <option key={value} value={value}>{t(`today.checklist.status.${value}`)}</option>)}
      </select>
      <Button
        size="sm"
        variant="quiet"
        loading={busy}
        onClick={async () => {
          setBusy(true);
          setError(null);
          try {
            await api.recordGasDayStatus({ gas_day: gasDay, line_ref: item.ref, step, status });
            onRecorded?.();
          } catch {
            setError(t("today.checklist.record_failed"));
          } finally {
            setBusy(false);
          }
        }}
      >
        {t("today.checklist.record")}
      </Button>
      {error && <span className="checklist-error" role="alert">{error}</span>}
    </span>
  );
}

function Item({ item, gasDay, t, nowMs, canRecord, onOpen, onRecorded }: { item: GasDayChecklistItemDTO; gasDay: string; t: Translate; nowMs: number; canRecord: boolean; onOpen?: (target: GasDayTargetDTO) => void; onRecorded?: () => void }) {
  const formatInstant = useInstantFormatter();
  const status = item.status;
  const recordedAt = status.at_utc ? formatInstant(status.at_utc, { nowMs }) : null;
  // A deadline matters while the step is open; a confirmed step shows who and when instead.
  const deadline = item.deadline && !item.deadline.passed && item.urgency !== "none" ? item.deadline : null;
  const due = deadline ? formatInstant(deadline.at_utc, { nowMs }) : null;
  const left = deadline ? timeLeft(deadline.at_utc, nowMs) : null;
  const urgency = item.urgency === "overdue" ? "imminent" : deadline ? cutoffUrgency(deadline.at_utc, nowMs) : "none";
  const who = [
    status.origin === "manual" ? t("today.checklist.by_hand", { who: status.by ?? "" }) : status.origin === "import" || status.origin === "delivery_record" ? t("today.checklist.as_recorded") : null,
    recordedAt?.text,
  ].filter(Boolean).join(" · ");
  const quantity = item.expected
    ? [
        t("today.checklist.expected", { value: formatQuantity(item.expected as { value: number; unit: "MWh/d"; mwh: number }), unit: item.expected.unit }),
        item.nominated ? t("today.checklist.nominated", { value: formatQuantity(item.nominated) }) : null,
      ].filter(Boolean).join(" · ")
    : null;
  return (
    <li className="checklist-item" data-checklist-step={item.step} data-urgency={item.urgency}>
      <div className="checklist-main">
        <span className="checklist-name">
          {onOpen ? <button type="button" className="gasday-link" onClick={() => onOpen(item.target)}>{item.label}</button> : item.label}
          <span className="muted"> · {item.hub}</span>
        </span>
        <span className="checklist-meta muted">
          {[t(`today.checklist.step.${item.step}`), item.point, item.agent ? t("today.checklist.agent", { agent: item.agent }) : item.ref.startsWith("contract:") && item.kind !== "lng" ? t("today.checklist.no_agent") : null]
            .filter(Boolean)
            .join(" · ")}
        </span>
        {quantity && (
          <span className="checklist-meta">
            {quantity}
            {item.mismatch && item.mismatch.over_tolerance && (
              <strong className="checklist-mismatch" title={t("today.checklist.tolerance", { pct: item.mismatch.tolerance_pct })}>
                {" · "}
                {t("today.checklist.mismatch", { value: formatQuantity(item.mismatch.quantity, true), pct: item.mismatch.pct })}
              </strong>
            )}
          </span>
        )}
      </div>
      <div className="checklist-side">
        <StatusBadge tone={STATUS_TONE[status.status] ?? "neutral"} title={status.note ?? undefined}>
          {t(`today.checklist.status.${status.status}`)}
        </StatusBadge>
        {who && <span className="checklist-meta muted">{who}</span>}
        {deadline && due && left && (
          <span className="checklist-deadline" data-urgency={urgency} title={`${due.title} · ${t(`today.gas_day.basis_of.${deadline.basis}`, { source: deadline.source })}`}>
            {t("today.checklist.due", { time: due.text, hours: left.hours, minutes: left.minutes })}
          </span>
        )}
        {item.urgency === "overdue" && <span className="checklist-deadline" data-urgency="imminent">{t("today.checklist.overdue")}</span>}
        {canRecord && <Record item={item} gasDay={gasDay} t={t} onRecorded={onRecorded} />}
      </div>
    </li>
  );
}

export function ChecklistRow({ row, t, language, nowMs, canRecord = false, onOpen, onRecorded }: ChecklistRowProps) {
  const [which, setWhich] = useState<"today" | "tomorrow">("today");
  const day = row.days.find((item) => item.which === which) ?? row.days[0];
  const open = (day?.items ?? []).filter((item) => item.urgency === "overdue" || item.urgency === "due_soon").length;
  return (
    <section className="today-row today-row-checklist" aria-labelledby="today-row-checklist" data-today-row="checklist">
      <header className="today-row-head">
        <h2 id="today-row-checklist">{t("today.row.checklist")}</h2>
        <span className="today-row-meta">{open > 0 ? t("today.checklist.due_count", { count: open }) : t("today.checklist.purpose")}</span>
      </header>
      {row.days.length > 1 && (
        <Segmented
          label={t("today.gas_day.day_choice")}
          value={which}
          onChange={setWhich}
          options={row.days.map((item) => ({ value: item.which, label: t(`today.gas_day.${item.which}`, { day: formatGasDay(item.gas_day, language) }) }))}
        />
      )}
      {!row.populated || !day || day.items.length === 0 ? (
        <EmptyState compact reason={row.empty?.reason ?? t("today.checklist.empty")} next={row.empty?.action} />
      ) : (
        <ul className="checklist-items" data-checklist-day={day.which}>
          {day.items.map((item) => (
            <Item key={`${item.ref}-${item.step}`} item={item} gasDay={day.gas_day} t={t} nowMs={nowMs} canRecord={canRecord} onOpen={onOpen} onRecorded={onRecorded} />
          ))}
        </ul>
      )}
    </section>
  );
}

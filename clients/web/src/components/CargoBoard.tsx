/**
 * Desk → Cargoes (QA-L-05): the firm's LNG cargoes in transit, one row each, and each cargo's
 * plan from ETA to hedge months in a sheet beside the board.
 *
 * - Rows: status in words and colour, cargo and vessel, route and hub, ETA in the reader's zone
 *   with the change the last import made and the import's age (stale past the feed's cadence),
 *   the slot window with the ETA on it, delivered energy, cover per hub month, the next action
 *   with its due time and countdown, who must act on the last change (LNG-2: trader, scheduler,
 *   risk, desk head; the reader's own roles bold), and what last changed, who and when. The
 *   ETA says what it rests on (basis and confidence, lesson P3).
 * - Order: missed and no-slot rows first, then by next action due (cargoBoardModel.ts).
 * - Keyboard: ↑ ↓ move, Enter opens the plan, `w` the what-if, `h` the hedge editor.
 * - Live: the board re-reads on the session's cargo and slot change notices (useCargoBoard).
 *
 * Decision support only: nothing here executes, books or nominates; suggestions are advice.
 */
import { useCallback, useEffect, useMemo, useState, type KeyboardEvent } from "react";

import type { CargoPlanBoardLineDTO, CargoPlanMonthDTO } from "@/api/client";
import { useCargoBoard } from "@/app/hooks/useCargoBoard";
import {
  ENERGY_DISPLAY_UNITS,
  boardKeyAction,
  convertEnergy,
  countdown,
  countdownText,
  coverTone,
  endOfDayMs,
  energyDigits,
  etaChangeHours,
  headerStrip,
  importAge,
  slotBar,
  sortCargoBoard,
  statusTone,
  type EnergyDisplayUnit,
} from "@/app/model/cargoBoardModel";
import { describeFailure, presentError } from "@/app/experience/errorPresentation";
import { formatDeliveryMonth, resolveTimeZone } from "@/app/time/timeFormat";
import { formatAmount, plainDecimal } from "@/app/time/valueFormat";
import { useInstantFormatter } from "@/app/time/useInstant";
import { useTimePreferenceStore } from "@/stores/timePreference";
import { Button, DataGrid, EmptyState, Instant, Segmented, StatusBadge, UpdatingMark, type DataGridColumn } from "@/components/ui";
import { PanelHelp } from "@/components/ui/PanelHelp";
import { CargoPlanSheet, EtaBasis, type PlanSection } from "@/components/CargoPlanView";
import "./cargo-board.css";

type Translate = (key: string, options?: Record<string, unknown>) => string;

/** Age words move on without a refetch: a minute clock, paused while hidden. */
function useMinuteClock(): number {
  const [nowMs, setNowMs] = useState(() => Date.now());
  useEffect(() => {
    const id = window.setInterval(() => {
      if (document.visibilityState === "visible") setNowMs(Date.now());
    }, 60_000);
    return () => window.clearInterval(id);
  }, []);
  return nowMs;
}

/** The cargo whose plan is open: the `cargo` URL parameter (a link, a palette result, Back). */
function useOpenCargo(): [string | null, (cargoId: string | null) => void] {
  const read = () => new URLSearchParams(window.location.search).get("cargo");
  const [cargo, setCargo] = useState<string | null>(read);
  useEffect(() => {
    const follow = () => setCargo(read());
    window.addEventListener("popstate", follow);
    return () => window.removeEventListener("popstate", follow);
  }, []);
  const open = useCallback((cargoId: string | null) => {
    const url = new URL(window.location.href);
    if (cargoId) url.searchParams.set("cargo", cargoId);
    else url.searchParams.delete("cargo");
    window.history.replaceState(window.history.state, "", url);
    setCargo(cargoId);
  }, []);
  return [cargo, open];
}

/** Who must act on the cargo's last change: one chip per open role message, the reader's bold. */
export function RoleChips({ line, t, language }: { line: CargoPlanBoardLineDTO; t: Translate; language: string }) {
  const zh = language.toLowerCase().startsWith("zh");
  const attention = line.attention ?? [];
  if (attention.length === 0) return <span className="muted">–</span>;
  return (
    <ul className="cargo-roles-chips" aria-label={t("lng.cargo.col.attention")}>
      {attention.map((item) => (
        <li key={item.alert_id} className="cargo-roles-chip" data-mine={item.mine ? "true" : "false"} data-role={item.role}>
          <StatusBadge tone={item.severity === "critical" ? "breach" : item.severity === "warning" ? "watch" : "neutral"} title={zh && item.title_zh ? item.title_zh : item.title}>
            {t(`lng.cargo.role.${item.role}`)}
            {item.mine ? ` · ${t("lng.cargo.role_mine")}` : ""}
          </StatusBadge>
        </li>
      ))}
    </ul>
  );
}

function signedHours(hours: number, language: string): string {
  const rounded = Math.round(hours);
  const text = formatAmount(Math.abs(rounded), language);
  return `${rounded >= 0 ? "+" : "−"}${text} h`;
}

export function CargoBoard({ t, language, canRecordHedges }: { t: Translate; language: string; canRecordHedges: boolean }) {
  const board = useCargoBoard(true);
  const nowMs = useMinuteClock();
  const [unit, setUnit] = useState<EnergyDisplayUnit>("GWh");
  const [openCargo, setOpenCargo] = useOpenCargo();
  const [section, setSection] = useState<PlanSection>("plan");
  const [focused, setFocused] = useState<string | null>(null);
  const format = useInstantFormatter();
  const preference = useTimePreferenceStore((state) => state.preference);

  const lines = useMemo(() => sortCargoBoard(board.lines ?? []), [board.lines]);
  const strip = useMemo(() => headerStrip(lines, endOfDayMs(nowMs, resolveTimeZone(preference))), [lines, nowMs, preference]);

  const energy = useCallback(
    (mwh: number | null | undefined) => (mwh === null || mwh === undefined ? "–" : formatAmount(convertEnergy(mwh, unit), language, energyDigits(unit))),
    [language, unit],
  );
  const asOfText = useCallback((value: string | null | undefined) => format(value, { date: "always" })?.text ?? "–", [format]);
  const hover = useCallback(
    (source: string, unitName: string, asOf: string | null | undefined) =>
      t("lng.cargo.hover", { source, unit: unitName, asOf: asOfText(asOf) }),
    [asOfText, t],
  );

  const open = useCallback(
    (cargoId: string, next: PlanSection = "plan") => {
      setSection(next);
      setOpenCargo(cargoId);
    },
    [setOpenCargo],
  );

  const readAt = board.readAt?.toISOString() ?? null;
  const columns = useMemo<DataGridColumn<CargoPlanBoardLineDTO>[]>(() => [
    {
      id: "status",
      header: t("lng.cargo.col.status"),
      value: (line) => line.error ?? line.slot_status ?? "",
      flash: true,
      priority: "primary",
      render: (line) => (
        <StatusBadge tone={statusTone(line)} title={line.error ? t(`lng.cargo.fix.${line.error}`, { defaultValue: t("lng.cargo.fix.other") }) : undefined}>
          {line.error ? t("lng.cargo.status.unplanned") : t(`lng.cargo.status.${line.slot_status ?? "no_slot"}`)}
        </StatusBadge>
      ),
    },
    {
      id: "cargo",
      header: t("lng.cargo.col.cargo"),
      rowHeader: true,
      priority: "primary",
      value: (line) => line.cargo_id,
      cellTitle: (line) => hover(line.source_system ?? "–", "–", line.imported_at_utc),
      render: (line) => (
        <span className="cargo-board-id">
          <strong>{line.cargo_id}</strong>
          <span className="cargo-board-sub">
            {line.vessel_name ?? "–"}
            {line.vessel_imo ? ` · IMO ${line.vessel_imo}` : ""}
          </span>
          {line.simulated && <StatusBadge tone="simulated" title={t("lng.cargo.simulated_title")}>{t("lng.cargo.simulated")}</StatusBadge>}
        </span>
      ),
    },
    {
      id: "route",
      header: t("lng.cargo.col.route"),
      value: (line) => `${line.load_port ?? ""} ${line.destination_terminal ?? ""}`,
      render: (line) => (
        <span className="cargo-board-id">
          <span>{line.load_port ?? "–"} → {line.slot?.terminal ?? line.destination_terminal ?? "–"}</span>
          <span className="cargo-board-sub">{line.hub ?? t("lng.cargo.no_hub")}</span>
        </span>
      ),
    },
    {
      id: "eta",
      header: t("lng.cargo.col.eta"),
      type: "date",
      flash: true,
      priority: "primary",
      value: (line) => line.eta_utc ?? null,
      cellTitle: (line) => hover(line.source_system ?? "–", t("lng.cargo.unit_instant"), line.imported_at_utc),
      render: (line) => {
        const change = etaChangeHours(line);
        const age = importAge(line, nowMs);
        return (
          <span className="cargo-board-id">
            <Instant value={line.eta_utc} date="always" />
            {line.eta && <EtaBasis eta={line.eta} t={t} />}
            <span className="cargo-board-sub">
              {change !== null && Math.abs(change) >= 0.5 && (
                <span className="cargo-board-change" data-direction={change > 0 ? "later" : "earlier"}>
                  {t("lng.cargo.eta_change", { hours: signedHours(change, language) })}
                </span>
              )}
              {age && (
                <span className={age.stale ? "cargo-board-stale" : undefined} title={t("lng.cargo.import_cadence", { hours: age.cadenceHours })}>
                  {t(age.stale ? "lng.cargo.imported_stale" : "lng.cargo.imported", { hours: formatAmount(age.hours, language, age.hours < 10 ? 1 : 0) })}
                </span>
              )}
            </span>
          </span>
        );
      },
    },
    {
      id: "slot",
      header: t("lng.cargo.col.slot"),
      value: (line) => line.slot?.window_start_utc ?? null,
      cellTitle: (line) =>
        line.slot
          ? t("lng.cargo.slot_title", { slot: line.slot.slot_id, start: asOfText(line.slot.window_start_utc), end: asOfText(line.slot.window_end_utc) })
          : undefined,
      render: (line) => <SlotMiniBar line={line} t={t} />,
    },
    {
      id: "delivered",
      header: t("lng.cargo.col.delivered"),
      unit,
      type: "number",
      flash: true,
      value: (line) => line.delivered_mwh ?? null,
      format: (value) => energy(value as number | null),
      cellTitle: (line) => hover(t("lng.cargo.source_plan"), unit, readAt ?? line.imported_at_utc),
    },
    {
      id: "cover",
      header: t("lng.cargo.col.cover"),
      value: (line) => (line.months ?? []).length,
      render: (line) => <CoverChips months={line.months ?? []} t={t} language={language} />,
    },
    {
      id: "next",
      header: t("lng.cargo.col.next"),
      priority: "primary",
      value: (line) => line.next_action?.due_utc ?? null,
      render: (line) => {
        if (line.error) return <span className="cargo-board-fix">{t(`lng.cargo.fix.${line.error}`, { defaultValue: t("lng.cargo.fix.other") })}</span>;
        const action = line.next_action;
        if (!action) return <span className="muted">{t("lng.cargo.nothing_due")}</span>;
        const due = action.due_utc ? Date.parse(action.due_utc) : null;
        const left = due === null ? null : countdown(due, nowMs);
        return (
          <span className="cargo-board-id" title={action.text}>
            <span>{t(`lng.cargo.kind.${action.kind}`)}</span>
            <span className="cargo-board-sub">
              {action.due_utc ? <Instant value={action.due_utc} date="always" /> : t("lng.cargo.no_due")}
              {left && (
                <span className={left.overdue ? "cargo-board-overdue" : "cargo-board-countdown"}>
                  {left.overdue ? t("lng.cargo.overdue", { time: countdownText(left) }) : t("lng.cargo.in", { time: countdownText(left) })}
                </span>
              )}
            </span>
          </span>
        );
      },
    },
    {
      id: "attention",
      header: t("lng.cargo.col.attention"),
      value: (line) => (line.attention ?? []).length,
      render: (line) => <RoleChips line={line} t={t} language={language} />,
    },
    {
      id: "changed",
      header: t("lng.cargo.col.changed"),
      value: (line) => line.changed?.at_utc ?? null,
      cellTitle: (line) => line.headline ?? undefined,
      render: (line) =>
        line.changed ? (
          <span className="cargo-board-id">
            <span>{line.changed.kinds.map((kind) => t(`lng.cargo.change_kind.${kind}`, { defaultValue: kind })).join(", ")}</span>
            <span className="cargo-board-sub">
              {line.changed.by} · <Instant value={line.changed.at_utc} />
            </span>
          </span>
        ) : (
          <span className="muted">–</span>
        ),
    },
  ], [asOfText, energy, hover, language, nowMs, readAt, t, unit]);

  const onKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    const row = (event.target as HTMLElement).closest?.("tr[data-row-key]") as HTMLTableRowElement | null;
    if (!row || event.target !== row) return;
    const action = boardKeyAction(event);
    const cargoId = row.dataset.rowKey ?? null;
    if (!cargoId) return;
    if (action === "what_if") {
      event.preventDefault();
      open(cargoId, "what_if");
    } else if (action === "hedge") {
      event.preventDefault();
      open(cargoId, "hedge");
    }
    // ↑ ↓ and Enter are the grid's own (DataGrid moves focus and calls onRowAction).
  };

  const failure = board.error ? presentError(t, describeFailure(board.error)) : null;
  const empty = (
    <EmptyState
      id="cargo-board-empty"
      reason={t("lng.cargo.empty")}
      next={t("lng.cargo.empty_next")}
    />
  );

  return (
    <section className="cargo-board" aria-labelledby="cargo-board-title" data-cargo-board="">
      <header className="cargo-board-head">
        <div className="cargo-board-title">
          <h2 id="cargo-board-title">{t("lng.cargo.title")}</h2>
          <span className="cargo-board-sub">
            {board.readAt ? <Instant value={board.readAt} prefix={t("lng.cargo.as_of")} /> : null}
            {" · "}
            {t(board.live ? "lng.cargo.live" : "lng.cargo.polling")}
            <UpdatingMark active={board.updating} label={t("lng.cargo.updating")} />
          </span>
        </div>
        <div className="cargo-board-actions">
          <Segmented
            label={t("lng.cargo.unit_label")}
            options={ENERGY_DISPLAY_UNITS.map((value) => ({ value, label: value, title: t(`lng.cargo.unit.${value}`) }))}
            value={unit}
            onChange={setUnit}
          />
          <Button variant="quiet" onClick={board.refresh} loading={board.updating}>{t("lng.cargo.refresh")}</Button>
        </div>
      </header>
      <PanelHelp label={t("lng.cargo.help_label")} text={t("lng.cargo.help")} />

      <HeaderStripView strip={strip} t={t} language={language} unit={unit} nowMs={nowMs} energy={energy} />

      {failure && (
        <div className="cargo-board-error" role="alert" data-cargo-board-error="">
          <strong>{failure.title}</strong>
          <span>{failure.action}</span>
          <Button variant="secondary" onClick={board.refresh}>{t("lng.cargo.retry")}</Button>
        </div>
      )}

      <div className="cargo-board-grid" onKeyDown={onKeyDown} onFocus={(event) => {
        const row = (event.target as HTMLElement).closest?.("tr[data-row-key]") as HTMLTableRowElement | null;
        if (row?.dataset.rowKey) setFocused(row.dataset.rowKey);
      }}>
        <DataGrid
          id="cargo-board"
          label={t("lng.cargo.title")}
          columns={columns}
          rows={lines}
          rowKey={(line) => line.cargo_id}
          density="compact"
          loading={board.loading}
          loadingLabel={t("lng.cargo.loading")}
          empty={failure ? t("lng.cargo.empty_error") : empty}
          onRowAction={(line) => open(line.cargo_id, "plan")}
          selectedKey={openCargo ?? focused ?? null}
          rowAttributes={(line) => ({ "data-slot-status": line.error ? "unplanned" : line.slot_status, "data-pinned": line.slot_status === "missed" || line.slot_status === "no_slot" ? "true" : undefined })}
        />
      </div>
      <p className="cargo-board-keys">{t("lng.cargo.keys")}</p>
      <p className="cargo-board-advisory">{t("lng.cargo.advice_only")}</p>

      <CargoPlanSheet
        cargoId={openCargo}
        section={section}
        onSection={setSection}
        onClose={() => setOpenCargo(null)}
        t={t}
        language={language}
        unit={unit}
        canRecordHedges={canRecordHedges}
        onSaved={board.refresh}
      />
    </section>
  );
}

function SlotMiniBar({ line, t }: { line: CargoPlanBoardLineDTO; t: Translate }) {
  const bar = slotBar(line);
  if (!bar) return <span className="muted">{line.slot ? "–" : t("lng.cargo.no_slot_short")}</span>;
  const pct = (share: number) => `${plainDecimal(Math.max(0, Math.min(100, share * 100)), 1)}%`;
  return (
    <span className="cargo-slot-bar" data-eta={bar.position} role="img" aria-label={t(`lng.cargo.slot_${bar.position}`)}>
      <span className="cargo-slot-window" style={{ left: pct(bar.windowStart), width: pct(bar.windowEnd - bar.windowStart) }} />
      <span className="cargo-slot-eta" style={{ left: pct(bar.eta) }} />
    </span>
  );
}

function CoverChips({ months, t, language }: { months: readonly CargoPlanMonthDTO[]; t: Translate; language: string }) {
  const shown = months.filter((month) => Math.abs(month.physical_mwh) >= 1 || Math.abs(month.hedge_mwh) >= 1);
  if (!shown.length) return <span className="muted">–</span>;
  return (
    <span className="cargo-cover-chips">
      {shown.map((month) => (
        <StatusBadge
          key={`${month.hub}-${month.month}`}
          tone={coverTone(month)}
          title={t("lng.cargo.cover_title", {
            hub: month.hub,
            month: formatDeliveryMonth(month.month),
            physical: formatAmount(month.physical_mwh, language),
            hedge: formatAmount(month.hedge_mwh, language),
            net: formatAmount(month.net_mwh, language),
          })}
        >
          {formatDeliveryMonth(month.month)} {month.cover_ratio === null ? "–" : `${formatAmount(month.cover_ratio * 100, language)} %`}
        </StatusBadge>
      ))}
    </span>
  );
}

function HeaderStripView({
  strip,
  t,
  language,
  unit,
  nowMs,
  energy,
}: {
  strip: ReturnType<typeof headerStrip>;
  t: Translate;
  language: string;
  unit: EnergyDisplayUnit;
  nowMs: number;
  energy: (mwh: number) => string;
}) {
  const expiry = strip.nextExpiry;
  const left = expiry ? countdown(Date.parse(expiry.due_utc), nowMs) : null;
  return (
    <div className="cargo-strip" role="group" aria-label={t("lng.cargo.strip_label")} data-cargo-strip="">
      <div className="cargo-strip-cell">
        <span className="cargo-strip-label">{t("lng.cargo.strip_open", { unit })}</span>
        {strip.open.length ? (
          <span className="cargo-strip-open">
            {strip.open.map((cell) => (
              <span key={`${cell.hub}-${cell.month}`} title={t("lng.cargo.strip_open_title", { cargoes: cell.cargoes })}>
                {cell.hub} {formatDeliveryMonth(cell.month)} <strong>{cell.net_mwh >= 0 ? "+" : "−"}{energy(Math.abs(cell.net_mwh))}</strong>
              </span>
            ))}
          </span>
        ) : (
          <span className="muted">{t("lng.cargo.strip_none_open")}</span>
        )}
      </div>
      <div className="cargo-strip-cell">
        <span className="cargo-strip-label">{t("lng.cargo.strip_expiry")}</span>
        {expiry ? (
          <span>
            {expiry.hub} {formatDeliveryMonth(expiry.month)} · <Instant value={expiry.due_utc} date="always" />
            {left && <span className="cargo-board-countdown"> {t("lng.cargo.in", { time: countdownText(left) })}</span>}
          </span>
        ) : (
          <span className="muted">–</span>
        )}
      </div>
      <div className="cargo-strip-cell">
        <span className="cargo-strip-label">{t("lng.cargo.strip_today")}</span>
        <strong data-need-today={strip.needActionToday}>{formatAmount(strip.needActionToday, language)}</strong>
        {strip.unplanned > 0 && <span className="cargo-board-stale"> {t("lng.cargo.strip_unplanned", { count: strip.unplanned })}</span>}
      </div>
    </div>
  );
}

/**
 * PeriodPicker: the app's own day, month and date-time control (DESIGN_TOKENS "PeriodPicker").
 *
 * It replaces `<input type="date|month|datetime-local">`, whose text and calendar follow the
 * device's locale (a Chinese phone showed "2026年12月" in the English interface). Everything here
 * follows the app's language. The value is the same string the native input produced, so pages
 * keep their data unchanged.
 *
 * Keyboard (WAI-ARIA date picker): the button opens a dialog; arrows move a day or a week, Home and
 * End the week, PageUp/PageDown a month (Shift: a year), Enter or Space chooses, Escape closes and
 * returns focus. A month picker moves by month with the arrows. Touch targets are 44 px on a
 * coarse pointer.
 */
import { useEffect, useId, useMemo, useRef, useState, type KeyboardEvent } from "react";
import { useTranslation } from "react-i18next";

import { Popover } from "./Popover";
import {
  addMonths,
  clampDay,
  dayKey,
  monthGrid,
  monthLabel,
  monthYearLabel,
  moveDay,
  parseDay,
  parseMonth,
  parseTime,
  periodText,
  todayValue,
  weekdayLabels,
  withTime,
  type DayValue,
  type PeriodKind,
} from "./periodModel";
import { Icon } from "./Icon";

export interface PeriodPickerProps {
  kind?: PeriodKind;
  value: string;
  onChange: (value: string) => void;
  /** Accessible name (the field's label). */
  label: string;
  /** Earliest / latest day ("YYYY-MM-DD") or month ("YYYY-MM"). */
  min?: string;
  max?: string;
  /** Shown when there is no value. */
  placeholder?: string;
  /** Offer "Clear" (an optional date). */
  clearable?: boolean;
  disabled?: boolean;
  id?: string;
  className?: string;
}

const pad = (value: number) => String(value).padStart(2, "0");
const MINUTES = Array.from({ length: 12 }, (_, index) => index * 5);
const HOURS = Array.from({ length: 24 }, (_, index) => index);

export function PeriodPicker({
  kind = "day",
  value,
  onChange,
  label,
  min,
  max,
  placeholder,
  clearable = false,
  disabled = false,
  id,
  className,
}: PeriodPickerProps) {
  const { t, i18n } = useTranslation();
  const language = i18n.language;
  const shown = periodText(kind, value, language);
  return (
    <Popover
      label={label}
      width="sm"
      className="ds-period-popover"
      trigger={(props) => (
        <button
          {...props}
          id={id}
          type="button"
          className={["ds-period", className].filter(Boolean).join(" ")}
          disabled={disabled}
          aria-label={`${label}: ${shown || placeholder || t("period.none")}`}
          data-period-kind={kind}
          data-period-value={value}
        >
          <span className={shown ? undefined : "ds-period-placeholder"}>{shown || placeholder || t("period.choose")}</span>
          <Icon name="calendar" />
        </button>
      )}
    >
      {(close) =>
        kind === "month" ? (
          <MonthGrid value={value} min={min} max={max} language={language} onChoose={(next) => { onChange(next); close(); }} />
        ) : (
          <DayCalendar
            kind={kind}
            value={value}
            min={min}
            max={max}
            language={language}
            clearable={clearable}
            onChoose={(next, done) => {
              onChange(next);
              if (done) close();
            }}
          />
        )
      }
    </Popover>
  );
}

function DayCalendar({
  kind,
  value,
  min,
  max,
  language,
  clearable,
  onChoose,
}: {
  kind: PeriodKind;
  value: string;
  min?: string;
  max?: string;
  language: string;
  clearable: boolean;
  onChoose: (value: string, done: boolean) => void;
}) {
  const { t } = useTranslation();
  const selected = parseDay(value);
  const [focus, setFocus] = useState<DayValue>(() => clampDay(selected ?? todayValue(), min, max));
  const time = parseTime(value) ?? { hour: 9, minute: 0 };
  const gridRef = useRef<HTMLTableElement>(null);
  const headingId = useId();
  const weeks = useMemo(() => monthGrid(focus.year, focus.month), [focus.year, focus.month]);
  const todayKey = dayKey(todayValue());

  useEffect(() => {
    gridRef.current?.querySelector<HTMLButtonElement>(`[data-day="${dayKey(focus)}"]`)?.focus({ preventScroll: true });
  }, [focus]);

  const choose = (day: DayValue) => {
    const key = dayKey(day);
    onChoose(kind === "datetime" ? withTime(key, time.hour, time.minute) : key, kind !== "datetime");
  };
  const outOfRange = (day: DayValue) => Boolean((min && dayKey(day) < min.slice(0, 10)) || (max && dayKey(day) > max.slice(0, 10)));
  const onKeyDown = (event: KeyboardEvent<HTMLTableElement>) => {
    const next = moveDay(focus, event.key, event.shiftKey);
    if (!next) return;
    event.preventDefault();
    setFocus(clampDay(next, min, max));
  };

  return (
    <div className="ds-period-calendar">
      <div className="ds-period-head">
        <button type="button" className="ds-period-nav" aria-label={t("period.previous_month")} title={t("period.previous_month")} onClick={() => setFocus(clampDay(addMonths(focus, -1), min, max))}><Icon name="chevron-left" /></button>
        <strong id={headingId} aria-live="polite">{monthYearLabel(focus.year, focus.month, language)}</strong>
        <button type="button" className="ds-period-nav" aria-label={t("period.next_month")} title={t("period.next_month")} onClick={() => setFocus(clampDay(addMonths(focus, 1), min, max))}><Icon name="chevron-right" /></button>
      </div>
      <table ref={gridRef} role="grid" aria-labelledby={headingId} className="ds-period-grid" onKeyDown={onKeyDown}>
        <thead>
          <tr>
            {weekdayLabels(language).map((day) => (
              <th key={day} scope="col" abbr={day}>{day}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {weeks.map((week, index) => (
            <tr key={index}>
              {week.map((day, column) => {
                if (!day) return <td key={column} />;
                const key = dayKey(day);
                const isFocus = key === dayKey(focus);
                return (
                  <td key={column}>
                    <button
                      type="button"
                      data-day={key}
                      tabIndex={isFocus ? 0 : -1}
                      aria-selected={selected ? key === dayKey(selected) : false}
                      aria-current={key === todayKey ? "date" : undefined}
                      disabled={outOfRange(day)}
                      onClick={() => choose(day)}
                    >
                      {day.day}
                    </button>
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
      {kind === "datetime" ? (
        <div className="ds-period-time">
          <label>
            <span>{t("period.hour")}</span>
            <select value={time.hour} onChange={(event) => selected && onChoose(withTime(dayKey(selected), Number(event.target.value), time.minute), false)} disabled={!selected}>
              {HOURS.map((hour) => <option key={hour} value={hour}>{pad(hour)}</option>)}
            </select>
          </label>
          <span aria-hidden="true">:</span>
          <label>
            <span>{t("period.minute")}</span>
            <select value={time.minute - (time.minute % 5)} onChange={(event) => selected && onChoose(withTime(dayKey(selected), time.hour, Number(event.target.value)), false)} disabled={!selected}>
              {MINUTES.map((minute) => <option key={minute} value={minute}>{pad(minute)}</option>)}
            </select>
          </label>
        </div>
      ) : null}
      <div className="ds-period-foot">
        <button type="button" className="ds-inline-link" onClick={() => { const today = clampDay(todayValue(), min, max); setFocus(today); choose(today); }}>
          {t("period.today")}
        </button>
        {clearable ? (
          <button type="button" className="ds-inline-link" onClick={() => onChoose("", true)}>
            {t("period.clear")}
          </button>
        ) : null}
      </div>
    </div>
  );
}

function MonthGrid({
  value,
  min,
  max,
  language,
  onChoose,
}: {
  value: string;
  min?: string;
  max?: string;
  language: string;
  onChoose: (value: string) => void;
}) {
  const { t } = useTranslation();
  const selected = parseMonth(value);
  const now = todayValue();
  const [year, setYear] = useState(selected?.year ?? now.year);
  const [focusMonth, setFocusMonth] = useState(selected?.month ?? now.month);
  const gridRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    gridRef.current?.querySelector<HTMLButtonElement>(`[data-month="${focusMonth}"]`)?.focus({ preventScroll: true });
  }, [focusMonth, year]);
  const key = (month: number) => `${year}-${pad(month)}`;
  const onKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    const step = { ArrowLeft: -1, ArrowRight: 1, ArrowUp: -3, ArrowDown: 3 }[event.key];
    if (step === undefined) return;
    event.preventDefault();
    let next = focusMonth + step;
    if (next < 1) { next += 12; setYear(year - 1); }
    if (next > 12) { next -= 12; setYear(year + 1); }
    setFocusMonth(next);
  };
  return (
    <div className="ds-period-calendar">
      <div className="ds-period-head">
        <button type="button" className="ds-period-nav" aria-label={t("period.previous_year")} title={t("period.previous_year")} onClick={() => setYear(year - 1)}><Icon name="chevron-left" /></button>
        <strong aria-live="polite">{year}</strong>
        <button type="button" className="ds-period-nav" aria-label={t("period.next_year")} title={t("period.next_year")} onClick={() => setYear(year + 1)}><Icon name="chevron-right" /></button>
      </div>
      <div ref={gridRef} className="ds-period-months" role="group" aria-label={String(year)} onKeyDown={onKeyDown}>
        {Array.from({ length: 12 }, (_, index) => index + 1).map((month) => (
          <button
            key={month}
            type="button"
            data-month={month}
            tabIndex={month === focusMonth ? 0 : -1}
            aria-pressed={selected ? selected.year === year && selected.month === month : false}
            disabled={Boolean((min && key(month) < min.slice(0, 7)) || (max && key(month) > max.slice(0, 7)))}
            onClick={() => onChoose(key(month))}
          >
            {monthLabel(month, language)}
          </button>
        ))}
      </div>
    </div>
  );
}

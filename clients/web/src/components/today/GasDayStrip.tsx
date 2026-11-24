/**
 * The trader's gas-day strip (owner, 2026-11-24): one line above "My market" with the next
 * nomination cut-off, overdue checklist steps and each hub whose net is outside its band, so
 * a trader who reads prices first still sees what is urgent. Each part opens My gas day.
 * Every figure is the server's (`gasDayAlert` only picks and orders them).
 */
import type { TodayChecklistRowDTO, TodayGasDayRowDTO } from "@/api/client";
import { cutoffUrgency, formatQuantity, gasDayAlert, timeLeft } from "@/app/model/gasDayModel";
import { useInstantFormatter } from "@/app/time/useInstant";

type Translate = (key: string, options?: Record<string, unknown>) => string;

function openGasDay() {
  const row = document.querySelector<HTMLElement>('[data-today-row="gas_day"]');
  if (!row) return;
  const smooth = !window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
  row.scrollIntoView({ behavior: smooth ? "smooth" : "auto", block: "start" });
  row.querySelector<HTMLElement>("h2")?.focus?.();
}

export function GasDayStrip({ gasDay, checklist, t, nowMs }: {
  gasDay: TodayGasDayRowDTO | null | undefined;
  checklist: TodayChecklistRowDTO | null | undefined;
  t: Translate;
  nowMs: number;
}) {
  const formatInstant = useInstantFormatter();
  if (!gasDay?.populated) return null;
  const alert = gasDayAlert(gasDay, checklist, nowMs);
  const next = alert.next;
  const at = next ? formatInstant(next.cutoff.at_utc, { nowMs }) : null;
  const left = next ? timeLeft(next.cutoff.at_utc, nowMs) : null;
  const urgency = next ? cutoffUrgency(next.cutoff.at_utc, nowMs) : "none";
  const name = next
    ? next.cutoff.key === "window" && next.cutoff.name ? next.cutoff.name : t(`today.gas_day.cutoff.${next.cutoff.key}`)
    : "";
  return (
    <button type="button" className="today-gasday-strip" data-today-strip="gas_day" onClick={openGasDay} aria-label={t("today.strip.open")}>
      <span className="today-gasday-strip-part" data-urgency={urgency}>
        {next && at && left
          ? <span title={at.title}>{t("today.strip.next_cutoff", { hub: next.hub, name, time: at.text, hours: left.hours, minutes: left.minutes })}</span>
          : t("today.strip.no_cutoff")}
      </span>
      {alert.overdue > 0 && (
        <span className="today-gasday-strip-part" data-urgency="overdue">{t("today.strip.overdue", { count: alert.overdue })}</span>
      )}
      {alert.open.map((item) => (
        <span key={item.hub} className="today-gasday-strip-part" data-state={item.state}>
          {t(`today.strip.${item.state}`, { hub: item.hub, net: formatQuantity(item.net, true), unit: item.net.unit })}
        </span>
      ))}
      {alert.overdue === 0 && alert.open.length === 0 && (
        <span className="today-gasday-strip-part">{t("today.strip.all_balanced")}</span>
      )}
    </button>
  );
}

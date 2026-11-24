/**
 * Scheduled reports (Research → Reports): the daily and weekly reports the worker generates and
 * who receives them. Everyone sees the schedules; an administrator adds and removes them. A
 * scheduled report is for distribution (no book sections) and runs as the service principal;
 * it appears in the library of its roles and, when asked, is announced by e-mail through the
 * notification channels for the "report" category.
 */
import { useEffect, useState } from "react";

import { api, type ReportScheduleDTO } from "@/api/client";
import { Button, Field, Panel, Select } from "@/components/ui";
import { useApiStore } from "@/stores/api";

type Translate = (key: string, values?: Record<string, string | number>) => string;

const ROLES = ["VIEWER", "SCHEDULER", "REVIEWER", "ANALYST", "OPERATOR", "ADMIN"] as const;
const WEEKDAYS = [0, 1, 2, 3, 4, 5, 6] as const;
/** Half-hour slots of the UTC day. */
const TIMES = Array.from({ length: 48 }, (_, i) => `${String(Math.floor(i / 2)).padStart(2, "0")}:${i % 2 ? "30" : "00"}`);

export function describeSchedule(schedule: ReportScheduleDTO, t: Translate): string {
  const when = schedule.kind === "weekly"
    ? t("reports.schedule.weekly_at", { day: t(`reports.schedule.weekday.${schedule.weekday ?? 0}`), time: schedule.at_utc })
    : t("reports.schedule.daily_at", { time: schedule.at_utc });
  const to = schedule.roles.map((role) => t(`reports.schedule.role.${role}`)).join(", ");
  return `${when} · ${schedule.language === "zh-CN" ? "中文" : "English"} · ${t("reports.schedule.to", { roles: to })}${schedule.email ? ` · ${t("reports.schedule.email")}` : ""}`;
}

export function ReportSchedules({ t }: { t: Translate }) {
  const currentUser = useApiStore((state) => state.currentUser);
  const roles = currentUser?.roles ?? (currentUser?.role ? [currentUser.role] : []);
  const isAdmin = roles.includes("ADMIN");
  const [schedules, setSchedules] = useState<ReportScheduleDTO[] | null>(null);
  const [draft, setDraft] = useState<ReportScheduleDTO>({ kind: "daily", at_utc: "06:30", weekday: 0, language: "en", roles: ["ANALYST"], email: false });
  const [message, setMessage] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api.reportSchedules().then((r) => setSchedules(r.data.schedules)).catch(() => setSchedules([]));
  }, []);

  async function save(next: ReportScheduleDTO[]) {
    setBusy(true);
    setMessage(null);
    try {
      const response = await api.saveReportSchedules(next);
      setSchedules(response.data.schedules);
      setMessage(t("reports.schedule.saved"));
    } catch {
      // What is entered stays; the server says what it refused.
      setMessage(t("reports.schedule.save_failed"));
    } finally {
      setBusy(false);
    }
  }

  const toggleRole = (role: string) =>
    setDraft({ ...draft, roles: draft.roles.includes(role) ? draft.roles.filter((r) => r !== role) : [...draft.roles, role] });

  return (
    <Panel title={t("reports.schedule.title")} level={3} className="reports-schedules">
      <p className="reports-note">{t("reports.schedule.note")}</p>
      {schedules && !schedules.length && <p className="reports-note">{t("reports.schedule.none")}</p>}
      <ul className="reports-schedule-list" data-report-schedules="">
        {(schedules ?? []).map((schedule) => (
          <li key={schedule.schedule_id}>
            <span>{t(`reports.kind.${schedule.kind}`)} — {describeSchedule(schedule, t)}</span>
            {isAdmin && (
              <Button size="sm" variant="quiet" disabled={busy}
                onClick={() => void save((schedules ?? []).filter((s) => s.schedule_id !== schedule.schedule_id))}>
                {t("reports.schedule.remove")}
              </Button>
            )}
          </li>
        ))}
      </ul>
      {isAdmin && (
        <form className="reports-schedule-form" onSubmit={(event) => { event.preventDefault(); void save([...(schedules ?? []), draft]); }} data-report-schedule-form="">
          <div className="reports-row">
            <Field label={t("reports.kind")}>
              <Select<"daily" | "weekly"> value={draft.kind}
                options={[{ value: "daily", label: t("reports.kind.daily") }, { value: "weekly", label: t("reports.kind.weekly") }]}
                onChange={(kind) => setDraft({ ...draft, kind })} />
            </Field>
            <Field label={t("reports.schedule.time")}>
              <Select<string> value={draft.at_utc} options={TIMES.map((time) => ({ value: time, label: time }))}
                onChange={(at_utc) => setDraft({ ...draft, at_utc })} />
            </Field>
            {draft.kind === "weekly" && (
              <Field label={t("reports.schedule.day")}>
                <Select<string> value={String(draft.weekday ?? 0)}
                  options={WEEKDAYS.map((day) => ({ value: String(day), label: t(`reports.schedule.weekday.${day}`) }))}
                  onChange={(day) => setDraft({ ...draft, weekday: Number(day) })} />
              </Field>
            )}
            <Field label={t("reports.language")}>
              <Select<"en" | "zh-CN"> value={draft.language}
                options={[{ value: "en", label: "English" }, { value: "zh-CN", label: "中文" }]}
                onChange={(language) => setDraft({ ...draft, language })} />
            </Field>
          </div>
          <fieldset className="reports-sections">
            <legend>{t("reports.schedule.roles")}</legend>
            {ROLES.map((role) => (
              <label key={role}>
                <input type="checkbox" checked={draft.roles.includes(role)} onChange={() => toggleRole(role)} />
                <span>{t(`reports.schedule.role.${role}`)}</span>
              </label>
            ))}
          </fieldset>
          <label className="reports-annex">
            <input type="checkbox" checked={draft.email} onChange={(event) => setDraft({ ...draft, email: event.target.checked })} />
            <span>{t("reports.schedule.email_too")}</span>
          </label>
          <div className="reports-actions">
            <Button type="submit" size="sm" loading={busy} disabled={!draft.roles.length}>{t("reports.schedule.add")}</Button>
          </div>
        </form>
      )}
      {message && <p className="reports-note" role="status">{message}</p>}
    </Panel>
  );
}

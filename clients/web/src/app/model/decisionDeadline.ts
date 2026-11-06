/**
 * Decision deadlines in the client (#58). The desk types a local date and time; the case stores
 * the UTC instant with an explicit offset, and the form shows that UTC instant back before it
 * is saved, so a deadline is never ambiguous across desks or a daylight-saving change.
 */

/** The UTC ISO instant for a `datetime-local` value read in this browser's time zone, or null. */
export function localDeadlineToUtc(local: string, toDate: (value: string) => Date = (value) => new Date(value)): string | null {
  if (!local || !/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}/.test(local)) return null;
  const date = toDate(local);
  if (Number.isNaN(date.getTime())) return null;
  return date.toISOString();
}

/** "2026-11-06 15:00 UTC" for a UTC ISO instant. */
export function formatDeadlineUtc(isoUtc: string): string {
  return `${isoUtc.slice(0, 10)} ${isoUtc.slice(11, 16)} UTC`;
}

export type DeadlineState = "none" | "due" | "overdue" | "decided_on_time" | "decided_late";

/** Translation key for the deadline state the API reports. */
export function deadlineStateKey(state: string | undefined | null): string | null {
  switch (state) {
    case "due":
      return "decision_case.deadline.due";
    case "overdue":
      return "decision_case.deadline.overdue";
    case "decided_on_time":
      return "decision_case.deadline.on_time";
    case "decided_late":
      return "decision_case.deadline.late";
    default:
      return null;
  }
}

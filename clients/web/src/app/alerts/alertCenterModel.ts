/**
 * The alert centre's own reading of the desk-wide alert list.
 *
 * Alerts are shared: their status (open, acknowledged, resolved) is the desk's and is audited.
 * What one person has read or dismissed is theirs alone and comes from `/api/me/alert-state`.
 * This module turns the two into the list a person works through:
 *
 * - repeats of one condition are one row (four REMIT notices for one interconnection point,
 *   two short days on one supply contract), so the list reads as things to act on, not as feed
 *   messages;
 * - rows are ordered by what needs the reader first: unread before read, critical before
 *   warning, newest event first;
 * - the badge counts unread rows the reader has not dismissed, from the same list the drawer
 *   shows, so the number on the bar and the drawer always agree.
 */

import type { MonitoringAlertDTO } from "@/api/client";

export interface AlertReaderMark {
  read: boolean;
  dismissed: boolean;
  read_at_utc: string | null;
  dismissed_at_utc: string | null;
}

export type AlertReaderMarks = Record<string, AlertReaderMark>;
export type AlertReaderAction = "read" | "dismiss" | "restore";

export interface AlertGroup {
  key: string;
  /** The member shown: the most severe, then the newest. */
  lead: MonitoringAlertDTO;
  members: MonitoringAlertDTO[];
  severity: MonitoringAlertDTO["severity"];
  unread: boolean;
  dismissed: boolean;
  acknowledged: boolean;
  simulated: boolean;
  /** The earliest event time among the members: since when this has been going on. */
  since: string;
}

const SEVERITY_RANK: Record<string, number> = { info: 0, warning: 1, critical: 2 };

/** Categories the drawer knows how to name; anything else is shown under "Other". */
export const ALERT_CATEGORIES = [
  "limits",
  "delivery",
  "physical",
  "market",
  "fundamentals",
  "data_source",
  "opportunity",
  "market_opportunity",
  "capacity",
  "lng_hedge",
  "lng_schedule",
  "lng_exposure",
  "lng_material",
  "gas_day_break",
  "news_trader",
  "news_lng",
  "news_scheduler",
] as const;

export function severityRank(severity: string): number {
  return SEVERITY_RANK[severity] ?? 0;
}

/**
 * Which alerts are one thing to the reader.
 *
 * - an outage: the same asset and the same unavailable volume, whatever auction or notice
 *   version repeated it (the title names both);
 * - a delivery shortfall: the same contract, across gas days;
 * - anything else stands alone.
 */
export function alertGroupKey(alert: MonitoringAlertDTO): string {
  if (alert.category === "physical") return `physical|${alert.alert_type}|${alert.title_en}`;
  if (alert.category === "delivery") {
    const contract = alert.evidence_snapshot?.contract_id;
    if (typeof contract === "string" && contract) return `delivery|${alert.alert_type}|${contract}`;
  }
  return `alert|${alert.alert_id}`;
}

function later(a: string, b: string): number {
  return Date.parse(b) - Date.parse(a);
}

export function groupAlerts(alerts: MonitoringAlertDTO[], marks: AlertReaderMarks): AlertGroup[] {
  const groups = new Map<string, MonitoringAlertDTO[]>();
  for (const alert of alerts) {
    if (alert.status === "resolved") continue;
    const key = alertGroupKey(alert);
    const members = groups.get(key);
    if (members) members.push(alert);
    else groups.set(key, [alert]);
  }
  const result: AlertGroup[] = [];
  for (const [key, members] of groups) {
    members.sort(
      (a, b) => severityRank(b.severity) - severityRank(a.severity) || later(a.event_time_utc, b.event_time_utc),
    );
    const lead = members[0];
    const since = members.reduce(
      (earliest, member) => (Date.parse(member.event_time_utc) < Date.parse(earliest) ? member.event_time_utc : earliest),
      lead.event_time_utc,
    );
    result.push({
      key,
      lead,
      members,
      severity: lead.severity,
      unread: members.some((member) => !marks[member.alert_id]?.read),
      dismissed: members.every((member) => marks[member.alert_id]?.dismissed === true),
      acknowledged: members.every((member) => member.status === "acknowledged"),
      simulated: members.some((member) => member.simulated),
      since,
    });
  }
  return result.sort(
    (a, b) =>
      Number(b.unread) - Number(a.unread) ||
      severityRank(b.severity) - severityRank(a.severity) ||
      later(a.lead.event_time_utc, b.lead.event_time_utc),
  );
}

export interface AlertCounts {
  /** Rows the reader has neither read nor dismissed: the number on the bar. */
  unread: number;
  unreadCritical: number;
  active: number;
  dismissed: number;
  critical: number;
  warning: number;
}

export function alertCounts(groups: AlertGroup[]): AlertCounts {
  const active = groups.filter((group) => !group.dismissed);
  return {
    unread: active.filter((group) => group.unread).length,
    unreadCritical: active.filter((group) => group.unread && group.severity === "critical").length,
    active: active.length,
    dismissed: groups.length - active.length,
    critical: active.filter((group) => group.severity === "critical").length,
    warning: active.filter((group) => group.severity === "warning").length,
  };
}

/** The reader's marks after an action, as the server will record it, for an immediate answer. */
export function applyReaderAction(
  marks: AlertReaderMarks,
  action: AlertReaderAction,
  alertIds: string[],
  nowUtc: string,
): AlertReaderMarks {
  const next: AlertReaderMarks = { ...marks };
  for (const id of alertIds) {
    const current = next[id] ?? { read: false, dismissed: false, read_at_utc: null, dismissed_at_utc: null };
    if (action === "read") next[id] = { ...current, read: true, read_at_utc: current.read_at_utc ?? nowUtc };
    if (action === "dismiss") {
      next[id] = { read: true, dismissed: true, read_at_utc: current.read_at_utc ?? nowUtc, dismissed_at_utc: nowUtc };
    }
    if (action === "restore") {
      if (!next[id]) continue;
      next[id] = { ...current, dismissed: false, dismissed_at_utc: null };
    }
  }
  return next;
}

export function memberIds(groups: AlertGroup[]): string[] {
  return groups.flatMap((group) => group.members.map((member) => member.alert_id));
}

/** The i18n key naming an alert category, with a fallback for categories added later. */
export function categoryKey(category: string): string {
  return (ALERT_CATEGORIES as readonly string[]).includes(category)
    ? `alerts.category.${category}`
    : "alerts.category.other";
}

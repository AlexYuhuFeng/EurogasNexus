import type { MonitoringAlertDTO } from "@/api/client";

/** The fields of an outage row the ticker reads (``/api/physical/outages``). */
export interface TickerOutage {
  event_id: string;
  facility_name: string;
  balancing_zone: string;
  event_type: string;
  status: string;
  start_utc: string;
  unit: string;
  unavailable_capacity: number | null;
  technical_capacity?: number | null;
  unavailable_gwh_d?: number | null;
}

/** One line in the breaking-news ticker under the top bar. */
export interface TickerItem {
  id: string;
  severity: "critical" | "warning" | "info";
  text: string;
  at: string; // ISO time the item became true, newest first within a severity
  kind: "alert" | "outage";
}

const RANK = { critical: 0, warning: 1, info: 2 } as const;

function capacity(outage: TickerOutage): string {
  if (outage.unavailable_gwh_d != null) return `${Math.round(outage.unavailable_gwh_d)} GWh/d`;
  if (outage.unavailable_capacity != null) return `${outage.unavailable_capacity} ${outage.unit}`;
  return "";
}

/**
 * What a trader should glance at without leaving the screen: open monitoring alerts and the
 * outages active now. Critical first, then newest; acknowledged or resolved alerts and
 * scheduled outages stay in their own panels, not on the ticker.
 */
export function buildTickerItems(
  alerts: readonly MonitoringAlertDTO[],
  outages: readonly TickerOutage[],
  language: string,
  t: (key: string, options?: Record<string, unknown>) => string,
): TickerItem[] {
  const chinese = language.toLowerCase().startsWith("zh");
  const items: TickerItem[] = [];
  for (const alert of alerts) {
    if (alert.status !== "open") continue;
    items.push({
      id: `alert:${alert.alert_id}`,
      severity: alert.severity,
      text: (chinese ? alert.title_zh_cn : alert.title_en) || alert.title_en,
      at: alert.updated_at_utc || alert.detected_at_utc,
      kind: "alert",
    });
  }
  for (const outage of outages) {
    if (outage.status !== "active") continue;
    const share =
      outage.technical_capacity && outage.unavailable_capacity != null
        ? outage.unavailable_capacity / outage.technical_capacity
        : 0;
    items.push({
      id: `outage:${outage.event_id}`,
      // Most of an asset out is market-moving; a partial derate is worth a glance.
      severity: share >= 0.5 ? "critical" : "warning",
      text: t("ticker.outage", {
        asset: outage.facility_name,
        zone: outage.balancing_zone,
        capacity: capacity(outage),
        kind: outage.event_type,
      }).replace(/\s+·\s+$/, ""),
      at: outage.start_utc,
      kind: "outage",
    });
  }
  return items.sort(
    (left, right) => RANK[left.severity] - RANK[right.severity] || right.at.localeCompare(left.at),
  );
}

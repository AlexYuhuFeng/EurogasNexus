/**
 * Desk → Board → Calendar (Package G): what is coming for the five hubs, from where it is
 * published. Non-trading days and early closes (the desk's hand-maintained file: the exchanges'
 * terms forbid the product storing their calendars, so each such line says "hand-maintained"
 * and links the publisher's page), capacity auction windows and offer-level days (ENTSOG's
 * calendar as fetched, else the rule-derived dates, said so), reminders to check a calendar, and
 * a source that changed and needs a person. The source and its published/fetched times are on
 * demand (the source cell's tooltip and link), not on every line (UX rule 17: provenance on
 * demand).
 */
import { useMemo, useState } from "react";

import type { PublicationCalendarItemDTO } from "@/api/client";
import { BOARD_HUBS } from "@/app/model/traderBoardModel";
import { DataGrid, EmptyState, Instant, Segmented, StatusBadge, type DataGridColumn } from "@/components/ui";

type Translate = (key: string, options?: Record<string, unknown>) => string;

/** "in 3 d", "in 5 h", "today" or "2 d ago": how far away a calendar item is. */
export function dueWords(at: string, nowMs: number, t: Translate): string {
  const minutes = Math.round((Date.parse(at) - nowMs) / 60_000);
  if (!Number.isFinite(minutes)) return "";
  if (Math.abs(minutes) < 60) return t("calendar.due.now");
  if (minutes > 0) {
    return minutes < 48 * 60 ? t("calendar.due.in_h", { count: Math.round(minutes / 60) }) : t("calendar.due.in_d", { count: Math.round(minutes / 1440) });
  }
  return minutes > -48 * 60 ? t("calendar.due.ago_h", { count: Math.round(-minutes / 60) }) : t("calendar.due.ago_d", { count: Math.round(-minutes / 1440) });
}

/** The provenance line of an item (shown on demand). */
export function provenanceText(item: PublicationCalendarItemDTO, t: Translate, formatTime: (iso: string) => string): string {
  const source = item.source;
  const parts = [t(`calendar.basis.${source.basis}`, { publisher: source.publisher ?? "" })];
  if (source.published_at_utc) parts.push(t("calendar.published", { time: formatTime(source.published_at_utc) }));
  if (source.fetched_at_utc) parts.push(t("calendar.fetched", { time: formatTime(source.fetched_at_utc) }));
  if (source.basis === "hand_maintained") parts.push(source.checked ? t("calendar.checked") : t("calendar.not_checked"));
  if (source.attribution) parts.push(source.attribution);
  return parts.join(" · ");
}

type HubFilter = "all" | (typeof BOARD_HUBS)[number];

export interface PublicationCalendarProps {
  items: readonly PublicationCalendarItemDTO[] | null;
  nowMs: number;
  t: Translate;
  loading?: boolean;
  failed?: boolean;
  formatTime?: (iso: string) => string;
}

export function PublicationCalendar({ items, nowMs, t, loading = false, failed = false, formatTime = (iso) => iso }: PublicationCalendarProps) {
  const [hub, setHub] = useState<HubFilter>("all");
  const rows = useMemo(
    () => (items ?? []).filter((item) => hub === "all" || item.hubs.includes(hub) || item.hubs.length === 0),
    [items, hub],
  );
  const columns = useMemo<DataGridColumn<PublicationCalendarItemDTO>[]>(
    () => [
      {
        id: "at",
        header: t("calendar.when"),
        value: (item) => item.at,
        render: (item) => (
          <span className="trader-event-time">
            {item.day ? <span>{item.day}</span> : <Instant value={item.at} date="always" />}
            <span className="trader-muted">{dueWords(item.at, nowMs, t)}</span>
          </span>
        ),
      },
      {
        id: "what",
        header: t("calendar.what"),
        rowHeader: true,
        value: (item) => item.title,
        render: (item) => (
          <span className="trader-event-what">
            <span className="trader-event-kind" data-kind={item.kind}>{t(`calendar.kind.${item.kind}`)}</span>
            {", "}
            {item.title}
            {item.source.basis === "hand_maintained" ? <> <StatusBadge tone="neutral">{t("calendar.hand_maintained")}</StatusBadge></> : null}
            {item.source.basis === "rule_derived" ? <> <StatusBadge tone="neutral">{t("calendar.rule_derived")}</StatusBadge></> : null}
            {item.kind === "source_changed" || item.overdue ? <> <StatusBadge tone="watch">{t("calendar.needs_person")}</StatusBadge></> : null}
          </span>
        ),
      },
      {
        id: "hubs",
        header: t("board.events.hubs"),
        value: (item) => item.hubs.join(" "),
        render: (item) => <span className="trader-event-hubs">{BOARD_HUBS.filter((h) => item.hubs.includes(h)).join(" · ") || <span className="trader-muted">–</span>}</span>,
      },
      {
        id: "source",
        header: t("calendar.source"),
        value: (item) => item.source.publisher ?? "",
        render: (item) =>
          item.source.url ? (
            <a href={item.source.url} target="_blank" rel="noreferrer noopener">{item.source.publisher ?? t("calendar.open_source")}</a>
          ) : (
            <span>{item.source.publisher ?? t(`calendar.basis.${item.source.basis}`, { publisher: "" })}</span>
          ),
        cellTitle: (item) => provenanceText(item, t, formatTime),
      },
    ],
    [nowMs, t, formatTime],
  );
  if (loading && !items) return <EmptyState compact reason={t("board.loading")} />;
  if (failed && !items) return <EmptyState compact reason={t("calendar.failed")} />;
  return (
    <div className="trader-events" data-publication-calendar="">
      <Segmented
        label={t("calendar.hub_filter")}
        value={hub}
        onChange={(value) => setHub(value as HubFilter)}
        options={[{ value: "all", label: t("calendar.all_hubs") }, ...BOARD_HUBS.map((code) => ({ value: code, label: code }))]}
      />
      <DataGrid
        id="publication-calendar"
        label={t("calendar.title")}
        columns={columns}
        rows={rows}
        rowKey={(item) => item.key}
        density="compact"
        phoneLayout="scroll"
        empty={t("calendar.empty")}
        rowAttributes={(item) => ({ "data-calendar-kind": item.kind, "data-basis": item.source.basis })}
      />
      <p className="trader-foot">{t("calendar.foot")}</p>
    </div>
  );
}

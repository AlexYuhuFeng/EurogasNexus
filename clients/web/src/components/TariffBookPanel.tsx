/**
 * The tariff book (TAR-1) on Sources → Infrastructure: public tariffs per point or terminal,
 * each labelled indicative or final with the reason, its version trail, the source it was
 * read from, the upcoming capacity windows, and each publisher's read state.
 *
 * Indicative and final are never merged: the status badge says which, and a row's title says
 * why (the operator stated it, the period has not started, the figures disagree, a second
 * person has or has not reviewed it). Rule-derived auction dates say so.
 *
 * TAR-2: each row names its tariff year, and a newly recorded figure is marked new. Opening a
 * row also shows that facility's tariff book by tariff year: the indicative and the final
 * version side by side, each with its publication date (or that none is stated), record time
 * and source, and which one a valuation today uses (final once held).
 */
import { useCallback, useEffect, useMemo, useState } from "react";

import {
  api,
  type CapacityNoticeDTO,
  type TariffPublisherDTO,
  type TariffVersionDTO,
  type TariffYearDTO,
} from "@/api/client";
import { orderedYears, yearCells, type YearCell } from "@/app/model/capacityCostModel";
import {
  facilities,
  noticeTone,
  periodText,
  publisherOrder,
  publisherTone,
  statusTone,
  tariffFigure,
  versionTrail,
} from "@/app/model/tariffBookModel";
import { DataGrid, EmptyState, Instant, Panel, Select, Skeleton, StatusBadge, type DataGridColumn } from "@/components/ui";
import { PanelHelp } from "@/components/ui/PanelHelp";

type Translate = (key: string, options?: Record<string, unknown>) => string;

const ALL = "__all__";

function labelOr(t: Translate, key: string, raw: string): string {
  const label = t(key);
  return label === key ? raw : label;
}

function YearVersion({ cell, t }: { cell: YearCell; t: Translate }) {
  if (!cell.held) return <span className="tariff-book-muted">{t("tariffBook.years.not_held")}</span>;
  return (
    <div className="tariff-year-cell" data-used={cell.used ? "true" : undefined}>
      <strong>{cell.figure}</strong>
      <span>v{cell.version}</span>
      {cell.used && <StatusBadge tone={cell.status === "FINAL" ? "ok" : "watch"}>{t("tariffBook.years.used")}</StatusBadge>}
      {cell.isNew && <StatusBadge tone="info">{t("tariffBook.new")}</StatusBadge>}
      {cell.published ? (
        <Instant value={cell.published} prefix={t("tariffBook.years.published")} />
      ) : (
        <span className="tariff-book-muted">{t("tariffBook.years.no_published_date")}</span>
      )}
      <Instant value={cell.recorded} prefix={t("tariffBook.recorded")} />
      {cell.sourceUrl && <SourceLink url={cell.sourceUrl} t={t} />}
    </div>
  );
}

function SourceLink({ url, t }: { url: string; t: Translate }) {
  return (
    <a className="tariff-book-source" href={url} target="_blank" rel="noreferrer noopener">
      {t("tariffBook.source")}
    </a>
  );
}

export function TariffBookPanel({ t }: { t: Translate }) {
  const [rows, setRows] = useState<TariffVersionDTO[] | null>(null);
  const [notices, setNotices] = useState<CapacityNoticeDTO[] | null>(null);
  const [publishers, setPublishers] = useState<TariffPublisherDTO[] | null>(null);
  const [failed, setFailed] = useState(false);
  const [facility, setFacility] = useState<string>(ALL);
  const [selected, setSelected] = useState<TariffVersionDTO | null>(null);
  const [history, setHistory] = useState<TariffVersionDTO[] | null>(null);
  const [years, setYears] = useState<TariffYearDTO[] | null>(null);

  useEffect(() => {
    api
      .tariffBook()
      .then((response) => setRows(response.data.rows))
      .catch(() => setFailed(true));
    api
      .capacityNotices({ days: 120 })
      .then((response) => setNotices(response.data.rows))
      .catch(() => setNotices([]));
    api
      .tariffPublishers()
      .then((response) => setPublishers(response.data.rows))
      .catch(() => setPublishers([]));
  }, []);

  const openHistory = useCallback((row: TariffVersionDTO) => {
    setSelected(row);
    setHistory(null);
    api
      .tariffBook({ key: row.tariff_key, history: true })
      .then((response) => setHistory(response.data.rows))
      .catch(() => setHistory([]));
    setYears(null);
    api
      .tariffYears({ facility: row.facility_id })
      .then((response) => setYears(orderedYears(response.data.years)))
      .catch(() => setYears([]));
  }, []);

  const choices = useMemo(() => facilities(rows ?? []), [rows]);
  const shown = useMemo(
    () => (rows ?? []).filter((row) => facility === ALL || row.facility_id === facility),
    [rows, facility],
  );
  const now = useMemo(() => new Date(), []);

  const columns = useMemo<DataGridColumn<TariffVersionDTO>[]>(
    () => [
      { id: "facility", header: t("tariffBook.col.facility"), value: (row) => row.facility_name, rowHeader: true },
      { id: "operator", header: t("tariffBook.col.operator"), value: (row) => row.operator, priority: "secondary" },
      {
        id: "product",
        header: t("tariffBook.col.product"),
        value: (row) => [row.direction, row.product].filter(Boolean).join(" "),
      },
      { id: "figure", header: t("tariffBook.col.figure"), align: "end", value: (row) => row.value ?? 0, render: (row) => tariffFigure(row) },
      { id: "period", header: t("tariffBook.col.period"), value: (row) => row.period_from, render: (row) => periodText(row) },
      { id: "year", header: t("tariffBook.col.tariff_year"), value: (row) => row.tariff_year ?? "" },
      {
        id: "status",
        header: t("tariffBook.col.status"),
        value: (row) => row.status,
        render: (row) => (
          <StatusBadge
            tone={statusTone(row)}
            title={row.status_rule ?? labelOr(t, `tariffBook.basis.${row.status_basis}`, row.status_basis)}
          >
            {t(row.status === "FINAL" ? "tariffBook.status.final" : "tariffBook.status.indicative")}
            {row.new ? ` · ${t("tariffBook.new")}` : ""}
          </StatusBadge>
        ),
      },
      { id: "version", header: t("tariffBook.col.version"), align: "end", value: (row) => row.version, priority: "secondary" },
      {
        id: "read",
        header: t("tariffBook.col.read"),
        value: (row) => row.retrieved_at_utc,
        render: (row) => <Instant value={row.retrieved_at_utc} />,
        priority: "secondary",
      },
      { id: "source", header: t("tariffBook.col.source"), render: (row) => <SourceLink url={row.source_url} t={t} /> },
    ],
    [t],
  );

  const noticeColumns = useMemo<DataGridColumn<CapacityNoticeDTO>[]>(
    () => [
      {
        id: "opens",
        header: t("tariffBook.notice.opens"),
        value: (row) => row.opens_at_utc,
        render: (row) => <Instant value={row.opens_at_utc} />,
      },
      { id: "title", header: t("tariffBook.notice.title"), value: (row) => row.title, rowHeader: true },
      {
        id: "basis",
        header: t("tariffBook.notice.basis"),
        value: (row) => row.basis,
        render: (row) => (
          <StatusBadge tone={noticeTone(row, now)}>
            {t(row.basis === "rule_derived" ? "tariffBook.notice.rule_derived" : "tariffBook.notice.published")}
          </StatusBadge>
        ),
      },
      { id: "source", header: t("tariffBook.col.source"), render: (row) => <SourceLink url={row.source_url} t={t} /> },
    ],
    [t, now],
  );

  const publisherColumns = useMemo<DataGridColumn<TariffPublisherDTO>[]>(
    () => [
      { id: "name", header: t("tariffBook.publisher.name"), value: (row) => row.name, rowHeader: true },
      {
        id: "access",
        header: t("tariffBook.publisher.access"),
        value: (row) => row.access,
        render: (row) => labelOr(t, `tariffBook.access.${row.access}`, row.access),
      },
      {
        id: "state",
        header: t("tariffBook.publisher.state"),
        value: (row) => row.state,
        render: (row) => (
          <StatusBadge tone={publisherTone(row.state)} title={row.terms}>
            {labelOr(t, `tariffBook.state.${row.state}`, row.state)}
          </StatusBadge>
        ),
      },
      {
        id: "last",
        header: t("tariffBook.publisher.last_read"),
        value: (row) => row.last_read_at_utc ?? "",
        render: (row) => <Instant value={row.last_read_at_utc} fallback="—" />,
        priority: "secondary",
      },
    ],
    [t],
  );

  const trail = useMemo(() => versionTrail(history ?? []), [history]);

  return (
    <Panel title={t("tariffBook.title")} className="span-3 tariff-book">
      <PanelHelp text={t("tariffBook.copy")} label={t("panel.how_to_read")} />
      {failed && <EmptyState reason={t("tariffBook.unavailable")} compact />}
      {rows && rows.length === 0 && !failed && <EmptyState reason={t("tariffBook.empty")} compact />}
      {rows && rows.length > 0 && (
        <>
          <label className="tariff-book-filter">
            <span>{t("tariffBook.col.facility")}</span>
            <Select
              value={facility}
              onChange={setFacility}
              options={[
                { value: ALL, label: t("tariffBook.all_facilities") },
                ...choices.map((item) => ({
                  value: item.id,
                  label: `${item.name} (${item.final} ${t("tariffBook.status.final")}, ${item.indicative} ${t("tariffBook.status.indicative")})`,
                })),
              ]}
            />
          </label>
          <DataGrid
            label={t("tariffBook.title")}
            columns={columns}
            rows={shown}
            rowKey={(row) => row.version_id}
            onRowAction={openHistory}
            selectedKey={selected?.version_id ?? null}
            density="compact"
            maxHeight="24rem"
          />
        </>
      )}
      {selected && (
        <section className="tariff-book-trail" aria-label={t("tariffBook.history")}>
          <h3>
            {t("tariffBook.history")}: {selected.facility_name} {selected.direction ?? ""} {selected.product}
          </h3>
          {history === null ? (
            <Skeleton label={t("tariffBook.loading")} rows={3} variant="text" />
          ) : (
            <ol>
              {trail.map((step) => (
                <li key={step.version} data-current={step.current ? "true" : undefined}>
                  <strong>v{step.version}</strong>
                  <StatusBadge tone={step.status === "FINAL" ? "ok" : "watch"}>
                    {t(step.status === "FINAL" ? "tariffBook.status.final" : "tariffBook.status.indicative")}
                  </StatusBadge>
                  <span>{labelOr(t, `tariffBook.change.${step.change}`, step.change)}</span>
                  <span>{step.figure}</span>
                  <Instant value={step.recorded} prefix={t("tariffBook.recorded")} />
                </li>
              ))}
            </ol>
          )}
          <h3>{t("tariffBook.years.title")}</h3>
          {years === null ? (
            <p className="tariff-book-muted">{t("tariffBook.loading")}</p>
          ) : years.length === 0 ? (
            <p className="tariff-book-muted">{t("tariffBook.years.empty")}</p>
          ) : (
            <table className="tariff-years">
              <thead>
                <tr>
                  <th scope="col">{t("tariffBook.col.tariff_year")}</th>
                  <th scope="col">{t("tariffBook.col.product")}</th>
                  <th scope="col">{t("tariffBook.status.indicative")}</th>
                  <th scope="col">{t("tariffBook.status.final")}</th>
                </tr>
              </thead>
              <tbody>
                {years.map((year) => {
                  const [indicative, final] = yearCells(year);
                  return (
                    <tr key={`${year.tariff_year.label}:${year.direction ?? ""}:${year.product}:${year.operator}`}>
                      <th scope="row">{year.tariff_year.label}</th>
                      <td>{[year.direction, year.product].filter(Boolean).join(" ")}</td>
                      <td><YearVersion cell={indicative} t={t} /></td>
                      <td><YearVersion cell={final} t={t} /></td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          )}
        </section>
      )}
      <h3 className="tariff-book-subhead">{t("tariffBook.windows")}</h3>
      {notices && notices.length === 0 && <p className="tariff-book-muted">{t("tariffBook.windows_empty")}</p>}
      {notices && notices.length > 0 && (
        <DataGrid
          label={t("tariffBook.windows")}
          columns={noticeColumns}
          rows={notices}
          rowKey={(row) => row.notice_key}
          density="compact"
          maxHeight="18rem"
        />
      )}
      <details className="tariff-book-publishers">
        <summary>{t("tariffBook.publishers")}</summary>
        {publishers && (
          <DataGrid
            label={t("tariffBook.publishers")}
            columns={publisherColumns}
            rows={publisherOrder(publishers)}
            rowKey={(row) => row.publisher_id}
            density="compact"
          />
        )}
      </details>
    </Panel>
  );
}

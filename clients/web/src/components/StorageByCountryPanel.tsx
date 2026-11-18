/**
 * Storage by country (CP-04; design basis 2, D.2 and E.2): the region first, then each country,
 * against their own history. One server read (`GET /api/fundamentals/storage`), nothing
 * recomputed here.
 *
 * - The region's headline: fill, day change, against the same gas day last year and the
 *   N-year mean (N stated), stock, the EU target, and where today sits in the range.
 * - The seasonal chart of the region, or of the country selected in the table: this gas year
 *   in the accent, last year as a labelled grey ghost, the history band (or the years held as
 *   grey lines), the target as a rule; hover, touch and keyboard read every value.
 * - The countries as a compact sortable table: fill, day change, vs last year, vs the N-year
 *   mean, stock, a 30-day sparkline with its own readout. Choosing a row shows its chart.
 * - Countries not held are named, with the reason on hover. Simulated figures carry the mark.
 * - Phone (a narrow container): the chart becomes the headline and a sparkline; a tap opens
 *   the chart (F.2: no hover-only information).
 */
import { useSimulatedPills } from "@/components/SimulatedScope";
import { useEffect, useMemo, useState } from "react";

import "./storage-panel.css";

import { api, type FundamentalsStorageDTO, type StorageEntityDTO } from "@/api/client";
import { headline, seasonChart, seasonCodes, sparkOf, versusAverage } from "@/app/model/storageByCountry";
import { formatGasDay } from "@/app/time/timeFormat";
import { Button, DataGrid, EmptyState, Segmented, Skeleton, StatusBadge, type DataGridColumn } from "@/components/ui";
import { Chart, PercentileStrip, Sparkline, formatSigned, useContainerWidth } from "@/components/ui/charts";

type Translate = (key: string, options?: Record<string, unknown>) => string;
type Region = "eu" | "nwe";

const NARROW = 560;

function signed(value: number | null | undefined, decimals = 1): string {
  return value == null ? "–" : formatSigned(value, decimals);
}

function num(value: number | null | undefined, decimals = 1): string {
  return value == null ? "–" : value.toLocaleString("en-GB", { minimumFractionDigits: decimals, maximumFractionDigits: decimals });
}

function RegionFigures({ entity, t, language }: { entity: StorageEntityDTO; t: Translate; language: string }) {
  const pills = useSimulatedPills();
  const average = entity.vs_average;
  const target = entity.target;
  return (
    <dl className="storage-figures" data-figure-entity={entity.code}>
      <div>
        <dt>{t("storage_panel.fill")}</dt>
        <dd data-figure="fill_pct">
          {num(entity.fill_pct)} <small>%</small>
          {entity.simulated && pills && <StatusBadge tone="simulated" title={t("today.simulated_long")}>{t("today.simulated_short")}</StatusBadge>}
        </dd>
        <dd className="storage-figure-note">{t("storage_panel.gas_day", { day: formatGasDay(entity.as_of, language, true) })}</dd>
      </div>
      <div>
        <dt>{t("storage_panel.day_change")}</dt>
        <dd>{signed(entity.day_change_pts, 2)} <small>{t("storage_panel.pts")}</small></dd>
        <dd className="storage-figure-note">{signed(entity.day_change_twh, 2)} TWh</dd>
      </div>
      <div>
        <dt>{t("storage_panel.vs_last_year")}</dt>
        <dd>{signed(entity.vs_last_year.diff_pts)} <small>{t("storage_panel.pts")}</small></dd>
        <dd className="storage-figure-note">{t("storage_panel.last_year_was", { pct: num(entity.vs_last_year.fill_pct) })}</dd>
      </div>
      <div>
        <dt>{average.years ? t("storage_panel.vs_avg", { count: average.years }) : t("storage_panel.vs_avg_none")}</dt>
        <dd>{signed(average.diff_pts)} <small>{t("storage_panel.pts")}</small></dd>
        {average.range_position != null && average.low_pct != null && average.high_pct != null && entity.history.mode === "band" && (
          <dd>
            <PercentileStrip
              t={t}
              position={average.range_position}
              outside={average.outside}
              caption={t("storage_panel.range_position", { pct: Math.round(average.range_position) })}
              window={entity.history.label}
              lowLabel={`${num(average.low_pct)} %`}
              highLabel={`${num(average.high_pct)} %`}
            />
          </dd>
        )}
      </div>
      <div>
        <dt>{t("storage_panel.stock")}</dt>
        <dd>{num(entity.stock_twh, 1)} <small>TWh</small></dd>
        <dd className="storage-figure-note">{t("storage_panel.of_capacity", { twh: num(entity.working_capacity_twh, 1) })}</dd>
      </div>
      {target && (
        <div>
          <dt>{t("storage_panel.target", { pct: target.pct })}</dt>
          <dd>{signed(target.gap_pts)} <small>{t("storage_panel.pts")}</small></dd>
          <dd className="storage-figure-note">
            {target.days_to_target_at_7d_rate != null
              ? t("storage_panel.days_to_target", { days: target.days_to_target_at_7d_rate })
              : t("storage_panel.target_window", {
                  // "10-01" -> "1 Oct" through the shell's date formatter (any year: no year shown).
                  open: formatGasDay(`${entity.as_of.slice(0, 4)}-${target.window_open}`, language),
                  deadline: formatGasDay(`${entity.as_of.slice(0, 4)}-${target.deadline}`, language),
                })}
          </dd>
        </div>
      )}
    </dl>
  );
}

/**
 * `summary` (Today): the headline figures and the country table with its sparklines; the season
 * chart is one click away and the "not held" list stays on the full view (Today is the summary).
 */
export function StorageByCountryPanel({ t, language, summary = false }: { t: Translate; language: string; summary?: boolean }) {
  const [region, setRegion] = useState<Region>("eu");
  const [selected, setSelected] = useState<string | null>(null);
  const [data, setData] = useState<FundamentalsStorageDTO | null>(null);
  const [attribution, setAttribution] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [showChart, setShowChart] = useState(false);
  const [ref, width] = useContainerWidth<HTMLElement>();
  const narrow = width > 0 && width < NARROW;
  const regionCode = region === "eu" ? "EU" : "NWE";

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    api
      .fundamentalsStorage({ region, season: seasonCodes(regionCode, selected) }, { signal: controller.signal })
      .then((response) => {
        setData(response.data);
        setAttribution((response.meta as { attribution?: string | null } | undefined)?.attribution ?? null);
        setError(null);
      })
      .catch((caught: unknown) => {
        if (controller.signal.aborted) return;
        setError(caught instanceof Error ? caught.message : String(caught));
      })
      .finally(() => !controller.signal.aborted && setLoading(false));
    return () => controller.abort();
  }, [region, regionCode, selected]);

  const shown = useMemo(() => {
    if (!data) return null;
    if (selected) return data.countries.find((country) => country.code === selected) ?? data.region;
    return data.region;
  }, [data, selected]);

  const chart = useMemo(() => {
    if (!shown) return null;
    return seasonChart(
      shown,
      {
        lastYear: (year) => t("storage_panel.last_year", { year }),
        thisYear: (year) => year,
        mean: (count) => t("chart.history.mean", { count }),
        target: (pct) => t("storage_panel.target_rule", { pct }),
        xTitle: t("storage_panel.day_of_gas_year"),
      },
      shown.season?.band ? t("storage_panel.compare_mean", { count: shown.season.band.years.length }) : t("storage_panel.compare_last_year"),
    );
  }, [shown, t]);

  const avgWords = (count: number) => t("storage_panel.vs_avg_short", { count });
  const pills = useSimulatedPills();
  const columns = useMemo<DataGridColumn<StorageEntityDTO>[]>(() => [
    {
      id: "country",
      header: t("storage_panel.country"),
      rowHeader: true,
      sortable: true,
      priority: "primary",
      value: (row) => row.name,
      render: (row) => (
        <>
          {row.name} <small className="muted">{row.code}</small>
          {row.simulated && pills && <span className="ds-cell-mark" data-state="simulated" title={t("today.simulated_long")}> {t("today.simulated_short")}</span>}
        </>
      ),
    },
    { id: "fill", header: t("storage_panel.fill"), unit: "%", type: "number", sortable: true, priority: "primary", value: (row) => row.fill_pct, format: (value) => num(value as number | null) },
    { id: "day", header: t("storage_panel.day_change_short"), unit: t("storage_panel.pts"), type: "number", sortable: true, value: (row) => row.day_change_pts, format: (value) => signed(value as number | null, 2) },
    { id: "last-year", header: t("storage_panel.vs_last_year_short"), unit: t("storage_panel.pts"), type: "number", sortable: true, priority: "primary", value: (row) => row.vs_last_year.diff_pts, format: (value) => signed(value as number | null) },
    {
      id: "average",
      header: t("storage_panel.vs_avg_column"),
      unit: t("storage_panel.pts"),
      type: "number",
      sortable: true,
      value: (row) => row.vs_average.diff_pts,
      format: (value) => signed(value as number | null),
      cellTitle: (row) => row.vs_average.years ? `${t("storage_panel.vs_avg", { count: row.vs_average.years })} · ${row.history.label}` : row.history.label,
    },
    { id: "stock", header: t("storage_panel.stock"), unit: "TWh", type: "number", sortable: true, value: (row) => row.stock_twh, format: (value) => num(value as number | null, 1) },
    {
      id: "trend",
      header: t("storage_panel.trend"),
      decorative: false,
      width: "120px",
      render: (row) => {
        const spark = sparkOf(row);
        return (
          <Sparkline values={spark.values} days={spark.days} label={t("storage_panel.spark_label", { name: row.name })} unit="%" decimals={1} simulated={row.simulated} height={20} t={t} />
        );
      },
    },
  ], [t, pills]);

  if (!data) {
    return (
      <section className="storage-panel" ref={ref} data-storage-panel="loading" aria-label={t("storage_panel.title")}>
        {error ? <EmptyState compact reason={t("storage_panel.failed")} next={error} /> : <Skeleton label={t("storage_panel.loading")} rows={4} />}
      </section>
    );
  }
  const regionEntity = data.region;
  const subject = shown ?? regionEntity;
  return (
    <section
      className={`storage-panel${narrow ? " is-narrow" : ""}`}
      ref={ref}
      aria-labelledby="storage-panel-title"
      data-storage-panel={data.simulated ? "simulated" : "provider"}
      data-storage-region={regionCode}
      data-storage-selected={selected ?? regionCode}
      aria-busy={loading || undefined}
    >
      <header className="storage-panel-head">
        <h3 id="storage-panel-title">{t("storage_panel.title")}</h3>
        <Segmented
          label={t("storage_panel.region")}
          options={[
            { value: "eu", label: t("storage_panel.region_eu") },
            { value: "nwe", label: t("storage_panel.region_nwe") },
          ]}
          value={region}
          onChange={(value) => {
            setSelected(null);
            setRegion(value as Region);
          }}
        />
      </header>
      {regionEntity ? (
        <RegionFigures entity={regionEntity} t={t} language={language} />
      ) : (
        <EmptyState compact reason={data.warnings[0] ?? t("storage_panel.no_region")} />
      )}
      {subject && chart && ((narrow || summary) && !showChart ? (
        <div className="storage-panel-phone">
          <span className="storage-panel-headline">
            <strong>{subject.name}</strong> {headline(subject, avgWords, t("storage_panel.per_day"))}
          </span>
          <Sparkline {...sparkOf(subject)} label={t("storage_panel.spark_label", { name: subject.name })} unit="%" decimals={1} simulated={subject.simulated} t={t} onOpen={() => setShowChart(true)} />
          <Button variant="quiet" onClick={() => setShowChart(true)}>{t("storage_panel.open_chart")}</Button>
        </div>
      ) : (
        <Chart
          id="storage-season"
          title={t("storage_panel.chart_title", { name: subject.name })}
          data={chart.data}
          subtitle={chart.subtitle}
          compare={chart.compare}
          t={t}
          height={narrow ? 200 : 260}
          simulated={subject.simulated}
          asOf={subject.as_of}
          controls={selected ? (
            <button type="button" className="ds-inline-link" onClick={() => setSelected(null)} data-storage-back="region">
              {t("storage_panel.back_to_region", { name: regionEntity?.name ?? regionCode })}
            </button>
          ) : undefined}
          note={[
            subject.definition ?? null,
            versusAverage(subject, avgWords) ? null : subject.history.label,
            attribution && !subject.simulated ? attribution : null,
          ].filter(Boolean).join(" · ") || undefined}
        />
      ))}
      <DataGrid
        id="storage-countries"
        label={t("storage_panel.countries")}
        columns={columns}
        rows={data.countries}
        rowKey={(row) => row.code}
        density="compact"
        selectedKey={selected}
        onRowAction={(row) => {
          setShowChart(true);
          setSelected(selected === row.code ? null : row.code);
        }}
        rowAttributes={(row) => ({ "data-storage-country": row.code, "data-simulated": row.simulated ? "true" : undefined })}
        caption={t("storage_panel.table_caption")}
      />
      {!summary && data.missing.length > 0 && (
        <p className="storage-panel-missing" data-storage-missing={data.missing.length}>
          {t("storage_panel.missing")}{" "}
          {data.missing.map((item, index) => (
            <span key={item.code} title={item.reason}>
              {index ? ", " : ""}
              <abbr title={item.reason}>{item.code}</abbr>
            </span>
          ))}
        </p>
      )}
    </section>
  );
}

import { useMemo, useState } from "react";
import { readKey, useCachedRead } from "@/app/data/readCache";

import { api, type DeliveryPerformanceDTO, type DeliveryPerformanceRowDTO } from "@/api/client";
import { ReportExport } from "./ReportExport";
import { DataGrid, Field, Select, type DataGridColumn } from "@/components/ui";
import { AlignedPanels, type ChartData } from "@/components/ui/charts";
import { formatMeasure } from "@/app/time/valueFormat";
import { serverWarningText } from "@/app/warningLabel";

type Translate = (key: string, options?: Record<string, unknown>) => string;

const WINDOWS = [30, 90, 365];

/** A volume in the column's unit (the unit is in the header). */
function qty(value: number | null | undefined): string {
  return value == null || !Number.isFinite(value) ? "–" : Math.round(value).toLocaleString("en-GB");
}

/**
 * Bilateral supply as it actually flowed: allocations against nominations and DCQ, per
 * contract. The trader sees which seller under-delivers, how volatile a field is, and the
 * imbalance the desk had to cover at the hub; selecting a contract shows its gas days.
 */
export function DeliveryPerformancePanel({ t }: { t: Translate }) {
  const [days, setDays] = useState(90);
  const [selected, setSelected] = useState<string | null>(null);
  // Kept across task switches (app/data/readCache.ts): the last answer shows at once.
  const read = useCachedRead(readKey("/portfolio/delivery-performance", { days }), (signal) =>
    api.deliveryPerformance(days, undefined, { signal }).then((response) => response.data),
  );
  const detailRead = useCachedRead(
    selected ? readKey("/portfolio/delivery-performance", { days, contract: selected }) : null,
    (signal) => api.deliveryPerformance(days, selected ?? undefined, { signal }).then((response) => response.data),
  );
  const data: DeliveryPerformanceDTO | null = read.data ?? null;
  const detail: DeliveryPerformanceDTO | null = selected ? detailRead.data ?? null : null;

  const columns = useMemo<DataGridColumn<DeliveryPerformanceRowDTO>[]>(() => [
    {
      id: "contract",
      header: t("delivery.contract"),
      rowHeader: true,
      sortable: true,
      value: (row) => row.contract,
      render: (row) => (
        <>
          {row.contract} <small className="muted">{[row.hub, row.tso].filter(Boolean).join(" · ")}</small>
        </>
      ),
    },
    { id: "dcq", header: t("delivery.dcq"), unit: "MWh/d", type: "number", sortable: true, value: (row) => row.dcq_mwh_d, format: (value) => qty(value as number) },
    { id: "mean", header: t("delivery.mean_allocated"), unit: "MWh/d", type: "number", sortable: true, value: (row) => row.mean_allocated_mwh_d, format: (value) => (value == null ? "–" : qty(value as number)) },
    { id: "deviation", header: t("delivery.net_deviation"), unit: "MWh", type: "number", sortable: true, value: (row) => row.net_deviation_mwh, format: (value) => qty(value as number) },
    { id: "imbalance", header: t("delivery.imbalance"), unit: "MWh", type: "number", sortable: true, value: (row) => row.imbalance_mwh, format: (value) => qty(value as number) },
    { id: "short-long", header: t("delivery.short_long"), type: "number", value: (row) => row.short_days, render: (row) => `${row.short_days} / ${row.long_days}` },
    { id: "cv", header: t("delivery.cv"), unit: "%", type: "number", sortable: true, value: (row) => row.cv_pct, format: (value) => formatMeasure("percent", value as number | null, { bare: true }) },
    {
      id: "trend",
      header: t("delivery.trend"),
      unit: "%",
      type: "number",
      sortable: true,
      value: (row) => row.trend_7d_vs_dcq_pct,
      format: (value) => formatMeasure("percent_change", value as number | null, { bare: true }),
    },
    {
      id: "flags",
      header: t("delivery.flags"),
      value: (row) => row.status,
      render: (row) => (
        <>
          <span className="limit-badge" data-status={row.status}>{t(`delivery.status_${row.status}`)}</span>
          {row.flags && <span className="limit-breaches" title={row.flags}> {(row.flag_notes?.length ? row.flag_notes : row.flags.split(/;\s+/)).map((flag) => serverWarningText(flag, t)).join("; ")}</span>}
          {row.missing_days > 0 && <small> {t("delivery.missing", { count: row.missing_days })}</small>}
        </>
      ),
    },
  ], [t]);

  // The selected contract's gas days: nominated and allocated against the DCQ, and beneath it,
  // on the same days, the signed difference (allocated minus nominated: below zero is short).
  const chart = useMemo<ChartData | null>(() => {
    if (!detail || detail.series.length === 0) return null;
    const series = detail.series;
    return {
      axis: "gas-day",
      x: series.map((day) => day.gas_day),
      xTitle: t("chart.gas_day"),
      unit: "MWh",
      series: [
        { id: "nominated", label: t("delivery.nominated"), values: series.map((day) => day.nominated_mwh), style: "bar", colour: 8, decimals: 0 },
        { id: "allocated", label: t("delivery.allocated"), values: series.map((day) => day.allocated_mwh), style: "step", colour: 1, decimals: 0 },
        { id: "dcq", label: t("delivery.dcq"), values: series.map((day) => day.dcq_mwh), reference: true, decimals: 0 },
      ],
    };
  }, [detail, t]);
  const shortfall = useMemo<ChartData | null>(() => {
    if (!detail || detail.series.length === 0) return null;
    const series = detail.series;
    return {
      axis: "gas-day",
      x: series.map((day) => day.gas_day),
      xTitle: t("chart.gas_day"),
      unit: "MWh",
      series: [{
        id: "deviation",
        label: t("delivery.deviation_series"),
        values: series.map((day) => (day.allocated_mwh == null || day.nominated_mwh == null ? null : day.allocated_mwh - day.nominated_mwh)),
        colour: 1,
        decimals: 0,
      }],
      rules: [{ id: "zero", value: 0, kind: "zero" }],
    };
  }, [detail, t]);
  const contractName = data?.rows.find((row) => row.contract_id === selected)?.contract ?? selected ?? "";

  return (
    <section className="workspace-panel span-3 delivery-panel" aria-labelledby="delivery-title">
      <div className="panel-title-row">
        <h2 id="delivery-title">{t("delivery.title")}</h2>
        <Field inline label={t("delivery.window")}>
          <Select value={String(days)} onChange={(value) => setDays(Number(value))} options={WINDOWS.map((value) => ({ value: String(value), label: t("delivery.days", { count: value }) }))} />
        </Field>
        <ReportExport t={t} path="/contracts/delivery-performance" params={{ days: String(days) }} />
      </div>
      {data && data.rows.length === 0 && <p className="muted">{t("delivery.empty")}</p>}
      {data && data.rows.length > 0 && (
        <DataGrid
          id="delivery-performance"
          label={t("delivery.title")}
          columns={columns}
          rows={data.rows}
          rowKey={(row) => row.contract_id}
          density="compact"
          selectedKey={selected}
          onRowAction={(row) => setSelected(selected === row.contract_id ? null : row.contract_id)}
          rowAttributes={(row) => ({ "data-status": row.status, "data-record": "delivery-contract" })}
          tableAttributes={{ "data-delivery-performance": "true" }}
        />
      )}
      {chart && shortfall && (
        <AlignedPanels
          id="delivery-days"
          title={t("delivery.strip_label", { contract: contractName })}
          t={t}
          panels={[
            { id: "volumes", title: t("delivery.volumes_panel"), data: chart, height: 180 },
            { id: "deviation", title: t("delivery.deviation_panel"), data: shortfall, height: 100 },
          ]}
          controls={<ReportExport t={t} path="/contracts/delivery-performance" params={{ days: String(days), contract_id: selected ?? "" }} />}
        />
      )}
    </section>
  );
}

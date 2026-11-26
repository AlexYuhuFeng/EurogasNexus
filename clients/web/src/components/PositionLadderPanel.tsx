import { useEffect, useMemo, useState } from "react";

import { api, type LadderRollupDTO, type PositionLadderDTO, type PositionLadderRowDTO } from "@/api/client";
import { hubCurrency } from "@/app/contractChoices";
import { ReportExport } from "./ReportExport";
import { MethodNote } from "./MethodNote";
import { MarksAsOf, marksRowAttributes } from "./MarksAsOf";
import { DataGrid, EmptyState, ExampleFrame, Field, Fold, KeyFigure, Segmented, Select, Skeleton, Toolbar, useExampleView, type DataGridColumn } from "@/components/ui";
import { examplePositionLadder } from "@/app/experience/examples";
import {
  barShare,
  cargoTitle,
  groupLadderByMonth,
  ladderMonthLabel,
  overallHedgeRatio,
} from "@/app/model/positionLadderModel";
import { pnlClass } from "@/app/model/pnlColor";
import { ladderNotes } from "@/app/model/ladderNotes";
import { unitLabel } from "@/app/model/instrumentPicker";
import { formatMeasure } from "@/app/time/valueFormat";

type Translate = (key: string, options?: Record<string, unknown>) => string;

function mwh(value: number | null | undefined): string {
  if (value == null || !Number.isFinite(value)) return "–";
  const rounded = Math.round(value);
  // A position reads by its sign (+ long, − short), never by a gain/loss colour.
  const sign = rounded > 0 ? "+" : rounded < 0 ? "−" : "";
  return `${sign}${Math.abs(rounded).toLocaleString("en-GB")}`;
}

function money(value: number | null | undefined): string {
  if (value == null || !Number.isFinite(value)) return "–";
  return Math.round(value).toLocaleString("en-GB");
}

function price(value: number | null | undefined): string {
  return formatMeasure("price", value);
}

function percent(value: number | null | undefined): string {
  return value == null || !Number.isFinite(value) ? "–" : `${Math.round(value * 100) + 0}%`;
}

function hedgeText(ratio: number | null | undefined, t: Translate): string {
  return ratio != null && Number.isFinite(ratio) && Math.round(ratio * 100) < 0
    ? t("position.hedge_adds", { pct: percent(-ratio) })
    : percent(ratio);
}

/**
 * The hedge figure. A negative ratio means the trades point the same way as the physical
 * position (bought on top of a long), so they add risk instead of hedging it: shown as
 * "adds N%", flagged, never as a negative hedge.
 */
function HedgeValue({ ratio, t }: { ratio: number | null | undefined; t: Translate }) {
  if (ratio != null && Number.isFinite(ratio) && Math.round(ratio * 100) < 0) {
    return (
      <span className="warning-text" title={t("position.hedge_adds_hint")}>
        {t("position.hedge_adds", { pct: percent(-ratio) })}
      </span>
    );
  }
  return <>{percent(ratio)}</>;
}

const signClass = (value: number) => (value >= 0 ? "is-long" : "is-short");

function useLadder(months: number, groupBy = "hub", reportingCurrency = "") {
  const [ladder, setLadder] = useState<PositionLadderDTO | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    let live = true;
    api
      .positionLadder(months, undefined, { groupBy, reportingCurrency: reportingCurrency || undefined })
      .then((response) => live && setLadder(response.data))
      .catch((caught: unknown) => live && setError(caught instanceof Error ? caught.message : String(caught)));
    return () => {
      live = false;
    };
  }, [months, groupBy, reportingCurrency]);
  return { ladder, error };
}

function SummaryStrip({ ladder, t }: { ladder: PositionLadderDTO; t: Translate }) {
  return (
    <div className="position-summary" data-position-summary="true">
      <KeyFigure label={t("position.net")} value={mwh(ladder.totals.net_mwh)} unit="MWh" />
      {/* The label already names the unit ("Physical (MWh)"). */}
      <KeyFigure label={t("position.physical")} value={mwh(ladder.totals.physical_mwh)} />
      <KeyFigure label={t("position.financial")} value={mwh(ladder.totals.financial_mwh)} />
      <KeyFigure label={t("position.hedged")} value={hedgeText(overallHedgeRatio(ladder), t)} />
      {/* Mark-to-market is a value of the open book, not a gain: it is not coloured as P&L. */}
      <KeyFigure
        label={t("position.mtm")}
        value={money(ladder.mark_to_market)}
        unit={ladder.reporting_currency || undefined}
        notes={
          <>
            <MethodNote method={ladder.methods?.mark_to_market} subject={t("position.mtm")} t={t} />
            {/* QA-R-07: the marks' day under the value; late or stale in words. */}
            <MarksAsOf row={{ marks_as_of: ladder.marks_as_of, state: ladder.marks_state }} t={t} />
          </>
        }
      />
      {/* Gross by month adds information only when months offset; equal to |net| it repeats it. */}
      {ladder.totals.gross_tenor_mwh !== undefined &&
        Math.abs(ladder.totals.gross_tenor_mwh) !== Math.abs(ladder.totals.net_mwh) && (
        <KeyFigure
          label={t("position.gross_tenor")}
          value={mwh(ladder.totals.gross_tenor_mwh)}
          unit="MWh"
          title={t("position.gross_tenor_help")}
        />
      )}
      {ladder.offsetting_hubs && ladder.offsetting_hubs.length > 0 ? (
        // A calendar spread is never shown as zero risk (#53).
        <KeyFigure
          label={t("position.var")}
          value={t("position.var_withheld").replace("{{hubs}}", ladder.offsetting_hubs.join(", "))}
          valueClassName="position-var-withheld"
          title={t("position.var_withheld_help")}
          notes={<MethodNote method={ladder.methods?.var_95_1d} subject={t("position.var")} t={t} />}
        />
      ) : (
        <KeyFigure
          label={t("position.var")}
          value={money(ladder.var_95_1d)}
          unit={ladder.var_95_1d == null ? undefined : ladder.reporting_currency || undefined}
          title={ladder.var_95_1d == null ? undefined : t("position.var_help", { count: ladder.var_observations })}
          notes={<MethodNote method={ladder.methods?.var_95_1d} subject={t("position.var")} t={t} />}
        />
      )}
    </div>
  );
}

/**
 * Physical supply and sales next to screen hedges, by delivery month and hub: how long or short
 * the desk is, where, when, and how much of it is hedged.
 */
export function PositionLadderPanel({ t }: { t: Translate }) {
  const [months, setMonths] = useState(12);
  const [groupBy, setGroupBy] = useState("hub");
  const [currency, setCurrency] = useState("");
  const { ladder: held, error } = useLadder(months, groupBy, currency);
  // "See an example" (design H.1): a book with no position can look at a bundled example ladder,
  // drawn by the same grid and figures, inert and labelled.
  const exampleView = useExampleView();
  const example = useMemo(() => (exampleView.example ? examplePositionLadder() : null), [exampleView.example]);
  const ladder = example ?? held;
  const rows = useMemo(
    () => groupLadderByMonth(ladder?.rows ?? []).flatMap((month) => month.rows),
    [ladder],
  );
  const rollupColumns = useRollupColumns(ladder, groupBy, t);
  const ladderColumns = useLadderColumns(ladder, t);

  return (
    <section className="workspace-panel span-3 position-ladder-panel" aria-labelledby="position-ladder-title">
      <div className="panel-title-row">
        <h2 id="position-ladder-title">{t("position.title")}</h2>
        <Toolbar
          label={t("position.title")}
          className="position-toolbar"
          end={
            <ReportExport t={t}
              path="/portfolio/position-ladder"
              params={{
                months: String(months),
                  ...(groupBy !== "hub" ? { group_by: groupBy } : {}),
                  ...(currency ? { reporting_currency: currency } : {}),
              }}
            />
          }
        >
          <Field inline label={t("position.horizon")}>
            <Select
              value={String(months)}
              onChange={(value) => setMonths(Number(value))}
              options={[3, 6, 12, 24].map((value) => ({ value: String(value), label: t("position.months", { count: value }) }))}
            />
          </Field>
          <Field inline label={t("position.group_by")}>
            <Select
              value={groupBy}
              onChange={setGroupBy}
              options={["hub", "firm", "legal_entity", "region", "business", "book"].map((value) => ({ value, label: t(`position.level_${value}`) }))}
            />
          </Field>
          <Field inline label={t("position.reporting_currency")}>
            <Select
              value={currency}
              onChange={setCurrency}
              options={[{ value: "", label: t("position.currency_auto") }, ...["EUR", "GBP", "USD", "CAD"].map((value) => ({ value, label: value }))]}
            />
          </Field>
        </Toolbar>
      </div>
      {error && <p role="alert">{error}</p>}
      {ladder?.rollup && ladder.rollup.length > 0 && (
        <DataGrid
          id="position-rollup"
          label={t(`position.level_${ladder.group_by ?? groupBy}`)}
          columns={rollupColumns}
          rows={ladder.rollup}
          rowKey={(row) => row.group}
          density="compact"
          rowAttributes={() => ({ "data-record": "position-rollup-row" })}
          tableAttributes={{ "data-position-rollup": "true" }}
        />
      )}
      {!ladder && !error && <Skeleton label={t("position.loading")} rows={6} />}
      {ladder && ladder.rows.length === 0 && <EmptyState reason={t("position.empty")} id="position-ladder" onSeeExample={exampleView.show} />}
      {example && (
        <ExampleFrame page="position" onLeave={exampleView.leave}>
          <SummaryStrip ladder={example} t={t} />
          <DataGrid
            id="position-ladder-example"
            label={t("position.title")}
            columns={ladderColumns}
            rows={rows}
            rowKey={(row) => `${row.month}-${row.hub}`}
            density="compact"
          />
        </ExampleFrame>
      )}
      {!example && ladder && ladder.rows.length > 0 && (
        <>
          <SummaryStrip ladder={ladder} t={t} />
          <DataGrid
            id="position-ladder"
            label={t("position.title")}
            columns={ladderColumns}
            rows={rows}
            rowKey={(row) => `${row.month}-${row.hub}`}
            density="compact"
            maxHeight="min(70vh, 720px)"
            rowAttributes={(row) => ({ "data-record": "position-row", ...marksRowAttributes(row) })}
            tableAttributes={{ "data-position-ladder": "true" }}
          />
          <TenorShockScenario ladder={ladder} months={months} currency={currency} t={t} />
          <ul className="position-notes">
            {ladderNotes(ladder, t).map((note) => <li key={note}>{note}</li>)}
          </ul>
        </>
      )}
    </section>
  );
}

function useRollupColumns(ladder: PositionLadderDTO | null, groupBy: string, t: Translate) {
  return useMemo<DataGridColumn<LadderRollupDTO>[]>(
    () => [
      {
        id: "group",
        header: t(`position.level_${ladder?.group_by ?? groupBy}`),
        rowHeader: true,
        sortable: true,
        value: (row) => row.group,
        format: (value) => (value === "UNASSIGNED" ? t("position.unassigned") : String(value)),
      },
      { id: "physical", header: t("position.physical"), type: "number", sortable: true, value: (row) => row.physical_mwh, format: (value) => mwh(value as number) },
      { id: "financial", header: t("position.financial"), type: "number", sortable: true, value: (row) => row.financial_mwh, format: (value) => mwh(value as number) },
      { id: "net", header: t("position.net"), unit: "MWh", type: "number", sortable: true, value: (row) => row.net_mwh, format: (value) => mwh(value as number), cellClassName: (row) => signClass(row.net_mwh) },
      { id: "hedged", header: t("position.hedged"), type: "number", sortable: true, value: (row) => row.hedge_ratio, render: (row) => <HedgeValue ratio={row.hedge_ratio} t={t} /> },
      { id: "mtm", header: t("position.mtm"), unit: ladder?.reporting_currency || undefined, type: "number", sortable: true, value: (row) => row.mark_to_market, format: (value) => money(value as number) },
    ],
    [ladder, groupBy, t],
  );
}

function useLadderColumns(ladder: PositionLadderDTO | null, t: Translate) {
  return useMemo<DataGridColumn<PositionLadderRowDTO>[]>(() => {
    const all = ladder?.rows ?? [];
    return [
      { id: "month", header: t("position.month"), rowHeader: true, span: true, sortable: true, value: (row) => row.month, format: (value) => ladderMonthLabel(String(value)) },
      { id: "hub", header: t("position.hub"), sortable: true, value: (row) => row.hub },
      { id: "physical", header: t("position.physical"), type: "number", sortable: true, value: (row) => row.physical_mwh, format: (value) => mwh(value as number), cellTitle: (row) => cargoTitle(row, t, mwh), cellAttributes: (row) => ({ "data-cargoes": row.cargoes?.map((cargo) => cargo.cargo_id).join(" ") || undefined }) },
      { id: "financial", header: t("position.financial"), type: "number", sortable: true, value: (row) => row.financial_mwh, format: (value) => mwh(value as number), cellTitle: (row) => cargoTitle(row, t, mwh) },
      { id: "net", header: t("position.net"), unit: "MWh", type: "number", sortable: true, value: (row) => row.net_mwh, format: (value) => mwh(value as number), cellClassName: (row) => signClass(row.net_mwh) },
      {
        id: "bar",
        header: <span className="ds-visually-hidden">{t("position.net_bar")}</span>,
        decorative: true,
        width: "120px",
        cellClassName: () => "ds-grid-bar-cell",
        render: (row) => (
          <span className="ds-grid-bar">
            <span className={signClass(row.net_mwh)} style={{ width: `${barShare(row.net_mwh, all) * 50}%` }} />
          </span>
        ),
      },
      { id: "hedged", header: t("position.hedged"), type: "number", sortable: true, value: (row) => row.hedge_ratio, render: (row) => <HedgeValue ratio={row.hedge_ratio} t={t} /> },
      {
        id: "mark",
        header: t("position.mark"),
        type: "number",
        value: (row) => row.mark_quote ?? row.mark,
        // Shown as the desk quotes the hub (NBP in GBp/th, rule 17); the unit differs by row and
        // is in the cell. The per-MWh value the book is valued at is on demand in the title.
        render: (row) => {
          if (row.mark == null) return "–";
          const quoted = row.mark_quote != null && row.mark_quote_unit;
          return (
            <>
              {price(quoted ? row.mark_quote : row.mark)}{" "}
              <small className="ds-grid-unit">{quoted ? row.mark_quote_unit : (row.mark_unit ?? `${hubCurrency(row.hub) ?? ""}/MWh`)}</small>
            </>
          );
        },
        cellTitle: (row) => {
          const parts = row.mark_method ? [t(`position.mark_${row.mark_method}`)] : [];
          const perMwhUnit = row.mark_unit ?? `${hubCurrency(row.hub) ?? ""}/MWh`;
          if (row.mark != null && row.mark_quote_unit && row.mark_quote_unit !== perMwhUnit) {
            parts.push(t("today.book.mark_per_mwh", { value: price(row.mark), unit: perMwhUnit }));
          }
          return parts.length ? parts.join(" · ") : undefined;
        },
        cellAttributes: (row) => ({ "data-mark-method": row.mark_method ?? undefined }),
      },
      {
        // QA-R-07: the day the row's marks were closed; late or stale in words, the row greyed.
        id: "marks_as_of",
        header: t("risk.marks.column"),
        value: (row) => row.marks_as_of ?? "",
        render: (row) => <MarksAsOf row={row} t={t} />,
      },
    ];
  }, [ladder, t]);
}

/** One move for every hub, per MWh in the hub's quote currency: the usual first question. */
const SHOCK_PRESETS = ["-5", "-2", "-1", "1", "2", "5"] as const;

/**
 * A price shock applied to the open position (#53). It opens on one move per hub (or a preset for
 * every hub); "By month" folds out the per-month grid, prefilled from the hub's move, so a
 * calendar spread that is flat at the hub can still show the loss a curve twist causes. Months
 * held without a shock are listed, never assumed to move by zero silently.
 */
function TenorShockScenario({
  ladder,
  months,
  currency,
  t,
}: {
  ladder: PositionLadderDTO;
  months: number;
  currency: string;
  t: Translate;
}) {
  const keys = useMemo(
    () => ladder.rows.filter((row) => Math.abs(row.net_mwh) > 1e-9).map((row) => `${row.hub}:${row.month}`),
    [ladder],
  );
  const hubs = useMemo(() => [...new Set(keys.map((key) => key.split(":")[0] ?? ""))].filter(Boolean), [keys]);
  const [hubShift, setHubShift] = useState<Record<string, string>>({});
  const [overrides, setOverrides] = useState<Record<string, string>>({});
  const [preset, setPreset] = useState<string | null>(null);
  const [result, setResult] = useState<PositionLadderDTO["scenario"]>(null);
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<string | null>(null);
  if (keys.length === 0) return null;
  // A shock is entered as the desk quotes the hub (NBP in p/th, AGENTS rule 17). The unit is
  // the one the server quotes the hub's marks in (`mark_quote_unit`, from the unit authority);
  // the server converts it, so no factor lives here.
  const quoteUnit = (hub: string) =>
    ladder.rows.find((row) => row.hub === hub && row.mark_quote_unit)?.mark_quote_unit ?? `${hubCurrency(hub) ?? ""}/MWh`;
  const unit = (hub: string) => unitLabel(quoteUnit(hub));
  const effective = (key: string) => {
    const own = overrides[key];
    return own !== undefined && own.trim() !== "" ? own : hubShift[key.split(":")[0] ?? ""] ?? "";
  };
  const shocks = keys
    .map((key) => [key, effective(key)] as const)
    .filter(([, value]) => value.trim() !== "" && Number.isFinite(Number(value)));
  const run = async () => {
    if (shocks.length === 0) return;
    setBusy(true);
    setFailure(null);
    try {
      const response = await api.positionLadder(months, undefined, {
        reportingCurrency: currency || undefined,
        shocks: shocks.map(([key, value]) => `${key}:${Number(value)}:${quoteUnit(key.split(":")[0] ?? "")}`),
      });
      setResult(response.data.scenario ?? null);
    } catch (caught) {
      setFailure(caught instanceof Error ? caught.message : String(caught));
    } finally {
      setBusy(false);
    }
  };
  const monthKey = (key: string) => {
    // "NBP:2026-11" here, "NBP 2026-11" in the scenario's unshocked list.
    const [hub, month] = key.split(/[: ]/);
    return `${hub} ${ladderMonthLabel(month ?? "")}`;
  };
  return (
    <Fold className="position-scenario" data-position-scenario="true" summary={t("position.scenario_title")}>
      <p className="muted">{t("position.scenario_help")}</p>
      <Toolbar label={t("position.scenario_title")} className="position-scenario-shift">
        <Segmented
          label={t("position.scenario_presets")}
          options={SHOCK_PRESETS.map((value) => ({ value, label: Number(value) > 0 ? `+${value}` : `−${value.slice(1)}` }))}
          value={preset as (typeof SHOCK_PRESETS)[number] | null}
          onChange={(value) => {
            setPreset(value);
            setHubShift(Object.fromEntries(hubs.map((hub) => [hub, value])));
            setOverrides({});
          }}
        />
        {hubs.map((hub) => (
          <Field key={hub} inline label={`${hub} ${unit(hub)}`}>
            <input
              type="number"
              step="0.01"
              inputMode="decimal"
              value={hubShift[hub] ?? ""}
              placeholder="0.00"
              data-shock-hub={hub}
              onChange={(event) => {
                setPreset(null);
                setHubShift((current) => ({ ...current, [hub]: event.target.value }));
              }}
            />
          </Field>
        ))}
        <button type="button" disabled={busy || shocks.length === 0} onClick={() => void run()}>{t("position.scenario_run")}</button>
      </Toolbar>
      <Fold quiet className="position-scenario-months" summary={t("position.scenario_by_month", { count: keys.length })}>
        <div className="position-scenario-grid">
          {keys.map((key) => (
            <label key={key}>
              <span>{monthKey(key)}</span>
              <input
                type="number"
                step="0.01"
                inputMode="decimal"
                value={overrides[key] ?? ""}
                placeholder={hubShift[key.split(":")[0] ?? ""] || "0.00"}
                onChange={(event) => {
                  setPreset(null);
                  setOverrides((current) => ({ ...current, [key]: event.target.value }));
                }}
              />
            </label>
          ))}
        </div>
      </Fold>
      {failure && <p role="alert">{failure}</p>}
      {result && (
        <div className="position-scenario-result" role="status">
          <strong className={pnlClass(result.pnl)}>
            {t("position.scenario_pnl")}: {money(result.pnl)} {ladder.reporting_currency ?? ""}
          </strong>
          {result.unshocked.length > 0 && (
            <small className="muted">{t("position.scenario_unshocked")}: {result.unshocked.map(monthKey).join(", ")}</small>
          )}
          {result.excluded_no_fx.length > 0 && (
            <small className="muted">{t("position.scenario_no_fx")}: {result.excluded_no_fx.join(", ")}</small>
          )}
        </div>
      )}
    </Fold>
  );
}

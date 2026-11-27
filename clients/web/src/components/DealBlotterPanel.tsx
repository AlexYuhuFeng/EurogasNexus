import { useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";

import { api, type DealBlotterDTO, type DealRowDTO } from "@/api/client";
import type { DealProblemDTO, DealTotalDTO, ManualDealInput } from "@/api/deals";
import { readKey, useCachedRead } from "@/app/data/readCache";
import { dealSourceText, shownDecimal, todayIso } from "@/app/model/dealCaptureModel";
import { DataGrid, Field, Instant, PeriodPicker, Select, Skeleton, type DataGridColumn } from "@/components/ui";

type Translate = (key: string, options?: Record<string, unknown>) => string;

const PRICE_DIGITS: Record<string, number> = { "GBp/th": 2, "EUR/MWh": 3 };

const EMPTY_MANUAL: ManualDealInput = {
  book: "",
  venue: "BROKER",
  counterparty: "",
  hub: "",
  product: "",
  side: "buy",
  volume: "",
  volume_unit: "MWh/d",
  price: "",
  price_unit: "EUR/MWh",
  physical: true,
  instrument: "forward",
};

/**
 * Book → Blotter: the day's deals as captured from the exchange exports and entered by hand.
 * Each row says where it came from (file and line, or by hand); rows a file could not read are
 * listed above the deals, never dropped; totals by hub and delivery period follow. Imports,
 * manual entry and the ETRM entry sheet are the panel's actions. Nothing here places an order.
 */
export function DealBlotterPanel({ t, canWrite }: { t: Translate; canWrite: boolean }) {
  const { i18n } = useTranslation();
  const language = i18n.language;
  const [day, setDay] = useState(todayIso);
  const [trader, setTrader] = useState("");
  const [hub, setHub] = useState("");
  const [venue, setVenue] = useState("");
  const [book, setBook] = useState("");
  const [format, setFormat] = useState("");
  const [message, setMessage] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [manual, setManual] = useState<ManualDealInput>(EMPTY_MANUAL);
  const [history, setHistory] = useState<DealRowDTO[] | null>(null);
  const [resolving, setResolving] = useState<{ id: string; note: string } | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);
  const filters = { day, trader, hub, venue };
  const read = useCachedRead(readKey("/desk/deals", filters), (signal) =>
    api.dealBlotter(filters, { signal }).then((response) => response.data),
  );
  const formats = useCachedRead(readKey("/desk/deals/formats"), (signal) =>
    api.dealFormats({ signal }).then((response) => response.data),
  );
  const data: DealBlotterDTO | undefined = read.data;
  const chosenBook = book || data?.books[0]?.book_id || "";

  const fail = (caught: unknown) => setMessage(caught instanceof Error ? caught.message : String(caught));

  const importFile = (file: File | undefined) => {
    if (!file || !chosenBook) return;
    setBusy(true);
    setMessage(null);
    api
      .importDeals(file, chosenBook, format || undefined)
      .then((response) => {
        const result = response.data;
        setMessage(t("deals.imported", { file: file.name, format: result.format_title, ...result.counts }));
        read.refresh();
      })
      .catch(fail)
      .finally(() => {
        setBusy(false);
        if (fileRef.current) fileRef.current.value = "";
      });
  };

  const saveManual = () => {
    setBusy(true);
    setMessage(null);
    api
      .enterManualDeal({ ...manual, book: manual.book || chosenBook, trade_date: day })
      .then((response) => {
        setMessage(t("deals.manual_saved", { key: response.data.deal_key }));
        setManual({ ...EMPTY_MANUAL, book: manual.book });
        read.refresh();
      })
      .catch(fail)
      .finally(() => setBusy(false));
  };

  const resolve = (problem: DealProblemDTO, note: string) => {
    if (note.trim().length < 3) return;
    api
      .resolveDealProblem(problem.problem_id, note.trim())
      .then(() => {
        setResolving(null);
        read.refresh();
      })
      .catch(fail);
  };

  const columns = useMemo<DataGridColumn<DealRowDTO>[]>(() => [
    {
      id: "time",
      header: t("deals.col.time"),
      value: (row) => row.trade_time_utc ?? "",
      render: (row) => <Instant value={row.trade_time_utc} />,
      sortable: true,
      priority: "secondary",
    },
    { id: "hub", header: t("deals.col.hub"), value: (row) => row.hub, sortable: true, rowHeader: true },
    { id: "period", header: t("deals.col.period"), value: (row) => row.product, cellTitle: (row) => `${row.delivery_start} – ${row.delivery_end}` },
    {
      id: "side",
      header: t("deals.col.side"),
      value: (row) => row.side,
      render: (row) => <span data-deal-side={row.side}>{t(`deals.side.${row.side}`)}</span>,
    },
    {
      id: "price",
      header: t("deals.col.price"),
      type: "number",
      value: (row) => Number(row.price),
      render: (row) => (
        <>
          {shownDecimal(row.price, language, PRICE_DIGITS[row.price_unit] ?? 3)} <small className="ds-grid-unit">{row.price_unit}</small>
        </>
      ),
      sortable: true,
    },
    {
      id: "volume",
      header: t("deals.col.volume"),
      type: "number",
      value: (row) => Number(row.volume),
      render: (row) => (
        <span title={t("deals.total_mwh", { mwh: shownDecimal(row.total_mwh, language, 0) })}>
          {shownDecimal(row.volume, language, 0)} <small className="ds-grid-unit">{row.volume_unit}</small>
        </span>
      ),
    },
    { id: "trader", header: t("deals.col.trader"), value: (row) => row.trader, sortable: true, priority: "secondary" },
    {
      id: "counterparty",
      header: t("deals.col.counterparty"),
      value: (row) => row.counterparty ?? row.venue,
      render: (row) => (
        <>
          {row.cleared ? t("deals.cleared", { venue: row.venue }) : row.counterparty ?? "–"}
          {row.instrument === "option" && <span className="limit-badge" data-status="breach"> {t("deals.option")}</span>}
        </>
      ),
      priority: "secondary",
    },
    {
      id: "ref",
      header: t("deals.col.ref"),
      value: (row) => row.deal_key,
      render: (row) => (
        <>
          <span title={row.deal_key}>{row.venue} {row.venue_trade_id}</span>
          {row.versions > 1 && (
            <button type="button" className="link-button" data-deal-history={row.deal_key} onClick={() => api.dealHistory(row.deal_key).then((response) => setHistory(response.data)).catch(fail)}>
              {" "}{t("deals.versions", { count: row.versions })}
            </button>
          )}
          {row.status === "cancelled" && <span className="limit-badge" data-status="watch"> {t("deals.cancelled")}</span>}
        </>
      ),
      priority: "secondary",
    },
    {
      id: "source",
      header: t("deals.col.source"),
      value: (row) => dealSourceText(row, t),
      cellTitle: (row) => row.change_reason ?? undefined,
      priority: "secondary",
    },
  ], [t, language]);

  const totalColumns = useMemo<DataGridColumn<DealTotalDTO>[]>(() => [
    { id: "hub", header: t("deals.col.hub"), value: (row) => row.hub, rowHeader: true, span: true },
    { id: "period", header: t("deals.col.period"), value: (row) => row.product },
    { id: "deals", header: t("deals.col.deals"), type: "number", value: (row) => row.deals },
    { id: "buy", header: t("deals.col.bought"), unit: "MWh", type: "number", value: (row) => Number(row.buy_mwh), format: (_v, row) => shownDecimal(row.buy_mwh, language, 0) },
    { id: "sell", header: t("deals.col.sold"), unit: "MWh", type: "number", value: (row) => Number(row.sell_mwh), format: (_v, row) => shownDecimal(row.sell_mwh, language, 0) },
    { id: "net", header: t("deals.col.net"), unit: "MWh", type: "number", value: (row) => Number(row.net_mwh), format: (_v, row) => shownDecimal(row.net_mwh, language, 0) },
    { id: "avg_buy", header: t("deals.col.avg_buy"), type: "number", value: (row) => Number(row.avg_buy_price ?? NaN), format: (_v, row) => shownDecimal(row.avg_buy_price, language, PRICE_DIGITS[row.price_unit ?? ""] ?? 3) },
    { id: "avg_sell", header: t("deals.col.avg_sell"), type: "number", value: (row) => Number(row.avg_sell_price ?? NaN), format: (_v, row) => shownDecimal(row.avg_sell_price, language, PRICE_DIGITS[row.price_unit ?? ""] ?? 3) },
    { id: "unit", header: t("deals.col.unit"), value: (row) => row.price_unit ?? "" },
  ], [t, language]);

  const choice = (values: string[] | undefined, all: string) => [
    { value: "", label: all },
    ...(values ?? []).map((value) => ({ value, label: value })),
  ];
  const field = (key: keyof ManualDealInput) => (event: { target: { value: string } }) =>
    setManual({ ...manual, [key]: event.target.value });
  const unverified = (formats.data?.formats ?? []).filter((item) => !item.verified);

  return (
    <section className="workspace-panel span-3" aria-labelledby="deal-blotter-title" data-deal-blotter="true">
      <h2 id="deal-blotter-title">{t("deals.title")}</h2>
      <p className="muted" data-day-status={data?.status.closed ? "closed" : "estimate"}>
        {data?.status.closed && data.status.closes.length
          ? t("deals.status_closed", { who: data.status.closes[data.status.closes.length - 1].closed_by })
          : t("deals.status_estimate")}
      </p>
      <div className="ds-form-grid" role="group" aria-label={t("deals.filters")}>
        <Field label={t("deals.day")}>
          <PeriodPicker label={t("deals.day")} value={day} onChange={(value) => setDay(value || todayIso())} />
        </Field>
        <Field label={t("deals.col.trader")}>
          <Select value={trader} onChange={setTrader} options={choice(data?.choices.traders, t("deals.all_traders"))} />
        </Field>
        <Field label={t("deals.col.hub")}>
          <Select value={hub} onChange={setHub} options={choice(data?.choices.hubs, t("deals.all_hubs"))} />
        </Field>
        <Field label={t("deals.venue")}>
          <Select value={venue} onChange={setVenue} options={choice(data?.choices.venues, t("deals.all_venues"))} />
        </Field>
      </div>

      {data && data.unreadable.length > 0 && (
        <div className="deal-unreadable" role="region" aria-label={t("deals.unreadable_title")} data-deal-unreadable={data.unreadable.length}>
          <h3>
            <span className="limit-badge" data-status="breach">{data.unreadable.length}</span> {t("deals.unreadable_title")}
          </h3>
          <ul>
            {data.unreadable.map((problem) => (
              <li key={problem.problem_id} data-record="deal-problem">
                <span title={problem.raw}>{t("deals.unreadable_line", { file: problem.file_name, line: problem.line })}</span>{" "}
                {t(`deals.problem.${problem.code}`, { defaultValue: problem.message, field: problem.field ?? "", value: problem.value ?? "" })}
                {canWrite && resolving?.id !== problem.problem_id && (
                  <>
                    {" "}
                    <button type="button" className="link-button" onClick={() => setResolving({ id: problem.problem_id, note: "" })}>
                      {t("deals.resolve")}
                    </button>
                  </>
                )}
                {resolving?.id === problem.problem_id && (
                  <span className="ds-field-inline">
                    <input
                      aria-label={t("deals.resolve_prompt")}
                      placeholder={t("deals.resolve_prompt")}
                      value={resolving.note}
                      onChange={(event) => setResolving({ id: problem.problem_id, note: event.target.value })}
                    />
                    <button type="button" disabled={resolving.note.trim().length < 3} onClick={() => resolve(problem, resolving.note)}>
                      {t("deals.resolve_save")}
                    </button>
                  </span>
                )}
              </li>
            ))}
          </ul>
        </div>
      )}

      {read.loading && !data ? (
        <Skeleton label={t("deals.loading")} rows={6} />
      ) : (
        <DataGrid
          id="deal-blotter"
          label={t("deals.title")}
          columns={columns}
          rows={data?.deals ?? []}
          rowKey={(row) => row.deal_key}
          density="compact"
          defaultSort={{ columnId: "time", direction: "descending" }}
          rowAttributes={(row) => ({ "data-record": "deal", "data-deal-origin": row.origin, "data-deal-status": row.status })}
          empty={t("deals.empty")}
          maxHeight="28rem"
        />
      )}
      {history && (
        <details open className="scope-fold" data-deal-history-panel="true">
          <summary>{t("deals.history_title", { key: history[0]?.deal_key ?? "" })}</summary>
          <ol>
            {history.map((row) => (
              <li key={row.version}>
                {t("deals.history_line", {
                  version: row.version,
                  status: t(`deals.status.${row.status}`),
                  price: `${row.price} ${row.price_unit}`,
                  volume: `${row.volume} ${row.volume_unit}`,
                  source: dealSourceText(row, t),
                })}
                {row.change_reason ? ` · ${row.change_reason}` : ""}
              </li>
            ))}
          </ol>
          <button type="button" onClick={() => setHistory(null)}>{t("deals.close")}</button>
        </details>
      )}

      {data && data.totals.length > 0 && (
        <>
          <h3>{t("deals.totals_title")}</h3>
          <DataGrid id="deal-totals" label={t("deals.totals_title")} columns={totalColumns} rows={data.totals} rowKey={(row) => `${row.hub}:${row.product}:${row.delivery_start}`} density="compact" />
        </>
      )}

      <div className="ds-form-grid" role="group" aria-label={t("deals.actions")}>
        <Field label={t("deals.book")}>
          <Select value={chosenBook} onChange={setBook} options={(data?.books ?? []).map((item) => ({ value: item.book_id, label: item.name }))} />
        </Field>
        <Field label={t("deals.format")} hint={unverified.length ? t("deals.formats_unverified") : undefined}>
          <Select
            value={format}
            onChange={setFormat}
            options={[{ value: "", label: t("deals.format_auto") }, ...(formats.data?.formats ?? []).map((item) => ({ value: item.name, label: item.title }))]}
          />
        </Field>
        {canWrite && (
          <Field label={t("deals.import")}>
            <input ref={fileRef} type="file" accept=".csv,.txt,text/csv" disabled={busy || !chosenBook} data-deal-import="true" onChange={(event) => importFile(event.target.files?.[0])} />
          </Field>
        )}
        <div className="ds-form-grid-action">
          <button type="button" onClick={() => api.downloadEtrmSheet(day, "xlsx").catch(fail)} data-etrm-sheet="xlsx">{t("deals.etrm_sheet_xlsx")}</button>{" "}
          <button type="button" onClick={() => api.downloadEtrmSheet(day, "csv").catch(fail)} data-etrm-sheet="csv">{t("deals.etrm_sheet_csv")}</button>{" "}
          <button type="button" onClick={() => api.downloadDealBlotter(filters).catch(fail)}>{t("deals.blotter_csv")}</button>
        </div>
      </div>
      {busy && <p role="status">{t("deals.working")}</p>}
      {message && <p role="status">{message}</p>}

      {canWrite && (
        <details className="scope-fold" data-deal-manual="true">
          <summary>{t("deals.manual_title")}</summary>
          <p className="muted">{t("deals.manual_hint")}</p>
          <div className="ds-form-grid">
            <Field label={t("deals.venue")}><input value={manual.venue ?? ""} onChange={field("venue")} /></Field>
            <Field label={t("deals.col.counterparty")}><input value={manual.counterparty ?? ""} onChange={field("counterparty")} /></Field>
            <Field label={t("deals.col.hub")}>
              <Select value={manual.hub ?? ""} onChange={(value) => setManual({ ...manual, hub: value, price_unit: value === "NBP" ? "GBp/th" : "EUR/MWh", volume_unit: value === "NBP" ? "th/d" : manual.volume_unit })} options={[{ value: "", label: "–" }, ...["NBP", "TTF", "ZTP", "THE", "PEG", "PVB"].map((code) => ({ value: code, label: code }))]} />
            </Field>
            <Field label={t("deals.col.period")} hint={t("deals.period_hint")}><input value={manual.product ?? ""} onChange={field("product")} /></Field>
            <Field label={t("deals.col.side")}>
              <Select value={manual.side ?? "buy"} onChange={(value) => setManual({ ...manual, side: value as "buy" | "sell" })} options={[{ value: "buy", label: t("deals.side.buy") }, { value: "sell", label: t("deals.side.sell") }]} />
            </Field>
            <Field label={t("deals.col.price")}><input inputMode="decimal" value={manual.price ?? ""} onChange={field("price")} /></Field>
            <Field label={t("deals.price_unit")}>
              <Select value={manual.price_unit ?? "EUR/MWh"} onChange={(value) => setManual({ ...manual, price_unit: value })} options={["EUR/MWh", "GBp/th"].map((unit) => ({ value: unit, label: unit }))} />
            </Field>
            <Field label={t("deals.col.volume")}><input inputMode="decimal" value={manual.volume ?? ""} onChange={field("volume")} /></Field>
            <Field label={t("deals.volume_unit")}>
              <Select value={manual.volume_unit ?? "MWh/d"} onChange={(value) => setManual({ ...manual, volume_unit: value })} options={["MWh/d", "MW", "MWh", "th/d"].map((unit) => ({ value: unit, label: unit }))} />
            </Field>
            <Field label={t("deals.physical")}>
              <Select value={manual.physical ? "yes" : "no"} onChange={(value) => setManual({ ...manual, physical: value === "yes" })} options={[{ value: "yes", label: t("deals.physical_yes") }, { value: "no", label: t("deals.physical_no") }]} />
            </Field>
            <div className="ds-form-grid-action">
              <button type="button" disabled={busy || !manual.hub || !manual.product || !manual.price || !manual.volume || !chosenBook} onClick={saveManual}>
                {t("deals.manual_save")}
              </button>
            </div>
          </div>
        </details>
      )}
    </section>
  );
}

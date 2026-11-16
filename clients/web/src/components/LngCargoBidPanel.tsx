import { useCallback, useEffect, useState } from "react";

import {
  api,
  type LngCargoBidDTO,
  type LngTerminalTermsDTO,
  type LngTerminalTermsInput,
} from "@/api/client";
import { formatMoney, formatPrice, nextMonth } from "@/app/model/riskLimitsModel";
import { PanelHelp } from "@/components/ui/PanelHelp";
import { DataGrid } from "@/components/ui";

type Translate = (key: string, options?: Record<string, unknown>) => string;

const EMPTY_TERMS = {
  terminal_id: "",
  name: "",
  country: "",
  hub: "TTF",
  regas_tariff_per_mwh: "",
  entry_tariff_per_mwh: "0",
  fuel_retention_pct: "0",
  port_costs_per_cargo: "0",
  other_per_mwh: "0",
  extra_sailing_days: "0",
  source_note: "",
  capacity_basis: "spot",
  variable_regas_per_mwh: "",
  regime: "negotiated",
  fixed_per_cargo: "0",
  source_url: "",
  effective_from: "",
};

/**
 * "If we bid for this cargo, what is our price?" The most the firm can pay DES at each
 * terminal it has terms for, from the hub's forward mark for the arrival month less regas,
 * entry, fuel, port, boil-off and charter, ranked in one currency, with the range a slipped
 * arrival gives and the bid in USD/MMBtu and as a share of the hub. Nothing is offered.
 */
export function LngCargoBidPanel({ t }: { t: Translate }) {
  const [unit, setUnit] = useState<"mmbtu" | "mwh">("mmbtu");
  const [size, setSize] = useState("3400000");
  const [arrival, setArrival] = useState(nextMonth());
  const [margin, setMargin] = useState("0.5");
  const [boilOff, setBoilOff] = useState("0.10");
  const [charter, setCharter] = useState("0");
  const [currency, setCurrency] = useState("EUR");
  const [result, setResult] = useState<LngCargoBidDTO | null>(null);
  const [warnings, setWarnings] = useState<string[]>([]);
  const [terms, setTerms] = useState<LngTerminalTermsDTO[]>([]);
  const [draft, setDraft] = useState(EMPTY_TERMS);
  const [editing, setEditing] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  const loadTerms = useCallback(() => {
    api.lngTerminalTerms().then((response) => setTerms(response.data.rows)).catch(() => setTerms([]));
  }, []);
  useEffect(loadTerms, [loadTerms]);

  const price = () => {
    setMessage(null);
    const amount = Number(size);
    api.lngCargoBid({
      ...(unit === "mmbtu" ? { cargo_mmbtu: amount } : { cargo_mwh: amount }),
      arrival_month: arrival,
      target_margin_per_mwh: Number(margin || 0),
      boil_off_pct_per_day: Number(boilOff || 0),
      charter_per_day: Number(charter || 0),
      ranking_currency: currency,
    })
      .then((response) => {
        setResult(response.data);
        setWarnings(response.meta?.warnings ?? []);
      })
      .catch((caught: unknown) => setMessage(caught instanceof Error ? caught.message : String(caught)));
  };

  const saveTerms = () => {
    const body: LngTerminalTermsInput = {
      name: draft.name.trim(),
      country: draft.country.trim().toUpperCase() || null,
      hub: draft.hub.trim().toUpperCase(),
      regas_tariff_per_mwh: Number(draft.regas_tariff_per_mwh),
      entry_tariff_per_mwh: Number(draft.entry_tariff_per_mwh || 0),
      fuel_retention_pct: Number(draft.fuel_retention_pct || 0),
      port_costs_per_cargo: Number(draft.port_costs_per_cargo || 0),
      other_per_mwh: Number(draft.other_per_mwh || 0),
      extra_sailing_days: Number(draft.extra_sailing_days || 0),
      source_note: draft.source_note.trim(),
      capacity_basis: draft.capacity_basis as "spot" | "long_term",
      variable_regas_per_mwh: draft.variable_regas_per_mwh === "" ? null : Number(draft.variable_regas_per_mwh),
      regime: draft.regime as LngTerminalTermsInput["regime"],
      fixed_per_cargo: Number(draft.fixed_per_cargo || 0),
      source_url: draft.source_url.trim() || null,
      effective_from: draft.effective_from.trim() || null,
    };
    api.saveLngTerminalTerms(draft.terminal_id.trim(), body)
      .then(() => {
        setDraft(EMPTY_TERMS);
        setEditing(false);
        loadTerms();
      })
      .catch((caught: unknown) => setMessage(caught instanceof Error ? caught.message : String(caught)));
  };
  const field = (key: keyof typeof EMPTY_TERMS) => (event: { target: { value: string } }) =>
    setDraft({ ...draft, [key]: event.target.value });
  const editTerms = (row: LngTerminalTermsDTO) => {
    setDraft({
      terminal_id: row.terminal_id,
      name: row.name,
      country: row.country ?? "",
      hub: row.hub,
      regas_tariff_per_mwh: String(row.regas_tariff_per_mwh),
      entry_tariff_per_mwh: String(row.entry_tariff_per_mwh),
      fuel_retention_pct: String(row.fuel_retention_pct),
      port_costs_per_cargo: String(row.port_costs_per_cargo),
      other_per_mwh: String(row.other_per_mwh),
      extra_sailing_days: String(row.extra_sailing_days),
      source_note: row.source_note,
      capacity_basis: row.capacity_basis ?? "spot",
      variable_regas_per_mwh: row.variable_regas_per_mwh === null || row.variable_regas_per_mwh === undefined ? "" : String(row.variable_regas_per_mwh),
      regime: row.regime ?? "negotiated",
      fixed_per_cargo: String(row.fixed_per_cargo ?? 0),
      source_url: row.source_url ?? "",
      effective_from: row.effective_from ?? "",
    });
    setEditing(true);
  };
  const rankKey = `max_bid_${currency.toLowerCase()}_per_mwh` as const;

  return (
    <section className="workspace-panel span-3 lng-bid-panel" aria-labelledby="lng-bid-title">
      <h2 id="lng-bid-title">{t("lngbid.title")}</h2>
      <PanelHelp text={t("lngbid.copy")} label={t("panel.how_to_read")} />
      <div className="licence-form lng-bid-inputs">
        <label>
          <span>{t("lngbid.size")}</span>
          <span className="input-with-unit">
            <input inputMode="decimal" value={size} onChange={(event) => setSize(event.target.value)} />
            <select value={unit} onChange={(event) => setUnit(event.target.value as "mmbtu" | "mwh")} aria-label={t("lngbid.size_unit")}>
              <option value="mmbtu">MMBtu</option>
              <option value="mwh">MWh</option>
            </select>
          </span>
        </label>
        <label><span>{t("lngbid.arrival")}</span><input type="month" value={arrival} onChange={(event) => setArrival(event.target.value)} /></label>
        <label><span>{t("lngbid.margin", { currency })}</span><input inputMode="decimal" value={margin} onChange={(event) => setMargin(event.target.value)} /></label>
        <label><span>{t("lngbid.boil_off")}</span><input inputMode="decimal" value={boilOff} onChange={(event) => setBoilOff(event.target.value)} /></label>
        <label><span>{t("lngbid.charter", { currency })}</span><input inputMode="decimal" value={charter} onChange={(event) => setCharter(event.target.value)} /></label>
        <label>
          <span>{t("lngbid.currency")}</span>
          <select value={currency} onChange={(event) => setCurrency(event.target.value)}>
            {["EUR", "GBP", "USD"].map((code) => <option key={code} value={code}>{code}</option>)}
          </select>
        </label>
        <button type="button" disabled={!(Number(size) > 0) || !arrival || terms.length === 0} onClick={price}>
          {t("lngbid.price")}
        </button>
      </div>
      {terms.length === 0 && <p className="muted">{t("lngbid.no_terms")}</p>}

      {result && result.rows.length > 0 && (
        <>
          <p className="lng-bid-headline">
            {t("lngbid.headline", {
              terminal: result.rows[0].terminal,
              bid: formatPrice(result.rows[0][rankKey], `${currency}/MWh`),
              usd: result.rows[0].max_bid_usd_mmbtu === null ? "-" : result.rows[0].max_bid_usd_mmbtu.toFixed(3),
              cargo: Math.round(result.cargo_mmbtu).toLocaleString("en-GB"),
            })}
          </p>
          <DataGrid
            id="lng-bid"
            label={t("lngbid.title")}
            rows={result.rows}
            rowKey={(row) => row.terminal_id}
            density="compact"
            defaultSort={{ columnId: "rank", direction: "ascending" }}
            tableAttributes={{ "data-lng-bid": "true" }}
            columns={[
              { id: "rank", header: "#", type: "number", sortable: true, value: (row) => row.rank, width: "4ch" },
              {
                id: "terminal",
                header: t("lngbid.terminal"),
                rowHeader: true,
                value: (row) => row.terminal,
                cellTitle: (row) => row.terms_source,
                render: (row) => <><strong>{row.terminal}</strong> <small>{[row.country, row.hub, `${row.currency}/MWh`].filter(Boolean).join(" · ")}</small></>,
              },
              {
                id: "mark",
                header: t("lngbid.hub_mark"),
                type: "number",
                value: (row) => row.hub_mark,
                render: (row) => <>{formatPrice(row.hub_mark, `${row.currency}/MWh`)}{row.spot !== null && <small> {t("lngbid.spot", { price: row.spot.toFixed(3) })}</small>}</>,
              },
              {
                id: "costs",
                header: t("lngbid.costs"),
                type: "number",
                value: (row) => row.costs_per_mwh,
                render: (row) => <>{row.costs_per_mwh.toFixed(3)}{row.regas_per_mwh !== undefined && <small> {t("lngbid.of_which_regas", { value: row.regas_per_mwh.toFixed(3) })}</small>}</>,
              },
              { id: "breakeven", header: t("lngbid.breakeven"), type: "number", value: (row) => row.breakeven_per_mwh, format: (value) => (value as number).toFixed(3) },
              { id: "max", header: t("lngbid.max_bid"), type: "number", sortable: true, value: (row) => row.max_bid_per_mwh, render: (row) => <strong>{row.max_bid_per_mwh.toFixed(3)}</strong> },
              { id: "range", header: t("lngbid.range"), type: "number", value: (row) => row.bid_low_per_mwh, render: (row) => `${row.bid_low_per_mwh.toFixed(2)} – ${row.bid_high_per_mwh.toFixed(2)}` },
              { id: "usd", header: "USD/MMBtu", type: "number", value: (row) => row.max_bid_usd_mmbtu, format: (value) => (value == null ? "–" : (value as number).toFixed(3)) },
              { id: "pct", header: t("lngbid.pct_hub"), unit: "%", type: "number", value: (row) => row.bid_pct_of_hub, format: (value) => (value == null ? "–" : (value as number).toFixed(1)) },
              {
                id: "ranked",
                header: t("lngbid.ranked", { currency }),
                type: "number",
                sortable: true,
                value: (row) => row[rankKey],
                render: (row) => <>{row[rankKey].toFixed(3)} <small>{formatMoney(row.cargo_value, row.currency)}</small></>,
              },
            ]}
          />
          {result.regions.length > 1 && (
            <p className="muted">
              {t("lngbid.regions")}{" "}
              {result.regions.map((region) => `${region.country} ${region.low.toFixed(2)}-${region.high.toFixed(2)}`).join(" · ")}
            </p>
          )}
        </>
      )}
      {result && result.rows.length === 0 && <p className="muted">{t("lngbid.no_rows")}</p>}
      {warnings.length > 0 && (
        <details className="limit-warnings">
          <summary>{t("limits.notes", { count: warnings.length })}</summary>
          <ul>{warnings.map((warning) => <li key={warning}>{warning}</li>)}</ul>
        </details>
      )}

      <details className="lng-terms" open={terms.length === 0 || editing}>
        <summary>{t("lngbid.terms_title", { count: terms.length })}</summary>
        {terms.length > 0 && (
          <DataGrid
            id="lng-terms"
            label={t("lngbid.terms_title", { count: terms.length })}
            rows={terms}
            rowKey={(row) => row.terminal_id}
            density="compact"
            onRowAction={editTerms}
            columns={[
              {
                id: "terminal",
                header: t("lngbid.terminal"),
                rowHeader: true,
                sortable: true,
                value: (row) => row.name,
                render: (row) => <><strong>{row.name}</strong> <small>{row.hub} · {row.currency}/MWh · {t(row.capacity_basis === "long_term" ? "lngbid.basis_long_term" : "lngbid.basis_spot")}</small></>,
              },
              {
                id: "regas",
                header: t("lngbid.regas"),
                type: "number",
                value: (row) => row.regas_tariff_per_mwh,
                render: (row) =>
                  row.by_cargo_class
                    ? <small>{Object.entries(row.by_cargo_class).map(([cls, total]) => `${t(`lngbid.class_${cls}`)} ${formatMoney(total, row.currency)}`).join(" · ")}</small>
                    : row.fixed_per_cargo
                      ? <>{formatMoney(row.fixed_per_cargo, row.currency)} <small>{t("lngbid.per_cargo")}</small></>
                      : row.regas_tariff_per_mwh.toFixed(3),
              },
              { id: "entry", header: t("lngbid.entry"), type: "number", value: (row) => row.entry_tariff_per_mwh, format: (value) => (value as number).toFixed(3) },
              { id: "fuel", header: t("lngbid.fuel"), unit: "%", type: "number", value: (row) => row.fuel_retention_pct, format: (value) => (value as number).toFixed(2) },
              { id: "port", header: t("lngbid.port"), type: "number", value: (row) => row.port_costs_per_cargo, render: (row) => formatMoney(row.port_costs_per_cargo, row.currency) },
              { id: "sailing", header: t("lngbid.sailing"), type: "number", value: (row) => row.extra_sailing_days, format: (value) => (value as number).toFixed(1) },
              {
                id: "source",
                header: t("lngbid.source"),
                value: (row) => row.regime ?? "negotiated",
                render: (row) => (
                  <>
                    <span className="limit-badge" data-status={row.regime === "negotiated" ? "watch" : "ok"}>{t(`lngbid.regime_${row.regime ?? "negotiated"}`)}</span>{" "}
                    <small>{row.source_note}</small>
                    {row.source_url && (
                      <small> <a href={row.source_url} target="_blank" rel="noreferrer noopener">{t("lngbid.source_doc")}</a>{row.retrieved_at_utc ? ` · ${t("lngbid.read_on", { date: row.retrieved_at_utc.slice(0, 10) })}` : ""}</small>
                    )}
                  </>
                ),
              },
            ]}
          />
        )}
        <div className="licence-form">
          <label><span>{t("lngbid.terminal_id")}</span><input value={draft.terminal_id} onChange={field("terminal_id")} /></label>
          <label><span>{t("lngbid.terminal")}</span><input value={draft.name} onChange={field("name")} /></label>
          <label><span>{t("lngbid.country")}</span><input value={draft.country} maxLength={2} onChange={field("country")} /></label>
          <label><span>{t("lngbid.hub")}</span><input value={draft.hub} onChange={field("hub")} /></label>
          <label>
            <span>{t("lngbid.capacity_basis")}</span>
            <select value={draft.capacity_basis} onChange={field("capacity_basis")}>
              <option value="spot">{t("lngbid.basis_spot")}</option>
              <option value="long_term">{t("lngbid.basis_long_term")}</option>
            </select>
          </label>
          <label><span>{t(draft.capacity_basis === "long_term" ? "lngbid.regas_fee_sunk" : "lngbid.regas")}</span><input inputMode="decimal" value={draft.regas_tariff_per_mwh} onChange={field("regas_tariff_per_mwh")} /></label>
          {draft.capacity_basis === "long_term" && (
            <label><span>{t("lngbid.variable_regas")}</span><input inputMode="decimal" value={draft.variable_regas_per_mwh} onChange={field("variable_regas_per_mwh")} /></label>
          )}
          <label><span>{t("lngbid.entry")}</span><input inputMode="decimal" value={draft.entry_tariff_per_mwh} onChange={field("entry_tariff_per_mwh")} /></label>
          <label><span>{t("lngbid.fuel")}</span><input inputMode="decimal" value={draft.fuel_retention_pct} onChange={field("fuel_retention_pct")} /></label>
          <label><span>{t("lngbid.port")}</span><input inputMode="decimal" value={draft.port_costs_per_cargo} onChange={field("port_costs_per_cargo")} /></label>
          <label><span>{t("lngbid.other")}</span><input inputMode="decimal" value={draft.other_per_mwh} onChange={field("other_per_mwh")} /></label>
          <label><span>{t("lngbid.sailing")}</span><input inputMode="decimal" value={draft.extra_sailing_days} onChange={field("extra_sailing_days")} /></label>
          <label>
            <span>{t("lngbid.regime")}</span>
            <select value={draft.regime} onChange={field("regime")}>
              {["negotiated", "auction", "regulated", "regulated_indexed"].map((value) => <option key={value} value={value}>{t(`lngbid.regime_${value}`)}</option>)}
            </select>
          </label>
          <label><span>{t("lngbid.fixed_per_cargo")}</span><input inputMode="decimal" value={draft.fixed_per_cargo} onChange={field("fixed_per_cargo")} /></label>
          <label><span>{t("lngbid.source")}</span><input value={draft.source_note} onChange={field("source_note")} placeholder={t("lngbid.source_hint")} /></label>
          <label><span>{t("lngbid.source_url")}</span><input type="url" value={draft.source_url} placeholder="https://" onChange={field("source_url")} /></label>
          <label><span>{t("lngbid.effective_from")}</span><input value={draft.effective_from} placeholder="2027-04-01" onChange={field("effective_from")} /></label>
          <button
            type="button"
            disabled={!draft.terminal_id.trim() || !draft.name.trim() || draft.regas_tariff_per_mwh === "" || !draft.source_note.trim()}
            onClick={saveTerms}
          >
            {t("lngbid.save_terms")}
          </button>
        </div>
      </details>
      {message && <p role="status">{message}</p>}
    </section>
  );
}

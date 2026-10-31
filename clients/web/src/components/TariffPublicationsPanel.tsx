import { useCallback, useEffect, useState } from "react";

import { api, type TariffPublicationDTO } from "@/api/client";

type Translate = (key: string, options?: Record<string, unknown>) => string;

const EMPTY = { publication_id: "", tso: "", country: "", gas_year: "", status: "expected", url: "" };

/**
 * Tariff publications by TSO and gas year: indicative or final, when the final is due under
 * NC TAR (30 days before the July annual auction), whether the publication page changed
 * since the desk last reviewed it. Overdue or in-force-without-final rows come first.
 */
export function TariffPublicationsPanel({ t }: { t: Translate }) {
  const [rows, setRows] = useState<TariffPublicationDTO[] | null>(null);
  const [draft, setDraft] = useState(EMPTY);
  const [message, setMessage] = useState<string | null>(null);
  const load = useCallback(() => {
    api.tariffPublications().then((response) => setRows(response.data.rows)).catch(() => setRows(null));
  }, []);
  useEffect(load, [load]);
  const fail = (caught: unknown) => setMessage(caught instanceof Error ? caught.message : String(caught));
  const save = (body: typeof EMPTY, markReviewed = false) =>
    api.saveTariffPublication(body.publication_id.trim(), {
      tso: body.tso.trim(),
      country: body.country.trim() || null,
      gas_year: body.gas_year.trim(),
      status: body.status,
      url: body.url.trim() || null,
      mark_reviewed: markReviewed,
    })
      .then(() => {
        setDraft(EMPTY);
        load();
      })
      .catch(fail);
  const field = (key: keyof typeof EMPTY) => (event: { target: { value: string } }) =>
    setDraft({ ...draft, [key]: event.target.value });
  const asDraft = (row: TariffPublicationDTO) => ({
    publication_id: row.publication_id,
    tso: row.tso,
    country: row.country ?? "",
    gas_year: row.gas_year,
    status: row.status,
    url: row.url ?? "",
  });

  return (
    <section className="workspace-panel span-3 tariff-publications" aria-labelledby="tariff-pub-title">
      <h2 id="tariff-pub-title">{t("tariffs.title")}</h2>
      <p className="panel-copy">{t("tariffs.copy")}</p>
      {rows && rows.length === 0 && <p className="muted">{t("tariffs.empty")}</p>}
      {rows && rows.length > 0 && (
        <table className="position-ladder">
          <thead>
            <tr>
              <th scope="col">{t("tariffs.tso")}</th>
              <th scope="col">{t("tariffs.gas_year")}</th>
              <th scope="col">{t("tariffs.held")}</th>
              <th scope="col">{t("tariffs.final_due")}</th>
              <th scope="col">{t("tariffs.checked")}</th>
              <th scope="col">{t("tariffs.action")}</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.publication_id} data-status={row.severity === "breach" ? "breach" : row.severity === "watch" ? "watch" : undefined}>
                <td>
                  <strong>{row.tso}</strong> <small>{row.country}</small>
                  {row.url && <div><a href={row.url} target="_blank" rel="noreferrer noopener"><small>{t("tariffs.open_page")}</small></a></div>}
                </td>
                <td>{row.gas_year}</td>
                <td>{t(`tariffs.status_${row.status}`)}</td>
                <td>{row.final_due ?? "-"}</td>
                <td><small>{row.last_checked_at_utc ? row.last_checked_at_utc.slice(0, 10) : t("tariffs.never")}</small></td>
                <td>
                  <span className="limit-badge" data-status={row.severity === "ok" ? "ok" : row.severity}>{t(`tariffs.state_${row.state}`)}</span>
                  {row.state === "changed" && (
                    <button type="button" className="link-button" onClick={() => void save(asDraft(row), true)}> {t("tariffs.mark_reviewed")}</button>
                  )}
                  {row.status !== "final" && (
                    <button type="button" className="link-button" onClick={() => void save({ ...asDraft(row), status: "final" })}> {t("tariffs.mark_final")}</button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      <details className="lng-terms">
        <summary>{t("tariffs.register")}</summary>
        <div className="licence-form">
          <label><span>{t("tariffs.id")}</span><input value={draft.publication_id} onChange={field("publication_id")} placeholder="gts-2027" /></label>
          <label><span>{t("tariffs.tso")}</span><input value={draft.tso} onChange={field("tso")} /></label>
          <label><span>{t("tariffs.country")}</span><input value={draft.country} maxLength={8} onChange={field("country")} /></label>
          <label><span>{t("tariffs.gas_year")}</span><input value={draft.gas_year} placeholder="2027/28" onChange={field("gas_year")} /></label>
          <label>
            <span>{t("tariffs.held")}</span>
            <select value={draft.status} onChange={field("status")}>
              {["expected", "indicative", "final"].map((value) => <option key={value} value={value}>{t(`tariffs.status_${value}`)}</option>)}
            </select>
          </label>
          <label><span>{t("tariffs.url")}</span><input type="url" value={draft.url} placeholder="https://" onChange={field("url")} /></label>
          <button type="button" disabled={!draft.publication_id.trim() || !draft.tso.trim() || !/^\d{4}/.test(draft.gas_year)} onClick={() => void save(draft)}>
            {t("tariffs.save")}
          </button>
        </div>
      </details>
      {message && <p role="status">{message}</p>}
    </section>
  );
}

import { useCallback, useEffect, useState } from "react";

import { api, type MarketDataLicenceDTO, type MarketDataLicenceInput } from "@/api/client";

type Translate = (key: string, options?: Record<string, unknown>) => string;

const EMPTY: MarketDataLicenceInput & { licence_id: string } = {
  licence_id: "",
  vendor: "",
  source_family: "",
  licence_type: "ENTERPRISE",
  licensed_use: "DISPLAY_AND_NON_DISPLAY",
  valid_from: new Date().toISOString().slice(0, 10),
  offices: [],
  seats: null,
  contract_reference: "",
};

/**
 * The firm's market-data licences and who holds each one. Licensed data scopes are granted
 * to people only against a licence here; the holder list is the vendor usage report.
 */
export function LicenceRegisterPanel({ t }: { t: Translate }) {
  const [licences, setLicences] = useState<MarketDataLicenceDTO[] | null>(null);
  const [draft, setDraft] = useState(EMPTY);
  const [message, setMessage] = useState<string | null>(null);
  const load = useCallback(() => {
    api
      .marketDataLicences()
      .then((response) => setLicences(response.data))
      .catch(() => setLicences([]));
  }, []);
  useEffect(load, [load]);

  const save = () => {
    const { licence_id: licenceId, ...body } = draft;
    api
      .saveMarketDataLicence(licenceId.trim(), {
        ...body,
        seats: body.licence_type === "NAMED_USER" ? body.seats : null,
        offices: body.licence_type === "SITE" ? body.offices : [],
      })
      .then(() => {
        setDraft(EMPTY);
        setMessage(t("licence.saved"));
        load();
      })
      .catch((caught: unknown) => setMessage(caught instanceof Error ? caught.message : String(caught)));
  };
  const field = (key: keyof typeof draft) => (event: { target: { value: string } }) =>
    setDraft({ ...draft, [key]: event.target.value });

  return (
    <section className="access-catalogue" aria-labelledby="licence-register-title" data-licence-register="true">
      <h3 id="licence-register-title">{t("licence.title")}</h3>
      <p className="muted">{t("licence.help")}</p>
      {licences && licences.length === 0 && <p className="muted">{t("licence.empty")}</p>}
      {licences && licences.length > 0 && (
        <table className="position-ladder">
          <thead>
            <tr>
              <th scope="col">{t("licence.source")}</th>
              <th scope="col">{t("licence.vendor")}</th>
              <th scope="col">{t("licence.type")}</th>
              <th scope="col">{t("licence.use")}</th>
              <th scope="col">{t("licence.valid")}</th>
              <th scope="col">{t("licence.holders")}</th>
            </tr>
          </thead>
          <tbody>
            {licences.map((row) => (
              <tr key={row.licence_id} data-record="licence-row" data-licence-active={row.active}>
                <td><strong>{row.source_family}</strong> <small>{row.licence_id}</small></td>
                <td>{row.vendor}{row.contract_reference ? ` · ${row.contract_reference}` : ""}</td>
                <td>
                  {t(`licence.type_${row.licence_type}`)}
                  {row.licence_type === "SITE" && row.offices?.length ? ` (${row.offices.join(", ")})` : ""}
                </td>
                <td>{t(`licence.use_${row.licensed_use}`)}</td>
                <td>{row.valid_from} – {row.valid_to ?? "…"}{row.active ? "" : ` (${t("licence.inactive")})`}</td>
                <td title={row.holders.map((holder) => holder.display_name).join(", ")}>
                  {row.licence_type === "NAMED_USER" ? `${row.seats_used ?? 0} / ${row.seats ?? 0}` : row.holders.length}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      <div className="licence-form">
        <label><span>{t("licence.id")}</span><input value={draft.licence_id} onChange={field("licence_id")} /></label>
        <label><span>{t("licence.source")}</span><input value={draft.source_family} onChange={field("source_family")} placeholder="EEX" /></label>
        <label><span>{t("licence.vendor")}</span><input value={draft.vendor} onChange={field("vendor")} /></label>
        <label>
          <span>{t("licence.type")}</span>
          <select value={draft.licence_type} onChange={field("licence_type")}>
            {(["ENTERPRISE", "SITE", "NAMED_USER"] as const).map((value) => (
              <option key={value} value={value}>{t(`licence.type_${value}`)}</option>
            ))}
          </select>
        </label>
        <label>
          <span>{t("licence.use")}</span>
          <select value={draft.licensed_use} onChange={field("licensed_use")}>
            {(["DISPLAY", "NON_DISPLAY", "DISPLAY_AND_NON_DISPLAY"] as const).map((value) => (
              <option key={value} value={value}>{t(`licence.use_${value}`)}</option>
            ))}
          </select>
        </label>
        {draft.licence_type === "NAMED_USER" && (
          <label>
            <span>{t("licence.seats")}</span>
            <input
              type="number"
              min={1}
              value={draft.seats ?? ""}
              onChange={(event) => setDraft({ ...draft, seats: Number(event.target.value) || null })}
            />
          </label>
        )}
        {draft.licence_type === "SITE" && (
          <label>
            <span>{t("licence.offices")}</span>
            <input
              value={(draft.offices ?? []).join(",")}
              onChange={(event) => setDraft({ ...draft, offices: event.target.value.split(",").map((o) => o.trim()).filter(Boolean) })}
              placeholder="UK,SG"
            />
          </label>
        )}
        <label><span>{t("licence.valid_from")}</span><input type="date" value={draft.valid_from} onChange={field("valid_from")} /></label>
        <label><span>{t("licence.contract")}</span><input value={draft.contract_reference ?? ""} onChange={field("contract_reference")} /></label>
        <button type="button" disabled={!draft.licence_id.trim() || !draft.source_family.trim() || !draft.vendor.trim()} onClick={save}>
          {t("licence.save")}
        </button>
      </div>
      {message && <p role="status">{message}</p>}
    </section>
  );
}

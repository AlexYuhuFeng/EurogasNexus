import { useCallback, useEffect, useState } from "react";

import { api, type HedgeApprovalRowDTO, type UpstreamContractDTO } from "@/api/client";
import { formatQuantity } from "@/app/model/riskLimitsModel";

type Translate = (key: string, options?: Record<string, unknown>) => string;

const EMPTY = { contract_id: "", min: "", max: "", ref: "", valid_until: "", notes: "" };

/**
 * Risk's approved hedge band per deal. A committee may approve one supply contract to be
 * hedged at most 80 % and another at most 50 %; the cover is measured from the trades the
 * ETRM links to each contract, month by month. Set by the risk function (REVIEWER), never by
 * the trader who booked the deal; the mandate's band still applies to the whole book.
 */
export function DealHedgeApprovalsPanel({ t }: { t: Translate }) {
  const [rows, setRows] = useState<HedgeApprovalRowDTO[] | null>(null);
  const [contracts, setContracts] = useState<UpstreamContractDTO[]>([]);
  const [draft, setDraft] = useState(EMPTY);
  const [editing, setEditing] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const load = useCallback(() => {
    api.hedgeApprovals().then((response) => setRows(response.data)).catch(() => setRows(null));
  }, []);
  useEffect(load, [load]);
  useEffect(() => {
    api.upstreamContracts().then((response) => setContracts(response.data)).catch(() => setContracts([]));
  }, []);
  const name = (id: string) => contracts.find((row) => row.contract_id === id)?.contract_name ?? id;
  const field = (key: keyof typeof EMPTY) => (event: { target: { value: string } }) =>
    setDraft({ ...draft, [key]: event.target.value });
  const save = () => {
    setMessage(null);
    api.saveHedgeApproval(draft.contract_id, {
      min_hedge_ratio_pct: draft.min === "" ? null : Number(draft.min),
      max_hedge_ratio_pct: draft.max === "" ? null : Number(draft.max),
      approval_ref: draft.ref.trim() || null,
      valid_until: draft.valid_until || null,
      notes: draft.notes.trim() || null,
    })
      .then(() => {
        setMessage(t("limits.saved"));
        setDraft(EMPTY);
        setEditing(false);
        load();
      })
      .catch((caught: unknown) => setMessage(caught instanceof Error ? caught.message : String(caught)));
  };
  const edit = (row: HedgeApprovalRowDTO) => {
    setDraft({
      contract_id: row.contract_id,
      min: row.min_hedge_ratio_pct == null ? "" : String(row.min_hedge_ratio_pct),
      max: row.max_hedge_ratio_pct == null ? "" : String(row.max_hedge_ratio_pct),
      ref: row.approval_ref ?? "",
      valid_until: row.valid_until ?? "",
      notes: row.notes ?? "",
    });
    setEditing(true);
  };
  const band = (row: HedgeApprovalRowDTO) =>
    row.min_hedge_ratio_pct != null
      ? `${row.min_hedge_ratio_pct}% – ${row.max_hedge_ratio_pct ?? 100}%`
      : t("hedgeapproval.at_most", { pct: row.max_hedge_ratio_pct });

  return (
    <section className="workspace-panel span-3 deal-hedge-panel" aria-labelledby="deal-hedge-title">
      <h2 id="deal-hedge-title">{t("hedgeapproval.title")}</h2>
      <p className="panel-copy">{t("hedgeapproval.copy")}</p>
      {rows && rows.length === 0 && <p className="muted">{t("hedgeapproval.empty")}</p>}
      {rows && rows.length > 0 && (
        <table className="position-ladder">
          <thead>
            <tr>
              <th scope="col">{t("hedgeapproval.contract")}</th>
              <th scope="col">{t("hedgeapproval.band")}</th>
              <th scope="col">{t("hedgeapproval.hedged")}</th>
              <th scope="col" className="num">{t("hedgeapproval.room")}</th>
              <th scope="col">{t("hedgeapproval.status")}</th>
              <th scope="col" />
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => {
              const next = row.months.find((month) => month.room_mwh != null);
              return (
                <tr key={row.contract_id} data-status={row.status === "ok" ? undefined : "breach"}>
                  <td>
                    <strong>{name(row.contract_id)}</strong>{" "}
                    <small className="muted">{row.approval_ref ?? ""}{row.valid_until ? ` · ${t("hedgeapproval.until", { date: row.valid_until })}` : ""}</small>
                  </td>
                  <td>{band(row)}</td>
                  <td>
                    {row.hedge_range ?? "–"} <small className="muted">{t("hedgeapproval.trades", { count: row.linked_trades })}</small>
                  </td>
                  <td className="num">{next ? `${formatQuantity(next.room_mwh)} · ${next.month}` : "–"}</td>
                  <td>
                    <span className="limit-badge" data-status={row.status === "ok" ? "ok" : "breach"}>{t(`hedgeapproval.status_${row.status}`)}</span>
                    {row.breaches.length > 0 && <div className="limit-breaches"><small>{row.breaches.join("; ")}</small></div>}
                  </td>
                  <td><button type="button" className="link-button" onClick={() => edit(row)}>{t("hedgeapproval.change")}</button></td>
                </tr>
              );
            })}
          </tbody>
        </table>
      )}
      <div className="limit-actions">
        <button type="button" className="secondary-button" onClick={() => { setDraft(EMPTY); setEditing(!editing); }}>
          {t("hedgeapproval.add")}
        </button>
        <small className="muted">{t("hedgeapproval.who")}</small>
      </div>
      {editing && (
        <div className="licence-form">
          <label>
            <span>{t("hedgeapproval.contract")}</span>
            <select value={draft.contract_id} onChange={field("contract_id")}>
              <option value="">{t("contracts.choose")}</option>
              {contracts.map((row) => <option key={row.contract_id} value={row.contract_id}>{row.contract_name}</option>)}
            </select>
          </label>
          <label><span>{t("hedgeapproval.min")}</span><input inputMode="decimal" value={draft.min} onChange={field("min")} /></label>
          <label><span>{t("hedgeapproval.max")}</span><input inputMode="decimal" value={draft.max} onChange={field("max")} /></label>
          <label><span>{t("hedgeapproval.ref")}</span><input value={draft.ref} maxLength={128} onChange={field("ref")} /></label>
          <label><span>{t("limits.valid_until")}</span><input type="date" value={draft.valid_until} onChange={field("valid_until")} /></label>
          <label><span>{t("hedgeapproval.notes")}</span><input value={draft.notes} maxLength={500} onChange={field("notes")} /></label>
          <button type="button" disabled={!draft.contract_id || (draft.min === "" && draft.max === "")} onClick={save}>
            {t("limits.save")}
          </button>
        </div>
      )}
      {message && <p role="status">{message}</p>}
    </section>
  );
}

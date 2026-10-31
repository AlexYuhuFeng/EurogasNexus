import { useEffect, useState } from "react";

import { api, type UpstreamContractDTO } from "@/api/client";

type Translate = (key: string, options?: Record<string, unknown>) => string;
export type ContractLifecycleAction = (
  contractId: string,
  action: "retire" | "reinstate",
  reason: string,
  editToken: string,
) => Promise<void>;

function errorText(caught: unknown): string {
  return caught instanceof Error ? caught.message : String(caught);
}

/**
 * Retire a stored contract with a reason. Retiring is how a contract is "removed": it
 * leaves positions, risk and the map, while its revisions and the audit trail stay, so the
 * firm can always show what was agreed and who took it out, and when.
 */
export function RetireContractButton({
  contract,
  onLifecycle,
  t,
}: {
  contract: UpstreamContractDTO;
  onLifecycle: ContractLifecycleAction;
  t: Translate;
}) {
  const [open, setOpen] = useState(false);
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  if (!contract.edit_token) return null;
  const confirm = () => {
    setBusy(true);
    setError(null);
    onLifecycle(contract.contract_id, "retire", reason.trim(), contract.edit_token ?? "")
      .then(() => setOpen(false))
      .catch((caught: unknown) => setError(errorText(caught)))
      .finally(() => setBusy(false));
  };
  if (!open) {
    return (
      <button type="button" className="contract-library-handoff danger-quiet" onClick={() => setOpen(true)}>
        {t("contracts.retire")}
      </button>
    );
  }
  return (
    <div className="contract-retire-form" role="group" aria-label={t("contracts.retire_title", { name: contract.contract_name })}>
      <label>
        <span>{t("contracts.retire_reason")}</span>
        <input
          autoFocus
          value={reason}
          maxLength={500}
          placeholder={t("contracts.retire_reason_hint")}
          onChange={(event) => setReason(event.target.value)}
        />
      </label>
      <button type="button" className="danger" disabled={busy || reason.trim().length < 3} onClick={confirm}>
        {t("contracts.retire_confirm")}
      </button>
      <button type="button" className="secondary-button" onClick={() => setOpen(false)}>{t("contracts.retire_cancel")}</button>
      <small className="muted">{t("contracts.retire_effect")}</small>
      {error && <span role="alert" className="limit-breaches">{error}</span>}
    </div>
  );
}

/** Retired contracts, with who retired them and why, and a way to bring one back. */
export function RetiredContractsList({
  onLifecycle,
  refreshKey,
  t,
}: {
  onLifecycle: ContractLifecycleAction;
  refreshKey: number;
  t: Translate;
}) {
  const [rows, setRows] = useState<UpstreamContractDTO[]>([]);
  const [error, setError] = useState<string | null>(null);
  const load = () => {
    api.retiredUpstreamContracts()
      .then((response) => setRows(response.data.filter((row) => row.retired_at_utc)))
      .catch(() => setRows([]));
  };
  useEffect(load, [refreshKey]);
  if (rows.length === 0) return null;
  const reinstate = (row: UpstreamContractDTO) => {
    const reason = window.prompt(t("contracts.reinstate_reason"));
    if (!reason || reason.trim().length < 3) return;
    onLifecycle(row.contract_id, "reinstate", reason.trim(), row.edit_token ?? "")
      .then(load)
      .catch((caught: unknown) => setError(errorText(caught)));
  };
  return (
    <details className="contract-retired">
      <summary>{t("contracts.retired_title", { count: rows.length })}</summary>
      <table className="position-ladder">
        <thead>
          <tr>
            <th scope="col">{t("contracts.resource_term")}</th>
            <th scope="col">{t("contracts.retired_when")}</th>
            <th scope="col">{t("contracts.retire_reason")}</th>
            <th scope="col" />
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.contract_id}>
              <td><strong>{row.contract_name}</strong> <small>{row.contract_id}</small></td>
              <td><small>{row.retired_at_utc?.slice(0, 16).replace("T", " ")} UTC · {row.retired_by}</small></td>
              <td>{row.retire_reason}</td>
              <td><button type="button" className="link-button" onClick={() => reinstate(row)}>{t("contracts.reinstate")}</button></td>
            </tr>
          ))}
        </tbody>
      </table>
      {error && <p role="alert" className="limit-breaches">{error}</p>}
    </details>
  );
}

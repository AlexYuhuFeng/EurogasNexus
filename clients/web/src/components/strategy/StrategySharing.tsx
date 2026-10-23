import { useEffect, useState } from "react";
import { api, type StrategyDTO, type StrategyGroupDTO } from "@/api/client";
import { sharingRequest, type SharingVisibility } from "@/app/model/strategySharingModel";

export function StrategySharing({ strategy, onSaved, t }: {
  strategy: StrategyDTO;
  onSaved: (updated: StrategyDTO) => void;
  t: (key: string) => string;
}) {
  const [visibility, setVisibility] = useState<SharingVisibility>("PRIVATE");
  const [groupIds, setGroupIds] = useState<string[]>([]);
  const [groups, setGroups] = useState<StrategyGroupDTO[] | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(false);
  const [saved, setSaved] = useState(false);
  const canManage = strategy.can_manage === true;
  useEffect(() => {
    setVisibility(strategy.visibility ?? "PRIVATE");
    setGroupIds(strategy.shared_group_ids ?? []);
    setError(false);
    setSaved(false);
  }, [strategy.strategy_id, strategy.visibility, strategy.shared_group_ids]);
  useEffect(() => {
    let active = true;
    setGroups(null);
    if (canManage) void api.strategyGroups().then((result) => {
      if (active) setGroups(result.data);
    }).catch(() => { if (active) setGroups(null); });
    return () => { active = false; };
  }, [strategy.strategy_id, canManage]);
  const body = sharingRequest(canManage, { visibility, group_ids: groupIds }, groups?.map((group) => group.group_id) ?? null);
  const dirty = visibility !== (strategy.visibility ?? "PRIVATE") ||
    [...groupIds].sort().join("\n") !== [...(strategy.shared_group_ids ?? [])].sort().join("\n");
  async function save() {
    if (!body || busy || !dirty) return;
    setBusy(true); setError(false); setSaved(false);
    try {
      const result = await api.updateStrategySharing(strategy.strategy_id, body);
      onSaved(result.data);
      setSaved(true);
    } catch { setError(true); }
    finally { setBusy(false); }
  }
  return <section className="strategy-sharing" aria-label={t("strategy_lab.sharing.title")}>
    <strong>{t("strategy_lab.sharing.title")}: {t(`strategy_lab.sharing.${(strategy.visibility ?? "PRIVATE").toLowerCase()}`)}</strong>
    <p>{t(canManage ? "strategy_lab.sharing.scope_note" : "strategy_lab.sharing.read_only")}</p>
    {canManage && <>
      <label>{t("strategy_lab.sharing.visibility")}
        <select value={visibility} disabled={busy} onChange={(event) => {
          setVisibility(event.target.value as SharingVisibility); setSaved(false);
          if (event.target.value !== "GROUPS") setGroupIds([]);
        }}>
          <option value="PRIVATE">{t("strategy_lab.sharing.private")}</option>
          <option value="PUBLIC">{t("strategy_lab.sharing.public")}</option>
          <option value="GROUPS">{t("strategy_lab.sharing.groups")}</option>
        </select>
      </label>
      {visibility === "GROUPS" && <label>{t("strategy_lab.sharing.choose_groups")}
        <select multiple value={groupIds} disabled={busy || groups === null} onChange={(event) => {
          setGroupIds(Array.from(event.target.selectedOptions, (option) => option.value)); setSaved(false);
        }}>
          {(groups ?? []).map((group) => <option key={group.group_id} value={group.group_id}>{group.name}</option>)}
        </select>
        {(!groups || groups.length === 0) && <span role="status">{t("strategy_lab.sharing.groups_unavailable")}</span>}
      </label>}
      <button type="button" disabled={busy || !body || !dirty} onClick={() => void save()}>{t("strategy_lab.sharing.save")}</button>
      {saved && <p role="status">{t("strategy_lab.sharing.saved")}</p>}
      {error && <p role="alert">{t("strategy_lab.sharing.failed")}</p>}
    </>}
  </section>;
}

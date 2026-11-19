/**
 * Contract kinds, type first (docs/product/CONTRACT_TYPES.md): choose what kind of agreement
 * this is, then fill only that kind's terms, grouped as the desk reads a contract. Parties,
 * points, terminals, ports, masters and indices are chosen from records the firm holds
 * (UX_REFERENCE rule 25); a value typed by hand is allowed only where a record may not exist
 * yet (a new seller, a load port) and the picker says so. The server validates the terms and
 * derives what positions, credit and the evaluators read; this form only collects them.
 *
 * The save is this form's own action (UX_REFERENCE rule 26: the tab row holds tabs only).
 */
import { useEffect, useMemo, useState, type FormEvent } from "react";

import { api, type ContractIntakeDTO, type RouteCandidateDTO, type UpstreamContractDTO } from "@/api/client";
import { useCachedRead } from "@/app/data/readCache";
import { GAS_HUBS, hubOfPoint, indexOptions, pointOptions } from "@/app/contractChoices";
import {
  CONTRACT_KINDS,
  KIND_GROUPS,
  draftFromTerms,
  draftWithProposal,
  kindTermsFromDraft,
  newKindDraft,
  periodText,
  typedContractBody,
  visibleFields,
  type AuthorableKind,
  type KindDraft,
  type KindField,
  type PickerSource,
} from "@/app/model/contractKinds";
import { contractOptions, counterpartyOptions } from "@/app/model/recordOptions";
import { PeriodPicker, RecordPicker, type RecordOption } from "@/components/ui";
import { idFromName } from "@/components/ui/recordPickerModel";
import { useApiStore } from "@/stores/api";
import { formatDeliveryMonth } from "@/app/time/timeFormat";
import "./contract-kinds.css";

type Translate = (key: string, options?: Record<string, unknown>) => string;

/** The cards a new contract starts from: one per kind, a line on what it is. */
export function ContractKindChooser({ onChoose, t }: { onChoose: (kind: AuthorableKind) => void; t: Translate }) {
  return (
    <section className="contract-kind-chooser" aria-labelledby="contract-kind-chooser-title">
      <h3 id="contract-kind-chooser-title">{t("contracts.kind.choose")}</h3>
      <div className="contract-kind-cards" role="list">
        {CONTRACT_KINDS.map((kind) => (
          <div role="listitem" key={kind}>
            <button type="button" className="contract-kind-card" data-contract-kind={kind} onClick={() => onChoose(kind)}>
              <strong>{t(`contracts.kind.${kind}`)}</strong>
              <span>{t(`contracts.kind.about.${kind}`)}</span>
            </button>
          </div>
        ))}
      </div>
    </section>
  );
}

interface TypedContractFormProps {
  kind: AuthorableKind;
  /** The stored contract being edited, or null for a new one. */
  editing: UpstreamContractDTO | null;
  upstreamContracts: readonly UpstreamContractDTO[];
  routeCandidates: readonly RouteCandidateDTO[];
  /** A PDF intake's proposal for this kind, applied once for review. */
  intake?: ContractIntakeDTO | null;
  save: (body: Record<string, unknown>) => Promise<UpstreamContractDTO | null>;
  onSaved?: (saved: UpstreamContractDTO) => void;
  onChangeKind: () => void;
  t: Translate;
}

function optionLabel(t: Translate, value: string): string {
  const key = `contracts.kind_option.${value}`;
  const label = t(key);
  return label === key ? value : label;
}

export function TypedContractForm({
  kind, editing, upstreamContracts, routeCandidates, intake = null, save, onSaved, onChangeKind, t,
}: TypedContractFormProps) {
  const [stored, setStored] = useState<UpstreamContractDTO | null>(editing);
  const [name, setName] = useState(editing?.contract_name ?? "");
  const [draft, setDraft] = useState<KindDraft>(() =>
    editing ? draftFromTerms(kind, editing.kind_terms ?? null, editing.master_contract_id) : newKindDraft(kind),
  );
  const [unmodelled, setUnmodelled] = useState(editing?.unmodelled_terms ?? "");
  const [manual, setManual] = useState<Set<string>>(new Set());
  const [busy, setBusy] = useState(false);
  const [tried, setTried] = useState(false);

  useEffect(() => {
    setStored(editing);
    setName(editing?.contract_name ?? "");
    setDraft(editing ? draftFromTerms(kind, editing.kind_terms ?? null, editing.master_contract_id) : newKindDraft(kind));
    setUnmodelled(editing?.unmodelled_terms ?? "");
    setTried(false);
  }, [editing, kind]);

  useEffect(() => {
    if (!intake || editing) return;
    const record = intake.record as Record<string, unknown>;
    setDraft((current) => draftWithProposal(kind, current, record.kind_terms as Record<string, unknown> | undefined));
    if (typeof record.contract_name === "string" && !name) setName(record.contract_name);
    // Applied once per intake; the reviewer edits from here.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [intake, kind]);

  // Registers the pickers read (UX_REFERENCE rule 25).
  const credit = useCachedRead("/portfolio/credit-exposure", () => api.creditExposure());
  const terminalTerms = useCachedRead("/portfolio/lng-terminal-terms", () => api.lngTerminalTerms());
  const freight = useCachedRead("/lng/freight-routes", () => api.freightRoutes());
  const observedTerminals = useApiStore((state) => state.lng);
  const terminalHubs = useMemo(() => {
    const out = new Map<string, string>();
    for (const row of terminalTerms.data?.data.rows ?? []) out.set(row.name, row.hub);
    return out;
  }, [terminalTerms.data]);

  const options: Record<PickerSource, RecordOption[] | null> = useMemo(() => {
    const counterparties = credit.data ? counterpartyOptions(credit.data.data.rows ?? []) : null;
    const terminals = new Map<string, RecordOption>();
    for (const row of terminalTerms.data?.data.rows ?? []) {
      terminals.set(row.name, { id: row.name, label: row.name, detail: [row.hub, row.country].filter(Boolean).join(" · ") });
    }
    for (const row of observedTerminals) {
      if (!terminals.has(row.terminal_name)) terminals.set(row.terminal_name, { id: row.terminal_name, label: row.terminal_name, detail: row.country ?? undefined });
    }
    const ports = new Map<string, RecordOption>();
    for (const route of freight.data?.data ?? []) {
      for (const port of [route.load_port, route.discharge_port]) if (port) ports.set(port, { id: port, label: port });
    }
    const pointHub = hubOfPoint(String(draft.delivery_point ?? "")) ?? (typeof draft.terminal_hub === "string" ? draft.terminal_hub : null);
    return {
      counterparty: counterparties,
      point: pointOptions(routeCandidates).map((point) => ({ id: point, label: point })),
      terminal: [...terminals.values()],
      port: [...ports.values()],
      master: contractOptions(
        upstreamContracts.filter((item) => item.contract_kind === "LNG_MSPA") as Parameters<typeof contractOptions>[0],
        typeof draft.master_contract_id === "string" ? [draft.master_contract_id] : [],
      ),
      hub: GAS_HUBS.map((code) => ({ id: code, label: code })),
      index: indexOptions(pointHub)
        .filter((item) => item !== "Fixed price" && item !== "Oil-indexed")
        .map((item) => ({ id: item, label: item })),
    };
  }, [credit.data, terminalTerms.data, observedTerminals, freight.data, routeCandidates, upstreamContracts, draft.delivery_point, draft.terminal_hub, draft.master_contract_id]);

  const set = (key: string, value: string | string[] | boolean) => setDraft((current) => ({ ...current, [key]: value }));
  const result = kindTermsFromDraft(kind, draft);
  const missing = [...(name.trim() ? [] : ["contract_name"]), ...result.missing];
  const fields = visibleFields(kind, draft);
  const contractId = stored?.contract_id ?? idFromName(name, upstreamContracts.map((item) => item.contract_id));

  async function submit(event: FormEvent) {
    event.preventDefault();
    setTried(true);
    if (missing.length > 0 || !result.terms || busy) return;
    setBusy(true);
    try {
      const saved = await save(
        typedContractBody({
          contractId,
          contractName: name,
          kind,
          terms: result.terms,
          masterId: typeof draft.master_contract_id === "string" ? draft.master_contract_id : null,
          unmodelled,
          notes: stored?.notes ?? JSON.stringify({ source: "web_contract_capture", manual_inputs: [...manual] }),
          editToken: stored?.edit_token ?? null,
        }),
      );
      if (saved) {
        setStored(saved);
        onSaved?.(saved);
      }
    } finally {
      setBusy(false);
    }
  }

  function control(field: KindField) {
    // A required term carries the form's own mark (explained once under the kind's title).
    const label = `${t(`contracts.kind_field.${field.key}`)}${field.unit ? ` (${field.unit.replace("GBp/th", "p/th")})` : ""}${field.required ? " *" : ""}`;
    const value = draft[field.key];
    const id = `kind-${field.key}`;
    const invalid = tried && result.missing.includes(field.key);
    if (field.input === "picker" && field.picker) {
      const source = options[field.picker];
      const current = typeof value === "string" && value ? value : null;
      // A counterparty is stored by name; its credit line id rides along when it has one.
      const shown = field.picker === "counterparty" ? (typeof draft.counterparty_id === "string" && draft.counterparty_id ? draft.counterparty_id : current) : current;
      return (
        <div key={field.key} className={invalid ? "contract-kind-invalid" : undefined}>
          <RecordPicker
            id={id}
            label={label}
            options={source}
            value={shown}
            recentKey={`contract-kind-${field.picker}`}
            allowManual={field.manual}
            emptyText={t(`contracts.kind_empty.${field.picker}`)}
            onChange={(choice) => {
              if (!choice) {
                set(field.key, "");
                if (field.picker === "counterparty") set("counterparty_id", "");
                return;
              }
              const option = source?.find((item) => item.id === choice.id);
              setManual((current) => {
                const next = new Set(current);
                if (choice.manual) next.add(field.key);
                else next.delete(field.key);
                return next;
              });
              if (field.picker === "counterparty") {
                set(field.key, option?.label ?? choice.id);
                set("counterparty_id", choice.manual ? "" : choice.id);
                return;
              }
              set(field.key, choice.id);
              if (field.picker === "terminal" && terminalHubs.has(choice.id)) set("terminal_hub", terminalHubs.get(choice.id) ?? "");
            }}
          />
        </div>
      );
    }
    if (field.input === "pickers" && field.picker) {
      return (
        <div key={field.key}>
          <RecordPicker
            id={id}
            label={label}
            multiple
            options={options[field.picker]}
            value={Array.isArray(value) ? value : []}
            onChange={(ids) => set(field.key, ids)}
          />
        </div>
      );
    }
    if (field.input === "multi") {
      const values = Array.isArray(value) ? value : [];
      return (
        <fieldset key={field.key} className={`contract-kind-checks${invalid ? " contract-kind-invalid" : ""}`}>
          <legend>{label}</legend>
          {(field.options ?? []).map((option) => (
            <label key={option} className="checkbox-row">
              <input
                type="checkbox"
                checked={values.includes(option)}
                onChange={() => set(field.key, values.includes(option) ? values.filter((item) => item !== option) : [...values, option])}
              />
              <span>{optionLabel(t, option)}</span>
            </label>
          ))}
        </fieldset>
      );
    }
    if (field.input === "bool") {
      return (
        <label key={field.key} className="checkbox-row contract-kind-bool">
          <input type="checkbox" checked={value === true} onChange={(event) => set(field.key, event.target.checked)} />
          <span>{t(`contracts.kind_field.${field.key}`)}</span>
        </label>
      );
    }
    if (field.input === "date" || field.input === "month") {
      return (
        <label key={field.key} className={`ds-field${invalid ? " contract-kind-invalid" : ""}`}>
          <span className="ds-field-label">{label}</span>
          <PeriodPicker
            id={id}
            kind={field.input === "month" ? "month" : "day"}
            label={label}
            value={typeof value === "string" ? value : ""}
            clearable={!field.required}
            onChange={(next) => set(field.key, next)}
          />
        </label>
      );
    }
    if (field.input === "choice") {
      return (
        <label key={field.key} className="ds-field" htmlFor={id}>
          <span className="ds-field-label">{label}</span>
          <select id={id} value={typeof value === "string" ? value : ""} aria-invalid={invalid || undefined} onChange={(event) => set(field.key, event.target.value)}>
            {!field.required && <option value="">{t("contracts.choose")}</option>}
            {(field.options ?? []).map((option) => <option key={option} value={option}>{optionLabel(t, option)}</option>)}
          </select>
        </label>
      );
    }
    return (
      <label key={field.key} className="ds-field" htmlFor={id}>
        <span className="ds-field-label">{label}</span>
        <input
          id={id}
          type={field.input === "number" ? "number" : "text"}
          inputMode={field.input === "number" ? "decimal" : undefined}
          step={field.input === "number" ? "any" : undefined}
          value={typeof value === "string" ? value : ""}
          aria-invalid={invalid || undefined}
          onChange={(event) => set(field.key, event.target.value)}
        />
      </label>
    );
  }

  return (
    <form className="contract-kind-form" data-contract-kind-form={kind} onSubmit={submit} noValidate>
      <div className="contract-kind-form-head">
        <div>
          <span className="eyebrow">{t("contracts.kind.label")}</span>
          <strong>{t(`contracts.kind.${kind}`)}</strong>
          <p className="muted">{t(`contracts.kind.about.${kind}`)} {t("contracts.kind.required_hint")}</p>
        </div>
        {!stored && (
          <button type="button" className="link-button" onClick={onChangeKind}>{t("contracts.kind.change")}</button>
        )}
      </div>
      <div className="ds-form-grid">
        <label className="ds-field" htmlFor="kind-contract-name">
          <span className="ds-field-label">{t("contracts.contract_name")} *</span>
          <input id="kind-contract-name" aria-required="true" value={name} aria-invalid={(tried && !name.trim()) || undefined} onChange={(event) => setName(event.target.value)} />
        </label>
      </div>
      {KIND_GROUPS.map((group) => {
        const inGroup = fields.filter((field) => field.group === group);
        if (inGroup.length === 0) {
          return group === "credit" && kind === "LNG_CARGO" ? (
            <fieldset key={group} className="contract-kind-group">
              <legend>{t(`contracts.kind_group.${group}`)}</legend>
              <p className="muted">{t("contracts.kind.credit_from_master")}</p>
            </fieldset>
          ) : null;
        }
        return (
          <fieldset key={group} className="contract-kind-group" data-kind-group={group}>
            <legend>{t(`contracts.kind_group.${group}`)}</legend>
            <div className="ds-form-grid">{inGroup.map(control)}</div>
          </fieldset>
        );
      })}
      <fieldset className="contract-kind-group">
        <legend>{t("contracts.kind_field.unmodelled_terms")}</legend>
        <p className="muted">{t("contracts.kind.unmodelled_hint")}</p>
        <textarea
          aria-label={t("contracts.kind_field.unmodelled_terms")}
          rows={3}
          maxLength={20000}
          value={unmodelled}
          onChange={(event) => setUnmodelled(event.target.value)}
        />
      </fieldset>
      {stored && (
        <p className="contract-kind-reads" data-kind-reads>
          {stored.contract_kind === "LNG_MSPA"
            ? t("contracts.kind.reads_master")
            : t("contracts.kind.reads", {
                point: stored.delivery_point_name,
                period: periodText(stored.gas_year, (iso) => formatDeliveryMonth(iso.slice(0, 7))),
                quantity: Math.round(stored.delivery_quantity_mwh_per_day).toLocaleString("en-GB"),
              })}
        </p>
      )}
      <div className="contract-kind-actions">
        <button type="submit" disabled={busy} aria-busy={busy || undefined}>
          {stored ? t("contracts.kind.save_changes") : t("contracts.kind.save")}
        </button>
        {tried && missing.length > 0 && (
          <p className="warning-text" role="status">
            {t("contracts.kind.still_needed", {
              fields: missing.map((key) => (key === "contract_name" ? t("contracts.contract_name") : t(`contracts.kind_field.${key}`))).join(", "),
            })}
          </p>
        )}
      </div>
    </form>
  );
}

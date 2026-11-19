/**
 * A contract's price (docs/product/CONTRACT_TYPES.md slice 2): the formula in words, the price
 * for a delivery month from the indices the firm holds (each input with its class, source and
 * window; an index not held is named), in the contract's own unit. A supply agreement's price
 * terms and quantity as written are edited here and saved with the stored row's edit token.
 */
import { useMemo, useState } from "react";

import { api, type UpstreamContractDTO } from "@/api/client";
import { useCachedRead } from "@/app/data/readCache";
import { contractPeriod } from "@/app/model/contractKinds";
import {
  AVERAGING,
  INDICES,
  PRICE_BASES,
  PRICE_UNITS,
  PRODUCTS,
  QUANTITY_UNITS,
  gsaBlockFromDraft,
  gsaPriceBody,
  monthsBetween,
  priceDraftFrom,
  priceWords,
  type IndexDraft,
  type PriceDraft,
} from "@/app/model/priceTerms";
import { formatDeliveryMonth } from "@/app/time/timeFormat";

type Translate = (key: string, options?: Record<string, unknown>) => string;

const unitLabel = (unit: string) => unit.replace("GBp/th", "p/th");

function figure(value: number, unit: string): string {
  const digits = unit.endsWith("/MMBtu") ? 3 : 2;
  return `${value.toLocaleString("en-GB", { minimumFractionDigits: digits, maximumFractionDigits: digits })} ${unitLabel(unit)}`;
}

export function ContractPricePanel({ contract, save, t }: {
  contract: UpstreamContractDTO;
  save?: (body: Record<string, unknown>) => Promise<UpstreamContractDTO | null>;
  t: Translate;
}) {
  const kind = contract.contract_kind ?? "SUPPLY_GSA";
  const months = useMemo(() => {
    const period = contractPeriod(contract.gas_year);
    if (!period) return [];
    const now = new Date().toISOString().slice(0, 7);
    const all = monthsBetween(period.start, period.end, 60);
    const fromNow = all.filter((month) => month >= now);
    return (fromNow.length ? fromNow : all).slice(0, 18);
  }, [contract.gas_year]);
  const [month, setMonth] = useState<string>(() => months[0] ?? "");
  const read = useCachedRead(
    kind === "LNG_MSPA" || !month ? null : `/contracts/${contract.contract_id}/price?month=${month}&v=${contract.edit_token ?? ""}`,
    () => api.contractPrice(contract.contract_id, month),
  );
  const priced = read.data?.data ?? null;
  const result = priced?.result ?? null;
  const [editing, setEditing] = useState(false);

  if (kind === "LNG_MSPA") return null;
  return (
    <section className="contract-price" data-contract-price={contract.contract_id} aria-label={t("contracts.price.title")}>
      <div className="contract-price-head">
        <span className="eyebrow">{t("contracts.price.title")}</span>
        {months.length > 0 && (
          <label className="contract-price-month">
            <span>{t("contracts.price.for_month")}</span>
            <select value={month} onChange={(event) => setMonth(event.target.value)}>
              {months.map((item) => <option key={item} value={item}>{formatDeliveryMonth(item)}</option>)}
            </select>
          </label>
        )}
      </div>
      {read.loading && <p className="muted">{t("contracts.price.reading")}</p>}
      {priced && (
        <>
          <p className="contract-price-words" data-price-words>{priceWords(priced.price_terms, t) ?? priced.note ?? t("contracts.price.not_recorded")}</p>
          {result && result.value !== null && (
            <p className="contract-price-value">
              <strong data-price-value>{figure(result.value, result.unit)}</strong>{" "}
              <span className="contract-price-class" data-input-class={result.input_class}>{t(`contracts.price.class.${result.input_class}`)}</span>
            </p>
          )}
          {result && result.missing.length > 0 && (
            <ul className="contract-price-missing" data-price-missing>
              {result.missing.map((item) => <li key={item}>{item}</li>)}
            </ul>
          )}
          {result && result.inputs.length > 0 && (
            <details className="contract-price-inputs">
              <summary>{t("contracts.price.inputs", { count: result.inputs.length })}</summary>
              <ul>
                {result.inputs.map((input) => (
                  <li key={input.index}>
                    {input.weight !== 1 ? `${input.weight} × ` : ""}{input.index}: {figure(input.value, input.unit)}
                    {" · "}{t(`contracts.price.class.${input.input_class}`)}{" · "}{input.source_ref}
                    {" · "}{t("contracts.price.window", { from: input.window[0], to: input.window[1], count: input.observations })}
                  </li>
                ))}
              </ul>
              {result.notes.map((note) => <p key={note} className="muted">{note}</p>)}
            </details>
          )}
        </>
      )}
      {kind === "SUPPLY_GSA" && save && !editing && (
        <button type="button" className="secondary-button" data-page-action="contract-price-edit" onClick={() => setEditing(true)}>{t("contracts.price.edit")}</button>
      )}
      {kind === "SUPPLY_GSA" && save && editing && (
        <GsaPriceEditor contract={contract} save={save} t={t} onDone={() => setEditing(false)} />
      )}
    </section>
  );
}

function IndexFields({ value, onChange, t, idPrefix }: { value: IndexDraft; onChange: (next: IndexDraft) => void; t: Translate; idPrefix: string }) {
  const set = (patch: Partial<IndexDraft>) => onChange({ ...value, ...patch });
  return (
    <>
      <label className="ds-field" htmlFor={`${idPrefix}-index`}>
        <span className="ds-field-label">{t("contracts.price.index")}</span>
        <select id={`${idPrefix}-index`} value={value.index} onChange={(event) => set({ index: event.target.value })}>
          {INDICES.map((item) => <option key={item} value={item}>{item === "HH" || item === "BRENT" ? t(`contracts.price.index_name.${item}`) : item}</option>)}
        </select>
      </label>
      <label className="ds-field" htmlFor={`${idPrefix}-product`}>
        <span className="ds-field-label">{t("contracts.price.product")}</span>
        <select id={`${idPrefix}-product`} value={value.product} onChange={(event) => set({ product: event.target.value })}>
          {PRODUCTS.map((item) => <option key={item} value={item}>{t(`contracts.price.product_name.${item}`)}</option>)}
        </select>
      </label>
      <label className="ds-field" htmlFor={`${idPrefix}-averaging`}>
        <span className="ds-field-label">{t("contracts.price.averaging")}</span>
        <select id={`${idPrefix}-averaging`} value={value.averaging} onChange={(event) => set({ averaging: event.target.value })}>
          {AVERAGING.map((item) => <option key={item} value={item}>{t(`contracts.price.averaging_name.${item}`)}</option>)}
        </select>
      </label>
      {value.averaging === "last_n_trading_days" && (
        <label className="ds-field" htmlFor={`${idPrefix}-n`}>
          <span className="ds-field-label">{t("contracts.price.n_days")}</span>
          <input id={`${idPrefix}-n`} type="number" min="1" max="60" value={value.n_days} onChange={(event) => set({ n_days: event.target.value })} />
        </label>
      )}
      <label className="ds-field" htmlFor={`${idPrefix}-publication`}>
        <span className="ds-field-label">{t("contracts.price.publication")}</span>
        <input id={`${idPrefix}-publication`} value={value.publication} onChange={(event) => set({ publication: event.target.value })} />
      </label>
    </>
  );
}

function GsaPriceEditor({ contract, save, t, onDone }: {
  contract: UpstreamContractDTO;
  save: (body: Record<string, unknown>) => Promise<UpstreamContractDTO | null>;
  t: Translate;
  onDone: () => void;
}) {
  const nbp = /\bNBP\b/i.test(contract.delivery_point_name);
  const [draft, setDraft] = useState<PriceDraft>(() => priceDraftFrom(contract.kind_terms ?? null, nbp));
  const [busy, setBusy] = useState(false);
  const [tried, setTried] = useState(false);
  const set = (patch: Partial<PriceDraft>) => setDraft((current) => ({ ...current, ...patch }));
  const { block, missing } = gsaBlockFromDraft(draft);

  async function submit() {
    setTried(true);
    if (!block || busy) return;
    setBusy(true);
    try {
      const saved = await save(gsaPriceBody(contract as unknown as Record<string, unknown>, block));
      if (saved) onDone();
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="contract-price-editor" data-gsa-price-editor>
      <div className="ds-form-grid">
        <label className="ds-field" htmlFor="gsa-quantity">
          <span className="ds-field-label">{t("contracts.price.quantity")}</span>
          <input id="gsa-quantity" type="number" inputMode="decimal" step="any" value={draft.quantity} onChange={(event) => set({ quantity: event.target.value })} />
        </label>
        <label className="ds-field" htmlFor="gsa-quantity-unit">
          <span className="ds-field-label">{t("contracts.kind_field.quantity_unit")}</span>
          <select id="gsa-quantity-unit" value={draft.quantity_unit} onChange={(event) => set({ quantity_unit: event.target.value })}>
            {QUANTITY_UNITS.map((unit) => <option key={unit} value={unit}>{unit}</option>)}
          </select>
        </label>
        <label className="ds-field" htmlFor="gsa-basis">
          <span className="ds-field-label">{t("contracts.price.basis")}</span>
          <select id="gsa-basis" value={draft.basis} onChange={(event) => set({ basis: event.target.value as PriceDraft["basis"] })}>
            {PRICE_BASES.map((basis) => <option key={basis} value={basis}>{t(`contracts.price.basis_name.${basis}`)}</option>)}
          </select>
        </label>
        <label className="ds-field" htmlFor="gsa-unit">
          <span className="ds-field-label">{t("contracts.kind_field.price_unit")}</span>
          <select id="gsa-unit" value={draft.unit} onChange={(event) => set({ unit: event.target.value })}>
            {PRICE_UNITS.map((unit) => <option key={unit} value={unit}>{unitLabel(unit)}</option>)}
          </select>
        </label>
        {draft.basis === "fixed" && (
          <label className="ds-field" htmlFor="gsa-fixed">
            <span className="ds-field-label">{t("contracts.kind_field.fixed_price")} *</span>
            <input id="gsa-fixed" type="number" inputMode="decimal" step="any" value={draft.fixed_price} aria-invalid={(tried && missing.includes("fixed_price")) || undefined} onChange={(event) => set({ fixed_price: event.target.value })} />
          </label>
        )}
        {draft.basis === "index" && (
          <>
            <IndexFields value={draft.index} onChange={(index) => set({ index })} t={t} idPrefix="gsa-index" />
            <label className="ds-field" htmlFor="gsa-premium">
              <span className="ds-field-label">{t("contracts.price.premium")}</span>
              <input id="gsa-premium" type="number" inputMode="decimal" step="any" value={draft.premium} onChange={(event) => set({ premium: event.target.value })} />
            </label>
          </>
        )}
        {draft.basis === "formula" && draft.components.map((component, position) => (
          <div key={position} className="contract-price-component ds-form-grid">
            <label className="ds-field" htmlFor={`gsa-weight-${position}`}>
              <span className="ds-field-label">{t("contracts.price.weight")} *</span>
              <input id={`gsa-weight-${position}`} type="number" inputMode="decimal" step="any" value={component.weight} onChange={(event) => set({ components: draft.components.map((item, index) => (index === position ? { ...item, weight: event.target.value } : item)) })} />
            </label>
            <IndexFields value={component.index} onChange={(index) => set({ components: draft.components.map((item, at) => (at === position ? { ...item, index } : item)) })} t={t} idPrefix={`gsa-component-${position}`} />
          </div>
        ))}
        {draft.basis === "formula" && (
          <label className="ds-field" htmlFor="gsa-constant">
            <span className="ds-field-label">{t("contracts.kind_field.constant")}</span>
            <input id="gsa-constant" type="number" inputMode="decimal" step="any" value={draft.constant} onChange={(event) => set({ constant: event.target.value })} />
          </label>
        )}
        <label className="ds-field" htmlFor="gsa-floor">
          <span className="ds-field-label">{t("contracts.price.floor")}</span>
          <input id="gsa-floor" type="number" inputMode="decimal" step="any" value={draft.floor} onChange={(event) => set({ floor: event.target.value })} />
        </label>
        <label className="ds-field" htmlFor="gsa-cap">
          <span className="ds-field-label">{t("contracts.price.cap")}</span>
          <input id="gsa-cap" type="number" inputMode="decimal" step="any" value={draft.cap} onChange={(event) => set({ cap: event.target.value })} />
        </label>
      </div>
      <div className="contract-kind-actions">
        <button type="button" disabled={busy} aria-busy={busy || undefined} data-page-action="contract-price-save" onClick={() => void submit()}>{t("contracts.price.save")}</button>
        <button type="button" className="link-button" onClick={onDone}>{t("contracts.price.cancel")}</button>
        {tried && missing.length > 0 && <p className="warning-text" role="status">{t("contracts.kind.still_needed", { fields: missing.map((key) => t(`contracts.price.field.${key}`)).join(", ") })}</p>}
      </div>
    </div>
  );
}

/**
 * Research → Cargo & netback (design basis 2, D.2 item 3, sections C.1-C.4; CP-18).
 *
 * "What does a cargo from X on terms Y net at each terminal, and how does the arb evolve?"
 * One cargo, FOB (own shipping) or DES, against the terminals the firm holds terms or reviewed
 * tariffs for. Every figure comes from the server's cargo chain (CP-12) and the terminal tariff
 * register (CP-11); this page arranges the form and the answer:
 *
 * - the terminal comparison (cost at the ship's rail, netback, margin, its range a month either
 *   side), with "within the assumption range" instead of a winner when two are close;
 * - one terminal's margin as a waterfall (hub → gas in kind → entry → regas → netback → FOB →
 *   boil-off → freight → margin);
 * - Henry Hub versus the hub at the same delivery point, read two ways (delivered at NW Europe,
 *   netback at the US Gulf) with the same total, and the delivered spread by arrival month;
 * - the margin's sensitivity to hire, Henry Hub, the hub price and FX.
 *
 * Henry Hub comes from the firm's mark or the customer's licensed data; otherwise the held EIA
 * spot is the form's default, a flat proxy labelled with its day (the demo desk has its own
 * simulated series, labelled); with neither, the page asks for a mark. FX for the arrival month
 * is the CP-01 forward, stated per month, spot only as the labelled fallback. The voyage is the desk's own unless the firm has
 * saved routes: no sea-distance table ships with the product. Research is hypothetical: no
 * book, no checks, nothing offered or nominated.
 */
import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { useTranslation } from "react-i18next";

import "@/styles/spreads.css";
import "@/styles/cargo.css";
import { api, type AssumptionSetSummaryDTO, type CargoEconomicsDTO, type CargoResultDTO, type CargoTerminalDTO, type FreightRouteDTO } from "@/api/client";
import {
  HISTORY_DAYS,
  arrivalMonths,
  cargoRequest,
  standardForm,
  fieldForBlock,
  henryHub,
  historyChart,
  hubQuote,
  hubSimulatedFlags,
  marginWaterfall,
  monthLabel,
  rankedTerminals,
  seriesChart,
  withSet,
  formFromConfirmation,
  type CargoForm,
  type VoyageMode,
} from "@/app/model/cargoStudy";
import { unitLabel } from "@/app/model/instrumentPicker";
import { formatGasDay } from "@/app/time/timeFormat";
import i18n from "@/i18n";
import { hubFromSearch, reportSearch, spreadsSearch } from "@/app/model/spreadsBoard";
import { NextSteps } from "./NextSteps";
import { SimulatedScope, simulatedScopeOf, useSimulatedPills } from "@/components/ui/SimulatedScope";
import { Button, RecordPicker, Segmented, Select, WorkProgress } from "@/components/ui";
import { contractOptions } from "@/app/model/recordOptions";
import type { UpstreamContractDTO } from "@/api/client";
import { Chart, Waterfall, type ChartData } from "@/components/ui/charts";
import { formatMeasure } from "@/app/time/valueFormat";

const fixed = (value: number | null | undefined, decimals = 2): string =>
  formatMeasure("ratio", value, { decimals });

const signed = (value: number | null | undefined, decimals = 2): string =>
  value === null || value === undefined || !Number.isFinite(value) ? "–" : `${value > 0 ? "+" : ""}${fixed(value, decimals)}`;

const millions = (value: number | null | undefined): string =>
  value === null || value === undefined ? "–" : `${signed(value / 1_000_000, 2)} m`;

const perMwh = (currency: string) => unitLabel(`${currency}/MWh`);

export function CargoStudy() {
  const { t } = useTranslation();
  const [routes, setRoutes] = useState<FreightRouteDTO[]>([]);
  const [sets, setSets] = useState<AssumptionSetSummaryDTO[]>([]);
  // Every terminal the register has offered, so the chooser keeps those left out.
  const [terminals, setTerminals] = useState<{ id: string; name: string; hub: string }[]>([]);
  const [form, setForm] = useState<CargoForm | null>(null);
  const [result, setResult] = useState<CargoEconomicsDTO | null>(null);
  const [busy, setBusy] = useState(false);
  const [failed, setFailed] = useState<string | null>(null);
  const [chosen, setChosen] = useState<string | null>(null);
  // Cargo confirmations the firm holds (CONTRACT_TYPES.md): one fills the study's inputs.
  const [confirmations, setConfirmations] = useState<UpstreamContractDTO[]>([]);
  const seq = useRef(0);

  const run = useCallback(async (next: CargoForm) => {
    const mine = ++seq.current;
    setBusy(true);
    setFailed(null);
    try {
      const response = await api.cargoEconomics(cargoRequest(next));
      if (mine !== seq.current) return;
      setResult(response.data);
      // Opened from a spread ("price a cargo against this spread"): its hub's terminal first.
      const linkedHub = typeof window === "undefined" ? null : hubFromSearch(window.location.search);
      const atHub = linkedHub ? response.data.cargoes[0]?.terminals.find((row) => row.hub === linkedHub && row.reason === null) : undefined;
      if (atHub) setChosen(atHub.terminal_id);
      setTerminals((held) => {
        const known = new Map(held.map((item) => [item.id, item]));
        for (const row of response.data.cargoes[0]?.terminals ?? []) known.set(row.terminal_id, { id: row.terminal_id, name: row.name, hub: row.hub });
        return [...known.values()];
      });
    } catch (error) {
      if (mine === seq.current) setFailed(error instanceof Error && error.message ? error.message : t("cargo.failed"));
    } finally {
      if (mine === seq.current) setBusy(false);
    }
  }, [t]);

  // Opens populated from what the firm holds: its saved routes and its approved assumption set
  // (whose figures then apply); what they do not hold is the desk standard, labelled.
  useEffect(() => {
    let live = true;
    Promise.all([
      api.freightRoutes().then((response) => response.data ?? [], () => [] as FreightRouteDTO[]),
      api.assumptionSets().then((response) => response.data?.sets ?? [], () => [] as AssumptionSetSummaryDTO[]),
    ]).then(([held, heldSets]) => {
      if (!live) return;
      const approved = heldSets.filter((set) => set.approved_version !== null);
      setRoutes(held);
      setSets(approved);
      const firm = approved.find((set) => set.scope === "organisation");
      const initial = withSet(standardForm(new Date(), held), firm?.set_id ?? "");
      setForm(initial);
      void run(initial);
    });
    api.upstreamContracts().then(
      (response) => { if (live) setConfirmations((response.data ?? []).filter((item) => item.contract_kind === "LNG_CARGO")); },
      () => undefined,
    );
    return () => { live = false; };
  }, [run]);

  const update = (patch: Partial<CargoForm>, now = false) => {
    if (!form) return;
    const next = { ...form, ...patch };
    setForm(next);
    if (now) void run(next);
  };

  const cargo: CargoResultDTO | null = result?.cargoes[0] ?? null;
  const { priced, leftOut } = rankedTerminals(cargo);
  const selected = priced.find((row) => row.terminal_id === chosen) ?? priced[0] ?? null;
  const scope = simulatedScopeOf(hubSimulatedFlags(cargo));

  if (!form) {
    return (
      <div className="cargo-page" data-cargo-study="true">
        <WorkProgress stages={[t("cargo.progress")]} current={0} label={t("cargo.progress")} reserve="20rem" />
      </div>
    );
  }

  return (
    <div className="cargo-page" data-cargo-study="true">
      {/* The purpose is the shell's line (UX_REFERENCE rule 24); what remains is the caveat. */}
      <p className="muted cargo-hypothetical">{t("cargo.hypothetical")}</p>
      <SimulatedScope scope={scope} notice={t("cargo.all_simulated")}>
        {/* Opens priced: the inputs fold above the answer, each one an override of what is held. */}
        <details className="cargo-inputs-fold" data-inputs-fold="true">
          <summary>{t("cargo.form.change", { term: form.term === "FOB" ? t("cargo.term.fob") : t("cargo.term.des"), month: monthLabel(form.arrivalMonth) })}</summary>
        <CargoFormView
          form={form}
          routes={routes}
          sets={sets}
          terminals={terminals}
          confirmations={confirmations}
          busy={busy}
          onChange={update}
          onRun={() => void run(form)}
          heldHh={form.hh.trim() === "" ? henryHub(cargo) : null}
        />
        </details>
        {failed && <p className="spreads-failed" role="alert">{failed}</p>}
        {busy && !result && <WorkProgress stages={[t("cargo.progress")]} current={0} label={t("cargo.progress")} reserve="16rem" />}
        {cargo && cargo.blocked && (
          <BlockedQuestion cargo={cargo} form={form} onAnswer={(patch) => update(patch, true)} />
        )}
        {cargo && !cargo.blocked && (
          <>
            <Headline cargo={cargo} best={priced[0] ?? null} />
            <TerminalTable cargo={cargo} priced={priced} leftOut={leftOut} selected={selected?.terminal_id ?? null} onSelect={setChosen} reportingCurrency={result?.reporting_currency ?? "EUR"} />
            {selected && <MarginWaterfall row={selected} />}
            {selected?.delivered_spread && <DeliveredSpread cargo={cargo} row={selected} />}
            {result?.delivered_spread_history && cargo.term === "FOB" && <HistoryLine result={result} cargo={cargo} />}
            {result?.delivered_spread_series && cargo.term === "FOB" && <SpreadLine result={result} cargo={cargo} />}
            {(cargo.sensitivity?.length ?? 0) > 0 && priced[0] && <Sensitivity cargo={cargo} row={priced[0]} />}
            <InputsFold cargo={cargo} fxMethod={result?.fx_method ?? ""} />
            <CargoNextSteps cargo={cargo} row={selected} arrival={form.arrivalMonth} />
          </>
        )}
      </SimulatedScope>
    </div>
  );
}

/** A labelled number field; empty means "use the firm's assumption set". */
function Field({ id, label, value, onChange, unit, step = "any", width = "s", hint }: {
  id: string; label: string; value: string; onChange: (value: string) => void; unit?: string; step?: string; width?: "s" | "m"; hint?: string;
}) {
  return (
    <label className="cargo-field" htmlFor={id} data-width={width}>
      <span className="cargo-field-label">{label}{unit ? <span className="cargo-field-unit"> {unit}</span> : null}</span>
      <input
        id={id}
        className="spreads-number"
        type="text"
        inputMode="decimal"
        value={value}
        step={step}
        placeholder={hint}
        onChange={(event) => onChange(event.target.value)}
      />
    </label>
  );
}

function CargoFormView({ form, routes, sets, terminals, confirmations, busy, onChange, onRun, heldHh }: {
  form: CargoForm; routes: FreightRouteDTO[]; sets: AssumptionSetSummaryDTO[];
  confirmations: UpstreamContractDTO[];
  terminals: { id: string; name: string; hub: string }[]; busy: boolean;
  onChange: (patch: Partial<CargoForm>, now?: boolean) => void; onRun: () => void;
  heldHh: ReturnType<typeof henryHub>;
}) {
  const { t } = useTranslation();
  const [pickedCargo, setPickedCargo] = useState<string | null>(null);
  const months = useMemo(() => arrivalMonths(new Date()), []);
  // With a set chosen, an empty figure is the set's: the field says so.
  const setHint = form.assumptionSetId ? t("cargo.form.from_set") : t("cargo.form.desk_standard");
  const pricingMonths = useMemo(() => arrivalMonths(new Date(), 19).map((m) => m), []);
  const voyageOptions: { value: VoyageMode; label: string }[] = [
    ...(routes.length > 0 ? [{ value: "route" as const, label: t("cargo.voyage.route") }] : []),
    { value: "distance", label: t("cargo.voyage.distance") },
    { value: "days", label: t("cargo.voyage.days") },
  ];
  return (
    <form
      className="cargo-form"
      aria-label={t("cargo.form.label")}
      onSubmit={(event) => { event.preventDefault(); onRun(); }}
    >
      <fieldset className="cargo-group" data-sources="true">
        <legend>{t("cargo.form.from_records")}</legend>
        <label className="cargo-field" data-width="m">
          <span className="cargo-field-label">{t("cargo.form.assumption_set")}</span>
          <Select
            value={form.assumptionSetId}
            options={[
              { value: "", label: t("cargo.form.set_example") },
              ...sets.map((set) => ({ value: set.set_id, label: `${set.name} · v${set.approved_version}` })),
            ]}
            onChange={(setId) => {
              const next = withSet(form, setId);
              onChange(next, true);
            }}
          />
        </label>
        {terminals.length > 0 && (
          <div className="cargo-terminal-choice" role="group" aria-label={t("cargo.form.terminals")}>
            <span className="cargo-field-label">{t("cargo.form.terminals")}</span>
            <div className="cargo-terminal-list">
              {terminals.map((terminal) => {
                const on = form.terminalIds.length === 0 || form.terminalIds.includes(terminal.id);
                return (
                  <label key={terminal.id} className="cargo-terminal-option">
                    <input
                      type="checkbox"
                      checked={on}
                      onChange={() => {
                        const current = form.terminalIds.length === 0 ? terminals.map((item) => item.id) : form.terminalIds;
                        const next = on ? current.filter((id) => id !== terminal.id) : [...current, terminal.id];
                        if (next.length === 0) return; // at least one terminal
                        onChange({ terminalIds: next.length === terminals.length ? [] : next }, true);
                      }}
                    />
                    {terminal.name} → {terminal.hub}
                  </label>
                );
              })}
            </div>
          </div>
        )}
        {confirmations.length > 0 && (
          <div className="cargo-field" data-width="m" data-confirmed-cargo="true">
            <RecordPicker
              id="cargo-confirmed"
              label={t("cargo.form.confirmed_cargo")}
              options={contractOptions(confirmations)}
              value={pickedCargo}
              recentKey="cargo-confirmation"
              onChange={(choice) => {
                setPickedCargo(choice?.id ?? null);
                const picked = confirmations.find((item) => item.contract_id === choice?.id);
                if (picked?.kind_terms) onChange(formFromConfirmation(form, picked.kind_terms), true);
              }}
            />
          </div>
        )}
        {sets.length === 0 && <p className="cargo-voyage-note">{t("cargo.form.no_sets")}</p>}
      </fieldset>

      <fieldset className="cargo-group">
        <legend>{t("cargo.form.cargo")}</legend>
        <Segmented
          label={t("cargo.form.term")}
          options={[{ value: "FOB", label: t("cargo.term.fob") }, { value: "DES", label: t("cargo.term.des") }]}
          value={form.term}
          onChange={(term) => onChange({ term }, true)}
        />
        <label className="cargo-field" data-width="m">
          <span className="cargo-field-label">{t("cargo.form.arrival")}</span>
          <Select
            value={form.arrivalMonth}
            options={months.map((month) => ({ value: month, label: monthLabel(month) }))}
            onChange={(arrivalMonth) => onChange({ arrivalMonth }, true)}
          />
        </label>
        <Field id="cargo-size" hint={setHint} label={t("cargo.form.size")} unit="MMBtu" value={form.cargoSize} onChange={(cargoSize) => onChange({ cargoSize })} width="m" />
        {form.term === "DES" && (
          <>
            <Field id="cargo-des-price" label={t("cargo.form.des_price")} unit={perMwh(form.desCurrency)} value={form.desPrice} onChange={(desPrice) => onChange({ desPrice })} />
            <label className="cargo-field">
              <span className="cargo-field-label">{t("cargo.form.des_currency")}</span>
              <Select value={form.desCurrency} options={(["EUR", "GBP", "USD"] as const).map((value) => ({ value, label: value }))} onChange={(desCurrency) => onChange({ desCurrency }, true)} />
            </label>
          </>
        )}
      </fieldset>

      {form.term === "FOB" && (
        <>
          <fieldset className="cargo-group">
            <legend>{t("cargo.form.price")}</legend>
            <label className="cargo-field" data-width="m">
              <span className="cargo-field-label">{t("cargo.form.pricing_month")}</span>
              <Select
                value={form.pricingMonth}
                options={pricingMonths.map((month) => ({ value: month, label: monthLabel(month) }))}
                onChange={(pricingMonth) => onChange({ pricingMonth }, true)}
              />
            </label>
            <Field id="cargo-hh" label={t("cargo.form.hh")} unit="USD/MMBtu" value={form.hh} onChange={(hh) => onChange({ hh })} hint={t("cargo.form.hh_held")} width="m" />
            <Field id="cargo-slope" hint={setHint} label={t("cargo.form.slope")} unit="× HH" value={form.slope} onChange={(slope) => onChange({ slope })} />
            <Field id="cargo-fee" hint={setHint} label={t("cargo.form.fee")} unit="USD/MMBtu" value={form.fee} onChange={(fee) => onChange({ fee })} />
            {heldHh && heldHh.inputClass !== "assumption" && (
              <p className="cargo-voyage-note" data-hh-default={heldHh.proxy ? (heldHh.demo ? "demo" : "eia") : heldHh.inputClass}>
                {t("cargo.form.hh_using", { value: fixed(heldHh.value, 3), basis: hhBasisText(t, heldHh) })}
              </p>
            )}
          </fieldset>

          <fieldset className="cargo-group" data-voyage={form.voyageMode}>
            <legend>{t("cargo.form.voyage")}</legend>
            <Segmented label={t("cargo.form.voyage_as")} options={voyageOptions} value={form.voyageMode} onChange={(voyageMode) => onChange({ voyageMode }, true)} />
            {form.voyageMode === "route" && (
              <label className="cargo-field" data-width="m">
                <span className="cargo-field-label">{t("cargo.voyage.saved")}</span>
                <Select
                  value={form.routeId}
                  options={routes.map((route) => ({
                    value: route.route_id,
                    label: `${route.load_port} → ${route.discharge_port} · ${Math.round(route.distance_nm).toLocaleString("en-GB")} nm`,
                  }))}
                  onChange={(routeId) => onChange({ routeId }, true)}
                />
              </label>
            )}
            {form.voyageMode === "distance" && (
              <Field id="cargo-distance" hint={t("cargo.form.desk_standard")} label={t("cargo.form.distance")} unit="nm" value={form.distanceNm} onChange={(distanceNm) => onChange({ distanceNm })} />
            )}
            {form.voyageMode !== "days" && (
              <Field id="cargo-speed" hint={setHint} label={t("cargo.form.speed")} unit="kn" value={form.speedKn} onChange={(speedKn) => onChange({ speedKn })} />
            )}
            {form.voyageMode === "days" && (
              <Field id="cargo-days" label={t("cargo.form.laden_days")} unit={t("cargo.unit.days")} value={form.ladenDays} onChange={(ladenDays) => onChange({ ladenDays })} />
            )}
            <Segmented
              label={t("cargo.form.ballast")}
              options={[{ value: "round", label: t("cargo.ballast.round") }, { value: "one_way", label: t("cargo.ballast.one_way") }]}
              value={form.ballast}
              onChange={(ballast) => onChange({ ballast }, true)}
            />
            <Field id="cargo-hire" hint={setHint} label={t("cargo.form.hire")} unit="USD/d" value={form.hire} onChange={(hire) => onChange({ hire })} width="m" />
            <Field id="cargo-bor" hint={setHint} label={t("cargo.form.boil_off")} unit="%/d" value={form.boilOff} onChange={(boilOff) => onChange({ boilOff })} />
            <p className="cargo-voyage-note" data-voyage-note="true">
              {routes.length > 0 ? t("cargo.voyage.note_saved", { count: routes.length }) : t("cargo.voyage.note_none")}
            </p>
          </fieldset>

          <details className="cargo-more">
            <summary>{t("cargo.form.more")}</summary>
            <div className="cargo-group-body">
              <Field id="cargo-ballast-fuel" hint={setHint} label={t("cargo.form.ballast_fuel")} unit="MMBtu/d" value={form.ballastFuel} onChange={(ballastFuel) => onChange({ ballastFuel })} />
              <Field id="cargo-port" hint={setHint} label={t("cargo.form.port")} unit={t("cargo.unit.usd_call")} value={form.portCost} onChange={(portCost) => onChange({ portCost })} width="m" />
              <Field id="cargo-insurance" hint={setHint} label={t("cargo.form.insurance")} unit="%" value={form.insurance} onChange={(insurance) => onChange({ insurance })} />
              <Field id="cargo-canal" label={t("cargo.form.canal")} unit="USD" value={form.canalCost} onChange={(canalCost) => onChange({ canalCost })} width="m" />
            </div>
          </details>
        </>
      )}
      <div className="cargo-actions">
        <Button type="submit" variant="primary" loading={busy}>{t("cargo.form.run")}</Button>
        <span className="cargo-example-note">{t("cargo.form.example_note")}</span>
      </div>
    </form>
  );
}

function BlockedQuestion({ cargo, form, onAnswer }: { cargo: CargoResultDTO; form: CargoForm; onAnswer: (patch: Partial<CargoForm>) => void }) {
  const { t } = useTranslation();
  const field = fieldForBlock(cargo.blocked);
  const [draft, setDraft] = useState("");
  const month = monthLabel(form.term === "FOB" ? form.pricingMonth : form.arrivalMonth);
  return (
    <section className="spreads-questions" data-blocked={cargo.blocked ?? ""} aria-label={t("cargo.blocked.title")}>
      <h2 className="spreads-section-title">{t("cargo.blocked.title")}</h2>
      <p>{t(`cargo.blocked.${cargo.blocked}`, { month, defaultValue: t("cargo.blocked.other", { reason: cargo.blocked }) })}</p>
      {field && (
        <form
          className="cargo-answer"
          onSubmit={(event) => {
            event.preventDefault();
            if (draft.trim()) onAnswer({ [field]: draft.trim(), ...(field === "distanceNm" ? { voyageMode: "distance" as const } : {}) });
          }}
        >
          <label htmlFor="cargo-answer-input" className="cargo-field-label">{t(`cargo.answer.${field}`, { month })}</label>
          <input id="cargo-answer-input" className="spreads-number" inputMode="decimal" value={draft} onChange={(event) => setDraft(event.target.value)} />
          <Button type="submit" size="sm" variant="primary" disabled={!draft.trim()}>{t("cargo.answer.use")}</Button>
        </form>
      )}
    </section>
  );
}

function ClassMark({ inputClass }: { inputClass: string }) {
  const { t } = useTranslation();
  const pills = useSimulatedPills();
  if (inputClass === "simulated" && !pills) return null;
  return <span className="spreads-class" data-class={inputClass}>{t(`cargo.class.${inputClass}`, { defaultValue: inputClass })}</span>;
}

/** How a Henry Hub figure was obtained, in words (the spot proxy names its day). */
function hhBasisText(t: (key: string, options?: Record<string, unknown>) => string, hh: NonNullable<ReturnType<typeof henryHub>>): string {
  if (hh.proxy && hh.day) return t(hh.demo ? "cargo.hh.proxy_demo" : "cargo.hh.proxy_day", { day: shortDay(hh.day) });
  if (hh.proxy) return t("cargo.hh.proxy");
  return t(`cargo.hh.${hh.inputClass}`, { defaultValue: hh.source });
}

// Days through the shell's formatter, in the interface language (18 Nov, 11月18日).
const shortDay = (iso: string) => formatGasDay(iso, i18n.language);

function Headline({ cargo, best }: { cargo: CargoResultDTO; best: CargoTerminalDTO | null }) {
  const { t } = useTranslation();
  const hh = henryHub(cargo);
  // The owner's standard: the result says which inputs were typed in by hand.
  // The FOB cost leg carries the cargo size's source: name the input, not the step.
  const nameOf = (leg: { key: string; label: string }) =>
    (leg.key === "fob_cost" ? t("cargo.form.size") : t(`cargo.leg.${leg.key}`, { defaultValue: leg.label })).toLowerCase();
  const entered = cargo.legs.filter((leg) => leg.source.startsWith("entered")).map(nameOf);
  // What the firm's records did not hold and the desk standard filled (assumptions, labelled).
  const standard = cargo.legs.filter((leg) => leg.source.startsWith("desk standard")).map(nameOf);
  const voyage = cargo.voyage;
  const parts: ReactNode[] = [];
  if (hh) {
    parts.push(
      <span key="hh" data-hh-source={hh.proxy ? "proxy" : hh.inputClass} title={hh.source}>
        {t("cargo.headline.hh", { value: fixed(hh.value, 3) })}{" "}
        <span className="cargo-hh-basis">{hhBasisText(t, hh)}</span>
      </span>,
    );
  }
  if (cargo.term === "FOB" && cargo.days) {
    const days = t("cargo.headline.days", { laden: fixed(cargo.days.laden, 1), ballast: fixed(cargo.days.ballast, 1), port: fixed(cargo.days.port, 0) });
    parts.push(
      <span key="voyage" data-voyage-basis={voyage?.basis ?? ""} title={voyage?.source ?? ""}>
        {voyage?.basis === "saved_route" ? `${voyage.label} · ` : voyage?.basis === "entered_distance" || voyage?.basis === "standard" ? `${Math.round(voyage.distance_nm ?? 0).toLocaleString("en-GB")} nm · ` : ""}
        {days} · {t(voyage?.basis === "saved_route" ? "cargo.voyage.basis_saved" : voyage?.basis === "standard" ? "cargo.voyage.basis_standard" : "cargo.voyage.basis_entered")}
      </span>,
    );
  }
  return (
    <section className="cargo-headline" aria-label={t("cargo.headline.title")} data-headline="true">
      <div className="cargo-key-figures">
        <div>
          <span>{t("cargo.headline.cost")}</span>
          <strong data-figure="cost">{cargo.term === "FOB" ? `${fixed(cargo.cost_usd_mmbtu, 3)} USD/MMBtu` : best ? `${fixed(best.cost_per_mwh)} ${perMwh(best.currency)}` : "–"}</strong>
          {best && cargo.term === "FOB" && <small>= {fixed(best.cost_per_mwh)} {perMwh(best.currency)}</small>}
        </div>
        <div>
          <span>{t("cargo.headline.best")}</span>
          <strong data-figure="best">{best ? `${best.name} → ${best.hub}` : "–"}</strong>
          {cargo.no_winner && <small data-no-winner="true">{t("cargo.headline.no_winner")}</small>}
        </div>
        <div>
          <span>{t("cargo.headline.margin")}</span>
          <strong data-figure="margin">{best ? `${signed(best.margin_per_mwh)} ${perMwh(best.currency)}` : "–"}</strong>
          {best && <small>{t("cargo.headline.total", { total: millions(best.margin_total), currency: best.currency })}</small>}
        </div>
        {cargo.term === "FOB" && best && (
          <div>
            <span>{t("cargo.headline.lifting")}</span>
            <strong data-figure="lifting">{signed(best.lifting_margin_per_mwh)} {perMwh(best.currency)}</strong>
            <small>{t("cargo.headline.lifting_note")}</small>
          </div>
        )}
      </div>
      {parts.length > 0 && <p className="cargo-headline-basis">{parts.reduce<ReactNode[]>((all, part, index) => (index ? [...all, " · ", part] : [part]), [])}</p>}
      <p className="cargo-headline-basis">
        {t("cargo.headline.assumptions", { count: cargo.assumptions })}
        {entered.length > 0 && <> · <span data-entered="true">{t("cargo.headline.entered", { inputs: entered.join(", ") })}</span></>}
        {standard.length > 0 && <> · <span data-standard="true">{t("cargo.headline.standard", { inputs: standard.join(", ") })}</span></>}
      </p>
    </section>
  );
}

function TerminalTable({ cargo, priced, leftOut, selected, onSelect, reportingCurrency }: {
  cargo: CargoResultDTO; priced: CargoTerminalDTO[]; leftOut: CargoTerminalDTO[]; selected: string | null; onSelect: (id: string) => void;
  reportingCurrency: string;
}) {
  const { t } = useTranslation();
  // Several currencies: the server ranked the rows in the reporting currency at the stated FX.
  const reporting = priced.some((row) => row.margin_reporting_per_mwh != null) ? reportingCurrency : null;
  const leg = (row: CargoTerminalDTO, key: string) => row.legs.find((item) => item.key === key) ?? null;
  return (
    <section className="spreads-result" aria-label={t("cargo.table.title")}>
      <h2 className="spreads-section-title">{t("cargo.table.title")}</h2>
      {reporting && (
        <p className="cargo-note" data-ranked-in={reporting}>
          {t("cargo.table.ranked_in", { currencies: [...new Set(priced.map((row) => row.currency))].join(t("cargo.and")), reporting })}
        </p>
      )}
      <div className="spreads-table-wrap">
        <table className="spreads-table cargo-table" data-terminal-table="true">
          <caption>{t("cargo.table.caption")}</caption>
          <thead>
            <tr>
              <th scope="col">{t("cargo.table.terminal")}</th>
              <th scope="col" className="num">{t("cargo.table.hub")}</th>
              <th scope="col" className="num">{t("cargo.table.gas_in_kind")}</th>
              <th scope="col" className="num">{t("cargo.table.entry")}</th>
              <th scope="col" className="num">{t("cargo.table.regas")}</th>
              <th scope="col" className="num">{t("cargo.table.netback")}</th>
              <th scope="col" className="num">{t("cargo.table.margin")}</th>
              {reporting && <th scope="col" className="num">{t("cargo.table.margin_reporting", { unit: perMwh(reporting) })}</th>}
              <th scope="col" className="num">{t("cargo.table.range")}</th>
              {cargo.term === "FOB" && <th scope="col" className="num">USD/MMBtu</th>}
              <th scope="col" className="num">{t("cargo.table.total")}</th>
            </tr>
          </thead>
          <tbody>
            {priced.map((row) => {
              const hub = leg(row, "hub");
              const regas = leg(row, "regas");
              return (
                <tr key={row.terminal_id} data-terminal={row.terminal_id} aria-selected={row.terminal_id === selected} data-selected={row.terminal_id === selected || undefined}>
                  <th scope="row">
                    <button type="button" className="cargo-row-button" onClick={() => onSelect(row.terminal_id)} aria-pressed={row.terminal_id === selected}>
                      {row.name} → {row.hub}
                    </button>
                  </th>
                  <td className="num" title={hub?.source}>
                    <HubPrice row={row} amount={hub?.amount ?? null} /> {hub && <ClassMark inputClass={hub.input_class} />}
                  </td>
                  <td className="num">{fixed(leg(row, "gas_in_kind")?.amount, 1)} %</td>
                  <td className="num" title={leg(row, "entry")?.source}>{fixed(leg(row, "entry")?.amount)}</td>
                  <td className="num" title={regas?.source}>
                    {fixed(regas?.amount)} <span className="cargo-basis">{t(`cargo.regas.${row.regas_basis}`, { defaultValue: row.regas_basis })}</span>
                  </td>
                  <td className="num" data-figure="netback">{fixed(row.netback_per_mwh)}</td>
                  <td className="num" data-figure="margin"><strong>{signed(row.margin_per_mwh)}</strong> <span className="cargo-unit">{row.currency}</span></td>
                  {reporting && <td className="num" data-figure="margin-reporting">{signed(row.margin_reporting_per_mwh)}</td>}
                  <td className="num cargo-range">{fixed(row.margin_low_per_mwh)} … {fixed(row.margin_high_per_mwh)}</td>
                  {cargo.term === "FOB" && <td className="num">{signed(row.margin_usd_mmbtu, 3)}</td>}
                  <td className="num">{millions(row.margin_total)} {row.currency}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      {cargo.no_winner && <p className="cargo-note" data-no-winner="true">{t("cargo.table.no_winner")}</p>}
      {leftOut.length > 0 && (
        <ul className="cargo-left-out" data-left-out="true">
          {leftOut.map((row) => (
            <li key={row.terminal_id}>{row.name} → {row.hub}: {t(`cargo.reason.${row.reason}`, { defaultValue: row.reason ?? "" })}</li>
          ))}
        </ul>
      )}
    </section>
  );
}

/** The hub price as the desk quotes it (NBP in p/th), the per-MWh figure compared beside it. */
function HubPrice({ row, amount }: { row: CargoTerminalDTO; amount: number | null }) {
  const quote = hubQuote(row.hub, amount, row.currency);
  if (!quote.native) return <>{fixed(amount)} <span className="cargo-unit">{perMwh(row.currency)}</span></>;
  return (
    <span data-native-unit={unitLabel(quote.unit)}>
      {fixed(quote.value)} <span className="cargo-unit">{unitLabel(quote.unit)}</span>
      <span className="cargo-unit"> = {fixed(quote.perMwh)} {perMwh(row.currency)}</span>
    </span>
  );
}

function HistoryLine({ result, cargo }: { result: CargoEconomicsDTO; cargo: CargoResultDTO }) {
  const { t } = useTranslation();
  const history = result.delivered_spread_history!;
  const row = cargo.terminals.find((item) => item.terminal_id === history.terminal_id) ?? null;
  const chart = historyChart(history);
  const unit = perMwh(history.currency);
  const data = useMemo<ChartData>(() => ({
    axis: "gas-day",
    x: chart.x,
    xTitle: t("cargo.history.x"),
    unit,
    series: [
      { id: "hub", label: t("cargo.history.hub", { hub: history.hub }), values: chart.hub, simulated: chart.simulated, decimals: 2 },
      { id: "delivered", label: t("cargo.series.delivered"), values: chart.delivered, colour: 3, simulated: chart.simulated, decimals: 2 },
    ],
  }), [chart, history.hub, t, unit]);
  if (history.points.length === 0) {
    return (
      <p className="cargo-note" data-history="empty">
        {history.hh_days === 0 ? t("cargo.history.no_hh") : t("cargo.history.no_overlap", { hub: history.hub })}
      </p>
    );
  }
  const source = history.hh_source === "EIA" ? t("cargo.history.hh_eia") : t("cargo.history.hh_demo");
  return (
    <section className="spreads-result" data-history="true">
      <Chart
        id="cargo-hh-history"
        title={t("cargo.history.title", { hub: history.hub, terminal: row?.name ?? "", days: HISTORY_DAYS })}
        data={data}
        t={t}
        height={220}
        simulated={chart.simulated}
        note={`${t("cargo.history.note", { arb: signed(chart.last?.arb_per_mwh), unit, day: chart.last ? shortDay(chart.last.day) : "" })} ${source} ${history.fx ? `${history.fx}.` : ""}`}
      />
    </section>
  );
}

function MarginWaterfall({ row }: { row: CargoTerminalDTO }) {
  const { t } = useTranslation();
  const pills = useSimulatedPills();
  const items = marginWaterfall(row, {
    step: (key) => t(`cargo.step.${key}`),
    hub: (hub, month) => `${hub} ${monthLabel(month)}`,
  });
  if (items.length < 3) return null;
  return (
    <Waterfall
      id="cargo-margin-waterfall"
      title={t("cargo.waterfall.title", { terminal: row.name })}
      unit={perMwh(row.currency)}
      items={items.map((item) => ({ ...item, simulated: pills && item.simulated }))}
      t={t}
      decimals={2}
      simulated={!pills}
      note={row.fx_usd_per_unit ? t("cargo.waterfall.fx", { rate: fixed(row.fx_usd_per_unit, 4), pair: `${row.currency}/USD`, source: row.fx_source ?? "" }) : undefined}
    />
  );
}

function DeliveredSpread({ cargo, row }: { cargo: CargoResultDTO; row: CargoTerminalDTO }) {
  const { t } = useTranslation();
  const spread = row.delivered_spread!;
  const unit = perMwh(row.currency);
  return (
    <section className="cargo-spread" aria-label={t("cargo.spread.title", { hub: row.hub })} data-delivered-spread="true">
      <h2 className="spreads-section-title">{t("cargo.spread.title", { hub: row.hub })}</h2>
      <div className="cargo-spread-views">
        <div data-view="delivered">
          <h3>{t("cargo.spread.delivered", { hub: row.hub })}</h3>
          <p>{t("cargo.spread.delivered_line", { cost: fixed(spread.delivered_per_mwh), hub: row.hub, price: fixed(spread.hub_per_mwh), unit })}</p>
          <strong data-figure="arb">{t("cargo.spread.arb", { value: signed(spread.arb_per_mwh), unit })}</strong>
        </div>
        <div data-view="netback">
          <h3>{t("cargo.spread.netback")}</h3>
          <p>{t("cargo.spread.netback_line", { hub: row.hub, value: fixed(spread.fob_netback_usd_mmbtu, 3), fob: fixed(spread.fob_price_usd_mmbtu, 3) })}</p>
          <strong data-figure="netback-margin">{t("cargo.spread.netback_margin", { value: signed(spread.netback_margin_usd_mmbtu, 3) })}</strong>
          {cargo.lifting_price_usd_mmbtu !== cargo.fob_price_usd_mmbtu && (
            <small>{t("cargo.spread.lifting", { value: signed(spread.netback_lifting_margin_usd_mmbtu, 3), lifting: fixed(spread.lifting_price_usd_mmbtu, 3) })}</small>
          )}
        </div>
      </div>
      <p className="cargo-note" data-agree={Math.abs((spread.arb_total ?? 0) - (spread.netback_total ?? 0)) < 1 ? "true" : "false"}>
        {t("cargo.spread.agree", { total: millions(spread.arb_total), currency: row.currency })}
      </p>
    </section>
  );
}

function SpreadLine({ result, cargo }: { result: CargoEconomicsDTO; cargo: CargoResultDTO }) {
  const { t } = useTranslation();
  const series = result.delivered_spread_series!;
  const row = cargo.terminals.find((item) => item.terminal_id === series.terminal_id) ?? null;
  const chart = seriesChart(series);
  const unit = perMwh(row?.currency ?? "EUR");
  const hub = row?.hub ?? "";
  const hh = henryHub(cargo);
  const data = useMemo<ChartData>(() => ({
    axis: "period",
    x: chart.x,
    xTitle: t("cargo.series.x"),
    unit,
    series: [
      { id: "hub", label: hub, values: chart.hub, simulated: chart.simulated, decimals: 2 },
      { id: "delivered", label: t("cargo.series.delivered"), values: chart.delivered, colour: 3, decimals: 2 },
    ],
  }), [chart, hub, t, unit]);
  if (chart.priced === 0) return null;
  const hhBasis = !hh ? "" : hh.inputClass === "assumption" ? t("cargo.series.hh_entered") : hh.proxy ? t(hh.demo ? "cargo.series.hh_demo" : "cargo.series.hh_proxy") : t("cargo.series.hh_held");
  return (
    <section className="spreads-result" data-spread-series="true">
      <Chart
        id="cargo-delivered-spread"
        title={t("cargo.series.title", { hub, terminal: row?.name ?? "" })}
        data={data}
        t={t}
        height={220}
        simulated={chart.simulated}
        note={`${t("cargo.series.note")} ${hhBasis}`}
      />
    </section>
  );
}

function Sensitivity({ cargo, row }: { cargo: CargoResultDTO; row: CargoTerminalDTO }) {
  const { t } = useTranslation();
  const unit = perMwh(row.currency);
  return (
    <section className="spreads-result" data-sensitivity="true" aria-label={t("cargo.sens.title", { terminal: row.name })}>
      <h2 className="spreads-section-title">{t("cargo.sens.title", { terminal: row.name })}</h2>
      <div className="spreads-table-wrap">
      <table className="spreads-table cargo-sens">
        <thead>
          <tr>
            <th scope="col">{t("cargo.sens.input")}</th>
            <th scope="col" className="num">{t("cargo.sens.move")}</th>
            <th scope="col" className="num">{t("cargo.sens.change", { unit })}</th>
          </tr>
        </thead>
        <tbody>
          {(cargo.sensitivity ?? []).map((item) => (
            <tr key={item.key} data-sens={item.key}>
              <th scope="row">{item.key === "hub" ? t("cargo.sens.hub", { hub: row.hub }) : item.key === "fx" ? t("cargo.sens.fx", { pair: `${row.currency}/USD` }) : t(`cargo.sens.${item.key}`)}</th>
              <td className="num">{item.key === "hire" ? `+${item.bump.toLocaleString("en-GB")} USD/d` : item.key === "hub" ? `+${fixed(item.bump)} ${unit}` : item.key === "fx" ? `+${fixed(item.bump, 0)} %` : `+${fixed(item.bump)} USD/MMBtu`}</td>
              <td className="num">{signed(item.margin_change_per_mwh, 3)}</td>
            </tr>
          ))}
        </tbody>
      </table>
      </div>
    </section>
  );
}

/** From the cargo to the spread it trades against, and to a report about it. */
function CargoNextSteps({ cargo, row, arrival }: { cargo: CargoResultDTO; row: CargoTerminalDTO | null; arrival: string }) {
  const { t } = useTranslation();
  if (!row) return null;
  const search = typeof window === "undefined" ? "" : window.location.search;
  const hub = row.hub;
  const steps = [
    ...(hub !== "TTF"
      ? [{
          id: "spread",
          label: t("research.next.see_spread", { spread: `${hub} − TTF` }),
          href: spreadsSearch(search, {
            kind: "curve",
            legs: [{ hub, tenor: null, weight: 1 }, { hub: "TTF", tenor: null, weight: -1 }],
            unit: "EUR/MWh",
            fx: "forward",
            cost: { kind: "route_tariff", from_hub: "TTF", to_hub: hub },
          }),
        }]
      : []),
    {
      id: "report",
      label: t("research.next.add_report"),
      href: reportSearch(search, t("research.next.cargo_question", {
        term: cargo.term,
        terminal: row.name,
        hub,
        month: monthLabel(arrival),
      })),
    },
  ];
  return <NextSteps label={t("research.next.label")} steps={steps} />;
}

function InputsFold({ cargo, fxMethod }: { cargo: CargoResultDTO; fxMethod: string }) {
  const { t } = useTranslation();
  const money = (unit: string) => unit === "USD" || unit === "EUR" || unit === "GBP";
  return (
    <details className="cargo-more" data-inputs="true">
      <summary>{t("cargo.inputs.title", { count: cargo.assumptions })}</summary>
      <div className="spreads-table-wrap">
      <table className="spreads-table">
        <thead>
          <tr>
            <th scope="col">{t("cargo.inputs.step")}</th>
            <th scope="col" className="num">{t("cargo.inputs.value")}</th>
            <th scope="col">{t("cargo.inputs.class")}</th>
            <th scope="col">{t("cargo.inputs.source")}</th>
          </tr>
        </thead>
        <tbody>
          {cargo.legs.map((leg) => (
            <tr key={leg.key} data-leg={leg.key}>
              <th scope="row">{t(`cargo.leg.${leg.key}`, { defaultValue: leg.label })}</th>
              <td className="num">
                {leg.amount === null ? "–" : money(leg.unit) ? `${Math.round(leg.amount).toLocaleString("en-GB")} ${leg.unit}` : `${leg.amount.toLocaleString("en-GB", { maximumFractionDigits: 4 })} ${leg.unit === "x HH" ? "× HH" : leg.unit}`}
              </td>
              <td><ClassMark inputClass={leg.input_class} /></td>
              <td className="cargo-source">{leg.source}</td>
            </tr>
          ))}
        </tbody>
      </table>
      </div>
      {fxMethod && <p className="cargo-note">{t("cargo.inputs.fx", { method: fxMethod })}</p>}
    </details>
  );
}

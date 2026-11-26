/**
 * LNG-3 and LNG-4: the "Options" section of a cargo's plan sheet. The server re-optimises the
 * cargo's book around the disruption (`GET /api/lng/cargoes/{id}/disruption-options`): every
 * option ranked, each with its expected and worst P&L split into direct P&L and opportunity
 * cost, its flags (a contract it breaks, a cargo running to plan it moves, or that it cannot
 * physically happen), the consequences and which cargoes they hit, and a recommended set with
 * a reason for each. "Breakdown" lists each cost line with the price, rate and tariff sources it
 * applied. The FX picker chooses how a figure in another currency is converted (ECB by
 * default); the cargo's demurrage is shown in the contract's currency with the rate used.
 * "Berth rules" (2026-11-26) states each terminal's access rule as applied, recorded with its
 * citation or the default; quotes, approvals and another company's delay are worded from their
 * data in the reader's language, the server's sentence kept as the fallback.
 * "Choose" records the option a person picks (`POST .../choose`, audited): nothing is booked,
 * traded, nominated or sent. Styles: `cargo-options.css`, imported into `ds-components` by
 * `styles/design-system.css`.
 */
import { useMemo, useState } from "react";

import { api, type DisruptionFxQuery, type DisruptionLineDTO, type DisruptionOptionsDTO } from "@/api/client";
import { readKey, useCachedRead } from "@/app/data/readCache";
import { apiErrorDetailCode, describeFailure, presentError } from "@/app/experience/errorPresentation";
import {
  DEFAULT_FX,
  berthRuleLines,
  canChoose,
  consequences,
  costSplit,
  demurrageLine,
  fxQuery,
  lineSources,
  linesByBasis,
  optionRows,
  statusKey,
  timelineLine,
  type FxPicker,
  type OptionFlag,
  type OptionRow,
  type OptionStanding,
} from "@/app/model/disruptionOptionsModel";
import { formatAmount } from "@/app/time/valueFormat";
import { Button, Field, Instant, PeriodPicker, Skeleton, StatusBadge, type StatusTone } from "@/components/ui";
import { serverNotes, serverWarningText, warningKey } from "@/app/warningLabel";

type Translate = (key: string, options?: Record<string, unknown>) => string;

const TONE: Record<OptionStanding, StatusTone> = {
  recommended: "ok",
  frontier: "info",
  dominated: "neutral",
  infeasible: "breach",
};

/** A breach or an impossible option is red; what the option asks of others is to watch. */
const FLAG_TONE: Record<OptionFlag, StatusTone> = {
  contract_breach: "breach",
  not_possible: "breach",
  disrupts_normal_cargo: "watch",
  needs_terminal_approval: "watch",
  counterparty_quote_pending: "watch",
};

export function optionsKey(cargoId: string, fx?: DisruptionFxQuery): string {
  return readKey(`/lng/cargoes/${cargoId}/disruption-options`, { ...(fx ?? {}) });
}

function eur(value: number, language: string): string {
  const text = formatAmount(Math.abs(Math.round(value)), language);
  return value < 0 ? `−${text}` : text;
}

export function CargoOptionsPanel({ cargoId, t, language, canChooseOptions }: { cargoId: string; t: Translate; language: string; canChooseOptions: boolean }) {
  const [picker, setPicker] = useState<FxPicker>(DEFAULT_FX);
  const { query: fx, error: fxError } = fxQuery(picker);
  const read = useCachedRead(optionsKey(cargoId, fx), (signal) =>
    api.disruptionOptions(cargoId, { signal }, fx).then((response) => response.data),
  );
  const data = read.data ?? null;
  const failure = read.error ? presentError(t, describeFailure(read.error)) : null;
  const failureCode = read.error ? apiErrorDetailCode(read.error) : null;
  return (
    <div className="cargo-options" data-cargo-options="">
      <p className="cargo-plan-warning" role="note">{t("lng.cargo.options.advisory")}</p>
      <FxPickerFields picker={picker} onChange={setPicker} error={fxError} t={t} />
      {read.loading && !data && <Skeleton label={t("lng.cargo.options.loading")} rows={3} />}
      {failure && (
        <div className="cargo-board-error" role="alert">
          <strong>{failure.title}</strong>
          <span>{failureCode ? t(`lng.cargo.options.error.${failureCode}`, { defaultValue: failure.action }) : failure.action}</span>
          <Button variant="secondary" onClick={read.refresh}>{t("lng.cargo.retry")}</Button>
        </div>
      )}
      {data && <OptionsBody data={data} fx={fx} t={t} language={language} canChooseOptions={canChooseOptions} onChosen={read.refresh} />}
    </div>
  );
}

function FxPickerFields({ picker, onChange, error, t }: { picker: FxPicker; onChange: (next: FxPicker) => void; error: string | null; t: Translate }) {
  const set = (patch: Partial<FxPicker>) => onChange({ ...picker, ...patch });
  return (
    <fieldset className="cargo-options-fx">
      <legend>{t("lng.cargo.options.fx.title")}</legend>
      <Field label={t("lng.cargo.options.fx.source")} hint={t("lng.cargo.options.fx.source_hint")}>
        <select value={picker.source} onChange={(event) => set({ source: event.target.value as FxPicker["source"] })}>
          <option value="ECB">{t("lng.cargo.options.fx.ecb")}</option>
          <option value="WMR">WM/Reuters</option>
          <option value="BFIX">Bloomberg BFIX</option>
          <option value="manual">{t("lng.cargo.options.fx.manual")}</option>
        </select>
      </Field>
      <Field label={t("lng.cargo.options.fx.rate_date")} hint={t("lng.cargo.options.fx.rate_date_hint")}>
        <PeriodPicker label={t("lng.cargo.options.fx.rate_date")} value={picker.rateDate} clearable onChange={(value) => set({ rateDate: value })} />
      </Field>
      {picker.source === "manual" && (
        <>
          <Field label={t("lng.cargo.options.fx.rate", { currency: picker.rateCurrency })} error={error ? t(error) : undefined}>
            <input inputMode="decimal" value={picker.rate} onChange={(event) => set({ rate: event.target.value })} />
          </Field>
          <Field label={t("lng.cargo.options.fx.rate_currency")}>
            <select value={picker.rateCurrency} onChange={(event) => set({ rateCurrency: event.target.value as FxPicker["rateCurrency"] })}>
              <option value="USD">USD</option>
              <option value="GBP">GBP</option>
            </select>
          </Field>
        </>
      )}
      <Field label={t("lng.cargo.options.fx.reporting")}>
        <select value={picker.reporting} onChange={(event) => set({ reporting: event.target.value as FxPicker["reporting"] })}>
          <option value="EUR">EUR</option>
          <option value="GBP">GBP</option>
          <option value="USD">USD</option>
        </select>
      </Field>
    </fieldset>
  );
}

function Lines({ lines, t, language }: { lines: DisruptionLineDTO[]; t: Translate; language: string }) {
  return (
    <ul className="cargo-option-lines">
      {lines.map((line, index) => {
        const sources = lineSources(line);
        return (
          <li key={`${line.label}-${index}`}>
            <span className="cargo-option-line-text">{line.text}</span>
            <span className="cargo-option-line-value">{eur(line.value, language)} EUR</span>
            <span className="cargo-option-line-sources">{t("lng.cargo.options.sources", { sources: sources ?? t("lng.cargo.options.sources_none") })}</span>
          </li>
        );
      })}
    </ul>
  );
}

function Breakdown({ cargoId, optionId, fx, t, language }: { cargoId: string; optionId: string; fx?: DisruptionFxQuery; t: Translate; language: string }) {
  const read = useCachedRead(readKey(`/lng/cargoes/${cargoId}/disruption-options/${optionId}`, { ...(fx ?? {}) }), (signal) =>
    api.disruptionOption(cargoId, optionId, { signal }, fx).then((response) => response.data),
  );
  if (read.loading && !read.data) return <p className="muted" role="status">{t("lng.cargo.options.breakdown_loading")}</p>;
  if (read.error) return <p className="ds-field-error" role="alert">{presentError(t, describeFailure(read.error)).action}</p>;
  const grouped = linesByBasis(read.data?.arithmetic ?? []);
  return (
    <div className="cargo-option-breakdown">
      <h4>{t("lng.cargo.options.direct_lines")}</h4>
      <Lines lines={grouped.direct} t={t} language={language} />
      {grouped.opportunity.length > 0 && (
        <>
          <h4>{t("lng.cargo.options.opportunity_lines")}</h4>
          <Lines lines={grouped.opportunity} t={t} language={language} />
        </>
      )}
    </div>
  );
}

function OptionsBody({ data, fx, t, language, canChooseOptions, onChosen }: { data: DisruptionOptionsDTO; fx?: DisruptionFxQuery; t: Translate; language: string; canChooseOptions: boolean; onChosen: () => void }) {
  const rows = useMemo(() => optionRows(data), [data]);
  const [busy, setBusy] = useState<string | null>(null);
  const [open, setOpen] = useState<string | null>(null);
  const [note, setNote] = useState("");
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const demurrage = demurrageLine(data.demurrage);
  const berthRules = useMemo(() => berthRuleLines(data.berth_rules), [data.berth_rules]);
  const choose = (row: OptionRow) => {
    setBusy(row.option.option_id);
    setError(null);
    setMessage(null);
    api
      .chooseDisruptionOption(data.cargo.cargo_id, row.option.option_id, note.trim() || undefined, fx)
      .then((response) => {
        const breaks = response.data.consequences?.breaches?.length ?? 0;
        setMessage(
          t(response.data.was_recommended ? "lng.cargo.options.chosen" : "lng.cargo.options.chosen_not_default", {
            title: response.data.title,
          }) + (breaks ? ` ${t("lng.cargo.options.chosen_breaks", { count: breaks })}` : ""),
        );
        setNote("");
        onChosen();
      })
      .catch((caught: unknown) => {
        const code = apiErrorDetailCode(caught);
        const fallback = presentError(t, describeFailure(caught)).action;
        setError(code ? t(`lng.cargo.options.error.${code}`, { defaultValue: fallback }) : fallback);
      })
      .finally(() => setBusy(null));
  };

  return (
    <>
      <section className="cargo-plan-section" aria-labelledby="cargo-options-status">
        <h3 id="cargo-options-status">{t(statusKey(data.status))}</h3>
        {data.disrupted.length > 0 && (
          <ul className="cargo-options-disrupted">
            {data.disrupted.map((supply) => (
              <li key={supply.supply_id}>
                {supply.label}
                {supply.arrival ? ` · ${t("lng.cargo.options.arrives", { day: supply.arrival })}` : ""}
                {supply.terminal ? ` · ${supply.terminal}` : ""}
              </li>
            ))}
          </ul>
        )}
        <p className="cargo-board-sub">
          {t("lng.cargo.options.preference", {
            weight: formatAmount(data.preference.risk_weight, language, 2),
            count: data.book_options,
          })}
        </p>
        {(demurrage.original || demurrage.warning) && (
          <p className="cargo-board-sub" data-demurrage="">
            {demurrage.original &&
              t("lng.cargo.options.demurrage", {
                original: demurrage.original,
                eur: demurrage.eurPerDay === null ? "—" : formatAmount(Math.round(demurrage.eurPerDay), language),
                source: demurrage.source ?? "",
              })}
            {demurrage.rate && <> · {t("lng.cargo.options.demurrage_rate", { rate: demurrage.rate })}</>}
            {demurrage.warning && <> · {demurrage.warning}</>}
          </p>
        )}
        {data.decision && (
          <p className="cargo-options-decision" role="status">
            {t("lng.cargo.options.last_choice", { title: data.decision.title })} · <Instant value={data.decision.decided_at_utc} date="always" />
            {!data.decision.was_recommended && <> · {t("lng.cargo.options.not_default")}</>}
          </p>
        )}
      </section>

      {(data.recommended_set?.length ?? 0) > 0 && (
        <section className="cargo-plan-section" aria-labelledby="cargo-options-recommended">
          <h3 id="cargo-options-recommended">{t("lng.cargo.options.recommended_set")}</h3>
          <ul className="cargo-option-reasons">
            {data.recommended_set?.map((item) => (
              <li key={`${item.basis}-${item.option_id}`}>
                <strong>{t(`lng.cargo.options.basis.${item.basis}`, { defaultValue: item.basis })}</strong>: {item.title} · {item.reason}
              </li>
            ))}
          </ul>
          {data.valuation && <p className="cargo-board-sub">{data.valuation}</p>}
        </section>
      )}

      {rows.length > 0 && (
        <section className="cargo-plan-section" aria-labelledby="cargo-options-list">
          <h3 id="cargo-options-list">{t("lng.cargo.options.title")}</h3>
          {canChooseOptions && (
            <Field label={t("lng.cargo.options.note")} hint={t("lng.cargo.options.note_hint")}>
              <input maxLength={2000} value={note} onChange={(event) => setNote(event.target.value)} />
            </Field>
          )}
          {!canChooseOptions && <p className="cargo-plan-warning" role="note">{t("lng.cargo.options.read_only")}</p>}
          <ol className="cargo-options-list">
            {rows.map((row) => {
              const split = costSplit(row.option);
              const lines = consequences(row.option);
              return (
                <li key={row.option.option_id} className="cargo-option" data-standing={row.standing}>
                  <div className="cargo-option-head">
                    {typeof row.option.rank === "number" && <span className="cargo-option-rank">#{row.option.rank}</span>}
                    <StatusBadge tone={TONE[row.standing]}>{t(`lng.cargo.options.standing.${row.standing}`)}</StatusBadge>
                    {row.flags.map((flag) => (
                      <StatusBadge key={flag} tone={FLAG_TONE[flag]}>
                        {t(`lng.cargo.options.flag.${flag}`)}
                      </StatusBadge>
                    ))}
                    <span className="cargo-option-kind">{t(`lng.cargo.options.kind.${row.kind}`)}</span>
                    <strong className="cargo-option-title">{row.option.title}</strong>
                  </div>
                  {row.recommended.map((item) => (
                    <p key={item.basis} className="cargo-option-note" data-recommended={item.basis}>
                      {t("lng.cargo.options.recommended_as", { basis: t(`lng.cargo.options.basis.${item.basis}`, { defaultValue: item.basis }), reason: item.reason })}
                    </p>
                  ))}
                  <dl className="cargo-option-figures">
                    <div><dt>{t("lng.cargo.options.expected")}</dt><dd>{eur(split.pnl, language)} EUR</dd></div>
                    <div><dt>{t("lng.cargo.options.direct")}</dt><dd>{eur(split.direct, language)} EUR</dd></div>
                    <div><dt>{t("lng.cargo.options.opportunity")}</dt><dd>{eur(-split.opportunity, language)} EUR</dd></div>
                    <div><dt>{t("lng.cargo.options.worst")}</dt><dd>{eur(row.option.objectives.pnl_worst, language)} EUR</dd></div>
                    <div><dt>{t("lng.cargo.options.cost")}</dt><dd>{eur(row.option.objectives.cost, language)} EUR</dd></div>
                    <div><dt>{t("lng.cargo.options.spare")}</dt><dd>{formatAmount(row.option.objectives.flexibility_mwh, language)} MWh</dd></div>
                    <div><dt>{t("lng.cargo.options.moved")}</dt><dd>{formatAmount(row.option.objectives.disrupted_mwh, language)} MWh</dd></div>
                    {row.range && (
                      <div><dt>{t("lng.cargo.options.range")}</dt><dd>{eur(row.range.low, language)} … {eur(row.range.high, language)} EUR</dd></div>
                    )}
                  </dl>
                  {lines.length > 0 && (
                    <ul className="cargo-option-consequences" aria-label={t("lng.cargo.options.consequences")}>
                      {lines.map((line, index) => (
                        <li key={`${line.kind}-${index}`} data-kind={line.kind}>
                          <strong>{t(`lng.cargo.options.consequence.${line.kind}`)}</strong>:{" "}
                          {line.i18n ? t(`lng.cargo.options.${line.i18n.key}`, { ...line.i18n.params, defaultValue: line.text }) : line.text}
                          {line.value !== null && line.value !== 0 && <> · {eur(line.value, language)} EUR</>}
                          {line.sources.length > 0 && <> · {t("lng.cargo.options.sources", { sources: line.sources.join("; ") })}</>}
                        </li>
                      ))}
                    </ul>
                  )}
                  {row.beatenBy && (
                    <p className="cargo-option-note">{t("lng.cargo.options.beaten_by", { title: row.beatenBy.title, where: row.beatenBy.where.join(", ") })}</p>
                  )}
                  {row.option.reasons.length > 0 && (
                    <ul className="cargo-option-reasons">
                      {row.option.reasons.map((reason) => <li key={reason}>{reason}</li>)}
                    </ul>
                  )}
                  {row.option.notes.length > 0 && (
                    <ul className="cargo-option-notes">
                      {row.option.notes.map((text) => <li key={text}>{text}</li>)}
                    </ul>
                  )}
                  <div className="cargo-option-actions">
                    <Button
                      variant="secondary"
                      aria-expanded={open === row.option.option_id}
                      onClick={() => setOpen(open === row.option.option_id ? null : row.option.option_id)}
                    >
                      {t(open === row.option.option_id ? "lng.cargo.options.breakdown_hide" : "lng.cargo.options.breakdown")}
                    </Button>
                    {canChooseOptions && canChoose(row.option, true, false) && (
                      <Button
                        variant={row.standing === "recommended" ? "primary" : "secondary"}
                        onClick={() => choose(row)}
                        loading={busy === row.option.option_id}
                        disabled={!canChoose(row.option, canChooseOptions, busy !== null)}
                      >
                        {t("lng.cargo.options.choose")}
                      </Button>
                    )}
                  </div>
                  {open === row.option.option_id && (
                    <Breakdown cargoId={data.cargo.cargo_id} optionId={row.option.option_id} fx={fx} t={t} language={language} />
                  )}
                </li>
              );
            })}
          </ol>
          {message && <p role="status">{message}</p>}
          {error && <p className="ds-field-error" role="alert">{error}</p>}
          <p className="cargo-board-sub">{t("lng.cargo.options.audit")}</p>
        </section>
      )}

      {berthRules.length > 0 && (
        <section className="cargo-plan-section" aria-labelledby="cargo-options-berth-rules" data-berth-rules="">
          <details className="cargo-options-fold">
            <summary>
              <h3 id="cargo-options-berth-rules">{t("lng.cargo.options.berth_rules")}</h3>
            </summary>
            <ul className="cargo-option-notes">
              {berthRules.map((rule) => (
                <li key={rule.terminals.join("|")} data-basis={rule.basisKey}>
                  <strong>{rule.terminals.join(", ")}</strong> · {t(`lng.cargo.options.berth_rule.${rule.basisKey}`)}
                  {rule.citation ? ` [${rule.citation}]` : ""}
                  <ul>
                    <li>{t("lng.cargo.options.berth_rule.window", { count: rule.windowDays })}</li>
                    <li>{t(`lng.cargo.options.berth_rule.${rule.laytimeKey}`)}</li>
                    <li>{t(rule.approval ? "lng.cargo.options.berth_rule.approval_yes" : "lng.cargo.options.berth_rule.approval_no")}</li>
                    {rule.wording && <li>{t("lng.cargo.options.berth_rule.wording", { text: rule.wording })}</li>}
                  </ul>
                </li>
              ))}
            </ul>
          </details>
        </section>
      )}

      {(data.pipeline_outages?.length ?? 0) > 0 && (
        <section className="cargo-plan-section" aria-labelledby="cargo-options-outages">
          <h3 id="cargo-options-outages">{t("lng.cargo.options.outages")}</h3>
          <ul className="cargo-option-notes">
            {data.pipeline_outages?.map((supply) => (
              <li key={supply.supply_id}>
                <strong>{supply.label}</strong> · {t(`lng.cargo.options.outage_mode.${supply.outage_mode}`)}
                <ul>
                  {supply.links.map((link) => (
                    <li key={link.link_id}>
                      {t("lng.cargo.options.outage_link", {
                        message: link.message_id,
                        version: link.version,
                        status: t(`lng.cargo.options.outage_status.${link.status}`),
                        mwh: formatAmount(link.curtailed_mwh, language),
                      })}
                      {" · "}
                      {link.why}
                    </li>
                  ))}
                </ul>
              </li>
            ))}
          </ul>
          <p className="cargo-board-sub">{t("lng.cargo.options.outages_advisory")}</p>
        </section>
      )}

      {data.timeline.length > 0 && (
        <section className="cargo-plan-section" aria-labelledby="cargo-options-timeline">
          <h3 id="cargo-options-timeline">{t("lng.cargo.options.timeline")}</h3>
          <ol className="cargo-options-timeline">
            {data.timeline.map((run) => {
              const line = timelineLine(run);
              return (
                <li key={run.run_id}>
                  <Instant value={run.computed_at_utc} date="always" /> · {t(line.changeKey)}
                  {run.recommended_title ? ` · ${run.recommended_title}` : ""}
                  {line.told ? ` · ${t("lng.cargo.options.told")}` : ""}
                </li>
              );
            })}
          </ol>
        </section>
      )}

      {data.warnings.length > 0 && (
        <section className="cargo-plan-section" aria-labelledby="cargo-options-warnings">
          <h3 id="cargo-options-warnings">{t("lng.cargo.options.warnings")}</h3>
          <ul className="cargo-option-notes">
            {serverNotes(data).map((item) => <li key={warningKey(item)} title={warningKey(item)}>{serverWarningText(item, t)}</li>)}
          </ul>
        </section>
      )}
    </>
  );
}

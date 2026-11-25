/**
 * LNG-3: the "Options" section of a cargo's plan sheet. The server re-optimises the cargo's
 * book around the disruption (`GET /api/lng/cargoes/{id}/disruption-options`): each option
 * valued against the plan over the scenarios, the Pareto frontier, the dominated options with
 * who beats them and where, the options a hard constraint rules out and why, and a default by
 * the desk's stated preference. "Choose" records the option a person picks (`POST .../choose`,
 * audited): nothing is booked, traded, nominated or sent. Styles: `cargo-options.css`, imported
 * into `ds-components` by `styles/design-system.css`.
 */
import { useMemo, useState } from "react";

import { api, type DisruptionOptionsDTO } from "@/api/client";
import { readKey, useCachedRead } from "@/app/data/readCache";
import { apiErrorDetailCode, describeFailure, presentError } from "@/app/experience/errorPresentation";
import { canChoose, optionRows, statusKey, timelineLine, type OptionRow, type OptionStanding } from "@/app/model/disruptionOptionsModel";
import { formatAmount } from "@/app/time/valueFormat";
import { Button, Field, Instant, StatusBadge, type StatusTone } from "@/components/ui";

type Translate = (key: string, options?: Record<string, unknown>) => string;

const TONE: Record<OptionStanding, StatusTone> = {
  recommended: "ok",
  frontier: "info",
  dominated: "neutral",
  infeasible: "breach",
};

export function optionsKey(cargoId: string): string {
  return readKey(`/lng/cargoes/${cargoId}/disruption-options`);
}

function eur(value: number, language: string): string {
  const text = formatAmount(Math.abs(Math.round(value)), language);
  return value < 0 ? `−${text}` : text;
}

export function CargoOptionsPanel({ cargoId, t, language, canChooseOptions }: { cargoId: string; t: Translate; language: string; canChooseOptions: boolean }) {
  const read = useCachedRead(optionsKey(cargoId), (signal) =>
    api.disruptionOptions(cargoId, { signal }).then((response) => response.data),
  );
  const data = read.data ?? null;
  const failure = read.error ? presentError(t, describeFailure(read.error)) : null;
  return (
    <div className="cargo-options" data-cargo-options="">
      <p className="cargo-plan-warning" role="note">{t("lng.cargo.options.advisory")}</p>
      {read.loading && !data && <p className="muted" role="status">{t("lng.cargo.options.loading")}</p>}
      {failure && (
        <div className="cargo-board-error" role="alert">
          <strong>{failure.title}</strong>
          <span>{failure.action}</span>
          <Button variant="secondary" onClick={read.refresh}>{t("lng.cargo.retry")}</Button>
        </div>
      )}
      {data && <OptionsBody data={data} t={t} language={language} canChooseOptions={canChooseOptions} onChosen={read.refresh} />}
    </div>
  );
}

function OptionsBody({ data, t, language, canChooseOptions, onChosen }: { data: DisruptionOptionsDTO; t: Translate; language: string; canChooseOptions: boolean; onChosen: () => void }) {
  const rows = useMemo(() => optionRows(data), [data]);
  const [busy, setBusy] = useState<string | null>(null);
  const [note, setNote] = useState("");
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const choose = (row: OptionRow) => {
    setBusy(row.option.option_id);
    setError(null);
    setMessage(null);
    api
      .chooseDisruptionOption(data.cargo.cargo_id, row.option.option_id, note.trim() || undefined)
      .then((response) => {
        setMessage(
          t(response.data.was_recommended ? "lng.cargo.options.chosen" : "lng.cargo.options.chosen_not_default", {
            title: response.data.title,
          }),
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
        {data.decision && (
          <p className="cargo-options-decision" role="status">
            {t("lng.cargo.options.last_choice", { title: data.decision.title })} · <Instant value={data.decision.decided_at_utc} date="always" />
            {!data.decision.was_recommended && <> · {t("lng.cargo.options.not_default")}</>}
          </p>
        )}
      </section>

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
            {rows.map((row) => (
              <li key={row.option.option_id} className="cargo-option" data-standing={row.standing}>
                <div className="cargo-option-head">
                  <StatusBadge tone={TONE[row.standing]}>{t(`lng.cargo.options.standing.${row.standing}`)}</StatusBadge>
                  <span className="cargo-option-kind">{t(`lng.cargo.options.kind.${row.kind}`)}</span>
                  <strong className="cargo-option-title">{row.option.title}</strong>
                </div>
                <dl className="cargo-option-figures">
                  <div><dt>{t("lng.cargo.options.expected")}</dt><dd>{eur(row.option.objectives.pnl_expected, language)} EUR</dd></div>
                  <div><dt>{t("lng.cargo.options.worst")}</dt><dd>{eur(row.option.objectives.pnl_worst, language)} EUR</dd></div>
                  <div><dt>{t("lng.cargo.options.cost")}</dt><dd>{eur(row.option.objectives.cost, language)} EUR</dd></div>
                  <div><dt>{t("lng.cargo.options.spare")}</dt><dd>{formatAmount(row.option.objectives.flexibility_mwh, language)} MWh</dd></div>
                  <div><dt>{t("lng.cargo.options.moved")}</dt><dd>{formatAmount(row.option.objectives.disrupted_mwh, language)} MWh</dd></div>
                  {row.range && (
                    <div><dt>{t("lng.cargo.options.range")}</dt><dd>{eur(row.range.low, language)} … {eur(row.range.high, language)} EUR</dd></div>
                  )}
                </dl>
                {row.option.affects_other_supplies.length > 0 && (
                  <p className="cargo-option-note">{t("lng.cargo.options.disturbs", { supplies: row.option.affects_other_supplies.join(", ") })}</p>
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
                {canChooseOptions && row.option.feasible && (
                  <div className="cargo-option-actions">
                    <Button
                      variant={row.standing === "recommended" ? "primary" : "secondary"}
                      onClick={() => choose(row)}
                      loading={busy === row.option.option_id}
                      disabled={!canChoose(row.option, canChooseOptions, busy !== null)}
                    >
                      {t("lng.cargo.options.choose")}
                    </Button>
                  </div>
                )}
              </li>
            ))}
          </ol>
          {message && <p role="status">{message}</p>}
          {error && <p className="ds-field-error" role="alert">{error}</p>}
          <p className="cargo-board-sub">{t("lng.cargo.options.audit")}</p>
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
            {data.warnings.map((text) => <li key={text}>{text}</li>)}
          </ul>
        </section>
      )}
    </>
  );
}

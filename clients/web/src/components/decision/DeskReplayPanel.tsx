/**
 * Outage response replay (#48-#50): one book, hub and gas day as it was knowable.
 *
 * The desk loads normalized evidence exported by its ETRM and TSO adapters (positions,
 * versioned outages, evaluated responses). Only revisions available at the declared as-of
 * instant count. Each resource shows what was committed, what remains deliverable after the
 * outage, the gap if the plan is kept, and every response with what it covers or why it is
 * blocked. Missing evidence is shown as unknown, never as zero. The result carries an input
 * fingerprint and can be cited by a decision case; nothing is executed.
 */
import { useState } from "react";
import {
  api,
  type DecisionCaseSummaryDTO,
  type DeskReplayResultDTO,
} from "@/api/client";
import { EmptyState, PanelHeader } from "@/components/ui";

type Translate = (key: string) => string;

function quantity(value: string | null | undefined, t: Translate): string {
  if (value === null || value === undefined) return t("desk_replay.unknown");
  const number = Number(value);
  return Number.isFinite(number) ? `${number.toLocaleString(undefined, { maximumFractionDigits: 1 })} MWh` : value;
}

export function DeskReplayPanel({ t }: { t: Translate }) {
  const [evidenceText, setEvidenceText] = useState("");
  const [result, setResult] = useState<DeskReplayResultDTO | null>(null);
  const [failure, setFailure] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [cases, setCases] = useState<DecisionCaseSummaryDTO[] | null>(null);
  const [caseId, setCaseId] = useState("");
  const [attached, setAttached] = useState<string | null>(null);

  const run = async () => {
    setFailure(null);
    setAttached(null);
    let evidence: unknown;
    try {
      evidence = JSON.parse(evidenceText);
    } catch {
      setFailure(t("desk_replay.invalid_json"));
      return;
    }
    setBusy(true);
    try {
      const response = await api.deskReplay(evidence);
      setResult(response.data);
      if (cases === null) {
        api.decisionCases({ limit: "50" })
          .then((listed) => setCases(listed.data.filter((row) => row.status !== "DECIDED")))
          .catch(() => setCases([]));
      }
    } catch (caught) {
      setFailure(caught instanceof Error ? caught.message : String(caught));
    } finally {
      setBusy(false);
    }
  };

  const attach = async () => {
    if (!result || !caseId) return;
    setBusy(true);
    try {
      const frozen = result.frozen_inputs as { book_id?: string; hub_id?: string; gas_day?: string; as_of?: string };
      await api.attachDecisionCaseEvidence(caseId, {
        kind: "SCENARIO",
        ref: `desk-replay:${result.input_sha256}`,
        label: `${t("desk_replay.title")} ${frozen.book_id ?? ""} ${frozen.hub_id ?? ""} ${frozen.gas_day ?? ""}`.trim(),
        as_of_utc: frozen.as_of ?? "",
      });
      setAttached(caseId);
    } catch (caught) {
      setFailure(caught instanceof Error ? caught.message : String(caught));
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="workspace-panel span-3 desk-replay-panel" aria-labelledby="desk-replay-title">
      <PanelHeader title={<span id="desk-replay-title">{t("desk_replay.title")}</span>} meta={t("desk_replay.assessment_only")} />
      <details className="scope-fold">
        <summary>{t("desk_replay.how")}</summary>
        <p className="panel-copy">{t("desk_replay.help")}</p>
      </details>
      <div className="desk-replay-input">
        <label>
          <span>{t("desk_replay.file")}</span>
          <input
            type="file"
            accept="application/json,.json"
            onChange={(event) => {
              const file = event.target.files?.[0];
              if (file) void file.text().then(setEvidenceText);
            }}
          />
        </label>
        <label>
          <span>{t("desk_replay.evidence")}</span>
          <textarea
            rows={4}
            value={evidenceText}
            spellCheck={false}
            onChange={(event) => setEvidenceText(event.target.value)}
          />
        </label>
        <button type="button" className="button-primary" disabled={busy || !evidenceText.trim()} onClick={() => void run()}>
          {t("desk_replay.run")}
        </button>
      </div>
      {failure && <p role="alert">{failure}</p>}
      {result && result.resources.length === 0 && (
        <EmptyState reason={t("desk_replay.no_resources")} next={t("desk_replay.no_resources_next")} />
      )}
      {result && result.resources.length > 0 && (
        <div className="desk-replay-result" data-desk-replay="result">
          <p className="muted">
            {t("desk_replay.window")}: {result.delivery_start} → {result.delivery_end} ·{" "}
            <code title={result.input_sha256}>{result.input_sha256.slice(0, 12)}</code>
          </p>
          {result.unmatched_record_ids.length > 0 && (
            <p className="desk-replay-unmatched">
              {t("desk_replay.unmatched")}: {result.unmatched_record_ids.join(", ")}
            </p>
          )}
          {result.resources.map((resource) => (
            <article key={resource.resource_id} className="desk-replay-resource">
              <h3>{resource.resource_id}</h3>
              <dl className="desk-replay-facts">
                <div><dt>{t("desk_replay.committed")}</dt><dd>{quantity(resource.committed_mwh, t)}</dd></div>
                <div><dt>{t("desk_replay.outage_loss")}</dt><dd>{quantity(resource.outage_loss_mwh, t)}</dd></div>
                <div><dt>{t("desk_replay.deliverable")}</dt><dd>{quantity(resource.deliverable_mwh, t)}</dd></div>
                <div><dt>{t("desk_replay.prior_gap")}</dt><dd>{quantity(resource.prior_gap_mwh, t)}</dd></div>
                <div><dt>{t("desk_replay.gap")}</dt><dd><strong>{quantity(resource.keep_plan_gap_mwh, t)}</strong></dd></div>
              </dl>
              <ul className="desk-replay-alternatives">
                {resource.alternatives.map((alternative) => (
                  <li key={alternative.record_id} data-blocked={alternative.blocked ? "true" : undefined}>
                    <strong>{t(`desk_replay.kind.${alternative.kind}`)}</strong>{" "}
                    <small className="muted">{alternative.record_id}</small>
                    {alternative.blocked ? (
                      <span className="desk-replay-blocked">
                        {alternative.blocked.map((reason) => t(`desk_replay.blocked.${reason}`)).join(" · ")}
                      </span>
                    ) : (
                      <span>
                        {quantity(alternative.quantity_mwh, t)} · {t("desk_replay.cost")} {Number(alternative.incremental_cost).toLocaleString()} ·{" "}
                        {t("desk_replay.left")} {quantity(alternative.remaining_gap_mwh, t)} · {t("desk_replay.by")} {alternative.action_deadline}
                      </span>
                    )}
                  </li>
                ))}
              </ul>
            </article>
          ))}
          {cases && cases.length > 0 && (
            <div className="desk-replay-attach">
              <label>
                <span>{t("desk_replay.attach_to")}</span>
                <select value={caseId} onChange={(event) => setCaseId(event.target.value)}>
                  <option value="">{t("desk_replay.choose_case")}</option>
                  {cases.map((row) => <option key={row.case_id} value={row.case_id}>{row.objective}</option>)}
                </select>
              </label>
              <button type="button" disabled={busy || !caseId} onClick={() => void attach()}>{t("desk_replay.attach")}</button>
              {attached && <span role="status">{t("desk_replay.attached")}</span>}
            </div>
          )}
        </div>
      )}
    </section>
  );
}

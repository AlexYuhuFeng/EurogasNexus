import { formatUtcTimestamp } from "@/app/model/evidencePresentation";
import {
  snapshotStateLabelKey,
  type DecisionPackContextValue,
  type DecisionPackPresentation,
} from "@/app/model/decisionPackModel";

type Translate = (key: string) => string;

interface DecisionPackPanelProps {
  readonly t: Translate;
  /**
   * The pack as the surface reads it. The panel renders this and claims nothing of its own: it
   * fetches nothing, recomputes no hash and decides nothing the model has not already established.
   */
  readonly model: DecisionPackPresentation;
}

/** A context value in its own kind: text, a declared instant, a declared state, or nothing said. */
function contextValueText(value: DecisionPackContextValue, t: Translate): string {
  switch (value.kind) {
    case "text":
      return value.value;
    case "instant":
      return formatUtcTimestamp(value.value);
    case "state":
      return t(value.stateKey);
    default:
      return t("decision_pack.not_recorded");
  }
}

/**
 * The decision pack: the artefact a reviewer signs, beside the case's decision controls.
 *
 * It exists because the platform recorded everything a decision needs and none of it in a form a
 * reviewer could sign off on: the context, the evidence with each snapshot's resolvability
 * *measured*, the assumptions, the alternatives, the AI findings, the warnings, the human decision
 * with its actor, the acts recorded against the case, and a content hash over all of it. Assembling
 * that by hand from four reads is the work that gets skipped under deadline.
 *
 * Three things it is careful about:
 *
 * - the snapshot verdict is three-valued and rendered as three different states. `unresolved` is a
 *   hole in the record and looks like one; `not-cited` means the reference claims no snapshot at
 *   all, which is not the same statement and is not rendered as one;
 * - the blockers are rendered whole. The ones the pack itself computed get their own copy, and the
 *   case's own codes - or a code this client does not know - are shown as the raw code, because an
 *   unrecognised blocker is information rather than noise;
 * - it signs nothing, stores nothing and sends nothing. It is a read of the artefact, with the
 *   hash left selectable so a printed copy can be matched to the platform's record by hand.
 */
export function DecisionPackPanel({ t, model }: DecisionPackPanelProps) {
  return (
    <section className="decision-pack" aria-label={t("decision_pack.title")}>
      <div className="panel-title-row decision-pack-heading">
        <div>
          <span className="eyebrow">{t("decision_pack.eyebrow")}</span>
          <h3>{t("decision_pack.title")}</h3>
        </div>
        <span className="decision-pack-basis">
          {model.objective ?? t("decision_pack.objective_absent")}
          {model.statusLabelKey && model.status ? ` · ${t(model.statusLabelKey)}` : ""}
          {model.version ? ` · ${t("decision_pack.version")} ${model.version}` : ""}
        </span>
      </div>

      {!model.canShow ? (
        // Not shown is a statement, not an empty artefact: a case read with no pack (an older
        // deployment, or a read that failed) says so where the pack would have been.
        <p className="decision-pack-unavailable">
          {t(model.reasonKey ?? "decision_pack.unavailable.no_pack")}
        </p>
      ) : (
        <>
          <div className="decision-pack-section decision-pack-context">
            <h4>{t("decision_pack.context.title")}</h4>
            <dl className="decision-pack-facts">
              {model.context.map((row) => (
                <div key={row.labelKey}>
                  <dt>{t(row.labelKey)}</dt>
                  <dd>{contextValueText(row.value, t)}</dd>
                </div>
              ))}
            </dl>
          </div>

          <div className="decision-pack-section decision-pack-evidence">
            <h4>{t("decision_pack.evidence.title")}</h4>
            {model.evidence.length === 0 ? (
              <p className="decision-pack-none">{t("decision_pack.evidence.none")}</p>
            ) : (
              <ul className="decision-pack-evidence-list">
                {model.evidence.map((row) => (
                  <li key={`${row.kind}:${row.ref}`}>
                    <div className="decision-pack-evidence-head">
                      <strong>{t(row.kindLabelKey)}</strong>
                      <code className="decision-pack-ref">{row.ref}</code>
                    </div>
                    {row.label && <p className="decision-pack-evidence-label">{row.label}</p>}
                    <dl className="decision-pack-facts">
                      <div>
                        <dt>{t("decision_pack.evidence.as_of")}</dt>
                        <dd>
                          {row.asOfUtc
                            ? formatUtcTimestamp(row.asOfUtc)
                            : t("decision_pack.not_recorded")}
                        </dd>
                      </div>
                      <div>
                        <dt>{t("decision_pack.evidence.snapshot_id")}</dt>
                        <dd>
                          <code>{row.snapshotId ?? t("decision_pack.evidence.no_snapshot")}</code>
                        </dd>
                      </div>
                    </dl>
                    {/*
                      The verdict the pack measured, as its own word and its own class: a reference
                      whose snapshot is not on record has to look different from one that cites no
                      snapshot, because the first is a hole and the second is not a claim at all.
                    */}
                    <p className={`decision-pack-snapshot is-${row.snapshotState}`}>
                      {t(snapshotStateLabelKey(row.snapshotState))}
                    </p>
                  </li>
                ))}
              </ul>
            )}
          </div>

          <div className="decision-pack-section decision-pack-assumptions">
            <h4>{t("decision_pack.assumptions.title")}</h4>
            {model.assumptions.length === 0 ? (
              <p className="decision-pack-none">{t("decision_pack.assumptions.none")}</p>
            ) : (
              <ul className="decision-pack-list">
                {model.assumptions.map((row) => (
                  <li key={row.key}>
                    <code>{row.key}</code>
                    <span> = {row.value}</span>
                    {row.source && (
                      <small>
                        {" "}
                        {t("decision_pack.assumptions.source")} {row.source}
                      </small>
                    )}
                    {row.note && <p>{row.note}</p>}
                  </li>
                ))}
              </ul>
            )}
          </div>

          <div className="decision-pack-section decision-pack-alternatives">
            <h4>{t("decision_pack.alternatives.title")}</h4>
            {model.alternatives.length === 0 ? (
              <p className="decision-pack-none">{t("decision_pack.alternatives.none")}</p>
            ) : (
              <ul className="decision-pack-list">
                {model.alternatives.map((row) => (
                  <li key={row.alternativeId}>
                    <strong>{row.label || row.alternativeId}</strong>
                    {row.description && <p>{row.description}</p>}
                    <small>
                      {t("decision_pack.alternatives.economics")} {row.economicsRef || t("decision_pack.not_recorded")}
                    </small>
                    {row.warnings.length > 0 && (
                      <p className="decision-pack-warnings">
                        {t("decision_pack.alternatives.warnings")}: {row.warnings.join(", ")}
                      </p>
                    )}
                  </li>
                ))}
              </ul>
            )}
          </div>

          <div className="decision-pack-section decision-pack-findings">
            <h4>{t("decision_pack.ai_findings.title")}</h4>
            {model.aiFindings.length === 0 ? (
              <p className="decision-pack-none">{t("decision_pack.ai_findings.none")}</p>
            ) : (
              <ul className="decision-pack-list">
                {model.aiFindings.map((finding) => (
                  <li key={finding}>{finding}</li>
                ))}
              </ul>
            )}
          </div>

          <div className="decision-pack-section decision-pack-warnings">
            <h4>{t("decision_pack.warnings.title")}</h4>
            {model.warnings.length === 0 ? (
              <p className="decision-pack-none">{t("decision_pack.warnings.none")}</p>
            ) : (
              <ul className="decision-pack-list">
                {model.warnings.map((warning) => (
                  <li key={warning}>
                    <code>{warning}</code>
                  </li>
                ))}
              </ul>
            )}
          </div>

          <div className="decision-pack-section decision-pack-decision">
            <h4>{t("decision_pack.decision.title")}</h4>
            {model.decision ? (
              <>
                <dl className="decision-pack-facts">
                  <div>
                    <dt>{t("decision_pack.decision.outcome")}</dt>
                    <dd>{t(model.decision.outcomeLabelKey)}</dd>
                  </div>
                  <div>
                    <dt>{t("decision_pack.decision.actor")}</dt>
                    <dd>{model.decision.actor ?? t("decision_pack.not_recorded")}</dd>
                  </div>
                  <div>
                    <dt>{t("decision_pack.decision.recorded_at")}</dt>
                    <dd>
                      {model.decision.recordedAtUtc
                        ? formatUtcTimestamp(model.decision.recordedAtUtc)
                        : t("decision_pack.not_recorded")}
                    </dd>
                  </div>
                  <div>
                    <dt>{t("decision_pack.decision.evidence")}</dt>
                    <dd>
                      {model.decision.evidenceRefs.length > 0
                        ? model.decision.evidenceRefs.join(", ")
                        : t("decision_pack.decision.no_evidence")}
                    </dd>
                  </div>
                </dl>
                {model.decision.note && <p>{model.decision.note}</p>}
              </>
            ) : (
              // No record is a fact about the case, stated where the decision goes.
              <p className="decision-pack-none">{t(model.noDecisionKey)}</p>
            )}
          </div>

          <div className="decision-pack-section decision-pack-history">
            <h4>{t("decision_pack.history.title")}</h4>
            {model.history.length === 0 ? (
              <p className="decision-pack-none">{t("decision_pack.history.none")}</p>
            ) : (
              <ol className="decision-pack-history-list">
                {model.history.map((row, index) => (
                  <li key={`${index}:${row.recordedAtUtc ?? ""}:${row.actor ?? ""}`}>
                    <strong>{t(row.outcomeLabelKey)}</strong>
                    <span>{row.actor ?? t("decision_pack.not_recorded")}</span>
                    <time>{formatUtcTimestamp(row.recordedAtUtc)}</time>
                    {row.note && <p>{row.note}</p>}
                  </li>
                ))}
              </ol>
            )}
          </div>

          <div className="decision-pack-section decision-pack-audit">
            <h4>{t("decision_pack.audit.title")}</h4>
            <p className="decision-pack-note">
              {t("decision_pack.audit.resource")}:{" "}
              <code>{model.auditResource ?? t("decision_pack.not_recorded")}</code>
            </p>
            {model.auditRows.length === 0 ? (
              // The trail was read as part of the pack, so an empty one is a measurement: the
              // deployment recorded no act against this case. It is not "the trail was unavailable".
              <p className="decision-pack-none">{t("decision_pack.audit.none")}</p>
            ) : (
              <ol className="decision-pack-audit-list">
                {model.auditRows.map((row) => (
                  <li key={row.eventId}>
                    <strong>{row.action}</strong>
                    <span>{row.principal}</span>
                    <time>{formatUtcTimestamp(row.eventTsUtc)}</time>
                    <span>{`${row.severity} · ${row.outcome}`}</span>
                    {row.detail && <p>{row.detail}</p>}
                  </li>
                ))}
              </ol>
            )}
            {model.auditReadSurface && (
              <p className="decision-pack-note">
                {t("decision_pack.audit.read_surface")}: <code>{model.auditReadSurface}</code>
              </p>
            )}
          </div>

          <div className="decision-pack-section decision-pack-signable">
            <h4>{t("decision_pack.signable.title")}</h4>
            {model.signable ? (
              <p className="decision-pack-ready">{t("decision_pack.signable.ready")}</p>
            ) : (
              <p className="decision-pack-not-ready">{t("decision_pack.signable.blocked")}</p>
            )}
            {/*
              Every blocker, in the pack's order: the recognised ones in the product's words, the
              rest as the raw code the deployment used, because an unknown blocker is a fact. The
              list is rendered whether or not the pack calls itself signable - the pack can be
              signable and still name a blocker (an evidence reference whose snapshot is not on
              record is exactly that), and hiding it there would hide the reason a reviewer pauses.
              Only the heading changes: a blocker on a signable pack is a caveat, not a barrier.
            */}
            {(model.packBlockers.length > 0 || model.otherBlockers.length > 0) && (
              <div className="decision-pack-blockers" role="status">
                <strong>
                  {t(
                    model.signable
                      ? "decision_pack.caveats.title"
                      : "decision_pack.blockers.title",
                  )}
                </strong>
                <ul>
                  {model.packBlockers.map((blocker) => (
                    <li key={blocker.code}>{t(blocker.labelKey)}</li>
                  ))}
                  {model.otherBlockers.map((code) => (
                    <li key={code}>
                      <code>{code}</code>
                    </li>
                  ))}
                </ul>
              </div>
            )}
            <p className="decision-pack-signature">
              <span className="eyebrow">{t("decision_pack.signature.title")}</span>{" "}
              {/* The pack's own sentence, kept where a reader looks for a signature. */}
              {model.signatureNote ?? t("decision_pack.signature.none")}
            </p>
          </div>

          <div className="decision-pack-section decision-pack-hash">
            <h4>{t("decision_pack.hash.title")}</h4>
            {/*
              The hash is the point of the artefact, so it is rendered exactly as it arrived inside a
              `<code>` element: selectable, never truncated, never re-wrapped, and copyable by hand
              without this panel reaching for a browser API to do it.
            */}
            <code className={`decision-pack-content-hash is-${model.hash.state}`}>
              {model.hash.contentHash ?? t("decision_pack.hash.absent")}
            </code>
            <p className="decision-pack-note">
              {t("decision_pack.hash.basis")}:{" "}
              {model.hash.basis ?? t("decision_pack.not_recorded")}
            </p>
            <p className="decision-pack-note">{t("decision_pack.hash.match")}</p>
            {model.hash.state === "invalid" && (
              <p className="decision-pack-none">{t("decision_pack.hash.invalid")}</p>
            )}
            {model.hash.state === "unknown" && (
              <p className="decision-pack-none">{t("decision_pack.hash.unknown")}</p>
            )}
          </div>
        </>
      )}
    </section>
  );
}

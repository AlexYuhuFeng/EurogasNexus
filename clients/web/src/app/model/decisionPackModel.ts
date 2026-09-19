/**
 * The decision pack: one case's governance artefact, read as the reviewer signs it.
 *
 * The platform already records everything a decision needs, and none of it in a form a reviewer can
 * sign off on: assembling it by hand from four reads is the work that gets skipped under deadline.
 * `pack` on `GET /api/decision-cases/{case_id}` is that artefact, composed by the deterministic
 * layer, and this module is the client's reading of it: pure, no React, no fetch - a composition of
 * what the payload declares and nothing else.
 *
 * The rules it keeps, in the order they matter:
 *
 * - **a hole is shown, not smoothed.** `snapshot_resolvable` is measured and three-valued, and the
 *   three values become three different states here: the snapshot is on record, the reference cites
 *   a snapshot that is not, or the reference cites none at all. A `null` is never read as "not
 *   resolvable" (an accusation) nor as "resolved" (a clearance), because the pack claimed neither;
 * - **every blocker is rendered.** The list mixes the pack's own `DECISION_PACK_*` codes with the
 *   case's own codes. The ones this surface has copy for are translated; everything else travels
 *   through raw, because an unrecognised blocker is information and dropping it is the failure;
 * - **no signature is invented.** `signable` is the pack's own statement, and the pack holds no
 *   signature - `signature_note` says so, and this model neither signs nor stores anything;
 * - **unavailable is not empty.** A case read with no `pack` (an older deployment, or a read that
 *   failed) is a stated reason, never an empty pack, and the hash is reported as `unknown` rather
 *   than `invalid` when the pack declares none.
 */

import type {
  DecisionCaseAlternativeDTO,
  DecisionCaseAssumptionDTO,
  DecisionCaseRecordDTO,
  DecisionPackAuditEventDTO,
  DecisionPackContextDTO,
  DecisionPackDTO,
  DecisionPackEvidenceDTO,
} from "@/api/client";
import { caseStatusLabelKey, evidenceKindLabelKey, outcomeLabelKey } from "./decisionCaseModel.ts";

/** The pack shape this surface renders. A pack of another shape is stated, never guessed at. */
export const DECISION_PACK_VERSION = "decision-pack-1";

/** The namespace the pack's own blocker codes are declared in. */
export const DECISION_PACK_BLOCKER_PREFIX = "DECISION_PACK_";

/**
 * The `DECISION_PACK_*` codes this surface has copy for.
 *
 * The list is closed on purpose: a code outside it is rendered as its raw self rather than through a
 * label key that does not exist, so a blocker added by a newer backend is still visible to a
 * reviewer standing in front of an older client.
 */
export const RECOGNISED_DECISION_PACK_BLOCKERS = [
  "DECISION_PACK_EVIDENCE_MISSING",
  "DECISION_PACK_DECISION_NOT_RECORDED",
  "DECISION_PACK_SNAPSHOT_UNRESOLVED",
] as const;

/**
 * What the pack established about one reference's snapshot.
 *
 * `not-cited` is its own state, not a soft form of `unresolved`: a manual reference that names no
 * snapshot is not a broken citation.
 */
export type DecisionPackSnapshotState = "resolved" | "unresolved" | "not-cited";

/** The word for one snapshot state, in both locales. */
export function snapshotStateLabelKey(state: DecisionPackSnapshotState): string {
  switch (state) {
    case "resolved":
      return "decision_pack.snapshot.resolved";
    case "unresolved":
      return "decision_pack.snapshot.unresolved";
    default:
      return "decision_pack.snapshot.not_cited";
  }
}

/** Why a pack cannot be shown at all. Stated, so a surface never renders an empty artefact. */
export type DecisionPackUnavailableReason = "no-pack" | "version";

export interface DecisionPackAvailability {
  readonly showable: boolean;
  /** The key the panel states when the pack cannot be shown, or null when it can. */
  readonly reasonKey: string | null;
  readonly reason: DecisionPackUnavailableReason | null;
}

/**
 * Whether the pack can be shown at all.
 *
 * Two ways it cannot, and they are different statements: the case read carried no pack (an older
 * deployment, or a read that failed, so nothing is known), or it carried a pack composed under a
 * shape this surface does not render (so its fields may not mean what this client expects). Neither
 * is an empty pack, and neither is silently rendered as one.
 */
export function decisionPackAvailability(
  pack: DecisionPackDTO | null | undefined,
): DecisionPackAvailability {
  if (!pack || typeof pack !== "object") {
    return { showable: false, reasonKey: "decision_pack.unavailable.no_pack", reason: "no-pack" };
  }
  if (pack.pack_version !== DECISION_PACK_VERSION) {
    return { showable: false, reasonKey: "decision_pack.unavailable.version", reason: "version" };
  }
  return { showable: true, reasonKey: null, reason: null };
}

export type DecisionPackHashState = "intact" | "invalid" | "unknown";

const SHA256_PREFIX = "sha256:";

/**
 * Whether the pack's `content_hash` is present and shaped as `content_hash_basis` says.
 *
 * The hash is computed by the deployment over the deployment's own canonical JSON (sorted keys,
 * UTF-8, no insignificant whitespace), in a namespace this client cannot reproduce - a browser
 * canonicalising a JavaScript object would produce a different digest for the same artefact. So this
 * checks the *declaration* only: it never recomputes, reformats or repairs the value.
 *
 * An absent field is `unknown`, not `invalid`: nothing was stated, and "this was not checked" is not
 * the same claim as "this failed a check".
 */
export function decisionPackHashIsIntact(
  pack: DecisionPackDTO | null | undefined,
): DecisionPackHashState {
  const declared = pack?.content_hash;
  if (typeof declared !== "string" || declared.trim() === "") return "unknown";
  return declared.startsWith(SHA256_PREFIX) ? "intact" : "invalid";
}

/** The hash as it arrived, with the basis the deployment states for it. */
export interface DecisionPackHashView {
  /** The declared hash, character for character: it is what a printed copy is matched on. */
  readonly contentHash: string | null;
  readonly basis: string | null;
  readonly state: DecisionPackHashState;
}

/** How a context row's value is rendered: the pack's own kinds, not a guess about a string. */
export type DecisionPackContextValue =
  | { readonly kind: "text"; readonly value: string }
  | { readonly kind: "instant"; readonly value: string }
  | { readonly kind: "state"; readonly stateKey: string }
  | { readonly kind: "not-recorded" };

/** One declared field of the pack's context. The label is a translation key, not English text. */
export interface DecisionPackContextRow {
  readonly labelKey: string;
  readonly value: DecisionPackContextValue;
}

/** One evidence reference, with the snapshot state the pack measured for it. */
export interface DecisionPackEvidenceRow {
  readonly kind: string;
  /** The shared evidence-kind vocabulary, so the pack and the case read as one product. */
  readonly kindLabelKey: string;
  readonly ref: string;
  readonly label: string | null;
  readonly asOfUtc: string | null;
  readonly snapshotId: string | null;
  readonly snapshotState: DecisionPackSnapshotState;
}

/** One declared assumption, as the case carries it. */
export interface DecisionPackAssumptionRow {
  readonly key: string;
  readonly value: string;
  readonly source: string;
  readonly note: string;
}

/** One alternative the case considered, with the warnings attached to it. */
export interface DecisionPackAlternativeRow {
  readonly alternativeId: string;
  readonly label: string;
  readonly description: string;
  readonly economicsRef: string;
  readonly warnings: readonly string[];
}

/** The human decision the pack carries - the newest record - or the statement that none exists. */
export interface DecisionPackDecisionView {
  readonly outcome: string;
  readonly outcomeLabelKey: string;
  readonly actor: string | null;
  readonly note: string | null;
  readonly evidenceRefs: readonly string[];
  readonly recordedAtUtc: string | null;
}

/** One record in the case's decision history, oldest first. */
export interface DecisionPackHistoryRow {
  readonly outcomeLabelKey: string;
  readonly actor: string | null;
  readonly note: string | null;
  readonly evidenceRefs: readonly string[];
  readonly recordedAtUtc: string | null;
}

/** One act recorded against the case, as the audit trail cites it. */
export interface DecisionPackAuditRow {
  readonly eventId: string;
  readonly action: string;
  readonly principal: string;
  readonly outcome: string;
  readonly severity: string;
  readonly eventTsUtc: string | null;
  readonly detail: string | null;
}

/** A recognised blocker of the pack's own vocabulary, with the copy for it. */
export interface DecisionPackBlockerView {
  readonly code: string;
  readonly labelKey: string;
}

export interface DecisionPackPresentation {
  /** False when the pack cannot be shown; the panel then states `reasonKey` and nothing else. */
  readonly canShow: boolean;
  readonly reasonKey: string | null;
  readonly reason: DecisionPackUnavailableReason | null;
  readonly version: string | null;
  readonly objective: string | null;
  readonly status: string | null;
  readonly statusLabelKey: string | null;
  readonly context: readonly DecisionPackContextRow[];
  readonly evidence: readonly DecisionPackEvidenceRow[];
  readonly assumptions: readonly DecisionPackAssumptionRow[];
  readonly alternatives: readonly DecisionPackAlternativeRow[];
  readonly aiFindings: readonly string[];
  readonly warnings: readonly string[];
  readonly decision: DecisionPackDecisionView | null;
  /** What the panel states where the decision goes when `decision` is null. */
  readonly noDecisionKey: string;
  readonly history: readonly DecisionPackHistoryRow[];
  readonly auditResource: string | null;
  readonly auditRows: readonly DecisionPackAuditRow[];
  readonly auditReadSurface: string | null;
  readonly signable: boolean;
  /** The pack's own recognised blockers, in the order the pack declared them. */
  readonly packBlockers: readonly DecisionPackBlockerView[];
  /** Everything else, raw: the case's own codes and any code this surface does not know. */
  readonly otherBlockers: readonly string[];
  readonly signatureNote: string | null;
  readonly hash: DecisionPackHashView;
}

/** A declared string, or null when the pack records nothing for that field. */
function declaredText(value: string | null | undefined): string | null {
  const trimmed = (value ?? "").trim();
  return trimmed === "" ? null : trimmed;
}

/**
 * The declared content hash, carried exactly as it arrived.
 *
 * Unlike every other declared field, the hash is not trimmed: it is the one value on this surface a
 * printed copy is matched against, so the client passes it through character for character and lets
 * the reader copy it. A value that is empty or only whitespace declares nothing, and is reported as
 * absent rather than as a blank hash.
 */
function declaredHash(value: string | null | undefined): string | null {
  if (typeof value !== "string") return null;
  return value.trim() === "" ? null : value;
}

function contextValue(
  labelKey: string,
  value: string | null | undefined,
  valueIsInstant = false,
): DecisionPackContextRow {
  const text = declaredText(value);
  if (text === null) return { labelKey, value: { kind: "not-recorded" } };
  return { labelKey, value: { kind: valueIsInstant ? "instant" : "text", value: text } };
}

/**
 * The context rows, in the order a reviewer reads them.
 *
 * A field the pack declares as empty is carried as not-recorded rather than dropped: the difference
 * between "this case names no portfolio" and "this client does not show portfolios" is one a
 * compliance reader has to be able to see.
 */
function contextRows(context: DecisionPackContextDTO | undefined): DecisionPackContextRow[] {
  const reproducible = context?.reproducible;
  return [
    contextValue("decision_pack.context.gas_day", context?.gas_day),
    contextValue("decision_pack.context.delivery_product", context?.delivery_product),
    contextValue("decision_pack.context.hub_id", context?.hub_id),
    contextValue("decision_pack.context.portfolio_ref", context?.portfolio_ref),
    contextValue("decision_pack.context.snapshot_id", context?.snapshot_id),
    {
      labelKey: "decision_pack.context.reproducible",
      // Reproducibility is a state the pack declares, so it renders as its own word - and a pack
      // that declares neither value says nothing rather than defaulting to "not reproducible".
      value:
        typeof reproducible === "boolean"
          ? {
              kind: "state",
              stateKey: reproducible
                ? "decision_pack.context.reproducible.yes"
                : "decision_pack.context.reproducible.no",
            }
          : { kind: "not-recorded" },
    },
    contextValue("decision_pack.context.created_by", context?.created_by),
    contextValue("decision_pack.context.created_at_utc", context?.created_at_utc, true),
  ];
}

/**
 * One row per evidence reference.
 *
 * The state comes from the payload's own tri-state and only from it: exactly `true` is resolved,
 * exactly `false` is unresolved, and anything else - including an absent field - is not-cited. A
 * reference whose snapshot is not on record is the hole a reviewer is looking for, so it stays in
 * the list rather than being filtered out.
 */
function evidenceRows(
  evidence: readonly DecisionPackEvidenceDTO[] | undefined,
): DecisionPackEvidenceRow[] {
  return (evidence ?? []).map<DecisionPackEvidenceRow>((item) => ({
    kind: item.kind,
    kindLabelKey: evidenceKindLabelKey(item.kind),
    ref: item.ref,
    label: declaredText(item.label),
    asOfUtc: declaredText(item.as_of_utc),
    snapshotId: declaredText(item.snapshot_id),
    snapshotState:
      item.snapshot_resolvable === true
        ? "resolved"
        : item.snapshot_resolvable === false
          ? "unresolved"
          : "not-cited",
  }));
}

function assumptionRows(
  assumptions: readonly DecisionCaseAssumptionDTO[] | undefined,
): DecisionPackAssumptionRow[] {
  return (assumptions ?? []).map((item) => ({
    key: item.key,
    value: item.value,
    source: item.source,
    note: item.note,
  }));
}

function alternativeRows(
  alternatives: readonly DecisionCaseAlternativeDTO[] | undefined,
): DecisionPackAlternativeRow[] {
  return (alternatives ?? []).map((item) => ({
    alternativeId: item.alternative_id,
    label: item.label,
    description: item.description,
    economicsRef: item.economics_ref,
    warnings: item.warnings ?? [],
  }));
}

function historyRows(
  records: readonly DecisionCaseRecordDTO[] | undefined,
): DecisionPackHistoryRow[] {
  return (records ?? []).map((record) => ({
    outcomeLabelKey: outcomeLabelKey(record.outcome),
    actor: declaredText(record.actor),
    note: declaredText(record.note),
    evidenceRefs: record.evidence_refs ?? [],
    recordedAtUtc: declaredText(record.recorded_at_utc),
  }));
}

function auditRows(
  events: readonly DecisionPackAuditEventDTO[] | undefined,
): DecisionPackAuditRow[] {
  return (events ?? []).map((event) => ({
    eventId: event.event_id,
    action: event.action,
    principal: event.principal,
    outcome: event.outcome,
    severity: event.severity,
    eventTsUtc: declaredText(event.event_ts_utc),
    detail: declaredText(event.detail),
  }));
}

/**
 * Split the pack's blockers in two, keeping the order the pack declared.
 *
 * The pack's own vocabulary is closed and translated; everything else - the case's codes and any
 * code a newer backend added - travels through as its raw self. Dropping an unrecognised code would
 * hide the reason a reviewer cannot sign, which is the one thing this list exists to state.
 */
function blockerViews(blockers: readonly string[] | undefined): {
  packBlockers: DecisionPackBlockerView[];
  otherBlockers: string[];
} {
  const packBlockers: DecisionPackBlockerView[] = [];
  const otherBlockers: string[] = [];
  for (const raw of blockers ?? []) {
    const code = (raw ?? "").trim();
    if (code === "") continue;
    const recognised = (RECOGNISED_DECISION_PACK_BLOCKERS as readonly string[]).includes(code);
    if (recognised) {
      // `DECISION_PACK_EVIDENCE_MISSING` -> `decision_pack.blocker.evidence_missing`: the namespace
      // is the pack's, so it is stated once in the key rather than twice in every label.
      const suffix = code.slice(DECISION_PACK_BLOCKER_PREFIX.length).toLowerCase();
      packBlockers.push({ code, labelKey: `decision_pack.blocker.${suffix}` });
    } else {
      otherBlockers.push(code);
    }
  }
  return { packBlockers, otherBlockers };
}

/** The keys the panel states when the pack cannot be shown, or when it carries no decision. */
const NO_PACK_REASON_KEY = "decision_pack.unavailable.no_pack";
const VERSION_REASON_KEY = "decision_pack.unavailable.version";
const NO_DECISION_KEY = "decision_pack.decision.none";

/**
 * Read one pack as the surface that presents it.
 *
 * Every branch that cannot show the pack returns the same shape with `canShow: false` and a stated
 * reason, so a caller renders one sentence instead of an artefact that looks empty because it failed
 * to load.
 */
export function decisionPackPresentation(
  pack: DecisionPackDTO | null | undefined,
): DecisionPackPresentation {
  const availability = decisionPackAvailability(pack);

  if (!availability.showable || !pack) {
    return {
      canShow: false,
      reasonKey:
        availability.reasonKey ??
        (availability.reason === "version" ? VERSION_REASON_KEY : NO_PACK_REASON_KEY),
      reason: availability.reason,
      version: null,
      objective: null,
      status: null,
      statusLabelKey: null,
      context: [],
      evidence: [],
      assumptions: [],
      alternatives: [],
      aiFindings: [],
      warnings: [],
      decision: null,
      noDecisionKey: NO_DECISION_KEY,
      history: [],
      auditResource: null,
      auditRows: [],
      auditReadSurface: null,
      signable: false,
      packBlockers: [],
      otherBlockers: [],
      signatureNote: null,
      hash: { contentHash: null, basis: null, state: "unknown" },
    };
  }

  // The pack's `decision` is the newest of `history`; the client does not pick one of its own, so a
  // pack that carries records but names no decision says "none recorded" rather than promoting one.
  const decision = pack.decision ?? null;
  const blockers = blockerViews(pack.blockers);

  return {
    canShow: true,
    reasonKey: null,
    reason: null,
    version: declaredText(pack.pack_version),
    objective: declaredText(pack.objective),
    status: declaredText(pack.status),
    statusLabelKey: caseStatusLabelKey(pack.status ?? ""),
    context: contextRows(pack.context),
    evidence: evidenceRows(pack.evidence),
    assumptions: assumptionRows(pack.assumptions),
    alternatives: alternativeRows(pack.alternatives),
    aiFindings: [...(pack.ai_findings ?? [])],
    warnings: [...(pack.warnings ?? [])],
    decision: decision
      ? {
          outcome: decision.outcome,
          outcomeLabelKey: outcomeLabelKey(decision.outcome),
          actor: declaredText(decision.actor),
          note: declaredText(decision.note),
          evidenceRefs: decision.evidence_refs ?? [],
          recordedAtUtc: declaredText(decision.recorded_at_utc),
        }
      : null,
    noDecisionKey: NO_DECISION_KEY,
    history: historyRows(pack.history),
    auditResource: declaredText(pack.audit?.resource),
    auditRows: auditRows(pack.audit?.events),
    auditReadSurface: declaredText(pack.audit?.read_surface),
    // Signability is the pack's own statement, never recomputed here: the pack decides it from the
    // evidence and the record it composed, and a second opinion in the client could disagree with
    // the artefact a reviewer is holding.
    signable: pack.signable === true,
    packBlockers: blockers.packBlockers,
    otherBlockers: blockers.otherBlockers,
    signatureNote: declaredText(pack.signature_note),
    hash: {
      // Character for character: the hash is what ties a printed copy to the platform's record, so
      // it is never truncated, re-cased or re-wrapped on the way to the DOM.
      contentHash: declaredHash(pack.content_hash),
      basis: declaredText(pack.content_hash_basis),
      state: decisionPackHashIsIntact(pack),
    },
  };
}

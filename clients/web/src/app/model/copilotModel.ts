/**
 * Cross-workspace Copilot model (Architecture V2 Wave 7).
 *
 * Wave 1 declared the five canonical AI actions
 * (`app/experience/aiActions.ts`); this module is the pure half of the surface
 * that makes them invocable. It holds no React, performs no fetch and knows no
 * provider credential: it decides whether an action may be offered at all, composes
 * the governed request the existing backend analysis route already accepts, and
 * qualifies what comes back.
 *
 * Three rules are enforced here rather than trusted to a component:
 *
 * - **Evidence before invocation.** An action is withheld unless
 *   `aiActionIsAvailable` holds: the Active Context is complete *and* at least one
 *   evidence reference exists. Absence of evidence is a reason to withhold, never a
 *   reason to let the model guess.
 * - **Interpretation, never numeric authority.** Deterministic engines own
 *   calculations. The qualified output carries no number of its own, is labelled
 *   as interpretation, and keeps the decision-support markers of the response
 *   visible.
 * - **Observable runs, not hidden reasoning.** A run is recorded as what was asked,
 *   on which context, with which evidence references and over which route. The
 *   record has no field for hidden reasoning.
 *
 * The product boundary is inherited from `AI_INVARIANTS` and restated in
 * `COPILOT_BOUNDARY`: no trade execution, no order entry, no nomination, no
 * settlement, no entitlement widening.
 */

import type { AnalysisRequestDTO, AnalysisResultDTO, ApiMeta } from "@/api/client";
import { decisionSupportMarkers } from "../../api/decisionSupport.ts";
import {
  AI_INVARIANTS,
  aiActionContract,
  aiActionIsAvailable,
  type AiActionPosture,
} from "../experience/aiActions.ts";
import {
  activeContextFromParts,
  activeContextGaps,
  activeContextIsReproducible,
  activeContextKey,
  type ActiveContext,
  type ActiveContextGap,
} from "../experience/activeContext.ts";
import {
  AI_ACTION_KINDS,
  aiActionLabelKey,
  type AiActionKind,
  type InspectorSubjectKind,
} from "../experience/vocabulary.ts";
import {
  readSelectionContextUrl,
  readTraderContextUrl,
  resolveSelectionContext,
  resolveTraderContext,
} from "../context/contextUrl.ts";
import type { TraderContext } from "../context/traderContext.ts";
import type { SelectionContext } from "../context/selectionContext.ts";
import { coerceWorkspacePageId, type WorkspacePageId } from "../../workspaceNavigation.ts";

/**
 * The one backend route a Copilot run uses. It already exists in
 * `clients/web/src/api/client.ts` as `api.analysisQuery`; Wave 7 adds no route,
 * no permission and no provider call.
 */
export const COPILOT_REQUEST_ROUTE = "/analysis/query";

/** Posture vocabulary of the canonical actions, in the order Wave 1 declares them. */
export const COPILOT_POSTURES: readonly AiActionPosture[] = [
  "interpret-only",
  "evidence-backed-draft",
  "evidence-backed-review",
];

/**
 * Product invariants the Copilot surface inherits. Derived from the Wave 1
 * contract rather than restated, so the two cannot drift; the false entries are
 * the boundary the surface may never widen.
 */
export const COPILOT_BOUNDARY = {
  interpretationOnly: true,
  numericAuthority: "none",
  inheritsUserAuthority: AI_INVARIANTS.inheritsUserAuthority,
  mayWidenEntitlement: AI_INVARIANTS.mayBypassEntitlement,
  mayInventMissingData: AI_INVARIANTS.mayInventMissingData,
  mayExecuteOrNominate: AI_INVARIANTS.mayExecuteOrNominate,
  storesHiddenReasoning: AI_INVARIANTS.storesHiddenReasoning,
  requiresReauthorisationPerCall: AI_INVARIANTS.requiresReauthorisationPerCall,
} as const;

/** Translation keys for the withholding reasons, so EN and zh-CN share one wording. */
export const COPILOT_WITHHELD_CONTEXT = "experience.copilot.withheld_context";
export const COPILOT_WITHHELD_EVIDENCE = "experience.copilot.withheld_evidence";

/** Fields of the Active Context the surface shows, and which of them gate a run. */
export const COPILOT_CONTEXT_FIELDS = [
  "workspace",
  "gas-day",
  "delivery-product",
  "hub",
] as const;

export type CopilotContextField = (typeof COPILOT_CONTEXT_FIELDS)[number];

/**
 * Fields a run cannot be composed without. A hub focus is deliberately *not*
 * required: a run without one covers every hub and says so, which is a basis, not
 * a gap.
 */
export const COPILOT_REQUIRED_CONTEXT_FIELDS: readonly CopilotContextField[] = [
  "workspace",
  "gas-day",
  "delivery-product",
];

/** One governed object the run will carry into the model context. */
export interface CopilotEvidenceRef {
  readonly kind: InspectorSubjectKind;
  readonly ref: string;
}

/** Stable identity of what the Copilot is working in. */
export interface CopilotContext {
  readonly activeContext: ActiveContext;
  readonly contextKey: string;
  readonly gaps: readonly ActiveContextGap[];
  readonly reproducible: boolean;
  readonly complete: boolean;
  readonly missingFields: readonly CopilotContextField[];
}

/** The selection ids a surface may already hold; a missing id is a gap, not a zero. */
export interface CopilotSelectionIds {
  readonly routeId?: string | null;
  readonly resourceId?: string | null;
  readonly strategyVersionId?: string | null;
  readonly strategyRunId?: string | null;
}

export interface CopilotContextSources {
  readonly workspace: WorkspacePageId;
  readonly trader: TraderContext;
  readonly selection: SelectionContext;
  readonly compositionAvailable?: boolean;
}

function hasText(value: string | null | undefined): boolean {
  return typeof value === "string" && value.trim().length > 0;
}

/**
 * Evidence references the Active Context already holds. These are references to
 * objects the backend returned to *this* identity on this surface; the run carries
 * identities, never values, and the backend re-authorises every one of them.
 */
export function copilotEvidenceRefs(selection: CopilotSelectionIds): CopilotEvidenceRef[] {
  const candidates: Array<[InspectorSubjectKind, string | null | undefined]> = [
    ["route", selection.routeId],
    ["resource", selection.resourceId],
    ["strategy-version", selection.strategyVersionId],
    ["strategy-run", selection.strategyRunId],
  ];
  return candidates
    .filter(([, ref]) => hasText(ref))
    .map(([kind, ref]) => ({ kind, ref: (ref as string).trim() }));
}

export function copilotContextFromSources(sources: CopilotContextSources): CopilotContext {
  const activeContext = activeContextFromParts({
    workspace: sources.workspace,
    trader: sources.trader,
    selection: sources.selection,
  });
  return copilotContext(activeContext, sources.compositionAvailable !== false);
}

/**
 * Build the Copilot context from the canonical Active Context. A provider that has
 * no composition yet (`compositionAvailable: false`) is incomplete by definition:
 * the surface must not imply it is running on a context the product could not
 * resolve.
 */
export function copilotContext(
  activeContext: ActiveContext,
  compositionAvailable = true,
): CopilotContext {
  const required = COPILOT_REQUIRED_CONTEXT_FIELDS.filter(
    (field) => !copilotContextFieldPresent(activeContext, field),
  );
  return {
    activeContext,
    contextKey: activeContextKey(activeContext),
    gaps: activeContextGaps(),
    reproducible: activeContextIsReproducible(),
    complete: compositionAvailable && required.length === 0,
    missingFields: COPILOT_CONTEXT_FIELDS.filter(
      (field) => !copilotContextFieldPresent(activeContext, field),
    ),
  };
}

/** Whether one displayed field carries a value. Never guesses a substitute. */
export function copilotContextFieldPresent(
  activeContext: ActiveContext,
  field: CopilotContextField,
): boolean {
  if (field === "hub") return hasText(activeContext.hubId);
  if (field === "workspace") return hasText(activeContext.workspace);
  if (field === "gas-day") return /^\d{4}-\d{2}-\d{2}$/.test(activeContext.gasDay);
  return hasText(activeContext.deliveryProduct);
}

export function copilotContextFieldValue(
  activeContext: ActiveContext,
  field: CopilotContextField,
): string | null {
  if (field === "hub") return activeContext.hubId;
  if (field === "workspace") return activeContext.workspace;
  if (field === "gas-day") return activeContext.gasDay;
  return activeContext.deliveryProduct;
}

export function copilotContextFieldLabelKey(field: CopilotContextField): string {
  return `experience.copilot.field.${field}`;
}

/** Label key for an Active Context gap, so a gap is named instead of hidden. */
export function copilotGapLabelKey(gap: ActiveContextGap): string {
  return `experience.copilot.gap.${gap}`;
}

export interface CopilotContextFromSearchInput {
  /** `window.location.search` from the canonical context reader's own source. */
  readonly search: string;
  /** Result of the canonical persisted-context reader (injected, so this stays pure). */
  readonly persisted: Partial<TraderContext>;
  /** Selection the shell already holds; absent falls back to the URL selection. */
  readonly selection?: CopilotSelectionIds | null;
  readonly compositionAvailable?: boolean;
}

/**
 * Resolve the Copilot context from the same sources the Active Context already
 * uses: the URL context/selection keys and the persisted trader preference, passed
 * through the canonical readers (`app/context/contextUrl.ts`,
 * `app/context/contextPersistence.ts`) rather than re-implemented here. This is a
 * read of the canonical context, never a second owner of it: a shell that already
 * holds the context passes `sources` directly to `copilotContextFromSources`.
 */
export function copilotContextFromSearch(input: CopilotContextFromSearchInput): CopilotContext {
  const trader = resolveTraderContext(readTraderContextUrl(input.search), input.persisted);
  const selection: SelectionContext = {
    ...resolveSelectionContext(readSelectionContextUrl(input.search)),
    ...(input.selection
      ? {
          routeId: input.selection.routeId ?? null,
          resourceId: input.selection.resourceId ?? null,
          strategyVersionId: input.selection.strategyVersionId ?? null,
          strategyRunId: input.selection.strategyRunId ?? null,
        }
      : {}),
  };
  const workspace = coerceWorkspacePageId(new URLSearchParams(input.search).get("workspace"));
  return copilotContextFromSources({
    workspace,
    trader,
    selection,
    compositionAvailable: input.compositionAvailable,
  });
}

export interface CopilotOffer {
  readonly action: AiActionKind;
  /** Existing Wave 1 vocabulary: `experience.ai.<action>`. */
  readonly labelKey: string;
  /** Contract wording, kept as provenance for the run record. */
  readonly purpose: string;
  readonly posture: AiActionPosture;
  readonly postureKey: string;
  /** Contract wording for what the action produces. */
  readonly produces: string;
  readonly producesKey: string;
  /** Evidence references this action will carry into the run. */
  readonly evidenceRefs: readonly CopilotEvidenceRef[];
  readonly available: boolean;
  readonly withheldReasonKey: string | null;
}

export function copilotActionLabelKey(action: AiActionKind): string {
  return aiActionLabelKey(action);
}

export function copilotPostureLabelKey(posture: AiActionPosture): string {
  return `experience.copilot.posture.${posture}`;
}

export function copilotProducesLabelKey(action: AiActionKind): string {
  return `experience.copilot.produces.${action}`;
}

/** Why an action is withheld, in the same order the gate checks. */
export function copilotWithheldReasonKey(
  context: CopilotContext,
  evidenceRefs: readonly CopilotEvidenceRef[],
): string | null {
  if (!context.complete) return COPILOT_WITHHELD_CONTEXT;
  if (evidenceRefs.length < 1) return COPILOT_WITHHELD_EVIDENCE;
  return null;
}

/**
 * The offer list: exactly the five canonical actions, in contract order, each with
 * its posture, what it produces, the references it would carry, and whether it may
 * be invoked at all. No sixth action is ever added here.
 */
export function copilotOffers(
  context: CopilotContext,
  evidenceRefs: readonly CopilotEvidenceRef[],
): CopilotOffer[] {
  const withheldReasonKey = copilotWithheldReasonKey(context, evidenceRefs);
  return AI_ACTION_KINDS.map((action) => {
    const contract = aiActionContract(action);
    const available = aiActionIsAvailable(action, {
      activeContextComplete: context.complete,
      evidenceRefCount: evidenceRefs.length,
    });
    return {
      action,
      labelKey: copilotActionLabelKey(action),
      purpose: contract.purpose,
      posture: contract.posture,
      postureKey: copilotPostureLabelKey(contract.posture),
      produces: contract.produces,
      producesKey: copilotProducesLabelKey(action),
      evidenceRefs,
      available,
      withheldReasonKey: available ? null : withheldReasonKey,
    };
  });
}

export function copilotOfferFor(
  context: CopilotContext,
  evidenceRefs: readonly CopilotEvidenceRef[],
  action: AiActionKind,
): CopilotOffer | null {
  return copilotOffers(context, evidenceRefs).find((offer) => offer.action === action) ?? null;
}

/** The actions that may actually be invoked in this context. */
export function availableCopilotActions(
  context: CopilotContext,
  evidenceRefs: readonly CopilotEvidenceRef[],
): AiActionKind[] {
  return copilotOffers(context, evidenceRefs)
    .filter((offer) => offer.available)
    .map((offer) => offer.action);
}

/**
 * The backend task kind that accompanies a canonical action.
 *
 * All five canonical actions are questions over the same governed snapshot, so all
 * five run `DB_INQUIRY`: the action selects the *posture*, which is composed into
 * the question text and shown in the run record, not the backend's
 * missing-input/section logic. A task kind per action would be a backend contract
 * change; it is not invented here, and `DB_INQUIRY` is the honest choice because it
 * fabricates no missing-input claim.
 */
export function copilotTaskForAction(_action: AiActionKind): string {
  return "DB_INQUIRY";
}

/**
 * Default framing per action, used when the invoking user leaves the question
 * empty. It restates the contract's posture in English prompt language; the prompt
 * language is the backend's, the interface wording stays bilingual.
 */
export function defaultCopilotQuestion(action: AiActionKind): string {
  return aiActionContract(action).purpose;
}

/**
 * The question the backend receives: the user's question (or the action's default
 * framing), the context basis, the context key and the evidence references. This
 * is also what the backend persists as the run's prompt snapshot, so the run is
 * observable rather than hidden.
 */
export function copilotQuestion(input: {
  readonly action: AiActionKind;
  readonly question: string;
  readonly context: CopilotContext;
  readonly evidenceRefs: readonly CopilotEvidenceRef[];
}): string {
  const context = input.context.activeContext;
  const basis = [
    `workspace ${context.workspace}`,
    `gas day ${context.gasDay}`,
    `product ${context.deliveryProduct}`,
    `hub ${context.hubId ?? "ANY"}`,
  ].join(", ");
  const evidence = input.evidenceRefs.length
    ? input.evidenceRefs.map((ref) => `${ref.kind}:${ref.ref}`).join(", ")
    : "none";
  const asked = input.question.trim() || defaultCopilotQuestion(input.action);
  return [
    `[${input.action.toUpperCase()}] ${asked}`,
    `Context: ${basis}`,
    `Context key: ${input.context.contextKey}`,
    `Evidence references: ${evidence}`,
  ].join("\n");
}

export interface CopilotRunInput {
  readonly action: AiActionKind;
  readonly question: string;
  readonly context: CopilotContext;
  readonly evidenceRefs: readonly CopilotEvidenceRef[];
  readonly language: string;
}

/**
 * Compose the request for the existing `/analysis/query` route. Nothing numeric is
 * computed or restated here: the snapshot, the answers and every figure stay with
 * the backend's deterministic builders.
 */
export function composeCopilotRequest(input: CopilotRunInput): AnalysisRequestDTO {
  const assets = input.evidenceRefs
    .filter((ref) => ref.kind !== "contract")
    .map((ref) => ref.ref);
  const contracts = input.evidenceRefs
    .filter((ref) => ref.kind === "contract")
    .map((ref) => ref.ref);
  return {
    question: copilotQuestion(input),
    task: copilotTaskForAction(input.action),
    provider_id: "DEEPSEEK",
    model: "deepseek-v4-flash",
    // Invocation is the deliberate step: the user chose one canonical action on one
    // evidence set. The backend still re-authorises and fails closed before any
    // provider call.
    invoke_provider: true,
    selected_terms: [],
    selected_assets: assets,
    selected_contracts: contracts,
    language: input.language.startsWith("zh") ? "zh-CN" : "en",
  };
}

export interface CopilotRunRecord {
  readonly action: AiActionKind;
  /** Exactly the question that was sent, context and evidence included. */
  readonly question: string;
  readonly contextKey: string;
  readonly evidenceRefs: readonly CopilotEvidenceRef[];
  readonly route: string;
  readonly request: AnalysisRequestDTO;
  readonly recordedAtUtc: string;
  /** Always null: the surface records the action, never a reasoning trace. */
  readonly hiddenReasoning: null;
}

export function copilotRunRecord(
  input: CopilotRunInput & { readonly recordedAtUtc: string },
): CopilotRunRecord {
  return {
    action: input.action,
    question: copilotQuestion(input),
    contextKey: input.context.contextKey,
    evidenceRefs: input.evidenceRefs,
    route: COPILOT_REQUEST_ROUTE,
    request: composeCopilotRequest(input),
    recordedAtUtc: input.recordedAtUtc,
    hiddenReasoning: null,
  };
}

export interface CopilotOutputSection {
  readonly sectionId: string;
  readonly title: string;
  readonly content: string;
  readonly citations: readonly string[];
  readonly warnings: readonly string[];
}

/**
 * What the surface may show of an AI result. Every field is either backend-reported
 * or a fixed label; there is no derived number and no authority claim. The two
 * flags are the union of the response body and the response `meta`, so a run where
 * either says "research only" or "human review required" is shown as such.
 */
export interface CopilotOutput {
  readonly interpretation: true;
  readonly numericAuthority: "none";
  readonly researchOnly: boolean;
  readonly humanReviewRequired: boolean;
  readonly providerStatus: string;
  /** Whether the provider actually answered; false means a deterministic summary. */
  readonly providerInvoked: boolean;
  readonly analysisId: string | null;
  readonly snapshotId: string | null;
  readonly createdAtUtc: string | null;
  /** Answer in the request language, with the language actually shown. */
  readonly answer: string;
  readonly answerLanguage: "en" | "zh-CN";
  readonly citations: readonly string[];
  readonly missingInputs: readonly string[];
  readonly warnings: readonly string[];
  readonly sections: readonly CopilotOutputSection[];
}

export function qualifyCopilotOutput(input: {
  readonly result: AnalysisResultDTO;
  readonly meta?: ApiMeta | null;
  readonly language: string;
}): CopilotOutput {
  const { result, meta } = input;
  const wantsChinese = input.language.startsWith("zh");
  const preferred = wantsChinese ? result.answer_zh_cn : result.answer_en;
  const fallback = wantsChinese ? result.answer_en : result.answer_zh_cn;
  const answer = preferred?.trim() ? preferred : (fallback ?? "");
  const answerLanguage: "en" | "zh-CN" =
    preferred?.trim() ? (wantsChinese ? "zh-CN" : "en") : wantsChinese ? "en" : "zh-CN";
  const markers = decisionSupportMarkers(result, meta);
  return {
    interpretation: true,
    numericAuthority: "none",
    // Fail closed: either the body or the envelope reporting a marker is enough.
    researchOnly: markers.researchOnly,
    humanReviewRequired: markers.humanReviewRequired,
    providerStatus: result.provider_status ?? "",
    providerInvoked: result.provider_status === "success",
    analysisId: result.analysis_id || null,
    snapshotId: result.snapshot_id || null,
    createdAtUtc: result.created_at_utc || null,
    answer,
    answerLanguage,
    citations: [...(result.citations ?? [])],
    missingInputs: [...(result.missing_inputs ?? [])],
    warnings: [...(result.warnings ?? []), ...(meta?.warnings ?? [])],
    sections: (result.sections ?? []).map((section) => ({
      sectionId: section.section_id,
      title: section.title,
      content: section.content,
      citations: [...(section.citations ?? [])],
      warnings: [...(section.warnings ?? [])],
    })),
  };
}

/**
 * Copilot controller (Architecture V2 Wave 7).
 *
 * The thin half of the cross-workspace Copilot surface. It holds the run state of
 * one canonical AI action and nothing else: availability gating, request
 * composition, output qualification and the run record all live in the pure model
 * (`app/model/copilotModel.ts`), so they are testable without a browser.
 *
 * The transport is injected (`runAnalysis`). The composition root passes the
 * existing backend route (`api.analysisQuery`, `POST /analysis/query`); this hook
 * names no endpoint and calls neither a vendor API nor the DB.
 *
 * `useCopilotSources` resolves the Active Context and the evidence references the
 * run will carry. It *reads* the canonical context sources (the URL context keys
 * and the persisted trader preference, through the same readers the Active Context
 * owner uses) and never becomes a second owner of them: a shell that already holds
 * the context passes its own `sources` and no ambient read happens.
 */

import { useCallback, useEffect, useMemo, useState } from "react";

import type { AnalysisRequestDTO, AnalysisResultDTO, ApiResponse } from "@/api/client";
import { readPersistedTraderContext } from "@/app/context/contextPersistence";
import {
  describeFailure,
  type ErrorPresentation,
} from "@/app/experience/errorPresentation";
import type { AiActionKind } from "@/app/experience/vocabulary";
import {
  composeCopilotRequest,
  copilotContextFromSearch,
  copilotEvidenceRefs,
  copilotOffers,
  copilotRunRecord,
  qualifyCopilotOutput,
  type CopilotContext,
  type CopilotEvidenceRef,
  type CopilotOffer,
  type CopilotOutput,
  type CopilotRunRecord,
  type CopilotSelectionIds,
} from "@/app/model/copilotModel";

/** The transport one Copilot run uses. Injected so the hook stays testable. */
export type CopilotRunAnalysis = (
  body: AnalysisRequestDTO,
) => Promise<ApiResponse<AnalysisResultDTO>>;

export interface CopilotSources {
  readonly context: CopilotContext;
  readonly evidenceRefs: CopilotEvidenceRef[];
}

export interface CopilotSourcesInput {
  /** Defaults to `window.location.search`; a host may pass its own. */
  readonly search?: string;
  /** Selection the shell already holds; absent reads the URL selection keys. */
  readonly selection?: CopilotSelectionIds | null;
  /** Whether the identity composition resolved; false makes the context incomplete. */
  readonly compositionAvailable?: boolean;
}

/**
 * The context and evidence a Copilot run would use right now. Evidence references
 * are taken from the same Active Context the run reports, so what the panel shows
 * is what the request carries.
 */
export function useCopilotSources(input: CopilotSourcesInput = {}): CopilotSources {
  const search = input.search ?? (typeof window === "undefined" ? "" : window.location.search);
  const selection = input.selection ?? null;
  const compositionAvailable = input.compositionAvailable;
  return useMemo(() => {
    const context = copilotContextFromSearch({
      search,
      persisted: readPersistedTraderContext(),
      selection,
      compositionAvailable,
    });
    return { context, evidenceRefs: copilotEvidenceRefs(context.activeContext) };
  }, [search, selection, compositionAvailable]);
}

export interface UseCopilotOptions {
  /** The canonical action the surface is on, or null before one is chosen. */
  readonly action: AiActionKind | null;
  readonly sources: CopilotSources;
  readonly language: string;
  readonly runAnalysis: CopilotRunAnalysis;
}

export type CopilotRunState = "idle" | "running" | "succeeded" | "failed";

export interface CopilotController extends CopilotSources {
  readonly action: AiActionKind | null;
  /** Exactly the five canonical actions, each with its availability and evidence. */
  readonly offers: CopilotOffer[];
  /** The offer for the current action, or null when nothing is selected. */
  readonly selected: CopilotOffer | null;
  readonly state: CopilotRunState;
  readonly canRun: boolean;
  readonly question: string;
  readonly setQuestion: (value: string) => void;
  /** Invoke the action. Withheld actions are refused here, not merely hidden. */
  readonly run: () => Promise<void>;
  readonly reset: () => void;
  readonly output: CopilotOutput | null;
  readonly runRecord: CopilotRunRecord | null;
  readonly error: ErrorPresentation | null;
}

export function useCopilot(options: UseCopilotOptions): CopilotController {
  const { action, sources, language, runAnalysis } = options;
  const [question, setQuestion] = useState("");
  const [state, setState] = useState<CopilotRunState>("idle");
  const [output, setOutput] = useState<CopilotOutput | null>(null);
  const [runRecord, setRunRecord] = useState<CopilotRunRecord | null>(null);
  const [error, setError] = useState<ErrorPresentation | null>(null);

  const offers = useMemo(
    () => copilotOffers(sources.context, sources.evidenceRefs),
    [sources.context, sources.evidenceRefs],
  );
  const selected = offers.find((offer) => offer.action === action) ?? null;

  // A different action is a different run: nothing from the previous one carries over.
  useEffect(() => {
    setState("idle");
    setOutput(null);
    setRunRecord(null);
    setError(null);
    setQuestion("");
  }, [action]);

  const reset = useCallback(() => {
    setState("idle");
    setOutput(null);
    setRunRecord(null);
    setError(null);
    setQuestion("");
  }, []);

  const canRun = Boolean(selected?.available) && state !== "running";

  const run = useCallback(async () => {
    if (!selected || !selected.available || state === "running") return;
    const input = {
      action: selected.action,
      question,
      context: sources.context,
      evidenceRefs: sources.evidenceRefs,
      language,
    };
    setState("running");
    setError(null);
    try {
      const response = await runAnalysis(composeCopilotRequest(input));
      setOutput(
        qualifyCopilotOutput({
          result: response.data,
          meta: response.meta ?? null,
          language,
        }),
      );
      setRunRecord(copilotRunRecord({ ...input, recordedAtUtc: new Date().toISOString() }));
      setState("succeeded");
    } catch (cause) {
      setError(describeCopilotFailure(cause));
      setState("failed");
    }
  }, [selected, state, question, sources.context, sources.evidenceRefs, language, runAnalysis]);

  return {
    action,
    context: sources.context,
    evidenceRefs: sources.evidenceRefs,
    offers,
    selected,
    state,
    canRun,
    question,
    setQuestion,
    run,
    reset,
    output,
    runRecord,
    error,
  };
}

/**
 * A failure is explained through the product error taxonomy, never as a raw status:
 * what happened, what it affects, the likely cause and how to recover. The taxonomy body
 * (code, family, severity, recoverability, message/action keys, correlation id) is
 * reassembled by `describeFailure`, which reads the whole failure rather than only its
 * `detail` - the envelope's fields sit beside `detail`, not inside it.
 */
export function describeCopilotFailure(cause: unknown): ErrorPresentation {
  return describeFailure(cause);
}

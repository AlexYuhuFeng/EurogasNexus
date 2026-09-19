import { useCallback, useState } from "react";

import {
  api,
  type NominationScheduleResultDTO,
  type OptimizationRunDTO,
  type StorageDispatchResultDTO,
} from "@/api/client";
import {
  emptyNominationDraft,
  emptyStorageDispatchDraft,
  nominationReadiness,
  nominationRequest,
  runRecordState,
  storageDispatchReadiness,
  storageDispatchRequest,
  type AssessmentReadiness,
  type NominationDraft,
  type StorageDispatchDraft,
} from "@/app/model/optimizationAssessmentModel";

/** What an assessment panel needs: one draft, one run, one result and the record behind it. */
export interface AssessmentState<Draft, Result> {
  readonly draft: Draft;
  readonly updateDraft: (updater: (current: Draft) => Draft) => void;
  readonly readiness: AssessmentReadiness;
  readonly busy: boolean;
  readonly result: Result | null;
  /** Whether the engine persisted a run for this result, and its id when it did. */
  readonly runId: string | null;
  readonly recorded: boolean;
  readonly error: unknown;
  readonly run: () => Promise<void>;
}

function useAssessment<Draft, Result extends { status: string }>(
  empty: () => Draft,
  readinessOf: (draft: Draft) => AssessmentReadiness,
  requestOf: (draft: Draft) => unknown | null,
  send: (body: never) => Promise<{ data: Result; meta: { run_id?: string | null } }>,
): AssessmentState<Draft, Result> {
  const [draft, setDraft] = useState<Draft>(empty);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<Result | null>(null);
  const [runId, setRunId] = useState<string | null>(null);
  const [recorded, setRecorded] = useState(false);
  const [error, setError] = useState<unknown>(null);

  const updateDraft = useCallback((updater: (current: Draft) => Draft) => {
    setDraft(updater);
  }, []);

  const run = useCallback(async () => {
    const body = requestOf(draft);
    if (!body) return;
    setBusy(true);
    setError(null);
    try {
      const response = await send(body as never);
      setResult(response.data);
      const record = runRecordState(response.meta);
      setRunId(record.runId);
      setRecorded(record.recorded);
    } catch (reason) {
      setError(reason);
    } finally {
      setBusy(false);
    }
  }, [draft, requestOf, send]);

  return {
    draft,
    updateDraft,
    readiness: readinessOf(draft),
    busy,
    result,
    runId,
    recorded,
    error,
    run,
  };
}

/**
 * The nomination-window assessment (register C14/D8).
 *
 * The request and the readiness rule live in the model so the surface and the engine agree about
 * what a window is; this hook owns the state and performs the call, and the workspace header starts
 * the run because a `compute` consequence belongs in the primary slot.
 */
export function useNominationAssessment(): AssessmentState<NominationDraft, NominationScheduleResultDTO> {
  return useAssessment(
    emptyNominationDraft,
    nominationReadiness,
    nominationRequest,
    api.optimizeNominationWindow as never,
  );
}

/** The storage-dispatch assessment, on the same terms. */
export function useStorageDispatchAssessment(): AssessmentState<StorageDispatchDraft, StorageDispatchResultDTO> {
  return useAssessment(
    emptyStorageDispatchDraft,
    storageDispatchReadiness,
    storageDispatchRequest,
    api.optimizeStorageDispatch as never,
  );
}

export interface OptimizationRunRecord {
  readonly run: OptimizationRunDTO | null;
  readonly loading: boolean;
  readonly error: unknown;
  readonly load: (runId: string) => Promise<void>;
}

/**
 * Re-read a persisted run, which is what makes an assessment checkable after the fact.
 *
 * The engines persist what was decided from which inputs; this reads that row back. Asking for the
 * record is a deliberate act rather than an automatic one, because most of the time the operator
 * wants the answer, not the archive.
 */
export function useOptimizationRunRecord(): OptimizationRunRecord {
  const [run, setRun] = useState<OptimizationRunDTO | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<unknown>(null);

  const load = useCallback(async (runId: string) => {
    if (!runId.trim()) return;
    setLoading(true);
    setError(null);
    try {
      const response = await api.optimizationRun(runId.trim());
      setRun(response.data);
    } catch (reason) {
      setError(reason);
    } finally {
      setLoading(false);
    }
  }, []);

  return { run, loading, error, load };
}

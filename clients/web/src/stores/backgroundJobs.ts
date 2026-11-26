/**
 * Background jobs the user can leave (the notification centre's job lane).
 *
 * The server runs long work as a job (`application/background_jobs.py`); this store follows
 * the user's jobs so any page, and the notification centre, shows the same live state:
 *
 * - `start*` sends the request, records the job as started here (the page it came from and the
 *   request, for "Open result" and "Retry") and begins polling at once;
 * - polling (`GET /api/jobs`) runs only while a job is active, at the pace
 *   `jobPollDelay` sets, and stops when nothing is left running;
 * - what this browser started, dismissed and has seen is kept per user in browser storage, so a
 *   reload or a later visit to the starting page still finds the job. It is a convenience: the
 *   job itself lives on the server, and an unreadable storage only loses the "Retry".
 */

import { create } from "zustand";

import { api } from "@/api/client";
import type { JobDTO, ResearchRunStartDTO } from "@/api/client";
import {
  jobPollDelay,
  newlyFinishedJobs,
  pruneStartedJobs,
  type JobRetry,
  type StartedJob,
} from "@/app/jobs/backgroundJobsModel";

const STORAGE_PREFIX = "eurogas.backgroundJobs.v1";
const LIST_LIMIT = "25";

interface StoredJobState {
  started: Record<string, StartedJob>;
  dismissed: string[];
  seen: string[];
}

export interface StartOptions {
  /** The page that started the job (path and query); defaults to the current location. */
  readonly returnTo?: string;
  /** A name for the work the user will recognise in the notification centre. */
  readonly title?: string;
}

export interface BackgroundJobsState {
  principalId: string | null;
  jobs: JobDTO[];
  started: Record<string, StartedJob>;
  dismissed: string[];
  seen: string[];
  /** Jobs that finished since the user last looked, for the polite announcement. */
  justFinished: JobDTO[];
  lastError: string | null;
  /** Follow the jobs of this user (null when signed out); clears another user's state. */
  bindIdentity: (principalId: string | null) => void;
  /** Read the user's jobs once and keep polling while any is active. */
  refresh: () => Promise<void>;
  /** Start a dataset build in the background and follow it. */
  startDatasetBuild: (
    datasetSpec: Record<string, unknown>,
    options?: StartOptions & { snapshotId?: string | null },
  ) => Promise<JobDTO>;
  /** Start a governed research run in the background and follow it. */
  startResearchRun: (body: ResearchRunStartDTO, options?: StartOptions) => Promise<JobDTO>;
  /** Run a failed or cancelled job's request again, as a new job. */
  retry: (jobId: string) => Promise<JobDTO | null>;
  cancel: (jobId: string) => Promise<void>;
  dismiss: (jobId: string) => void;
  /** Dismiss every finished job in the list. */
  clearFinished: () => void;
  /** The user opened the notification centre: every finished job is now seen. */
  markSeen: () => void;
  /** Stop polling (sign-out, tests). */
  stop: () => void;
}

let pollTimer: ReturnType<typeof setTimeout> | null = null;
let generation = 0;

function storageKey(principalId: string): string {
  return `${STORAGE_PREFIX}.${principalId}`;
}

function readStored(principalId: string | null): StoredJobState {
  const empty: StoredJobState = { started: {}, dismissed: [], seen: [] };
  if (!principalId || typeof window === "undefined") return empty;
  try {
    const parsed = JSON.parse(window.localStorage.getItem(storageKey(principalId)) ?? "{}") as Partial<StoredJobState>;
    return {
      started: pruneStartedJobs(parsed.started ?? {}, Date.now()),
      dismissed: Array.isArray(parsed.dismissed) ? parsed.dismissed.slice(-200) : [],
      seen: Array.isArray(parsed.seen) ? parsed.seen.slice(-200) : [],
    };
  } catch {
    return empty;
  }
}

function writeStored(state: Pick<BackgroundJobsState, "principalId" | "started" | "dismissed" | "seen">): void {
  if (!state.principalId || typeof window === "undefined") return;
  try {
    window.localStorage.setItem(
      storageKey(state.principalId),
      JSON.stringify({ started: state.started, dismissed: state.dismissed, seen: state.seen }),
    );
  } catch {
    // Storage is a convenience; a private window simply forgets what it started.
  }
}

function currentLocation(): string {
  if (typeof window === "undefined") return "/";
  return `${window.location.pathname}${window.location.search}`;
}

function mergeJob(jobs: readonly JobDTO[], job: JobDTO): JobDTO[] {
  return [job, ...jobs.filter((row) => row.job_id !== job.job_id)];
}

export const useBackgroundJobsStore = create<BackgroundJobsState>((set, get) => {
  function schedule(): void {
    if (pollTimer !== null) clearTimeout(pollTimer);
    pollTimer = null;
    const delay = jobPollDelay(get().jobs, Date.now());
    if (delay === null) return;
    const scheduledFor = generation;
    pollTimer = setTimeout(() => {
      pollTimer = null;
      if (scheduledFor === generation) void get().refresh();
    }, delay);
  }

  function remember(job: JobDTO, retry: JobRetry | null, options: StartOptions | undefined): void {
    const entry: StartedJob = {
      job_id: job.job_id,
      return_to: options?.returnTo ?? currentLocation(),
      title: options?.title,
      retry,
      started_at_ms: Date.now(),
    };
    set((state) => ({
      jobs: mergeJob(state.jobs, job),
      started: { ...state.started, [job.job_id]: entry },
    }));
    writeStored(get());
    schedule();
  }

  async function launch(retry: JobRetry, options?: StartOptions): Promise<JobDTO> {
    if (retry.action === "dataset-build") {
      const body = retry.body as { dataset_spec: Record<string, unknown>; snapshot_id?: string | null };
      const response = await api.startDatasetBuild(body.dataset_spec, body.snapshot_id ?? null);
      remember(response.data, retry, options);
      return response.data;
    }
    if (retry.action === "research-run") {
      const response = await api.startResearchRun(retry.body as unknown as ResearchRunStartDTO);
      remember(response.data, retry, options);
      return response.data;
    }
    throw new Error(`unknown_job_action:${String(retry.action)}`);
  }

  return {
    principalId: null,
    jobs: [],
    started: {},
    dismissed: [],
    seen: [],
    justFinished: [],
    lastError: null,

    bindIdentity: (principalId) => {
      if (get().principalId === principalId) return;
      generation += 1;
      if (pollTimer !== null) clearTimeout(pollTimer);
      pollTimer = null;
      const stored = readStored(principalId);
      set({ principalId, jobs: [], justFinished: [], lastError: null, ...stored });
      if (principalId) void get().refresh();
    },

    refresh: async () => {
      if (!get().principalId) return;
      const asked = generation;
      try {
        const response = await api.jobs({ limit: LIST_LIMIT });
        if (asked !== generation) return;
        const previous = get().jobs;
        const warnings = response.meta?.warnings ?? [];
        if (warnings.includes("RUNTIME_POSTGRESQL_UNAVAILABLE")) {
          // An empty list from a store that could not be read is not "nothing running": keep the
          // jobs already followed and keep asking, so their notices come back with the store.
          set({ lastError: "RUNTIME_POSTGRESQL_UNAVAILABLE" });
          schedule();
          return;
        }
        const next = Array.isArray(response.data) ? response.data : [];
        const finished = newlyFinishedJobs(previous, next);
        set({
          jobs: next,
          lastError: null,
          justFinished: finished.length > 0 ? finished : get().justFinished,
        });
      } catch (error) {
        if (asked !== generation) return;
        set({ lastError: error instanceof Error ? error.message : String(error) });
      }
      schedule();
    },

    startDatasetBuild: (datasetSpec, options) =>
      launch(
        {
          action: "dataset-build",
          body: { dataset_spec: datasetSpec, snapshot_id: options?.snapshotId ?? null },
        },
        options,
      ),

    startResearchRun: (body, options) =>
      launch({ action: "research-run", body: { ...body } }, options),

    retry: async (jobId) => {
      const entry = get().started[jobId];
      if (!entry?.retry) return null;
      const job = await launch(entry.retry, { returnTo: entry.return_to, title: entry.title });
      get().dismiss(jobId);
      return job;
    },

    cancel: async (jobId) => {
      const response = await api.cancelJob(jobId);
      set((state) => ({ jobs: mergeJob(state.jobs, response.data) }));
      schedule();
    },

    dismiss: (jobId) => {
      set((state) => ({
        dismissed: state.dismissed.includes(jobId) ? state.dismissed : [...state.dismissed, jobId],
        justFinished: state.justFinished.filter((job) => job.job_id !== jobId),
      }));
      writeStored(get());
    },

    clearFinished: () => {
      const finished = get()
        .jobs.filter((job) => !["QUEUED", "RUNNING", "WAITING_FOR_INPUT"].includes(job.status))
        .map((job) => job.job_id);
      set((state) => ({
        dismissed: [...new Set([...state.dismissed, ...finished])],
        justFinished: [],
      }));
      writeStored(get());
    },

    markSeen: () => {
      const finished = get()
        .jobs.filter((job) => !["QUEUED", "RUNNING", "WAITING_FOR_INPUT"].includes(job.status))
        .map((job) => job.job_id);
      set((state) => ({ seen: [...new Set([...state.seen, ...finished])].slice(-200) }));
      writeStored(get());
    },

    stop: () => {
      generation += 1;
      if (pollTimer !== null) clearTimeout(pollTimer);
      pollTimer = null;
    },
  };
});

/**
 * The newest job a page started (by the page's path), with its live state: what a page shows
 * when the user comes back to it. `jobId` (from the `job` query parameter "Open result" adds)
 * picks a specific one.
 */
export function startedJobFor(
  state: Pick<BackgroundJobsState, "jobs" | "started">,
  pagePath: string,
  jobId?: string | null,
): JobDTO | null {
  const entries = Object.values(state.started)
    .filter((entry) => (jobId ? entry.job_id === jobId : entry.return_to.split("?")[0] === pagePath))
    .sort((left, right) => right.started_at_ms - left.started_at_ms);
  for (const entry of entries) {
    const job = state.jobs.find((row) => row.job_id === entry.job_id);
    if (job) return job;
  }
  return null;
}

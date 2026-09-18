import { useCallback, useEffect, useMemo, useState } from "react";
import type {
  BacktestAttributionDTO,
  BacktestDecisionEventDTO,
  BacktestExperimentCreateInputDTO,
  BacktestExperimentDTO,
  BacktestSeriesPointDTO,
  StrategyDTO,
  StrategyRunDTO,
  StrategyVersionDTO,
} from "@/api/client";
import { api as apiClient } from "@/api/client";
import { useApiStore } from "@/stores/api";

import {
  STRATEGY_TASKS,
  strategyTaskFromLocation,
  strategyTaskToSearch,
  type StrategyTaskId,
} from "./strategyLabModel";
import { experimentsForStrategy, experimentReadiness, experimentRequest } from "./strategyExperimentModel";

export type { StrategyTaskId };

export interface StrategyRunDetails {
  events: BacktestDecisionEventDTO[];
  series: BacktestSeriesPointDTO[];
  attribution: BacktestAttributionDTO[];
}

export interface StrategyLabSelection {
  strategyId: string | null;
  strategyVersionId: string | null;
  strategyRunId: string | null;
  setStrategyId: (value: string | null) => void;
  setStrategyVersionId: (value: string | null) => void;
  setStrategyRunId: (value: string | null) => void;
}

interface UseStrategyLabParams {
  selection: StrategyLabSelection;
  gasDay: string;
  locationRevision: number;
}

function readTaskFromLocation(): StrategyTaskId {
  return strategyTaskFromLocation(window.location.search);
}

function writeTaskToLocation(task: StrategyTaskId): void {
  const nextSearch = strategyTaskToSearch(window.location.search, task);
  const next = new URL(window.location.href);
  next.search = nextSearch;
  window.history.pushState({ task }, "", next);
}

export function useStrategyLab({ selection, gasDay, locationRevision }: UseStrategyLabParams) {
  const [task, setTask] = useState<StrategyTaskId>(() => readTaskFromLocation());

  useEffect(() => {
    setTask(readTaskFromLocation());
  }, [locationRevision]);

  const [strategies, setStrategies] = useState<StrategyDTO[]>([]);
  const [versionsByStrategy, setVersionsByStrategy] = useState<
    Record<string, StrategyVersionDTO[]>
  >({});
  const [runs, setRuns] = useState<StrategyRunDTO[]>([]);
  const [detailsByRun, setDetailsByRun] = useState<
    Record<string, StrategyRunDetails>
  >({});
  /**
   * Backtest experiments, and the one the surface is currently working in.
   *
   * The registry shipped experiment grouping with the strategy lifecycle and no surface ever
   * created one, so a run could only be grouped by calling the API. The list is read for the whole
   * deployment (the route's own bound) and filtered per strategy here, because an experiment names
   * its strategy and a user may switch strategy without re-reading.
   */
  const [experiments, setExperiments] = useState<BacktestExperimentDTO[]>([]);
  const [selectedExperimentId, setSelectedExperimentId] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const strategyId = selection.strategyId;
  const versionId = selection.strategyVersionId;
  const selectedRunId = selection.strategyRunId;

  const selectedStrategy = useMemo(
    () => strategies.find((item) => item.strategy_id === strategyId) ?? null,
    [strategies, strategyId],
  );
  const versions = useMemo(
    () => (strategyId ? versionsByStrategy[strategyId] ?? [] : []),
    [strategyId, versionsByStrategy],
  );
  // The Inspector resolves detail from state the identity already received, so the versions this
  // workspace read are published for the `strategy-version` subject; clearing them (an empty list)
  // removes detail rather than inventing it.
  const publishStrategyVersionsRead = useApiStore((state) => state.publishStrategyVersionsRead);
  useEffect(() => {
    publishStrategyVersionsRead(versions);
  }, [publishStrategyVersionsRead, versions]);
  const selectedVersion = useMemo(
    () => versions.find((item) => item.strategy_version_id === versionId) ?? null,
    [versions, versionId],
  );  const selectedRun = useMemo(
    () => runs.find((item) => item.run_id === selectedRunId) ?? null,
    [runs, selectedRunId],
  );
  const backtestRuns = useMemo(
    () => runs.filter((run) => run.run_type === "BACKTEST"),
    [runs],
  );
  const strategyExperiments = useMemo(
    () => experimentsForStrategy(experiments, strategyId),
    [experiments, strategyId],
  );
  const selectedExperiment = useMemo(
    () => experiments.find((item) => item.experiment_id === selectedExperimentId) ?? null,
    [experiments, selectedExperimentId],
  );

  const openTask = useCallback((next: StrategyTaskId) => {
    setTask(next);
    writeTaskToLocation(next);
  }, []);

  const refreshStrategies = useCallback(async () => {
    try {
      const result = await apiClient.strategies();
      setStrategies(result.data);
    } catch (err) {
      setError(String(err));
    }
  }, []);

  const refreshVersions = useCallback(
    async (nextStrategyId: string) => {
      try {
        const result = await apiClient.strategyVersions(nextStrategyId);
        setVersionsByStrategy((current) => ({
          ...current,
          [nextStrategyId]: result.data,
        }));
      } catch (err) {
        setError(String(err));
      }
    },
    [],
  );

  const refreshRuns = useCallback(
    async (nextStrategyId: string) => {
      try {
        const result = await apiClient.strategyRegistryRuns({
          strategy_id: nextStrategyId,
          limit: 50,
        });
        setRuns(result.data);
      } catch (err) {
        setError(String(err));
      }
    },
    [],
  );

  const refreshExperiments = useCallback(async () => {
    try {
      const result = await apiClient.backtestExperiments();
      setExperiments(result.data);
      return result.data;
    } catch (err) {
      setError(String(err));
      return [];
    }
  }, []);

  /**
   * Open one run from the registry by id.
   *
   * The run history is a bounded read (50 newest), so a run an experiment names may not be in it -
   * an experiment's base run is often older than the window. This reads that run directly, and
   * falls back to the route's own answer rather than pretending the run does not exist.
   */
  const loadRegistryRun = useCallback(
    async (runId: string) => {
      const known = runs.find((item) => item.run_id === runId);
      if (known) return known;
      try {
        const result = await apiClient.strategyRegistryRun(runId);
        setRuns((current) =>
          current.some((item) => item.run_id === result.data.run_id)
            ? current
            : [result.data, ...current],
        );
        return result.data;
      } catch (err) {
        setError(String(err));
        return null;
      }
    },
    [runs],
  );

  const selectStrategy = useCallback(
    (nextStrategyId: string | null) => {
      selection.setStrategyId(nextStrategyId);
      selection.setStrategyVersionId(null);
      selection.setStrategyRunId(null);
      if (nextStrategyId) {
        void refreshVersions(nextStrategyId);
        void refreshRuns(nextStrategyId);
      } else {
        setVersionsByStrategy({});
        setRuns([]);
      }
    },
    [
      refreshRuns,
      refreshVersions,
      selection.setStrategyId,
      selection.setStrategyRunId,
      selection.setStrategyVersionId,
    ],
  );

  const selectVersion = useCallback(
    (nextVersionId: string | null) => {
      selection.setStrategyVersionId(nextVersionId);
      selection.setStrategyRunId(null);
    },
    [selection.setStrategyRunId, selection.setStrategyVersionId],
  );

  const selectRun = useCallback(
    (runId: string | null) => {
      selection.setStrategyRunId(runId);
    },
    [selection.setStrategyRunId],
  );

  const loadRunDetails = useCallback(
    async (runId: string) => {
      if (detailsByRun[runId]) return detailsByRun[runId];
      const [events, series, attribution] = await Promise.all([
        apiClient.strategyRunEvents(runId),
        apiClient.strategyRunSeries(runId),
        apiClient.strategyRunAttribution(runId),
      ]);
      const details: StrategyRunDetails = {
        events: events.data,
        series: series.data,
        attribution: attribution.data,
      };
      setDetailsByRun((current) => ({ ...current, [runId]: details }));
      return details;
    },
    [detailsByRun],
  );

  const runBacktest = useCallback(
    async (payload: Record<string, unknown>) => {
      setLoading(true);
      setError(null);
      setMessage(null);
      try {
        const result = await apiClient.createStrategyRun({
          strategy_version_id: String(payload.strategy_version_id),
          run_type: "BACKTEST",
          evaluation_period_start_utc: String(payload.evaluation_period_start_utc),
          evaluation_period_end_utc: String(payload.evaluation_period_end_utc),
          economic_assumptions:
            (payload.economic_assumptions as Record<string, unknown>) ?? {},
          experiment_id: payload.experiment_id
            ? String(payload.experiment_id)
            : undefined,
        });
        setMessage(result.data.run_id);
        selection.setStrategyRunId(result.data.run_id);
        if (strategyId) {
          await refreshRuns(strategyId);
        }
        await loadRunDetails(result.data.run_id);
        openTask("backtest");
        return result.data;
      } catch (err) {
        setError(String(err));
        return null;
      } finally {
        setLoading(false);
      }
    },
    [
      loadRunDetails,
      openTask,
      refreshRuns,
      selection.setStrategyRunId,
      strategyId,
    ],
  );

  const defaultPeriod = useMemo(() => {
    const end = new Date(`${gasDay}T23:59:59Z`);
    const start = new Date(end);
    start.setUTCFullYear(start.getUTCFullYear() - 1);
    return {
      start: start.toISOString().slice(0, 10),
      end: end.toISOString().slice(0, 10),
    };
  }, [gasDay]);

  /**
   * Create an experiment for the selected strategy and frozen version.
   *
   * The rule decides *whether* it may be created and *what* the body is, so this only refuses what
   * the rule refused and reports what the route answered: a surface that composed a partial body
   * would be inventing the facts the route then rejects.
   */
  const createExperiment = useCallback(
    async (draft: { name: string; hypothesis: string; period: { start: string; end: string } }) => {
      const subject = {
        strategyId,
        version: selectedVersion
          ? {
              strategy_version_id: selectedVersion.strategy_version_id,
              status: selectedVersion.status,
            }
          : null,
      };
      const readiness = experimentReadiness({ subject, draft });
      const body: BacktestExperimentCreateInputDTO | null = experimentRequest(
        { subject, draft },
        readiness,
      );
      if (!body) return null;
      setLoading(true);
      setError(null);
      setMessage(null);
      try {
        const result = await apiClient.createBacktestExperiment(body);
        setExperiments((current) => [result.data, ...current]);
        setSelectedExperimentId(result.data.experiment_id);
        setMessage(result.data.experiment_id);
        return result.data;
      } catch (err) {
        setError(String(err));
        return null;
      } finally {
        setLoading(false);
      }
    },
    [selectedVersion, strategyId],
  );

  const selectExperiment = useCallback(
    (experimentId: string | null) => {
      setSelectedExperimentId(experimentId);
      // Selecting an experiment is a view of the runs it groups; it never changes which version
      // the next run would use, because that stays the user's selection in the navigator.
      selection.setStrategyRunId(null);
    },
    [selection.setStrategyRunId],
  );

  /**
   * Open one experiment by id, reading it when the list has not loaded it.
   *
   * The list is bounded (200 newest), so an experiment an identity cites - or one opened from a
   * deep link - may not be in it. The route answers for one experiment directly, and this reads it
   * there rather than reporting that it does not exist.
   */
  const openExperiment = useCallback(
    async (experimentId: string) => {
      const known = experiments.find((item) => item.experiment_id === experimentId);
      if (known) {
        selectExperiment(experimentId);
        return known;
      }
      try {
        const result = await apiClient.backtestExperiment(experimentId);
        setExperiments((current) =>
          current.some((item) => item.experiment_id === result.data.experiment_id)
            ? current
            : [result.data, ...current],
        );
        selectExperiment(result.data.experiment_id);
        return result.data;
      } catch (err) {
        setError(String(err));
        return null;
      }
    },
    [experiments, selectExperiment],
  );

  /**
   * Edit a strategy's own metadata (name, description, tags).
   *
   * This is a `persist` on the *identity*, not on a version: the version's draft has the
   * workspace's primary slot, and the identity is edited where its other bounded acts live. The
   * route owns the bounds (name 1..256, description <= 4000) and refuses a retired strategy; the
   * surface reports the answer rather than assuming one.
   */
  const updateStrategyMetadata = useCallback(
    async (strategyIdToEdit: string, body: { name?: string; description?: string; tags?: string[] }) => {
      setLoading(true);
      setError(null);
      setMessage(null);
      try {
        const result = await apiClient.updateStrategyMetadata(strategyIdToEdit, body);
        setStrategies((current) =>
          current.map((item) =>
            item.strategy_id === result.data.strategy_id ? result.data : item,
          ),
        );
        setMessage(result.data.strategy_id);
        return result.data;
      } catch (err) {
        setError(String(err));
        return null;
      } finally {
        setLoading(false);
      }
    },
    [],
  );

  useEffect(() => {
    void refreshStrategies();
    void refreshExperiments();
  }, [refreshExperiments, refreshStrategies]);

  useEffect(() => {
    if (strategyId) {
      void refreshVersions(strategyId);
      void refreshRuns(strategyId);
    }
  }, [refreshRuns, refreshVersions, strategyId]);

  useEffect(() => {
    if (selectedRunId) {
      void loadRunDetails(selectedRunId);
    }
  }, [loadRunDetails, selectedRunId]);

  return {
    task,
    openTask,
    strategies,
    selectedStrategy,
    versions,
    selectedVersion,
    runs,
    backtestRuns,
    selectedRun,
    detailsByRun,
    experiments: strategyExperiments,
    selectedExperiment,
    loading,
    message,
    error,
    defaultPeriod,
    refreshStrategies,
    refreshVersions,
    refreshRuns,
    refreshExperiments,
    selectStrategy,
    selectVersion,
    selectRun,
    loadRunDetails,
    loadRegistryRun,
    runBacktest,
    createExperiment,
    selectExperiment,
    openExperiment,
    updateStrategyMetadata,
  };
}

export type StrategyLabController = ReturnType<typeof useStrategyLab>;

import { useCallback, useEffect, useMemo, useState } from "react";
import type {
  BacktestAttributionDTO,
  BacktestDecisionEventDTO,
  BacktestSeriesPointDTO,
  StrategyDTO,
  StrategyRunDTO,
  StrategyVersionDTO,
} from "@/api/client";
import { api as apiClient } from "@/api/client";

import {
  STRATEGY_TASKS,
  strategyTaskFromLocation,
  strategyTaskToSearch,
  type StrategyTaskId,
} from "./strategyLabModel";

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
  const selectedVersion = useMemo(
    () => versions.find((item) => item.strategy_version_id === versionId) ?? null,
    [versions, versionId],
  );
  const selectedRun = useMemo(
    () => runs.find((item) => item.run_id === selectedRunId) ?? null,
    [runs, selectedRunId],
  );
  const backtestRuns = useMemo(
    () => runs.filter((run) => run.run_type === "BACKTEST"),
    [runs],
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

  useEffect(() => {
    void refreshStrategies();
  }, [refreshStrategies]);

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
    loading,
    message,
    error,
    defaultPeriod,
    refreshStrategies,
    refreshVersions,
    refreshRuns,
    selectStrategy,
    selectVersion,
    selectRun,
    loadRunDetails,
    runBacktest,
  };
}

export type StrategyLabController = ReturnType<typeof useStrategyLab>;

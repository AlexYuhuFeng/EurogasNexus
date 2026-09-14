import { useCallback, useEffect, useState } from "react";
import type { MarketTask } from "@/app/model/marketCockpitModel";
import {
  readMarketViewPreference,
  resolveMarketViewTask,
  writeMarketViewPreference,
  marketViewPreferenceForTask,
  type MarketViewPreferenceId,
  type MarketViewTaskResolution,
} from "./viewPreference";

export interface MarketViewPreferenceState extends MarketViewTaskResolution {
  /** Persisted view for this principal, or null when nothing valid is stored. */
  persistedView: MarketViewPreferenceId | null;
  /** Remember the choice for the current principal when it is a view. */
  rememberTask: (task: MarketTask) => MarketViewPreferenceId | null;
}

/**
 * Resolve the market primary's task from URL > persisted preference > numeric
 * default, and remember an explicit numeric/map choice for the current
 * principal. `overview` and `capacity` stay transient: selecting them never
 * overwrites the persisted landing view.
 */
export function useMarketViewPreference(input: {
  search: string;
  activeWorkspace: string;
  principalId: string | null | undefined;
}): MarketViewPreferenceState {
  const { search, activeWorkspace, principalId } = input;
  const [persistedView, setPersistedView] = useState<MarketViewPreferenceId | null>(
    () => readMarketViewPreference(principalId),
  );

  useEffect(() => {
    setPersistedView(readMarketViewPreference(principalId));
  }, [principalId]);

  const rememberTask = useCallback(
    (task: MarketTask): MarketViewPreferenceId | null => {
      const view = marketViewPreferenceForTask(task);
      if (!view) return null;
      writeMarketViewPreference(principalId, view);
      setPersistedView(view);
      return view;
    },
    [principalId],
  );

  const resolution = resolveMarketViewTask({ search, activeWorkspace, persisted: persistedView });

  return {
    task: resolution.task,
    source: resolution.source,
    persistedView,
    rememberTask,
  };
}

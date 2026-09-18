import { useMemo, useState } from "react";
import { WorkspaceHeader } from "@/components/ui";
import type { StrategyLabController, StrategyTaskId } from "@/app/model/useStrategyLab";
import type { StrategyLabSelection } from "@/app/model/useStrategyLab";
import {
  strategyBacktestReadiness,
  strategyBacktestRequest,
  type StrategyBacktestDraft,
} from "@/app/model/strategyBacktestModel";
import { StrategyDesignWorkspace } from "./StrategyDesignWorkspace";
import { useStrategyDesignDraft } from "@/app/model/useStrategyDesignDraft";
import { StrategyBacktestWorkspace } from "./StrategyBacktestWorkspace";
import { StrategyCompareWorkspace } from "./StrategyCompareWorkspace";
import { StrategyShadowShell } from "./StrategyShadowShell";
import { StrategyIdentityHeader } from "./StrategyIdentityHeader";
import { StrategyNavigator } from "./StrategyNavigator";
import "./strategy-lab.css";

type Translate = (key: string) => string;

interface StrategyLabWorkspaceProps {
  controller: StrategyLabController;
  selection: StrategyLabSelection;
  gasDay: string;
  language: string;
  t: Translate;
}

const TASK_LABEL_KEYS: Record<StrategyTaskId, string> = {
  design: "strategy_lab.task.design",
  backtest: "strategy_lab.task.backtest",
  compare: "strategy_lab.task.compare",
  shadow: "strategy_lab.task.shadow",
};

export function StrategyLabWorkspace({
  controller,
  selection,
  gasDay,
  language,
  t,
}: StrategyLabWorkspaceProps) {
  const tabs = useMemo(
    () =>
      (Object.keys(TASK_LABEL_KEYS) as StrategyTaskId[]).map((id) => ({
        id,
        label: t(TASK_LABEL_KEYS[id]),
      })),
    [t],
  );

  // Action geography (`app/experience/actionGeography.ts`): running a backtest is a `compute`
  // consequence, so it occupies this workspace's single primary slot instead of sitting inside
  // the panel that configures it. The draft therefore lives here - one owner for the facts the
  // action needs - while the panel renders the fields and reports the preflight verdict.
  const [backtestDraft, setBacktestDraft] = useState<StrategyBacktestDraft>(() => ({
    start: controller.defaultPeriod.start,
    end: controller.defaultPeriod.end,
    missingDataPolicy: "FAIL",
    transactionCostTreatment: "UNAVAILABLE",
    transactionCost: "",
  }));
  const backtestReadiness = strategyBacktestReadiness({
    draft: backtestDraft,
    frozen: controller.selectedVersion?.status === "FROZEN",
    running: controller.loading,
  });
  // The Design task's `persist` act is saving the draft, so its draft lives here too: the panel
  // renders the form and the validation verdict, and this workspace performs the write. The two
  // `lifecycle` acts on that surface (freeze, fork) stay bounded in the panel by design.
  const designDraft = useStrategyDesignDraft({ controller, selection, t });
  const primaryAction =
    controller.task === "backtest" ? (
      <button
        type="button"
        disabled={!backtestReadiness.canRun}
        title={
          backtestReadiness.firstBlockerKey
            ? t(backtestReadiness.firstBlockerKey)
            : t("strategy_lab.run_backtest_hint")
        }
        onClick={() => {
          const request = strategyBacktestRequest(
            backtestDraft,
            controller.selectedVersion?.strategy_version_id,
          );
          // The rule produced the request, so this can only be null if the version vanished
          // between the render and the click; refusing then is the honest answer.
          if (request) void controller.runBacktest(request);
        }}
      >
        {t("strategy_lab.run_backtest")}
      </button>
    ) : controller.task === "design" && !designDraft.frozen ? (
      <button
        type="button"
        disabled={!designDraft.readiness.canSave}
        title={
          designDraft.readiness.firstBlockerKey
            ? t(designDraft.readiness.firstBlockerKey)
            : t("strategy_lab.save_draft_hint")
        }
        onClick={() => void designDraft.saveDraft()}
      >
        {t("strategy_lab.save_draft")}
      </button>
    ) : undefined;

  return (
    <div className="strategy-lab-workspace">
      <WorkspaceHeader
        title={t("nav.strategy")}
        taskLabel={t(TASK_LABEL_KEYS[controller.task])}
        idPrefix="strategy-lab-task"
        tabs={tabs}
        activeId={controller.task}
        panelId="strategy-lab-panel"
        tabLabel={t("nav.strategy")}
        tabsClassName="strategy-lab-task-tabs"
        primaryAction={primaryAction}
        onActivate={controller.openTask}
      />
      <div className="strategy-lab-grid" id="strategy-lab-panel">
        <StrategyNavigator
          controller={controller}
          language={language}
          t={t}
        />
        <div className="strategy-lab-main">
          <StrategyIdentityHeader
            controller={controller}
            gasDay={gasDay}
            language={language}
            t={t}
          />
          <div role="tabpanel" aria-label={t(TASK_LABEL_KEYS[controller.task])}>
            {controller.task === "design" && (
              <StrategyDesignWorkspace
                controller={controller}
                draft={designDraft}
                t={t}
              />
            )}
            {controller.task === "backtest" && (
              <StrategyBacktestWorkspace
                controller={controller}
                selection={selection}
                gasDay={gasDay}
                language={language}
                draft={backtestDraft}
                readiness={backtestReadiness}
                onDraftChange={setBacktestDraft}
                t={t}
              />
            )}
            {controller.task === "compare" && (
              <StrategyCompareWorkspace
                controller={controller}
                language={language}
                t={t}
              />
            )}
            {controller.task === "shadow" && (
              <StrategyShadowShell
                controller={controller}
                language={language}
                t={t}
              />
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

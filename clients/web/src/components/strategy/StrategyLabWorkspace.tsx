import { useMemo } from "react";
import { WorkspaceTabs } from "@/components/ui";
import type { StrategyLabController, StrategyTaskId } from "@/app/model/useStrategyLab";
import type { StrategyLabSelection } from "@/app/model/useStrategyLab";
import { StrategyDesignWorkspace } from "./StrategyDesignWorkspace";
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

  return (
    <div className="strategy-lab-workspace">
      <WorkspaceTabs
        idPrefix="strategy-lab-task"
        label={t("nav.strategy")}
        tabs={tabs}
        activeId={controller.task}
        panelId="strategy-lab-panel"
        className="strategy-lab-task-tabs"
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
                selection={selection}
                t={t}
              />
            )}
            {controller.task === "backtest" && (
              <StrategyBacktestWorkspace
                controller={controller}
                selection={selection}
                gasDay={gasDay}
                language={language}
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
              <StrategyShadowShell controller={controller} t={t} />
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

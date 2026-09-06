import { useState } from "react";
import type { StrategyLabController } from "@/app/model/useStrategyLab";

type Translate = (key: string) => string;

interface StrategyNavigatorProps {
  controller: StrategyLabController;
  language: string;
  t: Translate;
}

export function StrategyNavigator({
  controller,
  language,
  t,
}: StrategyNavigatorProps) {
  const [query, setQuery] = useState("");
  const strategies = controller.strategies.filter((strategy) => {
    const haystack = `${strategy.name} ${strategy.strategy_id}`.toLowerCase();
    return haystack.includes(query.trim().toLowerCase());
  });

  return (
    <aside className="strategy-navigator" aria-label={t("strategy_lab.navigator")}>
      <div className="strategy-navigator-header">
        <input
          type="search"
          value={query}
          placeholder={t("strategy_lab.search_placeholder")}
          onChange={(event) => setQuery(event.target.value)}
          aria-label={t("strategy_lab.search_placeholder")}
        />
        <button type="button" onClick={() => controller.selectStrategy(null)}>
          {t("strategy_lab.new_strategy")}
        </button>
      </div>
      {strategies.length === 0 && (
        <p className="muted">{t("strategy_lab.no_strategies")}</p>
      )}
      <ul className="strategy-list">
        {strategies.map((strategy) => {
          const active = strategy.strategy_id === controller.selectedStrategy?.strategy_id;
          return (
            <li key={strategy.strategy_id}>
              <button
                type="button"
                className={active ? "active" : undefined}
                onClick={() => controller.selectStrategy(strategy.strategy_id)}
              >
                <strong>{strategy.name}</strong>
                <span>{strategy.strategy_id}</span>
                <span className={`status-badge status-${strategy.lifecycle_status.toLowerCase()}`}>
                  {strategy.lifecycle_status}
                </span>
              </button>
              {active && controller.versions.length > 0 && (
                <ul className="strategy-version-list">
                  {controller.versions.map((version) => (
                    <li key={version.strategy_version_id}>
                      <button
                        type="button"
                        className={
                          version.strategy_version_id === controller.selectedVersion?.strategy_version_id
                            ? "active"
                            : undefined
                        }
                        onClick={() => controller.selectVersion(version.strategy_version_id)}
                      >
                        <span>v{version.version_number}</span>
                        <span className={`status-badge status-${version.status.toLowerCase()}`}>
                          {version.status}
                        </span>
                      </button>
                    </li>
                  ))}
                </ul>
              )}
            </li>
          );
        })}
      </ul>
      {language ? null : null}
    </aside>
  );
}

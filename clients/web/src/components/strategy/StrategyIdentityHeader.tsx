import type { StrategyLabController } from "@/app/model/useStrategyLab";

type Translate = (key: string) => string;

interface StrategyIdentityHeaderProps {
  controller: StrategyLabController;
  gasDay: string;
  language: string;
  t: Translate;
}

function formatTimestamp(value: string | null | undefined, language: string): string {
  if (!value) return "n/a";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return "n/a";
  return new Intl.DateTimeFormat(language.startsWith("zh") ? "zh-CN" : "en-GB", {
    year: "numeric",
    month: "short",
    day: "2-digit",
  }).format(parsed);
}

export function StrategyIdentityHeader({
  controller,
  gasDay,
  language,
  t,
}: StrategyIdentityHeaderProps) {
  const strategy = controller.selectedStrategy;
  const version = controller.selectedVersion;
  const summary = version?.definition_json ?? {};
  const hubs = Array.isArray(summary.components)
    ? Array.from(
        new Set(
          summary.components.flatMap((component) =>
            Array.isArray((component as Record<string, unknown>).hubs)
              ? ((component as Record<string, unknown>).hubs as string[])
              : [],
          ),
        ),
      ).join(", ")
    : "";
  const resources = Array.isArray(summary.resource_contexts)
    ? summary.resource_contexts
        .map((resource) => (resource as Record<string, unknown>).resource_id)
        .filter((value): value is string => Boolean(value))
        .join(", ")
    : "";

  return (
    <section className="strategy-identity-header" aria-label={t("strategy_lab.identity")}>
      <div className="strategy-identity-primary">
        <span className="eyebrow">{t("strategy_lab.strategy_identity")}</span>
        <strong>{strategy?.name ?? t("strategy_lab.no_strategy_selected")}</strong>
        <span className="strategy-identity-id">{strategy?.strategy_id ?? ""}</span>
        {version && (
          <span className={`strategy-version-state state-${version.status.toLowerCase()}`}>
            v{version.version_number} · {version.status}
          </span>
        )}
        {strategy && (
          <span className="strategy-lifecycle-state">
            {strategy.lifecycle_status}
          </span>
        )}
      </div>
      <div className="strategy-identity-meta">
        <span>{t("strategy_lab.gas_day")}: {gasDay}</span>
        <span>{t("strategy_lab.hubs")}: {hubs || t("data.unavailable")}</span>
        <span>{t("strategy_lab.resources")}: {resources || t("data.unavailable")}</span>
        <span>{t("strategy_lab.owner")}: {strategy?.created_by ?? "n/a"}</span>
        <span>{t("strategy_lab.modified")}: {formatTimestamp(strategy?.updated_at_utc, language)}</span>
        {controller.selectedRun && (
          <span>{t("strategy_lab.selected_run")}: {controller.selectedRun.run_id}</span>
        )}
      </div>
    </section>
  );
}

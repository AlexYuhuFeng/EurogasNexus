import type { RuntimeDependencyStateDTO } from "@/api/client";

type Translate = (key: string, options?: Record<string, unknown>) => string;

export type SchedulerReadinessState = "ready" | "partial" | "blocked";

export interface SchedulerReadiness {
  state: SchedulerReadinessState;
  value: string;
  detail: string;
}

interface SourceCounts {
  /** Sources the source list says are on a schedule (rows the scheduler created). */
  scheduled: number;
  registered: number;
  stale: number;
  failed: number;
}

function ageText(seconds: number, t: Translate): string {
  const minutes = Math.max(0, Math.round(seconds / 60));
  return minutes < 1
    ? t("runtime.dep_detail.age_under_minute")
    : t("runtime.dep_detail.age_minutes", { count: minutes });
}

/**
 * The data-operations scheduler row of the Runtime page, read from the scheduler's own
 * heartbeat rather than inferred from the source list.
 *
 * The source list only has a schedule for sources whose runtime row a scheduler scan created,
 * so a store no scheduler ever ran on showed "0/42 scheduled" and blamed the sources. The
 * heartbeat says what is true: whether a scheduler process is running, how long ago it last
 * reported, and how many sources it has on a schedule.
 */
export function schedulerReadiness(
  heartbeat: RuntimeDependencyStateDTO | undefined,
  sources: SourceCounts,
  t: Translate,
): SchedulerReadiness {
  const scheduled = heartbeat?.sources_scheduled ?? sources.scheduled;
  const registered = heartbeat?.registered_sources ?? sources.registered;
  const counts = `${scheduled}/${registered} ${t("runtime.scheduled_sources")}`;
  const sourceHealth = `${sources.stale} ${t("runtime.stale_sources")} / ${sources.failed} ${t("runtime.failed_sources")}`;
  if (!heartbeat) {
    // Dependencies not loaded yet: the source list is all there is.
    return {
      state: sources.scheduled === 0 ? "blocked" : sources.stale > 0 || sources.failed > 0 ? "partial" : "ready",
      value: counts,
      detail: sources.scheduled === 0 ? t("runtime.scheduler_blocked_detail") : sourceHealth,
    };
  }
  const age = typeof heartbeat.age_seconds === "number" ? heartbeat.age_seconds : null;
  if (age === null || !heartbeat.last_heartbeat_at_utc) {
    return {
      state: "blocked",
      value: t("runtime.scheduler_not_running"),
      detail: t("runtime.scheduler_no_heartbeat_detail"),
    };
  }
  const reported = t("runtime.dep_detail.heartbeat_age", { age: ageText(age, t) });
  if (heartbeat.state === "UNAVAILABLE") {
    return {
      state: "blocked",
      value: counts,
      detail: `${reported}. ${t("runtime.scheduler_stopped_detail")}`,
    };
  }
  if (heartbeat.state === "DEGRADED") {
    return { state: "partial", value: counts, detail: `${reported}. ${sourceHealth}` };
  }
  if (scheduled === 0) {
    return { state: "blocked", value: counts, detail: t("runtime.scheduler_blocked_detail") };
  }
  return {
    state: sources.stale > 0 || sources.failed > 0 ? "partial" : "ready",
    value: counts,
    detail: `${reported}. ${sourceHealth}`,
  };
}

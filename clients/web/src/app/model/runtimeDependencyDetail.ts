import type { RuntimeDependencyStateDTO } from "@/api/client";

type Translate = (key: string, options?: Record<string, unknown>) => string;

/**
 * The server's dependency notes in the reader's language. A server that predates `detail_code`
 * sends only its English note; the notes it can send are known, so they map to the same codes.
 */
const LEGACY_DETAIL_CODES: Record<string, string> = {
  "Runtime PostgreSQL is not configured.": "database_not_configured",
  "schema ok": "schema_ok",
  "schema incomplete": "schema_incomplete",
  "external provider calls are profile-gated": "provider_calls_gated",
  "SSE is advisory; PostgreSQL/API remain canonical": "stream_advisory",
  "no heartbeat recorded": "no_heartbeat",
};

function minutesText(seconds: number, t: Translate): string {
  const minutes = Math.max(0, Math.round(seconds / 60));
  return minutes < 1 ? t("runtime.dep_detail.age_under_minute") : t("runtime.dep_detail.age_minutes", { count: minutes });
}

export function dependencyDetailText(row: RuntimeDependencyStateDTO | undefined, t: Translate): string {
  if (!row) return "–";
  const code = row.detail_code
    ?? (row.detail ? LEGACY_DETAIL_CODES[row.detail] : undefined)
    ?? (row.detail === undefined && typeof row.age_seconds === "number" ? "heartbeat_age" : undefined);
  if (code === "heartbeat_age" && typeof row.age_seconds === "number") {
    return t("runtime.dep_detail.heartbeat_age", { age: minutesText(row.age_seconds, t) });
  }
  if (code === "schema_incomplete" && row.missing_tables?.length) {
    return t("runtime.dep_detail.schema_incomplete_count", { count: row.missing_tables.length });
  }
  if (code) {
    const key = `runtime.dep_detail.${code}`;
    const text = t(key);
    if (text && text !== key) return text;
  }
  return row.detail ?? "–";
}

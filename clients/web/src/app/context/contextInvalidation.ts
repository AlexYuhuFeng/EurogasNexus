import { traderContextKey, type TraderContext } from "./traderContext.ts";

export function resultContextMatches(
  resultContextKey: string | null,
  currentContext: TraderContext,
): boolean {
  return resultContextKey === traderContextKey(currentContext);
}

export function describeContextMismatch(
  resultContextKey: string | null,
  currentContext: TraderContext,
): string | null {
  if (resultContextMatches(resultContextKey, currentContext)) return null;
  return `result-context-mismatch:${resultContextKey ?? "unknown"}->${traderContextKey(currentContext)}`;
}

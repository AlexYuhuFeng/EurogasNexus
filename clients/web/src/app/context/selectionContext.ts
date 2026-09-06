export interface SelectionContext {
  routeId: string | null;
  resourceId: string | null;
  strategyRunId: string | null;
}

export const EMPTY_SELECTION_CONTEXT: SelectionContext = {
  routeId: null,
  resourceId: null,
  strategyRunId: null,
};

const SAFE_ID_PATTERN = /^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$/;

export function normalizeSelectionId(
  value: string | null | undefined,
): string | null {
  if (!value) return null;
  const normalized = value.trim();
  return SAFE_ID_PATTERN.test(normalized) ? normalized : null;
}

export function selectionContextKey(context: SelectionContext): string {
  return [
    context.routeId ?? "-",
    context.resourceId ?? "-",
    context.strategyRunId ?? "-",
  ].join("|");
}

export const EVIDENCE_TIME_BASIS = "UTC";

export function formatUtcTimestamp(
  value: string | null | undefined,
  fallback = "n/a",
): string {
  if (!value) return fallback;
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return fallback;
  return `${parsed.toISOString().slice(0, 19).replace("T", " ")} UTC`;
}

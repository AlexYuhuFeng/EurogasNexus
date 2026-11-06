/** The label of a tab and, when `<key>.short` is translated, its compact form. */
export function tabLabels(
  t: (key: string) => string,
  key: string,
): { label: string; shortLabel?: string } {
  const label = t(key);
  const shortKey = `${key}.short`;
  const shortLabel = t(shortKey);
  return shortLabel && shortLabel !== shortKey && shortLabel !== label ? { label, shortLabel } : { label };
}

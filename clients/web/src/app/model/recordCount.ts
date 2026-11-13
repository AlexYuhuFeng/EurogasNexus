/**
 * How a source's record count is displayed. ``null`` is the server saying it could not count
 * (the read failed): it is shown as an em dash, never as 0, which would read as "no data".
 */
export function formatRecordCount(value: number | null): string {
  return value === null ? "\u2014" : value.toLocaleString();
}

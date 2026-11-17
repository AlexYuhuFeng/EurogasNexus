/**
 * DataGrid's pure parts (UX-03): sorting, the next sort on a header press, and which cells of a
 * grouping column merge. Kept out of the component so they are tested without a browser and so
 * sorting 500 rows is one stable pass, not work done during render of each row.
 */
export type SortDirection = "ascending" | "descending";

export interface SortState {
  columnId: string;
  direction: SortDirection;
}

export type SortValue = string | number | null | undefined;

function missing(value: SortValue): boolean {
  return value === null || value === undefined || value === "" || (typeof value === "number" && !Number.isFinite(value));
}

/**
 * Compare two cell values for an ascending sort. Numbers compare as numbers, text with the
 * locale's collation and numeric segments ("Q1-27" before "Q10-27"). A missing value is not
 * zero: it sorts after every value in both directions (see `sortRows`).
 */
export function compareValues(left: SortValue, right: SortValue): number {
  if (typeof left === "number" && typeof right === "number") return left - right;
  return String(left).localeCompare(String(right), undefined, { numeric: true, sensitivity: "base" });
}

/** A stable sort that keeps missing values last whichever way the column is sorted. */
export function sortRows<R>(
  rows: readonly R[],
  value: ((row: R) => SortValue) | undefined,
  direction: SortDirection,
): R[] {
  if (!value) return [...rows];
  const sign = direction === "ascending" ? 1 : -1;
  return rows
    .map((row, index) => ({ row, index, key: value(row) }))
    .sort((left, right) => {
      const leftMissing = missing(left.key);
      const rightMissing = missing(right.key);
      if (leftMissing || rightMissing) {
        if (leftMissing && rightMissing) return left.index - right.index;
        return leftMissing ? 1 : -1;
      }
      return sign * compareValues(left.key, right.key) || left.index - right.index;
    })
    .map((entry) => entry.row);
}

/**
 * The sort after a press on a column header: a new column starts in its first direction
 * (figures largest first, text A to Z), the same column reverses.
 */
export function nextSort(
  current: SortState | null | undefined,
  columnId: string,
  firstDirection: SortDirection = "ascending",
): SortState {
  if (current?.columnId === columnId) {
    return { columnId, direction: current.direction === "ascending" ? "descending" : "ascending" };
  }
  return { columnId, direction: firstDirection };
}

/**
 * Row spans for a grouping column: the first row of each run of equal values carries the run's
 * length, the rows it covers carry 0, and a run of one carries 1.
 */
export function spanRuns(values: readonly SortValue[]): number[] {
  const spans = new Array<number>(values.length).fill(1);
  let start = 0;
  for (let index = 1; index <= values.length; index += 1) {
    if (index < values.length && values[index] === values[start]) continue;
    const length = index - start;
    spans[start] = length;
    for (let covered = start + 1; covered < index; covered += 1) spans[covered] = 0;
    start = index;
  }
  return spans;
}

/** What the phone split reads from a column. */
export interface PhoneColumn {
  rowHeader?: boolean;
  decorative?: boolean;
  priority?: "primary" | "secondary";
}

/** The columns a phone keeps in the row, and the ones it folds into Details. */
export function phoneColumnSplit<C extends PhoneColumn>(
  columns: readonly C[],
  keep = 3,
): { visible: C[]; folded: C[] } {
  const declared = columns.some((column) => column.priority === "primary");
  const visible = columns.filter((column, index) =>
    declared ? column.priority === "primary" || column.rowHeader : column.priority !== "secondary" && index < keep,
  );
  if (visible.length === 0 && columns[0]) visible.push(columns[0]);
  const folded = columns.filter((column) => !visible.includes(column) && !column.decorative);
  return { visible, folded };
}


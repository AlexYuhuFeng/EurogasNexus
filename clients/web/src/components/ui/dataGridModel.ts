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

/** A column the empty-column rule can judge: its raw value and whether it draws its own cell. */
export interface ValueColumn<R> {
  value?: (row: R) => SortValue;
  render?: (row: R) => unknown;
  rowHeader?: boolean;
  keepWhenEmpty?: boolean;
}

/**
 * The columns that carry a value in at least one row (owner, 2026-11-26: a column of dashes is
 * not information). Only a column that shows its raw value is judged: one that renders its own
 * cell, the row header, a column marked `keepWhenEmpty`, and any column of an empty grid stay.
 */
export function columnsWithValues<R, C extends ValueColumn<R>>(columns: readonly C[], rows: readonly R[]): C[] {
  if (rows.length === 0) return [...columns];
  return columns.filter((column) => {
    if (!column.value || column.render || column.rowHeader || column.keepWhenEmpty) return true;
    return rows.some((row) => {
      const value = column.value?.(row);
      return value !== null && value !== undefined && value !== "";
    });
  });
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


/** Up or down; null when there is no direction to show (first value, not a number, equal). */
export type Direction = "up" | "down" | null;

export function directionOf(value: number | null | undefined): Direction {
  if (value == null || !Number.isFinite(value) || value === 0) return null;
  return value > 0 ? "up" : "down";
}

/**
 * The live-cell flash (UX R2). `identity` is the row key, the column and the instrument the
 * value belongs to (a hub's row shows another contract when the tenor changes). Only a new
 * value under the same identity is a tick: it bumps `count` (which restarts the neutral flash)
 * and, for numbers, sets the direction shown beside the value until the next tick. A new
 * identity resets quietly: no flash, no direction.
 */
export interface FlashState {
  identity: string;
  value: SortValue;
  count: number;
  direction: Direction;
}

export function nextFlash(previous: FlashState | null, identity: string, value: SortValue): FlashState {
  if (!previous || previous.identity !== identity) return { identity, value, count: 0, direction: null };
  if (Object.is(previous.value, value)) return previous;
  const direction =
    typeof previous.value === "number" && typeof value === "number" ? directionOf(value - previous.value) : null;
  return { identity, value, count: previous.count + 1, direction };
}

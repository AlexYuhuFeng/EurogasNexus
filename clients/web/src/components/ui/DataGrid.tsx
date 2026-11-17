/**
 * DataGrid (UX-03): the one table. It replaces the semantic `<table class="position-ladder">`
 * tables and the div-based `.data-table` rows-as-buttons.
 *
 * - A real `<table>`: column headers, row headers, a sticky header row when the grid scrolls.
 * - Alignment by type: text left; figures right in tabular numerals with the unit in the header
 *   (a per-row unit only when units differ by row).
 * - Sortable columns: the header is a button, `aria-sort` on the sorted column, missing values
 *   last in both directions. Controlled (`sort` + `onSortChange`) or not (`defaultSort`).
 * - Rows with an action (or a selection) are a `grid`: one row is the Tab stop, Up/Down,
 *   Home/End and PageUp/PageDown move, Enter or Space runs the row action, the selected row is
 *   `aria-selected`. Controls inside a cell keep their own keys.
 * - Dense rows from tokens (28 compact, 32 regular), Skeleton rows while loading, one
 *   EmptyState line when there is nothing.
 * - Optional per-cell state marker (stale, late, simulated, revised, manual): a short visible
 *   word next to the value with its full description for assistive technology, so a simulated
 *   price is marked in the cell itself, not only in a banner.
 * - Optional live-cell flash on a value change, once, background only; off under reduced motion.
 *
 * - Phone width (DESIGN_TOKENS "DataGrid on a phone"): a grid with more columns than a phone shows
 *   keeps its first columns (or the ones marked `priority: "primary"`) and puts the rest behind a
 *   per-row "Details" toggle as label/value rows, so it never makes the page wider than the
 *   screen. `phoneLayout="scroll"` keeps every column and scrolls the grid inside its own box
 *   instead (a ladder read across).
 *
 * Performance: no layout reads during render; rows are memoised, sorting is one stable pass,
 * focus moves through the table's own `rows` collection. 500 rows render without measuring.
 */
import {
  Fragment,
  memo,
  useEffect,
  useMemo,
  useId,
  useRef,
  useState,
  type KeyboardEvent,
  type MouseEvent,
  type ReactNode,
} from "react";

import { useTranslation } from "react-i18next";
import { useCompactWidth } from "@/app/shell/useShellLayout";
import { EmptyState } from "./EmptyState";
import { gridRowIndex } from "./keyboard";
import { Skeleton } from "./Skeleton";
import { nextSort, phoneColumnSplit, sortRows, spanRuns, type SortDirection, type SortState, type SortValue } from "./dataGridModel";

export { phoneColumnSplit };

export type { SortDirection, SortState } from "./dataGridModel";

export type CellStateKind = "stale" | "late" | "simulated" | "revised" | "manual";

export interface CellState {
  kind: CellStateKind;
  /** Short visible word ("sim", "late 3 h"). */
  label: string;
  /** Full description for the tooltip and screen readers ("Simulated: not a market price"). */
  description: string;
}

export interface DataGridColumn<R> {
  id: string;
  header: ReactNode;
  /** Tooltip on the header (the full name of an abbreviation). */
  headerTitle?: string;
  /** The unit, shown once in the header ("MWh", "EUR/MWh"). */
  unit?: ReactNode;
  /** `number` aligns right in tabular numerals; `text` and `date` align left. */
  type?: "text" | "number" | "date";
  align?: "start" | "end" | "center";
  /** The raw value: used to sort, to detect a change for the flash, and to display by default. */
  value?: (row: R) => SortValue;
  /** Display of the value (defaults to the value, "–" when missing). */
  format?: (value: SortValue, row: R) => ReactNode;
  /** Full cell content, overriding value/format for display. */
  render?: (row: R) => ReactNode;
  sortable?: boolean;
  /** The first direction a press sorts in (figures usually largest first). */
  firstDirection?: SortDirection;
  /** The row's header cell (`<th scope="row">`). */
  rowHeader?: boolean;
  /** Merge equal consecutive values (a month over its hubs) while the grid is in this order. */
  span?: boolean;
  state?: (row: R) => CellState | null | undefined;
  /** Flash the cell once when its value changes. */
  flash?: boolean;
  cellTitle?: (row: R) => string | undefined;
  cellClassName?: (row: R) => string | undefined;
  cellAttributes?: (row: R) => Record<string, string | undefined>;
  /** CSS width of the column ("8ch", "120px"). */
  width?: string;
  /** Hidden from screen readers (a decorative bar). */
  decorative?: boolean;
  /**
   * At phone width: `primary` columns stay in the row, `secondary` ones move into the row's
   * Details. Unset on every column: the first `phoneColumns` columns stay.
   */
  priority?: "primary" | "secondary";
}

export interface DataGridProps<R> {
  columns: readonly DataGridColumn<R>[];
  rows: readonly R[];
  rowKey: (row: R) => string;
  /** The table's accessible name. */
  label: string;
  density?: "compact" | "regular";
  sort?: SortState | null;
  defaultSort?: SortState | null;
  onSortChange?: (sort: SortState) => void;
  /** Enter, Space or a click on the row. */
  onRowAction?: (row: R) => void;
  /** The selected row (selection mode when not undefined). */
  selectedKey?: string | null;
  rowAttributes?: (row: R) => Record<string, string | undefined>;
  rowClassName?: (row: R) => string | undefined;
  loading?: boolean;
  loadingLabel?: string;
  /** What an empty grid says (an EmptyState, or a reason string). */
  empty?: ReactNode;
  caption?: ReactNode;
  /** Rows below the body (totals), rendered as given inside `<tfoot>`. */
  footer?: ReactNode;
  /** CSS max-height: the grid scrolls inside it and its header sticks. */
  maxHeight?: string;
  className?: string;
  /** Marker for acceptance checks (`data-grid`). */
  id?: string;
  /** Extra attributes on the table (`data-position-ladder`). */
  tableAttributes?: Record<string, string | undefined>;
  /**
   * At phone width: `columns` (default) keeps the primary columns and folds the rest into each
   * row's Details; `scroll` keeps every column and scrolls inside the grid's own box.
   */
  phoneLayout?: "columns" | "scroll";
  /** How many columns stay in the row at phone width when none is marked primary (default 3). */
  phoneColumns?: number;
}

function alignOf<R>(column: DataGridColumn<R>): "start" | "end" | "center" {
  return column.align ?? (column.type === "number" ? "end" : "start");
}

function display<R>(column: DataGridColumn<R>, row: R): ReactNode {
  if (column.render) return column.render(row);
  const value = column.value?.(row);
  if (column.format) return column.format(value, row);
  return value === null || value === undefined || value === "" ? "–" : value;
}

function StateMark({ state }: { state: CellState }) {
  return (
    <span className="ds-cell-mark" data-state={state.kind} title={state.description}>
      <span aria-hidden="true">{state.label}</span>
      <span className="ds-visually-hidden">{state.description}</span>
    </span>
  );
}

/** A cell value that flashes once when it changes (background only, CSS animation). */
function FlashValue({ watch, children }: { watch: SortValue; children: ReactNode }) {
  const previous = useRef(watch);
  const [count, setCount] = useState(0);
  useEffect(() => {
    if (previous.current !== watch) {
      previous.current = watch;
      setCount((value) => value + 1);
    }
  }, [watch]);
  return (
    <span className="ds-cell-flash" data-flash={count === 0 ? undefined : count % 2 ? "a" : "b"}>
      {children}
    </span>
  );
}

interface RowProps<R> {
  row: R;
  rowId: string;
  columns: readonly DataGridColumn<R>[];
  spans: (number[] | null)[];
  index: number;
  tabbable: boolean;
  interactive: boolean;
  selected: boolean | undefined;
  attributes?: Record<string, string | undefined>;
  className?: string;
  /** Phone width: the columns folded into this row's Details, and whether they are open. */
  folded?: readonly DataGridColumn<R>[];
  expanded?: boolean;
  onToggle?: (rowId: string) => void;
  detailsLabel?: string;
  detailId?: string;
}

function RowView<R>({ row, rowId, columns, spans, index, tabbable, interactive, selected, attributes, className, folded, expanded, onToggle, detailsLabel, detailId }: RowProps<R>) {
  const hasDetails = Boolean(folded && folded.length > 0);
  return (
    <Fragment>
    <tr
      data-row-key={rowId}
      data-row-index={index}
      tabIndex={interactive ? (tabbable ? 0 : -1) : undefined}
      aria-selected={selected}
      className={[className, selected ? "is-selected" : ""].filter(Boolean).join(" ") || undefined}
      {...attributes}
    >
      {columns.map((column, columnIndex) => {
        const span = spans[columnIndex]?.[index] ?? 1;
        if (span === 0) return null;
        const state = column.state?.(row) ?? null;
        const content = display(column, row);
        const Cell = column.rowHeader ? "th" : "td";
        return (
          <Cell
            key={column.id}
            scope={column.rowHeader ? (span > 1 ? "rowgroup" : "row") : undefined}
            rowSpan={span > 1 ? span : undefined}
            data-align={alignOf(column)}
            data-col={column.id}
            className={column.cellClassName?.(row)}
            title={column.cellTitle?.(row)}
            aria-hidden={column.decorative || undefined}
            {...column.cellAttributes?.(row)}
          >
            {column.flash ? <FlashValue watch={column.value?.(row)}>{content}</FlashValue> : content}
            {state ? <StateMark state={state} /> : null}
          </Cell>
        );
      })}
      {hasDetails ? (
        <td className="ds-grid-more" data-align="end">
          <button
            type="button"
            className="ds-grid-more-toggle"
            aria-expanded={expanded}
            aria-controls={detailId}
            aria-label={detailsLabel}
            title={detailsLabel}
            onClick={() => onToggle?.(rowId)}
          >
            <span aria-hidden="true">{expanded ? "▾" : "▸"}</span>
          </button>
        </td>
      ) : null}
    </tr>
    {hasDetails && expanded ? (
      <tr className="ds-grid-detail" id={detailId}>
        <td colSpan={columns.length + 1}>
          <dl className="ds-grid-detail-list">
            {folded!.map((column) => {
              const state = column.state?.(row) ?? null;
              return (
                <div key={column.id} data-col={column.id}>
                  <dt>
                    {column.header}
                    {column.unit ? <span className="ds-grid-unit">{column.unit}</span> : null}
                  </dt>
                  <dd data-align={alignOf(column)} title={column.cellTitle?.(row)}>
                    {display(column, row)}
                    {state ? <StateMark state={state} /> : null}
                  </dd>
                </div>
              );
            })}
          </dl>
        </td>
      </tr>
    ) : null}
    </Fragment>
  );
}

const Row = memo(RowView) as typeof RowView;

export function DataGrid<R>({
  columns: allColumns,
  rows,
  rowKey,
  label,
  density = "regular",
  sort: controlledSort,
  defaultSort = null,
  onSortChange,
  onRowAction,
  selectedKey,
  rowAttributes,
  rowClassName,
  loading = false,
  loadingLabel,
  empty,
  caption,
  footer,
  maxHeight,
  className,
  id,
  tableAttributes,
  phoneLayout = "columns",
  phoneColumns = 3,
}: DataGridProps<R>) {
  const { t } = useTranslation();
  const compactWidth = useCompactWidth();
  const phoneFold = compactWidth && phoneLayout === "columns" && allColumns.length > phoneColumns;
  const split = useMemo(
    () => (phoneFold ? phoneColumnSplit(allColumns, phoneColumns) : { visible: [...allColumns], folded: [] }),
    [phoneFold, allColumns, phoneColumns],
  );
  const columns = split.visible;
  const [expandedKeys, setExpandedKeys] = useState<ReadonlySet<string>>(() => new Set());
  const toggleExpanded = useMemo(
    () => (rowId: string) =>
      setExpandedKeys((current) => {
        const next = new Set(current);
        if (next.has(rowId)) next.delete(rowId);
        else next.add(rowId);
        return next;
      }),
    [],
  );
  const gridDomId = useId();
  const [ownSort, setOwnSort] = useState<SortState | null>(defaultSort);
  const sort = controlledSort !== undefined ? controlledSort : ownSort;
  const interactive = Boolean(onRowAction) || selectedKey !== undefined;
  const body = useRef<HTMLTableSectionElement>(null);

  const sorted = useMemo(() => {
    if (!sort) return [...rows];
    const column = allColumns.find((item) => item.id === sort.columnId);
    return sortRows(rows, column?.value, sort.direction);
  }, [rows, allColumns, sort]);

  const spans = useMemo(
    () =>
      columns.map((column) =>
        column.span && (!sort || sort.columnId === column.id) && column.value
          ? spanRuns(sorted.map((row) => column.value!(row)))
          : null,
      ),
    [columns, sorted, sort],
  );

  const keys = useMemo(() => sorted.map(rowKey), [sorted, rowKey]);
  const selectedIndex = selectedKey == null ? -1 : keys.indexOf(selectedKey);
  const [focusKey, setFocusKey] = useState<string | null>(null);
  const focusIndex = focusKey !== null && keys.includes(focusKey) ? keys.indexOf(focusKey) : Math.max(selectedIndex, 0);

  const pressSort = (column: DataGridColumn<R>) => {
    const next = nextSort(sort, column.id, column.firstDirection ?? (column.type === "number" ? "descending" : "ascending"));
    if (controlledSort === undefined) setOwnSort(next);
    onSortChange?.(next);
  };

  const rowAt = (target: EventTarget | null): HTMLTableRowElement | null => {
    const element = target as HTMLElement | null;
    const tr = element?.closest?.("tr");
    return tr && body.current?.contains(tr) ? (tr as HTMLTableRowElement) : null;
  };

  const onKeyDown = (event: KeyboardEvent<HTMLTableSectionElement>) => {
    if (!interactive) return;
    const tr = rowAt(event.target);
    if (!tr || event.target !== tr) return; // a control inside a cell keeps its keys
    const index = Number(tr.dataset.rowIndex);
    if ((event.key === "Enter" || event.key === " ") && onRowAction) {
      event.preventDefault();
      const row = sorted[index];
      if (row !== undefined) onRowAction(row);
      return;
    }
    const next = gridRowIndex(index, sorted.length, event.key);
    if (next === null) return;
    event.preventDefault();
    setFocusKey(keys[next] ?? null);
    const target = body.current?.querySelector<HTMLTableRowElement>(`tr[data-row-index="${next}"]`);
    target?.focus();
  };

  const onClick = (event: MouseEvent<HTMLTableSectionElement>) => {
    if (!onRowAction) return;
    const tr = rowAt(event.target);
    if (!tr) return;
    const control = (event.target as HTMLElement).closest("button, a, input, select, textarea, summary, [role='dialog']");
    if (control && tr.contains(control)) return;
    const row = sorted[Number(tr.dataset.rowIndex)];
    setFocusKey(tr.dataset.rowKey ?? null);
    if (row !== undefined) onRowAction(row);
  };

  const anySortable = columns.some((column) => column.sortable);
  const showBody = !loading || rows.length > 0;
  const classes = ["ds-grid", `ds-grid-${density}`, interactive ? "ds-grid-interactive" : "", className]
    .filter(Boolean)
    .join(" ");
  return (
    <div
      className={maxHeight ? "ds-grid-wrap ds-grid-scroll" : "ds-grid-wrap"}
      style={maxHeight ? { maxHeight } : undefined}
      // A scrolling region is reachable by keyboard; a grid with focusable rows or sort buttons
      // already is.
      tabIndex={interactive || anySortable ? undefined : 0}
      data-grid={id}
      data-phone-layout={phoneFold ? "folded" : undefined}
    >
      <table className={classes} role={interactive ? "grid" : undefined} aria-label={label} aria-busy={loading || undefined} {...tableAttributes}>
        {caption ? <caption className="ds-grid-caption">{caption}</caption> : null}
        <colgroup>
          {columns.map((column) => (
            <col key={column.id} style={column.width ? { width: column.width } : undefined} />
          ))}
        </colgroup>
        <thead>
          <tr>
            {columns.map((column) => {
              const sorted = sort?.columnId === column.id ? sort.direction : undefined;
              const heading = (
                <span className="ds-grid-head">
                  <span className="ds-grid-head-label">{column.header}</span>
                  {column.unit ? <span className="ds-grid-unit">{column.unit}</span> : null}
                </span>
              );
              return (
                <th
                  key={column.id}
                  scope="col"
                  data-align={alignOf(column)}
                  data-col={column.id}
                  aria-sort={column.sortable ? (sorted ?? "none") : undefined}
                  title={column.headerTitle}
                >
                  {column.sortable ? (
                    <button type="button" className="ds-grid-sort" onClick={() => pressSort(column)} data-sorted={sorted}>
                      {heading}
                      <span className="ds-grid-sort-mark" aria-hidden="true">
                        {sorted === "ascending" ? "▲" : sorted === "descending" ? "▼" : ""}
                      </span>
                    </button>
                  ) : (
                    heading
                  )}
                </th>
              );
            })}
            {split.folded.length > 0 ? (
              <th scope="col" className="ds-grid-more" data-align="end">
                <span className="ds-visually-hidden">{t("grid.details")}</span>
              </th>
            ) : null}
          </tr>
        </thead>
        {showBody && sorted.length > 0 ? (
          <tbody ref={body} onKeyDown={onKeyDown} onClick={onClick}>
            {sorted.map((row, index) => {
              const key = keys[index]!;
              return (
                <Row
                  key={key}
                  row={row}
                  rowId={key}
                  columns={columns}
                  spans={spans}
                  index={index}
                  tabbable={index === focusIndex}
                  interactive={interactive}
                  selected={selectedKey === undefined ? undefined : key === selectedKey}
                  attributes={rowAttributes?.(row)}
                  className={rowClassName?.(row)}
                  folded={split.folded.length > 0 ? split.folded : undefined}
                  expanded={expandedKeys.has(key)}
                  onToggle={toggleExpanded}
                  detailsLabel={t("grid.details")}
                  detailId={`${gridDomId}-detail-${index}`}
                />
              );
            })}
          </tbody>
        ) : (
          <tbody>
            <tr className="ds-grid-placeholder">
              <td colSpan={columns.length + (split.folded.length > 0 ? 1 : 0)}>
                {loading ? (
                  <Skeleton label={loadingLabel ?? label} rows={4} />
                ) : typeof empty === "string" || empty === undefined ? (
                  <EmptyState compact reason={empty ?? "–"} />
                ) : (
                  empty
                )}
              </td>
            </tr>
          </tbody>
        )}
        {footer ? <tfoot>{footer}</tfoot> : null}
      </table>
    </div>
  );
}

/**
 * Native ENTSOG context for one explicit point.
 *
 * The panel is a read surface, not an analysis engine: it asks the shared authenticated
 * transport for native physical flows and firm technical capacity, lets
 * `buildNativeCapacityContext` pair them, and renders exactly what that model returned.
 * The approximate ratio is reading context only; it is never clipped, promoted to an
 * economic measure, or turned into a zero when the model did not indicate one.
 */

import { useEffect, useRef, useState, type FormEvent } from "react";
import {
  fetchNativeCapacity,
  fetchNativeFlows,
  type ApiMeta,
  type NativeCapacityObsDTO,
  type NativeFlowObsDTO,
  type NativePhysicalFetchOptions,
} from "@/api/client";
import {
  NATIVE_CAPACITY_MAX_OBSERVATIONS,
  NATIVE_CAPACITY_REASON_CODES,
  buildNativeCapacityContext,
  type NativeCapacityContext,
} from "@/app/model/nativeCapacityContext";

export type NativeCapacityTranslate = (key: string) => string;

const POINT_ID_MAX_LENGTH = 128;
const KNOWN_REASONS: ReadonlySet<string> = new Set<string>(NATIVE_CAPACITY_REASON_CODES);

export const NATIVE_CAPACITY_PAGE_SIZE = 50;
const NO_PAGE_CHANGE = (_page: number): void => {};

/** The explicit From/To pair a caller supplied; both bounds travel together. */
export interface NativeCapacityWindow {
  readonly fromUtc: string;
  readonly toUtc: string;
}

export type NativeCapacityWindowInput =
  | { readonly state: "none" }
  | { readonly state: "invalid"; readonly validationKey: string }
  | { readonly state: "window"; readonly window: NativeCapacityWindow };

/**
 * Pair the two optional text inputs without inventing a date.
 *
 * Both blank means no window, exactly as before. One blank is a caller error and is
 * rejected before a query is started. The panel deliberately does not parse the
 * timestamps here: the shared API client owns strict aware-ISO validation, so the
 * accepted text is forwarded verbatim rather than re-derived.
 */
export function nativeCapacityWindowFromInputs(
  fromInput: string,
  toInput: string,
): NativeCapacityWindowInput {
  const fromUtc = fromInput.trim();
  const toUtc = toInput.trim();
  if (!fromUtc && !toUtc) return { state: "none" };
  if (!fromUtc || !toUtc) {
    return { state: "invalid", validationKey: "nativeCapacity.validation_window_pair" };
  }
  return { state: "window", window: { fromUtc, toUtc } };
}

export interface NativeCapacityPageWindow {
  readonly page: number;
  readonly pageCount: number;
  readonly start: number;
  readonly end: number;
  readonly total: number;
}

/**
 * Resolve one deterministic display page. The caller keeps the complete read; this
 * window never rewrites the model, it only decides which slice is painted. Out-of-range
 * pages clamp instead of throwing or silently returning an empty result.
 */
export function nativeCapacityPageWindow(
  total: number,
  requestedPage: number,
): NativeCapacityPageWindow {
  const safeTotal = Math.max(0, Math.trunc(total));
  const pageCount = Math.max(1, Math.ceil(safeTotal / NATIVE_CAPACITY_PAGE_SIZE));
  const page = Math.min(Math.max(0, Math.trunc(requestedPage)), pageCount - 1);
  const startIndex = page * NATIVE_CAPACITY_PAGE_SIZE;
  const end = Math.min(startIndex + NATIVE_CAPACITY_PAGE_SIZE, safeTotal);
  return {
    page,
    pageCount,
    start: safeTotal === 0 ? 0 : startIndex + 1,
    end,
    total: safeTotal,
  };
}

/**
 * A new read starts at the first page; re-rendering the same read only clamps a page
 * that no longer exists. This keeps loading more/shrinking data from stranding a page.
 */
export function nativeCapacityPageForRead(
  previousRead: NativeCapacityRead,
  read: NativeCapacityRead,
  requestedPage: number,
): number {
  if (previousRead !== read) return 0;
  return nativeCapacityPageWindow(read.contexts.length, requestedPage).page;
}

export interface NativeCapacityRead {
  readonly contexts: readonly NativeCapacityContext[];
  readonly flowMeta: ApiMeta;
  readonly capacityMeta: ApiMeta;
}

export type NativeCapacityReader = (
  pointId: string,
  signal: AbortSignal,
  window?: NativeCapacityWindow | null,
) => Promise<NativeCapacityRead>;

/**
 * Read both native physical endpoints concurrently under one signal. The shared API
 * client owns authentication, the browser/Tauri base URL and envelope parsing. When
 * the caller supplies a window, the exact same pair is attached to both reads.
 */
export async function readNativeCapacity(
  pointId: string,
  signal: AbortSignal,
  window: NativeCapacityWindow | null = null,
): Promise<NativeCapacityRead> {
  const options: NativePhysicalFetchOptions = {
    pointId,
    limit: NATIVE_CAPACITY_MAX_OBSERVATIONS,
    signal,
    ...(window ? { fromUtc: window.fromUtc, toUtc: window.toUtc } : {}),
  };
  const [flowResponse, capacityResponse] = await Promise.all([
    fetchNativeFlows(options),
    fetchNativeCapacity(options),
  ]);
  return {
    contexts: buildNativeCapacityContext(flowResponse.data, capacityResponse.data),
    flowMeta: flowResponse.meta,
    capacityMeta: capacityResponse.meta,
  };
}

export type NativeCapacityQueryOutcome =
  | {
      readonly state: "success";
      readonly pointId: string;
      /** The accepted pair; optional only so older custom readers stay compatible. */
      readonly window?: NativeCapacityWindow | null;
      readonly read: NativeCapacityRead;
    }
  | { readonly state: "error"; readonly pointId: string; readonly error: unknown }
  | { readonly state: "superseded" };

/**
 * Owns one query generation at a time. Starting a query aborts the previous one and
 * invalidates its completion; disposing the session (unmount) does the same without
 * producing another result. A superseded request can never publish over a newer one.
 */
export class NativeCapacityQuerySession {
  private generation = 0;
  private controller: AbortController | null = null;

  constructor(private readonly read: NativeCapacityReader = readNativeCapacity) {}

  async run(
    pointId: string,
    window: NativeCapacityWindow | null = null,
  ): Promise<NativeCapacityQueryOutcome> {
    const generation = ++this.generation;
    this.controller?.abort();
    const controller = new AbortController();
    this.controller = controller;

    try {
      const read = await this.read(pointId, controller.signal, window);
      if (generation !== this.generation) return { state: "superseded" };
      return { state: "success", pointId, window, read };
    } catch (error) {
      if (generation !== this.generation || controller.signal.aborted) {
        return { state: "superseded" };
      }
      return { state: "error", pointId, error };
    } finally {
      if (this.controller === controller) this.controller = null;
    }
  }

  dispose(): void {
    this.generation += 1;
    this.controller?.abort();
    this.controller = null;
  }
}

type QueryState = "idle" | "loading" | "success" | "error";

function reasonLabelKey(reasonCode: string): string {
  return KNOWN_REASONS.has(reasonCode)
    ? `nativeCapacity.reason.${reasonCode}`
    : "nativeCapacity.reason.general";
}

function failureCode(error: unknown): string {
  if (typeof error === "object" && error !== null) {
    const status = (error as { status?: unknown }).status;
    if (typeof status === "number") return `HTTP ${status}`;
    const code = (error as { code?: unknown }).code;
    if (typeof code === "string" && code.trim().length > 0) return code;
  }
  return "native_capacity_query_failed";
}

function formatIndicativeRatio(value: number): string {
  // Display rounding only. The model's comparison is never clipped or reclassified.
  return value.toLocaleString(undefined, { maximumFractionDigits: 6 });
}

function unavailable(value: string | null | undefined, t: NativeCapacityTranslate): string {
  return value && value.trim().length > 0 ? value : t("nativeCapacity.not_available");
}

export function NativeCapacityPaginationControls({
  pagination,
  onPageChange,
  t,
}: {
  pagination: NativeCapacityPageWindow;
  onPageChange: (page: number) => void;
  t: NativeCapacityTranslate;
}) {
  const hasPrevious = pagination.page > 0;
  const hasNext = pagination.page + 1 < pagination.pageCount;

  return (
    <nav
      className="capacity-pagination"
      aria-label={t("nativeCapacity.pagination")}
      data-native-pagination="true"
    >
      <span data-native-page-status="true" aria-live="polite">
        {t("nativeCapacity.page")}{" "}
        <strong data-native-page-current={pagination.page + 1}>{pagination.page + 1}</strong>{" "}
        {t("nativeCapacity.page_of")}{" "}
        <strong data-native-page-count={pagination.pageCount}>{pagination.pageCount}</strong>
      </span>
      <span
        data-native-page-range="true"
        data-native-page-start={pagination.start}
        data-native-page-end={pagination.end}
        data-native-page-total={pagination.total}
      >
        {t("nativeCapacity.showing")}{" "}
        <strong>{pagination.start}</strong>–<strong>{pagination.end}</strong>{" "}
        {t("nativeCapacity.of")} <strong>{pagination.total}</strong>
      </span>
      <span>{t("nativeCapacity.page_size")}</span>
      <button
        type="button"
        aria-label={t("nativeCapacity.previous_page")}
        disabled={!hasPrevious}
        onClick={() => onPageChange(pagination.page - 1)}
        data-native-page-action="previous"
      >
        {t("nativeCapacity.previous")}
      </button>
      <button
        type="button"
        aria-label={t("nativeCapacity.next_page")}
        disabled={!hasNext}
        onClick={() => onPageChange(pagination.page + 1)}
        data-native-page-action="next"
      >
        {t("nativeCapacity.next")}
      </button>
    </nav>
  );
}

function EvidenceValue({
  value,
  t,
}: {
  value: string | null | undefined;
  t: NativeCapacityTranslate;
}) {
  return value && value.trim().length > 0 ? (
    <code>{value}</code>
  ) : (
    <span>{t("nativeCapacity.not_available")}</span>
  );
}

function ObservationEvidence({
  title,
  observation,
  t,
}: {
  title: string;
  observation: NativeFlowObsDTO | NativeCapacityObsDTO;
  t: NativeCapacityTranslate;
}) {
  const capacityType = "capacity_type" in observation ? observation.capacity_type : null;
  return (
    <section className="capacity-inspector-section">
      <h4>{title}</h4>
      <dl className="capacity-point-metrics">
        <div><dt>{t("nativeCapacity.observation_id")}</dt><dd><EvidenceValue t={t} value={observation.observation_id} /></dd></div>
        <div><dt>{t("nativeCapacity.point")}</dt><dd>{observation.point_id} · {observation.point_name}</dd></div>
        <div><dt>{t("nativeCapacity.operator")}</dt><dd>{unavailable(observation.operator_key, t)}</dd></div>
        <div><dt>{t("nativeCapacity.direction")}</dt><dd>{observation.direction}</dd></div>
        {capacityType && <div><dt>{t("nativeCapacity.capacity_type")}</dt><dd><code>{capacityType}</code></dd></div>}
        <div><dt>{t("nativeCapacity.period")}</dt><dd>{observation.period_start_utc} – {observation.period_end_utc}</dd></div>
        <div><dt>{t("nativeCapacity.observed_at")}</dt><dd>{unavailable(observation.observed_at_utc, t)}</dd></div>
        <div><dt>{t("nativeCapacity.received_at")}</dt><dd>{unavailable(observation.received_at_utc, t)}</dd></div>
        <div><dt>{t("nativeCapacity.source_system")}</dt><dd>{observation.source_system}</dd></div>
        <div><dt>{t("nativeCapacity.source_reference")}</dt><dd><EvidenceValue t={t} value={observation.source_reference} /></dd></div>
        <div><dt>{t("nativeCapacity.source_record_id")}</dt><dd><EvidenceValue t={t} value={observation.source_record_id} /></dd></div>
        <div><dt>{t("nativeCapacity.normalizer_version")}</dt><dd><code>{observation.normalizer_version}</code></dd></div>
        <div><dt>{t("nativeCapacity.quantity_basis")}</dt><dd><code>{observation.quantity_basis}</code></dd></div>
        <div><dt>{t("nativeCapacity.archive_id")}</dt><dd><EvidenceValue t={t} value={observation.raw_archive_id} /></dd></div>
        <div><dt>{t("nativeCapacity.payload_sha256")}</dt><dd><EvidenceValue t={t} value={observation.payload_sha256} /></dd></div>
      </dl>
    </section>
  );
}

function NativeCapacityContextCard({
  context,
  t,
}: {
  context: NativeCapacityContext;
  t: NativeCapacityTranslate;
}) {
  const { flow, capacity, unit, indicativeRatioPct, reasonCode } = context;
  const indicated = indicativeRatioPct !== null;
  const pointName = flow.point_name.trim() || flow.point_id;

  return (
    <article
      className="capacity-inspector-section"
      aria-label={`${pointName} · ${flow.point_id}`}
      data-native-context="true"
      data-native-context-id={flow.observation_id}
      data-native-reason={reasonCode}
      data-native-ratio={indicated ? "indicated" : "not-indicated"}
      data-native-ratio-value={indicated ? String(indicativeRatioPct) : undefined}
    >
      <div className="capacity-point-heading">
        <div>
          <strong>{pointName}</strong>
          <span>{flow.point_id}</span>
        </div>
        <span>{flow.direction} · {unavailable(flow.operator_key, t)}</span>
      </div>

      <dl className="capacity-point-metrics">
        <div>
          <dt>{t("nativeCapacity.flow_rate")}</dt>
          <dd>
            <code>{context.flowRateText ?? t("nativeCapacity.not_available")}</code>
            {context.flowRateText && <span> {unit ?? t("nativeCapacity.unit_unavailable")}</span>}
          </dd>
        </div>
        <div>
          <dt>{t("nativeCapacity.capacity_rate")}</dt>
          <dd>
            <code>{context.capacityRateText ?? t("nativeCapacity.not_available")}</code>
            {context.capacityRateText && <span> {unit ?? t("nativeCapacity.unit_unavailable")}</span>}
          </dd>
        </div>
        <div>
          <dt>{t("nativeCapacity.ratio")}</dt>
          <dd>
            {indicated ? (
              <>
                <strong>{formatIndicativeRatio(indicativeRatioPct)}%</strong>
                <span> {t("nativeCapacity.ratio_approximate")}</span>
              </>
            ) : (
              <>
                <strong>{t("nativeCapacity.ratio_not_indicated")}</strong>
                <span> {t("nativeCapacity.reason")}: {t(reasonLabelKey(reasonCode))}</span>
                <code>{reasonCode}</code>
              </>
            )}
          </dd>
        </div>
      </dl>

      <details>
        <summary>{t("nativeCapacity.evidence_details")}</summary>
        <ObservationEvidence title={t("nativeCapacity.flow_evidence")} observation={flow} t={t} />
        {capacity ? (
          <ObservationEvidence title={t("nativeCapacity.capacity_evidence")} observation={capacity} t={t} />
        ) : (
          <p className="capacity-empty-state">{t("nativeCapacity.no_capacity_match")}</p>
        )}
      </details>
    </article>
  );
}

function nativeStringList(values: readonly string[] | undefined): readonly string[] {
  return values ?? [];
}

function MetaBlock({
  kind,
  label,
  meta,
  t,
}: {
  kind: "flow" | "capacity";
  label: string;
  meta: ApiMeta;
  t: NativeCapacityTranslate;
}) {
  const warnings = nativeStringList(meta.warnings);
  const sourceReferences = nativeStringList(meta.source_references);
  const missingInputs = nativeStringList(meta.missing_inputs);

  return (
    <section className="capacity-inspector-section" data-native-meta={kind}>
      <h4>{label}</h4>
      <dl className="capacity-point-metrics">
        <div><dt>{t("nativeCapacity.research_only")}</dt><dd>{t(meta.research_only ? "nativeCapacity.yes" : "nativeCapacity.no")}</dd></div>
        <div><dt>{t("nativeCapacity.human_review_required")}</dt><dd>{t(meta.human_review_required ? "nativeCapacity.yes" : "nativeCapacity.no")}</dd></div>
      </dl>
      <h5>{t("nativeCapacity.warnings")}</h5>
      {warnings.length > 0 ? (
        <ul>{warnings.map((warning, index) => <li key={`${warning}-${index}`}><code>{warning}</code></li>)}</ul>
      ) : (
        <p>{t("nativeCapacity.no_warnings")}</p>
      )}
      <h5>{t("nativeCapacity.source_references")}</h5>
      {sourceReferences.length > 0 ? (
        <ul>{sourceReferences.map((reference, index) => <li key={`${reference}-${index}`}><code>{reference}</code></li>)}</ul>
      ) : (
        <p>{t("nativeCapacity.no_source_references")}</p>
      )}
      <h5>{t("nativeCapacity.missing_inputs")}</h5>
      {missingInputs.length > 0 ? (
        <ul>{missingInputs.map((input, index) => <li key={`${input}-${index}`}><code>{input}</code></li>)}</ul>
      ) : (
        <p>{t("nativeCapacity.no_missing_inputs")}</p>
      )}
    </section>
  );
}

/** The model output and both response envelopes, rendered without re-deriving either. */
export function NativeCapacityContextResults({
  read,
  t,
  page = 0,
  onPageChange = NO_PAGE_CHANGE,
  pointId = null,
  acceptedWindow = null,
}: {
  read: NativeCapacityRead;
  t: NativeCapacityTranslate;
  page?: number;
  onPageChange?: (page: number) => void;
  pointId?: string | null;
  /**
   * The window the displayed read was accepted with. This is deliberately separate
   * from the editable form inputs so editing them never relabels an existing result.
   */
  acceptedWindow?: NativeCapacityWindow | null;
}) {
  const indicated = read.contexts.filter((context) => context.indicativeRatioPct !== null).length;
  const warningCount =
    nativeStringList(read.flowMeta.warnings).length +
    nativeStringList(read.capacityMeta.warnings).length;
  const previousReadRef = useRef(read);
  const pageForRender = previousReadRef.current === read ? page : 0;
  const pagination = nativeCapacityPageWindow(read.contexts.length, pageForRender);
  const visibleContexts = read.contexts.slice(
    pagination.page * NATIVE_CAPACITY_PAGE_SIZE,
    pagination.end,
  );

  useEffect(() => {
    const nextPage = nativeCapacityPageForRead(previousReadRef.current, read, page);
    previousReadRef.current = read;
    if (nextPage !== page) onPageChange(nextPage);
  }, [onPageChange, page, read]);

  return (
    <div data-native-results="true">
      {pointId && (
        <p className="capacity-readiness-note" data-native-resolved-point="true">
          {t("nativeCapacity.loaded_point")}: <code>{pointId}</code>
        </p>
      )}
      {acceptedWindow && (
        <p
          className="capacity-readiness-note"
          data-native-resolved-window="true"
          data-native-window-from={acceptedWindow.fromUtc}
          data-native-window-to={acceptedWindow.toUtc}
        >
          {t("nativeCapacity.loaded_window")}:{" "}
          <code>{acceptedWindow.fromUtc}</code> – <code>{acceptedWindow.toUtc}</code>
        </p>
      )}

      <div className="capacity-kpi-strip">
        <div><span>{t("nativeCapacity.summary_points")}</span><strong>{read.contexts.length}</strong></div>
        <div><span>{t("nativeCapacity.summary_indicated")}</span><strong>{indicated}</strong></div>
        <div><span>{t("nativeCapacity.summary_not_indicated")}</span><strong>{read.contexts.length - indicated}</strong></div>
        <div className={warningCount > 0 ? "warning" : ""}><span>{t("nativeCapacity.summary_warnings")}</span><strong>{warningCount}</strong></div>
      </div>

      {read.contexts.length > 0 && (
        <NativeCapacityPaginationControls
          pagination={pagination}
          onPageChange={onPageChange}
          t={t}
        />
      )}

      {visibleContexts.map((context, index) => (
        <NativeCapacityContextCard
          key={`${context.flow.observation_id}-${index}`}
          context={context}
          t={t}
        />
      ))}

      <section className="capacity-inspector-section">
        <h3>{t("nativeCapacity.meta_title")}</h3>
        <MetaBlock kind="flow" label={t("nativeCapacity.meta_flow")} meta={read.flowMeta} t={t} />
        <MetaBlock kind="capacity" label={t("nativeCapacity.meta_capacity")} meta={read.capacityMeta} t={t} />
      </section>

      <p className="capacity-readiness-note" data-native-disclaimer="true">
        {t("nativeCapacity.disclaimer")}
      </p>
    </div>
  );
}

export function NativeCapacityContextPanel({ t }: { t: NativeCapacityTranslate }) {
  const [pointId, setPointId] = useState("");
  const [fromUtcInput, setFromUtcInput] = useState("");
  const [toUtcInput, setToUtcInput] = useState("");
  const [validationKey, setValidationKey] = useState<string | null>(null);
  const [state, setState] = useState<QueryState>("idle");
  const [read, setRead] = useState<NativeCapacityRead | null>(null);
  const [resolvedPointId, setResolvedPointId] = useState<string | null>(null);
  const [acceptedWindow, setAcceptedWindow] = useState<NativeCapacityWindow | null>(null);
  const [page, setPage] = useState(0);
  const [error, setError] = useState<unknown>(null);
  const sessionRef = useRef<NativeCapacityQuerySession | null>(null);

  if (sessionRef.current === null) sessionRef.current = new NativeCapacityQuerySession();
  const session = sessionRef.current as NativeCapacityQuerySession;

  useEffect(() => () => session.dispose(), [session]);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const trimmed = pointId.trim();
    if (trimmed.length === 0) {
      setValidationKey("nativeCapacity.validation_point");
      return;
    }
    if (trimmed.length > POINT_ID_MAX_LENGTH) {
      setValidationKey("nativeCapacity.validation_length");
      return;
    }
    const windowInput = nativeCapacityWindowFromInputs(fromUtcInput, toUtcInput);
    if (windowInput.state === "invalid") {
      // Keep the previous read and its accepted label: nothing was queried.
      setValidationKey(windowInput.validationKey);
      return;
    }
    const window = windowInput.state === "window" ? windowInput.window : null;

    setValidationKey(null);
    setState("loading");
    setRead(null);
    setResolvedPointId(null);
    setAcceptedWindow(null);
    setPage(0);
    setError(null);

    const outcome = await session.run(trimmed, window);
    if (outcome.state === "superseded") return;
    if (outcome.state === "error") {
      setError(outcome.error);
      setState("error");
      return;
    }
    setResolvedPointId(outcome.pointId);
    setAcceptedWindow(outcome.window ?? null);
    setPage(0);
    setRead(outcome.read);
    setState("success");
  }

  return (
    <section
      className="workspace-panel capacity-native-context-panel"
      aria-labelledby="native-capacity-context-title"
      data-native-panel-state={state}
    >
      <div className="panel-title-row">
        <div>
          <h2 id="native-capacity-context-title">{t("nativeCapacity.title")}</h2>
          <p>{t("nativeCapacity.subtitle")}</p>
        </div>
      </div>

      <form className="capacity-command-bar" onSubmit={submit} data-native-query-form="true">
        <label htmlFor="native-capacity-point-id">{t("nativeCapacity.form_label")}</label>
        <input
          id="native-capacity-point-id"
          name="point_id"
          value={pointId}
          onChange={(event) => {
            setPointId(event.target.value);
            if (validationKey) setValidationKey(null);
          }}
          placeholder={t("nativeCapacity.point_placeholder")}
          aria-label={t("nativeCapacity.point_id")}
          aria-invalid={
            validationKey === "nativeCapacity.validation_point" ||
            validationKey === "nativeCapacity.validation_length"
          }
          aria-describedby="native-capacity-query-hint"
          autoComplete="off"
          spellCheck={false}
          data-native-point-id="true"
        />
        <label htmlFor="native-capacity-from-utc">{t("nativeCapacity.window_from")}</label>
        <input
          id="native-capacity-from-utc"
          name="from_utc"
          value={fromUtcInput}
          onChange={(event) => {
            setFromUtcInput(event.target.value);
            if (validationKey) setValidationKey(null);
          }}
          placeholder={t("nativeCapacity.window_from_placeholder")}
          aria-label={t("nativeCapacity.window_from")}
          aria-invalid={validationKey === "nativeCapacity.validation_window_pair"}
          aria-describedby="native-capacity-window-hint"
          autoComplete="off"
          spellCheck={false}
          data-native-window-from="true"
        />
        <label htmlFor="native-capacity-to-utc">{t("nativeCapacity.window_to")}</label>
        <input
          id="native-capacity-to-utc"
          name="to_utc"
          value={toUtcInput}
          onChange={(event) => {
            setToUtcInput(event.target.value);
            if (validationKey) setValidationKey(null);
          }}
          placeholder={t("nativeCapacity.window_to_placeholder")}
          aria-label={t("nativeCapacity.window_to")}
          aria-invalid={validationKey === "nativeCapacity.validation_window_pair"}
          aria-describedby="native-capacity-window-hint"
          autoComplete="off"
          spellCheck={false}
          data-native-window-to="true"
        />
        <button type="submit" aria-busy={state === "loading"}>
          {state === "loading" ? t("nativeCapacity.query_busy") : t("nativeCapacity.query")}
        </button>
      </form>
      <p id="native-capacity-query-hint" className="capacity-readiness-note">
        {t("nativeCapacity.query_hint")}
      </p>
      <p
        id="native-capacity-window-hint"
        className="capacity-readiness-note"
        data-native-window-hint="true"
      >
        {t("nativeCapacity.window_hint")}
      </p>

      {validationKey && (
        <div className="capacity-data-warning" role="alert" data-native-validation="true">
          {t(validationKey)}
        </div>
      )}

      {state === "idle" && (
        <div className="capacity-empty-state" role="status" data-native-state="idle">
          {t("nativeCapacity.idle")}
        </div>
      )}

      {state === "loading" && (
        <div className="capacity-empty-state" role="status" aria-live="polite" data-native-state="loading">
          {t("nativeCapacity.loading")}
        </div>
      )}

      {state === "error" && (
        <div className="capacity-data-warning" role="alert" data-native-state="error">
          <strong>{t("nativeCapacity.error")}</strong>
          <p>{t("nativeCapacity.error_code")}: <code>{failureCode(error)}</code></p>
          <p data-native-error-hint="true">{t("nativeCapacity.error_window_hint")}</p>
        </div>
      )}

      {state === "success" && read && read.contexts.length === 0 && (
        <div className="capacity-empty-state" role="status" data-native-state="empty">
          {t("nativeCapacity.empty")}
        </div>
      )}

      {state === "success" && read && (
        <NativeCapacityContextResults
          read={read}
          t={t}
          page={page}
          onPageChange={setPage}
          pointId={resolvedPointId}
          acceptedWindow={acceptedWindow}
        />
      )}
    </section>
  );
}

/**
 * Receipt-bound EEX TTF NGP reference-index evidence.
 *
 * This is a read-only view over the existing shared market projection. It adds
 * no transport, permission, calendar or arithmetic rule:
 *
 * - a row is included only when the backend's own source identity and the
 *   receipt-bound metadata version/basis identify it as EEX TTF NGP;
 * - the exact source string and unit are rendered verbatim. A missing or
 *   invalid exact claim is an explicit diagnostic, never the canonical float,
 *   `price_gbp_mwh`, zero or a client-side conversion;
 * - every delivery period is kept and sorted deterministically by period and
 *   observation id. The section deliberately does not collapse to a "latest"
 *   row;
 * - the receipt is `available_at_utc` / `source_receipt_at_utc`; a null
 *   `publication_time_utc` stays unknown and is never replaced with the
 *   receipt. The raw `publication_timestamp_raw` text stays labelled as
 *   unproven provider text;
 * - the source revision flag is Final/Temporary, not a readiness judgement.
 *
 * The section is evidence only: `executable_quote === false` is labelled
 * "Reference only", and no quote, right, activation or production claim is
 * created here.
 */

import { useMemo, useState } from "react";

import { formatUtcTimestamp } from "@/app/model/evidencePresentation";
import type { NormalizedMarketObsDTO } from "@/api/client";

type Translate = (key: string) => string;

/** The evidence list is bounded per page; every row remains reachable by paging. */
export const REFERENCE_INDEX_PAGE_SIZE = 50;

const EEX_SOURCE_SYSTEM = "EEX";
const EEX_NGP_SOURCE_REFERENCE = "eex-ttf-ngp-15-mins";
const EEX_NGP_RECEIPT_NORMALIZER_VERSION = "eex-ngp-receipt-v1";
const EEX_NGP_RECEIPT_AVAILABILITY_BASIS = "response_receipt";
const EEX_NGP_RECEIPT_PUBLICATION_BASIS = "unknown";

export interface ReferenceIndexEvidenceProps {
  markets: NormalizedMarketObsDTO[];
  /** The terminal's focused hub, matched against the backend-normalized `hub`. */
  focusedHub?: string | null;
  t: Translate;
}

interface ReferenceIndexPageState {
  dataKey: string;
  page: number;
}

const nonEmptyText = (value: unknown): string | null => (
  typeof value === "string" && value.trim() ? value : null
);

const sameToken = (value: unknown, expected: string): boolean => (
  typeof value === "string" && value.trim() === expected
);

const metadataText = (row: NormalizedMarketObsDTO, key: string): string | null =>
  nonEmptyText(row.metadata_json?.[key]);

/**
 * Whether the row is the receipt-bound EEX TTF NGP reference-index observation.
 *
 * The source identity is checked on the row and in its metadata, and the
 * receipt metadata version/basis must be the backend's declared values. A
 * legacy publication-bound EEX row, an EEX future/spot row, or a row whose
 * receipt basis cannot be identified is therefore not shown here.
 */
export function isReceiptBoundEexNgpObservation(row: NormalizedMarketObsDTO): boolean {
  const metadata = row.metadata_json ?? {};
  return (
    sameToken(row.source_system, EEX_SOURCE_SYSTEM) &&
    sameToken(row.source_reference, EEX_NGP_SOURCE_REFERENCE) &&
    sameToken(metadata.source_system, EEX_SOURCE_SYSTEM) &&
    sameToken(metadata.source_reference, EEX_NGP_SOURCE_REFERENCE) &&
    sameToken(metadata.normalizer_version, EEX_NGP_RECEIPT_NORMALIZER_VERSION) &&
    sameToken(metadata.availability_basis, EEX_NGP_RECEIPT_AVAILABILITY_BASIS) &&
    sameToken(metadata.publication_time_basis, EEX_NGP_RECEIPT_PUBLICATION_BASIS)
  );
}

/** Clamp a page to the pages the current row count actually has. */
export function clampReferenceIndexPage(page: number, totalRows: number): number {
  const pageCount = Math.max(1, Math.ceil(totalRows / REFERENCE_INDEX_PAGE_SIZE));
  const candidate = Number.isFinite(page) ? Math.trunc(page) : 1;
  return Math.min(Math.max(candidate, 1), pageCount);
}

/**
 * Derive the page state for the current data identity.
 *
 * A new data key (new rows or a changed hub scope) starts at page one without
 * an effect or a render-time state write. An unchanged key keeps the operator's
 * page, clamped if the row count shrank.
 */
export function reconcileReferenceIndexPage(
  previous: ReferenceIndexPageState,
  dataKey: string,
  totalRows: number,
): ReferenceIndexPageState {
  if (previous.dataKey !== dataKey) {
    return { dataKey, page: 1 };
  }
  return { dataKey, page: clampReferenceIndexPage(previous.page, totalRows) };
}

/** The rows of one clamped page; the callers keep the period/id ordering. */
export function referenceIndexPageRows<T>(rows: T[], page: number): T[] {
  const safePage = clampReferenceIndexPage(page, rows.length);
  return rows.slice(
    (safePage - 1) * REFERENCE_INDEX_PAGE_SIZE,
    safePage * REFERENCE_INDEX_PAGE_SIZE,
  );
}

const compareReferenceRows = (
  left: NormalizedMarketObsDTO,
  right: NormalizedMarketObsDTO,
): number => {
  const leftPeriod = nonEmptyText(left.period_start_utc) ?? "";
  const rightPeriod = nonEmptyText(right.period_start_utc) ?? "";
  if (leftPeriod < rightPeriod) return -1;
  if (leftPeriod > rightPeriod) return 1;
  const leftId = nonEmptyText(left.observation_id) ?? "";
  const rightId = nonEmptyText(right.observation_id) ?? "";
  if (leftId < rightId) return -1;
  if (leftId > rightId) return 1;
  return 0;
};

function ReferenceIndexCard({
  row,
  t,
}: {
  row: NormalizedMarketObsDTO;
  t: Translate;
}) {
  const metadata = row.metadata_json ?? {};
  const status = nonEmptyText(row.source_price_status);
  const exact = nonEmptyText(row.source_price_exact);
  const exactAvailable = status === "exact" && exact !== null;
  const unit = nonEmptyText(row.unit);
  const issue = nonEmptyText(row.source_price_issue);
  const issueDetail = nonEmptyText(row.source_price_issue_detail);
  const gbpExact = exactAvailable ? nonEmptyText(row.price_gbp_mwh_exact) : null;
  const gbpProvenance = nonEmptyText(row.price_gbp_mwh_provenance);

  const revision = nonEmptyText(metadata.revision_status)?.toLowerCase() ?? null;
  const revisionLabel = revision === "final"
    ? t("referenceIndex.revision_final")
    : revision === "temporary"
      ? t("referenceIndex.revision_temporary")
      : t("referenceIndex.revision_unavailable");

  const executable = row.executable_quote;
  const executableLabel = executable === false
    ? t("referenceIndex.executable_false")
    : executable === true
      ? t("referenceIndex.executable_true")
      : t("referenceIndex.executable_unknown");

  const availableAt = metadataText(row, "available_at_utc");
  const firstReceived = metadataText(row, "source_receipt_at_utc");
  const publicationTime = metadataText(row, "publication_time_utc");
  const rawSourceClock = metadataText(row, "publication_timestamp_raw");

  const periodStart = nonEmptyText(row.period_start_utc);
  const periodEnd = nonEmptyText(row.period_end_utc);
  const periodText = periodStart && periodEnd
    ? `${formatUtcTimestamp(periodStart, t("referenceIndex.not_available"))} → ${formatUtcTimestamp(periodEnd, t("referenceIndex.not_available"))}`
    : t("referenceIndex.period_unavailable");

  const details: Array<[string, string | null]> = [
    [t("referenceIndex.observation_id"), nonEmptyText(row.observation_id)],
    [t("referenceIndex.source_record_id"), nonEmptyText(row.source_record_id)],
    [
      t("referenceIndex.archive_id"),
      metadataText(row, "archive_id") ?? metadataText(row, "raw_archive_id"),
    ],
    [t("referenceIndex.payload_sha256"), metadataText(row, "payload_sha256")],
    [t("referenceIndex.ingestion_run_id"), metadataText(row, "ingestion_run_id")],
    [t("referenceIndex.adapter_version"), metadataText(row, "adapter_version")],
    [t("referenceIndex.normalizer_version"), metadataText(row, "normalizer_version")],
    [t("referenceIndex.availability_basis"), metadataText(row, "availability_basis")],
    [t("referenceIndex.publication_time_basis"), metadataText(row, "publication_time_basis")],
    [t("referenceIndex.source_receipt_at"), firstReceived],
    [t("referenceIndex.available_at"), availableAt],
    [t("referenceIndex.source_clock_raw"), rawSourceClock],
    [t("referenceIndex.revision_raw"), metadataText(row, "revision_status_raw")],
    [t("referenceIndex.source_price_raw"), nonEmptyText(row.source_price_raw)],
    [t("referenceIndex.source_price_provenance"), nonEmptyText(row.source_price_provenance)],
    [t("referenceIndex.price_float_provenance"), nonEmptyText(row.price_float_provenance)],
    [t("referenceIndex.price_semantics"), nonEmptyText(row.price_semantics)],
    [
      t("referenceIndex.source_price_volume_exact"),
      nonEmptyText(row.source_price_volume_mwh_exact),
    ],
    [t("referenceIndex.source_price_volume_raw"), nonEmptyText(row.source_price_volume_raw)],
    [
      t("referenceIndex.source_price_volume_status"),
      nonEmptyText(row.source_price_volume_status),
    ],
    [t("referenceIndex.source_dataset"), nonEmptyText(row.source_price_source_dataset)],
    [t("referenceIndex.source_system"), nonEmptyText(row.source_price_source_system)],
    [
      t("referenceIndex.source_reference"),
      nonEmptyText(row.source_price_source_reference),
    ],
    [t("referenceIndex.gbp_provenance"), gbpProvenance],
  ];

  return (
    <article
      className="reference-index-card"
      role="listitem"
      data-reference-index-row="true"
      data-observation-id={nonEmptyText(row.observation_id) ?? undefined}
    >
      <header className="reference-index-card-heading">
        <div>
          <strong>{nonEmptyText(row.product) ?? t("referenceIndex.not_available")}</strong>
          <span>
            {t("referenceIndex.hub")}: {nonEmptyText(row.hub) ?? t("referenceIndex.not_available")}
          </span>
        </div>
        <span
          className={`reference-index-revision ${revision === "final" || revision === "temporary" ? "" : "is-unavailable"}`}
          data-reference-index-revision={revision ?? "unavailable"}
        >
          {revisionLabel}
        </span>
      </header>

      <div className="reference-index-exact" data-reference-index-field="exact-price">
        <span>{t("referenceIndex.exact_price")}</span>
        {exactAvailable ? (
          <p>
            <strong>{exact}</strong>
            <span className="reference-index-unit">
              {unit ?? t("referenceIndex.unit_unavailable")}
            </span>
          </p>
        ) : (
          <div className="reference-index-unavailable">
            <strong>{t("referenceIndex.exact_unavailable")}</strong>
            {status && <code>{status}</code>}
            {issue && <code>{issue}</code>}
            {issueDetail && <p>{issueDetail}</p>}
            <p>{t("referenceIndex.exact_unavailable_detail")}</p>
          </div>
        )}
      </div>

      <div className="reference-index-defaults">
        <span
          className={`reference-index-executable ${executable === false ? "is-reference-only" : "is-unverified"}`}
          data-reference-index-field="executable-quote"
        >
          {executableLabel}
        </span>
        <p className="reference-index-gbp-exact">
          <span>{t("referenceIndex.gbp_exact")}</span>{" "}
          {gbpExact ?? t("referenceIndex.gbp_exact_unavailable")}
        </p>
      </div>

      <dl className="reference-index-facts">
        <div>
          <dt>{t("referenceIndex.delivery_period")}</dt>
          <dd>{periodText}</dd>
        </div>
        <div>
          <dt>{t("referenceIndex.first_received")}</dt>
          <dd data-reference-index-field="first-received">
            {firstReceived
              ? formatUtcTimestamp(firstReceived, t("referenceIndex.not_available"))
              : t("referenceIndex.unknown")}
          </dd>
        </div>
        <div>
          <dt>{t("referenceIndex.available_at")}</dt>
          <dd>
            {availableAt
              ? formatUtcTimestamp(availableAt, t("referenceIndex.not_available"))
              : t("referenceIndex.unknown")}
          </dd>
        </div>
        <div>
          <dt>{t("referenceIndex.publication_time")}</dt>
          <dd data-reference-index-field="publication-time">
            {publicationTime
              ? `${formatUtcTimestamp(publicationTime, t("referenceIndex.not_available"))} · ${t("referenceIndex.publication_present")}`
              : t("referenceIndex.publication_unknown")}
          </dd>
        </div>
        <div className="reference-index-fact-wide">
          <dt>{t("referenceIndex.source_clock_raw")}</dt>
          <dd data-reference-index-field="source-clock">
            {rawSourceClock
              ? <code>{rawSourceClock}</code>
              : t("referenceIndex.source_clock_unavailable")}
            <small>{t("referenceIndex.source_clock_raw_hint")}</small>
          </dd>
        </div>
      </dl>

      <details className="reference-index-details">
        <summary>{t("referenceIndex.evidence_details")}</summary>
        <dl className="reference-index-detail-grid">
          {details.map(([label, value]) => (
            <div key={label}>
              <dt>{label}</dt>
              <dd>
                {value
                  ? <code>{value}</code>
                  : <span className="reference-index-muted">{t("referenceIndex.not_available")}</span>}
              </dd>
            </div>
          ))}
        </dl>
      </details>
    </article>
  );
}

export function ReferenceIndexEvidence({
  markets,
  focusedHub,
  t,
}: ReferenceIndexEvidenceProps) {
  const normalizedHub = focusedHub?.trim().toUpperCase() || null;
  const rows = useMemo(() => {
    const scoped = markets.filter((row) => (
      isReceiptBoundEexNgpObservation(row) &&
      (
        normalizedHub === null ||
        (nonEmptyText(row.hub)?.trim().toUpperCase() ?? "") === normalizedHub
      )
    ));
    return scoped.slice().sort(compareReferenceRows);
  }, [markets, normalizedHub]);

  const dataKey = useMemo(() => (
    `${normalizedHub ?? "*"}\u0002${rows.map((row) => (
      `${nonEmptyText(row.observation_id) ?? ""}\u0000${nonEmptyText(row.period_start_utc) ?? ""}`
    )).join("\u0001")}`
  ), [normalizedHub, rows]);

  const [pageState, setPageState] = useState<ReferenceIndexPageState>({
    dataKey: "",
    page: 1,
  });
  const currentPage = reconcileReferenceIndexPage(
    pageState,
    dataKey,
    rows.length,
  );
  const pageCount = Math.max(1, Math.ceil(rows.length / REFERENCE_INDEX_PAGE_SIZE));
  const pageRows = referenceIndexPageRows(rows, currentPage.page);

  const goToPage = (next: number) => {
    setPageState({
      dataKey,
      page: clampReferenceIndexPage(next, rows.length),
    });
  };

  return (
    <section className="reference-index-evidence" aria-labelledby="reference-index-title">
      <div className="section-heading">
        <span className="eyebrow">{t("referenceIndex.eyebrow")}</span>
        <strong id="reference-index-title">{t("referenceIndex.title")}</strong>
      </div>
      <p className="panel-copy">{t("referenceIndex.subtitle")}</p>

      <div className="reference-index-meta">
        <span>
          {t("referenceIndex.total_rows")}:{" "}
          <strong data-reference-index-total={String(rows.length)}>{rows.length}</strong>
        </span>
        {normalizedHub && (
          <span>
            {t("referenceIndex.scope")}: <strong>{normalizedHub}</strong>
          </span>
        )}
      </div>

      {rows.length === 0 ? (
        <div className="reference-index-empty" data-reference-index-empty="true">
          <strong>{t("referenceIndex.empty_title")}</strong>
          <p>
            {normalizedHub
              ? `${t("referenceIndex.empty_scope")} (${normalizedHub}).`
              : t("referenceIndex.empty")}
          </p>
        </div>
      ) : (
        <>
          <div className="reference-index-list" role="list">
            {pageRows.map((row) => (
              <ReferenceIndexCard
                key={`${nonEmptyText(row.observation_id) ?? ""}-${nonEmptyText(row.period_start_utc) ?? ""}`}
                row={row}
                t={t}
              />
            ))}
          </div>

          <nav
            className="reference-index-pagination"
            aria-label={t("referenceIndex.pagination")}
          >
            <button
              type="button"
              disabled={currentPage.page <= 1}
              onClick={() => goToPage(currentPage.page - 1)}
            >
              {t("referenceIndex.previous")}
            </button>
            <span>
              {t("referenceIndex.page")} {currentPage.page} / {pageCount}
            </span>
            <button
              type="button"
              disabled={currentPage.page >= pageCount}
              onClick={() => goToPage(currentPage.page + 1)}
            >
              {t("referenceIndex.next")}
            </button>
            <span className="reference-index-total">
              {t("referenceIndex.total_rows")}: <strong>{rows.length}</strong>
            </span>
          </nav>
        </>
      )}
    </section>
  );
}

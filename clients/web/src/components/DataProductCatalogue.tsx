/**
 * Data Product catalogue panel (Architecture V2 Wave 4, client half).
 *
 * The platform declares a Data Product catalogue - what each product is, its time basis, the
 * source families behind it and, per caller, whether this identity may see its values - and
 * nothing in the client read it. This panel is that consumer, and it keeps the contract's own
 * honesty rules rather than smoothing them over:
 *
 * - a product the caller is not entitled to is **listed**, marked restricted, and shows no
 *   provenance block: never omitted, never printed as a measured zero;
 * - an entitled product with nothing measured says so instead of showing an empty table;
 * - a state this build has no label for is shown as its own code, so the operator reads the
 *   platform's vocabulary rather than a wrong word.
 *
 * It reads on demand like the activity timeline does: one governed read, and a failure is
 * reported rather than rendered as an empty catalogue.
 */

import { useCallback, useEffect, useState } from "react";

import { api } from "@/api/client";
import type { DataProductCatalogueDTO } from "@/api/client";
import { describeApiError } from "@/app/experience/errorPresentation";
import {
  dataProductAvailabilityKey,
  dataProductFreshnessKey,
  dataProductRows,
  dataProductSummary,
  dataProductTimeBasisKey,
  type DataProductRow,
} from "@/app/model/dataProductModel";
import { MetricStrip, PanelHeader, StatusBadge } from "@/components/ui";

type Translate = (key: string) => string;

interface DataProductCatalogueProps {
  t: Translate;
}

/** The provenance cell: three distinct states, none of them a fabricated zero. */
function provenanceCell(row: DataProductRow, t: Translate): string {
  if (row.provenanceState === "restricted") return t("data_product.provenance.restricted");
  if (row.provenanceState === "unmeasured") return t("data_product.provenance.unmeasured");
  const freshness = row.freshnessStatus
    ? t(dataProductFreshnessKey(row.freshnessStatus))
    : t("data_product.freshness.unknown");
  return `${row.rowCount ?? 0} · ${freshness} · ${row.confidence ?? t("data_product.freshness.unknown")}`;
}

export function DataProductCatalogue({ t }: DataProductCatalogueProps) {
  const [catalogue, setCatalogue] = useState<DataProductCatalogueDTO | null>(null);
  const [errorText, setErrorText] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const refresh = useCallback(async () => {
    setBusy(true);
    setErrorText(null);
    try {
      const response = await api.dataProducts();
      setCatalogue(response.data);
    } catch (error) {
      setErrorText(explain(error, t));
    } finally {
      setBusy(false);
    }
  }, [t]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const rows = dataProductRows(catalogue);
  const summary = dataProductSummary(catalogue);

  return (
    <section
      className="research-registry data-product-catalogue"
      id="research-task-panel"
      role="tabpanel"
      aria-label={t("research.tab.products")}
    >
      <PanelHeader title={t("data_product.title")} meta={t("data_product.subtitle")} />

      <MetricStrip
        className="metric-grid four-column"
        items={[
          { label: t("data_product.summary.total"), value: String(summary.total) },
          { label: t("data_product.summary.allowed"), value: String(summary.allowed) },
          { label: t("data_product.summary.restricted"), value: String(summary.restricted) },
          {
            label: t("data_product.summary.runtime"),
            value: summary.runtimeAvailable
              ? t("data_product.summary.runtime_measured")
              : t("data_product.summary.runtime_declared_only"),
          },
        ]}
      />

      {!summary.runtimeAvailable && catalogue && (
        // The catalogue is still the declared contract; only its provenance is missing.
        <p className="panel-copy">{t("data_product.runtime_unavailable")}</p>
      )}
      {errorText && (
        <div className="research-catalog-error" role="alert">
          {errorText}
        </div>
      )}

      <div className="research-table-wrap">
        <table className="research-semantic-table">
          <thead>
            <tr>
              <th scope="col">{t("data_product.column.product")}</th>
              <th scope="col">{t("data_product.column.availability")}</th>
              <th scope="col">{t("data_product.column.time_basis")}</th>
              <th scope="col">{t("data_product.column.sources")}</th>
              <th scope="col">{t("data_product.column.entitlement")}</th>
              <th scope="col">{t("data_product.column.provenance")}</th>
            </tr>
          </thead>
          <tbody>
            {catalogue === null && !errorText && (
              <tr>
                <td colSpan={6} className="research-state-row">
                  {busy ? t("status.loading") : t("data_product.empty")}
                </td>
              </tr>
            )}
            {rows.map((row) => (
              <tr key={row.productId}>
                <th scope="row">
                  <strong>{row.businessName}</strong>
                  <code>{row.productId}</code>
                  <small>{row.description}</small>
                </th>
                <td>
                  <StatusBadge variant="source" status={row.availabilityState}>
                    {t(dataProductAvailabilityKey(row.availabilityState))}
                  </StatusBadge>
                  {row.availabilityNote && <small>{row.availabilityNote}</small>}
                </td>
                <td>
                  {t(dataProductTimeBasisKey(row.timeBasis))}
                  {row.gasDayCalendar && <small>{row.gasDayCalendar}</small>}
                  {row.freshnessExpectationMinutes !== null && (
                    <small>
                      {t("data_product.expectation")}: {row.freshnessExpectationMinutes}
                    </small>
                  )}
                </td>
                <td>
                  {row.sourceFamilies.join(", ") || t("data_product.no_source_family")}
                  {row.simulatedFamilies.length > 0 && (
                    <small>
                      {t("data_product.simulated")}: {row.simulatedFamilies.join(", ")}
                    </small>
                  )}
                  {row.servedBy.length > 0 && <small>{row.servedBy.join(", ")}</small>}
                </td>
                <td>
                  {/* A restricted product says why, and never shows a count in its place. */}
                  {row.provenanceState === "restricted"
                    ? t("data_product.entitlement.restricted")
                    : t("data_product.entitlement.allowed")}
                  {row.provenanceState === "restricted" && (
                    <small>
                      {row.entitlementReason} · {t("data_product.withheld_families")}:{" "}
                      {row.restrictedFamilyCount}
                    </small>
                  )}
                </td>
                <td>{provenanceCell(row, t)}</td>
              </tr>
            ))}
            {catalogue !== null && rows.length === 0 && (
              <tr>
                <td colSpan={6} className="research-state-row">
                  {t("data_product.empty")}
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      {summary.generatedAtUtc && (
        <p className="panel-copy">
          {t("data_product.generated_at")}: {summary.generatedAtUtc}
        </p>
      )}
    </section>
  );
}

function explain(error: unknown, t: Translate): string {
  const detail =
    error && typeof error === "object" && "detail" in error
      ? (error as { detail?: unknown }).detail
      : undefined;
  const body =
    detail && typeof detail === "object" ? (detail as Record<string, unknown>) : undefined;
  const presentation = describeApiError(body ?? { error: "service_unavailable" });
  return `${t(presentation.titleKey)}. ${t(presentation.actionKey)}`;
}

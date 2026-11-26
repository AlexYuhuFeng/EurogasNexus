import { useEffect, useMemo, useState } from "react";

import { api } from "@/api/client";
import { DataGrid, PanelHeader, Skeleton, StatusBadge, type DataGridColumn } from "@/components/ui";
import { describeFailure, presentError } from "@/app/experience/errorPresentation";
import {
  capacityContractRows,
  coveredPointCount,
  firmnessOptions,
  type CapacityContractRow,
} from "@/app/model/capacityContractModel";
import { readState, type ReadState } from "@/app/model/readPosture";
import { PanelHelp } from "@/components/ui/PanelHelp";

type Translate = (key: string) => string;

interface CapacityContractBookProps {
  t: Translate;
}

const UNREAD: ReadState = { posture: "not-read", missingInputs: [], source: null };

/**
 * The capacity profile book (slice D of the D3 decision).
 *
 * `GET /api/contracts/capacity` publishes the capacity profiles the runtime stores: one row per
 * point with its capacity, the unit that row declares, the window it is valid for, its firmness
 * and its source reference. No surface read it, so the operating board could show what flowed and
 * what is technically available while the capacity the operator actually booked stayed invisible.
 *
 * The panel states the read's own result:
 *
 * - an unconfigured runtime database is named as such (the route marks it
 *   `runtime-db-not-configured`), never rendered as a book with no contracts;
 * - a book that was measured and holds nothing says so, because that is a fact about the
 *   deployment;
 * - the capacity is rendered with the unit the row declares rather than with one inferred from the
 *   payload's field name, and the rows are not summed: they are separate windows over the same
 *   points, so a total would be a number nobody stated.
 */
export function CapacityContractBook({ t }: CapacityContractBookProps) {
  const [rows, setRows] = useState<CapacityContractRow[]>([]);
  const [read, setRead] = useState<ReadState>(UNREAD);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<unknown>(null);
  const failure = error ? presentError(t, describeFailure(error)) : null;

  useEffect(() => {
    let active = true;
    void api
      .capacityContracts()
      .then((response) => {
        if (!active) return;
        setRows(capacityContractRows(response.data));
        setRead(readState(response.meta));
        setLoading(false);
      })
      .catch((reason) => {
        if (!active) return;
        setError(reason);
        setLoading(false);
      });
    return () => {
      active = false;
    };
  }, []);

  const firmness = firmnessOptions(rows);
  const columns = useMemo<DataGridColumn<CapacityContractRow>[]>(() => [
    { id: "point", header: t("capacity.contracts.point"), rowHeader: true, sortable: true, value: (row) => row.pointName },
    {
      id: "capacity",
      header: t("capacity.contracts.capacity"),
      type: "number",
      sortable: true,
      value: (row) => row.capacity,
      // Each profile declares its own unit, so the unit is per row and the rows are not summed.
      render: (row) => <>{row.capacity.toLocaleString("en-GB")} <small className="ds-grid-unit">{row.unit}</small></>,
    },
    { id: "from", header: t("capacity.contracts.window_from"), type: "date", sortable: true, value: (row) => row.validFrom },
    { id: "to", header: t("capacity.contracts.window_to"), type: "date", sortable: true, value: (row) => row.validTo },
    { id: "firmness", header: t("capacity.contracts.firmness"), sortable: true, value: (row) => row.firmness, render: (row) => <StatusBadge tone="neutral">{row.firmness}</StatusBadge> },
  ], [t]);

  return (
    <section className="workspace-panel capacity-contract-book" aria-label={t("capacity.contracts.title")}>
      <PanelHeader
        title={t("capacity.contracts.title")}
        meta={read.source ?? t("status.unknown")}
      />
      {/* The explanation of how to read the rows is shown only when there are rows (#69). */}
      {rows.length > 0 && <PanelHelp text={t("capacity.contracts.note")} label={t("panel.how_to_read")} />}
      {/* This panel's own read, named as such (skeleton rows where the table will be, below): the
          workspace is not loading because one panel is. */}
      {failure && (
        <div className="alert">
          <strong>{failure.title}</strong>
          <p>{failure.action}</p>
        </div>
      )}

      {read.posture === "runtime-db-not-configured" ? (
        <div className="capacity-contracts-unavailable">
          <strong>{t("capacity.contracts.not_configured")}</strong>
          <p>
            {t("capacity.contracts.missing_inputs")}:{" "}
            {read.missingInputs.join(", ") || t("data.unavailable")}
          </p>
        </div>
      ) : loading ? (
        <Skeleton label={t("capacity.contracts.loading")} rows={5} />
      ) : rows.length === 0 ? (
        <p className="muted">{t("capacity.contracts.none")}</p>
      ) : (
        <>
          <div className="capacity-contract-summary">
            <span>
              {rows.length} {t("capacity.contracts.profiles")}
            </span>
            <span>
              {coveredPointCount(rows)} {t("capacity.contracts.points")}
            </span>
            <span className="muted">
              {t("capacity.contracts.firmness")}: {firmness.join(", ") || t("data.unavailable")}
            </span>
          </div>
          <DataGrid
            id="capacity-contracts"
            label={t("capacity.contracts.title")}
            columns={columns}
            rows={rows}
            rowKey={(row) => row.contractId}
            density="compact"
            maxHeight="min(60vh, 560px)"
            defaultSort={{ columnId: "point", direction: "ascending" }}
          />
          <p className="muted">{t("capacity.contracts.window_note")}</p>
        </>
      )}
    </section>
  );
}

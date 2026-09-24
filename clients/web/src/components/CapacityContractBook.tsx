import { useEffect, useState } from "react";

import { api } from "@/api/client";
import { PanelHeader } from "@/components/ui";
import { describeFailure, presentError } from "@/app/experience/errorPresentation";
import {
  capacityContractRows,
  coveredPointCount,
  firmnessOptions,
  type CapacityContractRow,
} from "@/app/model/capacityContractModel";
import { readState, type ReadState } from "@/app/model/readPosture";

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

  return (
    <section className="workspace-panel capacity-contract-book" aria-label={t("capacity.contracts.title")}>
      <PanelHeader
        title={t("capacity.contracts.title")}
        meta={read.source ?? t("status.unknown")}
      />
      <p className="panel-copy">{t("capacity.contracts.note")}</p>
      {/* This panel's own read, named as such: the workspace is not loading because one panel is. */}
      {loading && <p className="muted">{t("capacity.contracts.loading")}</p>}
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
          <div className="research-table data-table" tabIndex={0}>
            <div className="data-table-row header five">
              <span>{t("capacity.contracts.point")}</span>
              <span>{t("capacity.contracts.capacity")}</span>
              <span>{t("capacity.contracts.window_from")}</span>
              <span>{t("capacity.contracts.window_to")}</span>
              <span>{t("capacity.contracts.firmness")}</span>
            </div>
            {rows.map((row) => (
              <div key={row.contractId} className="data-table-row five">
                <strong>{row.pointName}</strong>
                <span>
                  {row.capacity.toLocaleString()} {row.unit}
                </span>
                <span>{row.validFrom}</span>
                <span>{row.validTo}</span>
                <span className="status-badge">{row.firmness}</span>
              </div>
            ))}
          </div>
          <p className="muted">{t("capacity.contracts.window_note")}</p>
        </>
      )}
    </section>
  );
}

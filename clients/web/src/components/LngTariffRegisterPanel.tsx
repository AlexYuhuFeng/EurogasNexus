/**
 * The public LNG terminal tariff register on Admin → Connectors → Access (CP-11, design C.5).
 *
 * Two things an administrator or operator does here:
 * - Operator reuse terms: the operators' sites restrict reuse of their tariff documents, so the
 *   product reads none until the firm records the operator's written permission. Each operator
 *   shows "Needs the firm's terms" or "Permitted" with the reference; only an administrator
 *   records it (the server checks; the button only mirrors the role).
 * - Published figures: each figure read from an operator document is a candidate until a second
 *   person marks it reviewed (four eyes, enforced by the server). Candidates price a cargo only
 *   as indicative.
 */

import { useCallback, useEffect, useMemo, useState } from "react";

import {
  api,
  ApiError,
  type LngTariffOperatorDTO,
  type LngTerminalTariffDTO,
  type LngTerminalTariffRegisterDTO,
} from "@/api/client";
import { Button, DataGrid, PanelHeader, StatusBadge, type DataGridColumn } from "@/components/ui";
import { useApiStore } from "@/stores/api";
import "./lng-tariff-register.css";

type Translate = (key: string, options?: Record<string, unknown>) => string;

const AMOUNT = new Intl.NumberFormat("en-GB", { maximumFractionDigits: 4 });
/** Money per cargo reads to the cent, as the operator's document states it. */
const MONEY = new Intl.NumberFormat("en-GB", { minimumFractionDigits: 2, maximumFractionDigits: 2 });

function labelOr(t: Translate, key: string, raw: string, options?: Record<string, unknown>): string {
  const label = t(key, options);
  return label === key ? raw : label;
}

/** The figure in the operator's own unit: price first, the basis after it. */
export function tariffCharge(row: LngTerminalTariffDTO, t: Translate): string {
  const unit = labelOr(t, `lng_tariff.basis.${row.charge_basis}`, row.charge_basis, {
    currency: row.currency,
  });
  if (row.charge_basis === "per_cargo_class" && row.by_cargo_class) {
    const classes = Object.entries(row.by_cargo_class)
      .map(([name, total]) => `${name} ${MONEY.format(total)}`)
      .join(" · ");
    return `${classes} ${unit}`;
  }
  if (row.amount === null) return "—";
  const figure = row.charge_basis === "per_cargo" ? MONEY : AMOUNT;
  return `${figure.format(row.amount)} ${unit}`;
}

export function LngTariffRegisterPanel({ t }: { t: Translate }) {
  const currentUser = useApiStore((state) => state.currentUser);
  const roles = currentUser?.roles ?? (currentUser?.role ? [currentUser.role] : []);
  const isAdmin = roles.includes("ADMIN");
  const canReview = isAdmin || roles.includes("OPERATOR");
  const [view, setView] = useState<LngTerminalTariffRegisterDTO | null>(null);
  const [failed, setFailed] = useState(false);
  const [editing, setEditing] = useState<{ operator: string; permitted: boolean } | null>(null);
  const [reference, setReference] = useState("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const response = await api.lngTerminalTariffRegister();
      setView(response.data);
      setFailed(false);
    } catch {
      setFailed(true);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const review = useCallback(
    async (row: LngTerminalTariffDTO) => {
      setBusy(true);
      setMessage(null);
      try {
        await api.reviewLngTerminalTariff(row.tariff_id);
        await load();
      } catch (error) {
        const detail = error instanceof ApiError ? (error.detail as { code?: string } | null) : null;
        const code = detail?.code;
        setMessage(t(code === "four_eyes" ? "lng_tariff.four_eyes" : "lng_tariff.review_failed"));
      } finally {
        setBusy(false);
      }
    },
    [load, t],
  );

  const saveTerms = async () => {
    if (!editing) return;
    if (editing.permitted && !reference.trim()) return;
    setBusy(true);
    setMessage(null);
    try {
      await api.recordLngTariffOperatorTerms(editing.operator, {
        permitted: editing.permitted,
        reference: reference.trim(),
      });
      setEditing(null);
      await load();
    } catch {
      setMessage(t("lng_tariff.save_failed"));
    } finally {
      setBusy(false);
    }
  };

  const columns = useMemo<DataGridColumn<LngTerminalTariffDTO>[]>(
    () => [
      {
        id: "terminal",
        header: t("lng_tariff.col.terminal"),
        value: (row) => row.terminal_name,
        rowHeader: true,
        priority: "primary",
      },
      {
        id: "charge",
        header: t("lng_tariff.col.charge"),
        value: (row) => row.amount,
        render: (row) => tariffCharge(row, t),
        align: "end",
        priority: "primary",
      },
      {
        id: "product",
        header: t("lng_tariff.col.product"),
        value: (row) => row.product,
        render: (row) => labelOr(t, `lng_tariff.product.${row.product}`, row.product),
      },
      {
        id: "valid",
        header: t("lng_tariff.col.valid"),
        type: "date",
        value: (row) => row.valid_from,
        render: (row) => row.period_label ?? row.valid_from ?? "—",
      },
      {
        id: "status",
        header: t("lng_tariff.col.status"),
        value: (row) => row.review_status,
        priority: "primary",
        render: (row) =>
          row.review_status === "REVIEWED" ? (
            <StatusBadge tone="ok" title={row.reviewed_by ? t("lng_tariff.reviewed_by", { name: row.reviewed_by }) : undefined}>
              {t("lng_tariff.status.REVIEWED")}
            </StatusBadge>
          ) : canReview ? (
            <Button size="sm" variant="secondary" disabled={busy} onClick={() => void review(row)}>
              {t("lng_tariff.review")}
            </Button>
          ) : (
            <StatusBadge tone="watch">{t("lng_tariff.status.CANDIDATE")}</StatusBadge>
          ),
      },
      {
        id: "source",
        header: t("lng_tariff.col.source"),
        value: (row) => row.document_title,
        render: (row) =>
          row.source_url ? (
            <a href={row.source_url} target="_blank" rel="noreferrer">
              {row.document_title ?? row.source_url}
            </a>
          ) : (
            row.document_title ?? "—"
          ),
      },
    ],
    [busy, canReview, review, t],
  );

  if (failed && !view) {
    return (
      <section className="workspace-panel span-3 lng-tariff-register" data-record="lng-tariff-register">
        <PanelHeader title={t("lng_tariff.title")} />
        <p className="muted">{t("lng_tariff.read_failed")}</p>
      </section>
    );
  }

  const counts = view?.counts ?? { reviewed: 0, candidate: 0, terminals: 0 };
  return (
    <section
      className="workspace-panel span-3 lng-tariff-register"
      aria-labelledby="lng-tariff-register-title"
      data-record="lng-tariff-register"
    >
      <PanelHeader
        headingId="lng-tariff-register-title"
        title={t("lng_tariff.title")}
        meta={t("lng_tariff.meta", counts)}
      />
      <h3 className="lng-tariff-subhead">{t("lng_tariff.operators")}</h3>
      <ul className="lng-tariff-operators">
        {(view?.operators ?? []).map((operator: LngTariffOperatorDTO) => (
          <li key={operator.operator} data-record-id={operator.operator} data-terms-state={operator.permission_state}>
            <strong>{operator.display_name}</strong>
            <StatusBadge tone={operator.permission_state === "permitted" ? "ok" : "watch"}>
              {t(`lng_tariff.state.${operator.permission_state}`)}
            </StatusBadge>
            <span className="muted">
              {operator.permission_state === "permitted"
                ? t("lng_tariff.permitted_by", {
                    reference: operator.reference ?? "",
                    when: (operator.recorded_at_utc ?? "").slice(0, 10),
                  })
                : operator.finding}
            </span>
            <a href={operator.legal_url} target="_blank" rel="noreferrer">
              {t("lng_tariff.legal")}
            </a>
            <span className="muted">{t("lng_tariff.checked", { date: operator.checked_on })}</span>
            {isAdmin ? (
              <Button
                size="sm"
                variant={operator.permission_state === "permitted" ? "quiet" : "secondary"}
                onClick={() => {
                  setEditing({ operator: operator.operator, permitted: operator.permission_state !== "permitted" });
                  setReference("");
                  setMessage(null);
                }}
              >
                {t(operator.permission_state === "permitted" ? "lng_tariff.withdraw" : "lng_tariff.record")}
              </Button>
            ) : (
              operator.permission_state !== "permitted" && <span className="muted">{t("lng_tariff.ask_admin")}</span>
            )}
          </li>
        ))}
      </ul>
      {editing && (
        <form
          className="lng-tariff-terms-form"
          onSubmit={(event) => {
            event.preventDefault();
            void saveTerms();
          }}
        >
          <label htmlFor="lng-tariff-reference">
            {t(editing.permitted ? "lng_tariff.reference" : "lng_tariff.withdraw_reason")}
          </label>
          <input
            id="lng-tariff-reference"
            value={reference}
            maxLength={256}
            required={editing.permitted}
            onChange={(event) => setReference(event.target.value)}
          />
          <div className="lng-tariff-actions">
            <Button type="submit" disabled={busy || (editing.permitted && !reference.trim())}>
              {t("lng_tariff.save")}
            </Button>
            <Button variant="quiet" onClick={() => setEditing(null)} disabled={busy}>
              {t("lng_tariff.cancel")}
            </Button>
          </div>
        </form>
      )}
      <h3 className="lng-tariff-subhead">{t("lng_tariff.rows")}</h3>
      <DataGrid
        id="lng-tariff-rows"
        label={t("lng_tariff.rows")}
        density="compact"
        columns={columns}
        rows={view?.tariffs ?? []}
        rowKey={(row) => row.tariff_id}
        rowAttributes={(row) => ({ "data-record": "lng-tariff", "data-review-status": row.review_status })}
        loading={!view}
        loadingLabel={t("lng_tariff.loading")}
        empty={<span data-empty-state="lng-tariff-rows">{t("lng_tariff.empty")}</span>}
      />
      {message && (
        <p className="lng-tariff-message" role="status">
          {message}
        </p>
      )}
    </section>
  );
}

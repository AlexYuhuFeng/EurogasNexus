/**
 * Admin → Data sources → Watched publications (Package G): every public publication the desk
 * relies on, with its terms verdict, when it was last fetched and changed, and its state:
 * current, changed (needs a person to confirm), unreachable, fetched under the publisher's
 * written consent (with the consent line), consented but not yet implemented, consent
 * withdrawn, hand-maintained (the terms forbid storing it; the desk keeps a file and checks it
 * by a date) or not permitted (link only). So the desk can see what is automatic and what is not
 * yet. An administrator confirms a changed document the product could not read (the dates held
 * stay, the alarm clears), and withdraws or restores a publisher's consent (audited; a
 * withdrawal stops fetching at once and leaves the data held, marked).
 */
import { useCallback, useEffect, useMemo, useState } from "react";

import { api, type PublisherConsentDTO, type WatchedPublicationDTO } from "@/api/client";
import { Button, DataGrid, EmptyState, Instant, StatusBadge, type DataGridColumn } from "@/components/ui";

type Translate = (key: string, options?: Record<string, unknown>) => string;

const TONE: Record<WatchedPublicationDTO["state"], "ok" | "watch" | "breach" | "neutral" | "info"> = {
  current: "ok",
  needs_confirmation: "watch",
  unreachable: "breach",
  never_fetched: "info",
  hand_maintained: "neutral",
  link_only: "neutral",
  consent_withdrawn: "watch",
  not_implemented: "neutral",
  site_refuses: "watch",
};

/** Order: what needs a person first, then what is automatic, then what is not. */
export function watchOrder(rows: readonly WatchedPublicationDTO[]): WatchedPublicationDTO[] {
  const rank: Record<string, number> = { needs_confirmation: 0, unreachable: 1, site_refuses: 2, consent_withdrawn: 3, current: 4, never_fetched: 5, not_implemented: 6, hand_maintained: 7, link_only: 8 };
  return [...rows].sort((a, b) => (rank[a.state] ?? 9) - (rank[b.state] ?? 9) || a.title.localeCompare(b.title));
}

export function WatchedPublicationsPanel({ t, canConfirm }: { t: Translate; canConfirm: boolean }) {
  const [rows, setRows] = useState<WatchedPublicationDTO[] | null>(null);
  const [failed, setFailed] = useState(false);
  const [busy, setBusy] = useState<string | null>(null);
  const [consents, setConsents] = useState<PublisherConsentDTO[] | null>(null);

  const load = useCallback(() => {
    api
      .watchedPublications()
      .then((response) => setRows(response.data.rows))
      .catch(() => setFailed(true));
    api
      .publisherConsents()
      .then((response) => setConsents(response.data.rows))
      .catch(() => setConsents([]));
  }, []);

  const changeConsent = useCallback(
    (row: PublisherConsentDTO) => {
      const withdraw = row.state === "in_force";
      if (withdraw && typeof window !== "undefined" && !window.confirm(t("watch.consents.confirm_withdraw", { publisher: row.name }))) return;
      setBusy(`consent:${row.publisher_id}`);
      (withdraw ? api.withdrawPublisherConsent(row.publisher_id) : api.restorePublisherConsent(row.publisher_id))
        .then(load)
        .catch(() => setFailed(true))
        .finally(() => setBusy(null));
    },
    [load, t],
  );
  useEffect(load, [load]);

  const confirm = useCallback(
    (row: WatchedPublicationDTO) => {
      setBusy(row.publication_id);
      api
        .confirmWatchedPublication(row.publication_id)
        .then(load)
        .catch(() => setFailed(true))
        .finally(() => setBusy(null));
    },
    [load],
  );

  const columns = useMemo<DataGridColumn<WatchedPublicationDTO>[]>(
    () => [
      {
        id: "title",
        header: t("watch.col.publication"),
        rowHeader: true,
        value: (row) => row.title,
        render: (row) => (
          <span>
            <a href={row.url} target="_blank" rel="noreferrer noopener">{row.title}</a>
            <span className="tariff-book-muted"> · {row.publisher}</span>
          </span>
        ),
      },
      {
        id: "state",
        header: t("watch.col.state"),
        value: (row) => row.state,
        render: (row) => (
          <span>
            <StatusBadge tone={TONE[row.state]} title={row.detail || row.fetch_refusal || undefined}>{t(`watch.state.${row.state}`)}</StatusBadge>
            {row.hand_file?.overdue ? <> <StatusBadge tone="watch">{t("watch.check_overdue")}</StatusBadge></> : null}
            {!row.verified_live ? <> <StatusBadge tone="neutral" title={t("watch.not_verified_hint")}>{t("watch.not_verified")}</StatusBadge></> : null}
            {row.next_check_at_utc && row.state === "unreachable" ? <span className="tariff-book-muted"> · {t("watch.next_try", { time: row.next_check_at_utc.slice(0, 16).replace("T", " ") })}</span> : null}
          </span>
        ),
        cellTitle: (row) => [row.detail, row.site_refusal, row.history, row.record_summary?.first_day ? t("watch.history", { first: row.record_summary.first_day, last: row.record_summary.last_day ?? "" }) : ""].filter(Boolean).join(" · ") || undefined,
      },
      {
        id: "consent",
        header: t("watch.col.consent"),
        value: (row) => row.consent_line ?? "",
        render: (row) => (row.consent_line ? <span data-consent-line="">{row.consent_line}</span> : <span className="tariff-book-muted">–</span>),
      },
      {
        id: "fetched",
        header: t("watch.col.fetched"),
        value: (row) => row.last_fetched_at_utc ?? "",
        render: (row) =>
          row.last_fetched_at_utc ? <Instant value={row.last_fetched_at_utc} date="auto" /> : row.hand_file?.check_by ? <span>{t("watch.check_by", { day: row.hand_file.check_by })}</span> : <span className="tariff-book-muted">–</span>,
      },
      {
        id: "changed",
        header: t("watch.col.changed"),
        value: (row) => row.last_changed_at_utc ?? "",
        render: (row) => (row.last_changed_at_utc ? <Instant value={row.last_changed_at_utc} date="auto" /> : <span className="tariff-book-muted">–</span>),
      },
      {
        id: "terms",
        header: t("watch.col.terms"),
        value: (row) => row.verdict,
        render: (row) => (
          <a href={row.terms_url} target="_blank" rel="noreferrer noopener">{t(`watch.verdict.${row.verdict}`)}</a>
        ),
        cellTitle: (row) => `${row.terms_quote} (${t("watch.checked_on", { day: row.terms_checked_on })})`,
      },
      {
        id: "action",
        header: t("watch.col.action"),
        render: (row) =>
          row.state === "needs_confirmation" && canConfirm ? (
            <span>
              {row.pending_url ? <a href={row.pending_url} target="_blank" rel="noreferrer noopener">{t("watch.open_document")}</a> : null}{" "}
              <Button size="sm" onClick={() => confirm(row)} disabled={busy === row.publication_id}>{t("watch.confirm")}</Button>
            </span>
          ) : null,
      },
    ],
    [t, canConfirm, busy, confirm],
  );

  const consentColumns = useMemo<DataGridColumn<PublisherConsentDTO>[]>(
    () => [
      { id: "publisher", header: t("watch.consents.col.publisher"), rowHeader: true, value: (row) => row.name, cellTitle: (row) => `${row.scope} · ${row.basis} · ${row.supersedes}` },
      {
        id: "state",
        header: t("watch.consents.col.state"),
        value: (row) => row.state,
        render: (row) => (
          <StatusBadge tone={row.state === "in_force" ? "ok" : "watch"} title={row.line}>
            {row.state === "in_force" ? t("watch.consents.in_force") : t("watch.consents.withdrawn", { day: (row.withdrawn_at_utc ?? "").slice(0, 10) })}
          </StatusBadge>
        ),
      },
      {
        id: "action",
        header: t("watch.consents.col.action"),
        render: (row) =>
          canConfirm ? (
            <Button size="sm" onClick={() => changeConsent(row)} disabled={busy === `consent:${row.publisher_id}`} data-consent-action={row.publisher_id}>
              {row.state === "in_force" ? t("watch.consents.withdraw") : t("watch.consents.restore")}
            </Button>
          ) : null,
      },
    ],
    [t, canConfirm, busy, changeConsent],
  );

  if (failed && !rows) return <EmptyState compact reason={t("watch.failed")} />;
  return (
    <div data-watched-publications="">
      <p className="tariff-book-muted">{t("watch.intro")}</p>
      <DataGrid
        id="watched-publications"
        label={t("watch.title")}
        columns={columns}
        rows={watchOrder(rows ?? [])}
        rowKey={(row) => row.publication_id}
        density="compact"
        phoneLayout="scroll"
        empty={rows ? t("watch.empty") : t("board.loading")}
        rowAttributes={(row) => ({ "data-state": row.state })}
      />
      <h3>{t("watch.consents.title")}</h3>
      <p className="tariff-book-muted">{t("watch.consents.intro")}</p>
      <DataGrid
        id="publisher-consents"
        label={t("watch.consents.title")}
        columns={consentColumns}
        rows={consents ?? []}
        rowKey={(row) => row.publisher_id}
        density="compact"
        phoneLayout="scroll"
        empty={consents ? t("watch.empty") : t("board.loading")}
        rowAttributes={(row) => ({ "data-consent-state": row.state })}
      />
    </div>
  );
}

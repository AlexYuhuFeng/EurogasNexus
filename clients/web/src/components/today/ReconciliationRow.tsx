/**
 * Today, the scheduler's reconciliation (SCHED-1): per hub (point) and counterparty, what was
 * traded, confirmed, nominated and matched by the TSO for the gas day, and each break in plain
 * words with its arithmetic and the next step, soonest cut-off first. Decision support only
 * (AGENTS.md rule 8): nothing here nominates, confirms or sends.
 * Its own read (`GET /api/desk/gas-day/{gas_day}/reconciliation`), today and tomorrow.
 */
import { useEffect, useState } from "react";

import {
  api,
  type GasDayReconciliationDTO,
  type GasDayReconciliationFilters,
  type ReconciliationBreakDTO,
  type ReconciliationBreakKind,
  type ReconciliationGroupDTO,
} from "@/api/client";
import {
  breakTone,
  breaksOf,
  breakWords,
  cashOutText,
  countdownUrgency,
  groupKey,
  hubOptions,
  kindOptions,
  minutesUntil,
  signedQuantity,
} from "@/app/model/reconciliationModel";
import { formatGasDay } from "@/app/time/timeFormat";
import { useInstantFormatter } from "@/app/time/useInstant";
import { Button, EmptyState, Field, Segmented, Select, Skeleton, StatusBadge, Toolbar } from "@/components/ui";

type Translate = (key: string, options?: Record<string, unknown>) => string;

export interface ReconciliationRowProps {
  /** Today's gas day (`YYYY-MM-DD`); tomorrow is the day after. */
  gasDay: string;
  t: Translate;
  language: string;
  nowMs: number;
}

const ALL = "all";

function nextDay(day: string): string {
  const at = new Date(`${day}T12:00:00Z`);
  at.setUTCDate(at.getUTCDate() + 1);
  return at.toISOString().slice(0, 10);
}

function Countdown({ atUtc, urgency, t, nowMs }: { atUtc: string | null | undefined; urgency: ReconciliationBreakDTO["urgency"]; t: Translate; nowMs: number }) {
  const formatInstant = useInstantFormatter();
  if (urgency === "closed") return <span className="recon-countdown muted">{t("recon.closed")}</span>;
  if (urgency === "passed" || !atUtc) return <span className="recon-countdown" data-urgency="imminent">{t("recon.passed")}</span>;
  const left = minutesUntil(atUtc, nowMs) ?? 0;
  const at = formatInstant(atUtc, { nowMs });
  return (
    <time className="recon-countdown" dateTime={atUtc} title={at?.title} data-urgency={countdownUrgency(urgency, left)}>
      {t("recon.left", { hours: Math.floor(left / 60), minutes: left % 60, time: at?.text ?? "" })}
    </time>
  );
}

function BreakDetail({ item, t, language, nowMs }: { item: ReconciliationBreakDTO; t: Translate; language: string; nowMs: number }) {
  const words = breakWords(item, language);
  const cash = cashOutText(item);
  return (
    <li className="recon-break" data-break-kind={item.kind}>
      <div className="recon-break-head">
        <StatusBadge tone={breakTone(item)}>{t(`recon.kind.${item.kind}`)}</StatusBadge>
        {item.gap_mwh !== null && (
          <span className="recon-figure">
            {t("recon.at_risk", { mwh: Math.round(item.mwh_at_risk).toLocaleString("en-GB"), kwh: item.quantity ? Math.round(Math.abs(item.quantity.kwh_h)).toLocaleString("en-GB") : "—" })}
          </span>
        )}
        <Countdown atUtc={item.cutoff?.at_utc} urgency={item.urgency} t={t} nowMs={nowMs} />
      </div>
      <p className="recon-text">{words.explanation}</p>
      <p className="recon-text">
        <strong>{t("recon.next")}</strong> {words.next}
      </p>
      {cash ? (
        <p className="recon-cash muted" title={item.cash_out.note}>{t("recon.cash_out", { value: cash })}</p>
      ) : item.cash_out.basis === "missing" ? (
        <p className="recon-cash muted">{t("recon.cash_out_missing")}</p>
      ) : null}
    </li>
  );
}

function GroupRows({ group, breaks, t, language, nowMs, open, onToggle }: { group: ReconciliationGroupDTO; breaks: ReconciliationBreakDTO[]; t: Translate; language: string; nowMs: number; open: boolean; onToggle: () => void }) {
  const id = `recon-${groupKey(group).replace(/[^a-zA-Z0-9]+/g, "-")}`;
  return (
    <>
      <tr className="recon-group" data-state={group.state} data-urgency={group.urgency}>
        <th scope="row" className="recon-cell-name">
          {breaks.length > 0 ? (
            <button type="button" className="gasday-link" aria-expanded={open} aria-controls={id} onClick={onToggle}>
              {group.counterparty}
            </button>
          ) : (
            group.counterparty
          )}
          <span className="recon-meta muted">
            {[group.hub, group.point, group.shipper_codes.length ? t("recon.codes", { codes: group.shipper_codes.join(", ") }) : null].filter(Boolean).join(" · ")}
          </span>
        </th>
        <td className="recon-num">{signedQuantity(group.traded)}</td>
        <td className="recon-num">{group.held.confirmation ? signedQuantity(group.confirmed) : <span className="muted" title={t("recon.not_held")}>—</span>}</td>
        <td className="recon-num">{signedQuantity(group.nominated)}</td>
        <td className="recon-num">{group.held.tso ? signedQuantity(group.tso) : <span className="muted" title={t("recon.not_held")}>—</span>}</td>
        <td className="recon-chips">
          {breaks.length === 0 ? (
            <StatusBadge tone="ok">{t("recon.matched")}</StatusBadge>
          ) : (
            breaks.map((item) => <StatusBadge key={item.id} tone={breakTone(item)}>{t(`recon.kind.${item.kind}`)}</StatusBadge>)
          )}
        </td>
        <td>{breaks.length > 0 ? <Countdown atUtc={group.cutoff?.at_utc} urgency={group.urgency} t={t} nowMs={nowMs} /> : null}</td>
      </tr>
      {breaks.length > 0 && (
        <tr className="recon-detail" id={id} hidden={!open}>
          <td colSpan={7}>
            <ul className="recon-breaks">
              {breaks.map((item) => <BreakDetail key={item.id} item={item} t={t} language={language} nowMs={nowMs} />)}
            </ul>
          </td>
        </tr>
      )}
    </>
  );
}

export function ReconciliationRow({ gasDay, t, language, nowMs }: ReconciliationRowProps) {
  const [which, setWhich] = useState<"today" | "tomorrow">("today");
  const [hub, setHub] = useState(ALL);
  const [kind, setKind] = useState<ReconciliationBreakKind | typeof ALL>(ALL);
  const [counterparty, setCounterparty] = useState("");
  const [show, setShow] = useState<"all" | "breaks">("all");
  const [data, setData] = useState<GasDayReconciliationDTO | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [open, setOpen] = useState<Set<string>>(new Set());
  const [exporting, setExporting] = useState(false);
  const day = which === "today" ? gasDay : nextDay(gasDay);
  const filters: GasDayReconciliationFilters = {
    hub: hub === ALL ? undefined : hub,
    kind: kind === ALL ? undefined : kind,
    counterparty: counterparty.trim() || undefined,
    breaks_only: show === "breaks",
  };
  const query = JSON.stringify([day, filters]);

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    setError(null);
    api
      .gasDayReconciliation(day, filters, { signal: controller.signal })
      .then((response) => setData(response.data))
      .catch((reason: unknown) => {
        if (!controller.signal.aborted) setError(reason instanceof Error ? reason.message : t("recon.failed"));
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
    // `query` carries the day and every filter.
  }, [query]);

  const breakCount = data?.breaks.length ?? 0;
  const hubs = hubOptions(data);
  return (
    <section className="today-row today-row-reconciliation" aria-labelledby="today-row-reconciliation" data-today-row="reconciliation">
      <header className="today-row-head">
        <h2 id="today-row-reconciliation">{t("today.row.reconciliation")}</h2>
        <span className="today-row-meta">
          {breakCount > 0 ? t("recon.summary", { count: breakCount, mwh: Math.round(data?.mwh_at_risk ?? 0).toLocaleString("en-GB") }) : t("recon.purpose")}
        </span>
      </header>
      <Segmented
        label={t("today.gas_day.day_choice")}
        value={which}
        onChange={setWhich}
        options={[
          { value: "today", label: t("today.gas_day.today", { day: formatGasDay(gasDay, language) }) },
          { value: "tomorrow", label: t("today.gas_day.tomorrow", { day: formatGasDay(nextDay(gasDay), language) }) },
        ]}
      />
      <Toolbar
        label={t("recon.filters")}
        className="recon-filters"
        end={
          <Button
            size="sm"
            variant="quiet"
            loading={exporting}
            disabled={breakCount === 0}
            onClick={async () => {
              setExporting(true);
              try {
                await api.downloadGasDayReconciliation(day, filters);
              } catch {
                setError(t("recon.export_failed"));
              } finally {
                setExporting(false);
              }
            }}
          >
            {t("recon.export")}
          </Button>
        }
      >
        <Field label={t("recon.hub")} inline>
          <Select value={hub} onChange={setHub} options={[{ value: ALL, label: t("recon.all_hubs") }, ...(hub !== ALL && !hubs.includes(hub) ? [hub] : hubs).map((value) => ({ value, label: value }))]} />
        </Field>
        <Field label={t("recon.kind_filter")} inline>
          <Select
            value={kind}
            onChange={setKind}
            options={[
              { value: ALL, label: t("recon.all_kinds") },
              ...kindOptions(data).map((option) => ({ value: option.kind, label: option.count > 0 ? `${t(`recon.kind.${option.kind}`)} (${option.count})` : t(`recon.kind.${option.kind}`) })),
            ]}
          />
        </Field>
        <Field label={t("recon.counterparty")} inline>
          <input className="recon-search" type="search" value={counterparty} maxLength={160} onChange={(event) => setCounterparty(event.target.value)} />
        </Field>
        <Segmented
          label={t("recon.show")}
          value={show}
          onChange={setShow}
          options={[{ value: "all", label: t("recon.show_all") }, { value: "breaks", label: t("recon.show_breaks") }]}
        />
      </Toolbar>
      {error && <p className="recon-error" role="alert">{error}</p>}
      {loading && !data ? (
        <Skeleton label={t("recon.loading")} rows={3} />
      ) : !data || data.groups.length === 0 ? (
        <EmptyState compact reason={data?.empty?.reason ?? t("recon.empty")} next={data?.empty?.action} />
      ) : (
        <div className="recon-scroll" aria-busy={loading}>
          <table className="recon-table">
            <caption className="ds-visually-hidden">{t("recon.caption", { day: formatGasDay(day, language), unit: data.groups[0]?.traded?.unit ?? data.groups[0]?.nominated?.unit ?? "" })}</caption>
            <thead>
              <tr>
                <th scope="col">{t("recon.col.counterparty")}</th>
                <th scope="col" className="recon-num">{t("recon.col.traded")}</th>
                <th scope="col" className="recon-num">{t("recon.col.confirmed")}</th>
                <th scope="col" className="recon-num">{t("recon.col.nominated")}</th>
                <th scope="col" className="recon-num">{t("recon.col.tso")}</th>
                <th scope="col">{t("recon.col.breaks")}</th>
                <th scope="col">{t("recon.col.cutoff")}</th>
              </tr>
            </thead>
            <tbody>
              {data.groups.map((group) => {
                const key = groupKey(group);
                return (
                  <GroupRows
                    key={key}
                    group={group}
                    breaks={breaksOf(group, data.breaks)}
                    t={t}
                    language={language}
                    nowMs={nowMs}
                    open={open.has(key)}
                    onToggle={() =>
                      setOpen((current) => {
                        const next = new Set(current);
                        if (next.has(key)) next.delete(key);
                        else next.add(key);
                        return next;
                      })
                    }
                  />
                );
              })}
            </tbody>
          </table>
        </div>
      )}
      {data && data.exchange_trades.length > 0 && (
        <p className="recon-note muted">
          {t("recon.exchange", { hubs: data.exchange_trades.map((entry) => `${entry.hub} (${entry.trades})`).join(", ") })}
        </p>
      )}
      <p className="recon-note muted">{t("recon.read_only")}</p>
    </section>
  );
}

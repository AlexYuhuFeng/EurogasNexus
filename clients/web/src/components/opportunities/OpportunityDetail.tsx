/**
 * One opportunity beside the list (B.7): the claim, the arithmetic table, assumptions,
 * falsifiers, sensitivity, checks and data quality, from the version the server froze. One
 * primary action, "Open as a case", which hands the frozen legs to Deals → Review; watching and
 * dismissing are the caller's own and change nothing for anyone else.
 */
import { useEffect, useState } from "react";

import { api, type OpportunityDetailDTO, type OpportunityRowDTO } from "@/api/client";
import {
  canOpenCase,
  formatEnergy,
  groupMembers,
  memberCount,
  periodLabel,
  rowFigure,
  checkTone,
  DISMISS_REASONS,
  formatMeasure,
  formatValue,
  isDismissed,
  isWatched,
  legFigure,
  legIsTotal,
  markerTone,
  qualityMarker,
} from "@/app/model/opportunitiesModel";
import { Button, EmptyState, Select, StatusBadge } from "@/components/ui";
import { useSimulatedPills } from "@/components/SimulatedScope";
import { Instant } from "@/components/ui/Instant";

type Translate = (key: string, options?: Record<string, unknown>) => string;

export interface OpportunityDetailProps {
  t: Translate;
  opportunityId: string;
  onClose: () => void;
  onChanged: () => void;
  onOpenCase: (caseId: string) => void;
  /** The list item this opportunity belongs to (one per subject, its months inside). */
  group?: OpportunityRowDTO;
  onSelectMember?: (opportunityId: string) => void;
}

function errorCode(error: unknown): string | null {
  const detail = (error as { detail?: { code?: string; case_id?: string } } | null)?.detail;
  return detail?.code ?? null;
}

export function OpportunityDetail({ t, opportunityId, onClose, onChanged, onOpenCase, group, onSelectMember }: OpportunityDetailProps) {
  const [detail, setDetail] = useState<OpportunityDetailDTO | null>(null);
  const [failed, setFailed] = useState(false);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [reason, setReason] = useState<(typeof DISMISS_REASONS)[number]>("not_relevant");
  const [revision, setRevision] = useState(0);
  const pills = useSimulatedPills();

  useEffect(() => {
    const controller = new AbortController();
    api
      .opportunity(opportunityId, { signal: controller.signal })
      .then((response) => {
        setDetail(response.data);
        setFailed(false);
      })
      .catch(() => {
        if (!controller.signal.aborted) setFailed(true);
      });
    return () => controller.abort();
  }, [opportunityId, revision]);

  // On a phone or tablet the detail sits below the list: bring it into view when it opens.
  useEffect(() => {
    if (!detail || typeof window === "undefined" || window.innerWidth > 960) return;
    document.querySelector(`[data-opportunity="${CSS.escape(detail.opportunity_id)}"]`)?.scrollIntoView({ block: "start" });
  }, [detail]);

  if (failed) {
    return (
      <aside className="opportunity-detail" aria-label={t("opportunities.detail")}>
        <EmptyState id="opportunity-unavailable" reason={t("opportunities.detail.unavailable")} />
      </aside>
    );
  }
  if (!detail) return <aside className="opportunity-detail" aria-busy="true" aria-label={t("opportunities.detail")} />;

  const object = detail.object;
  const rawMarker = qualityMarker(detail);
  const marker = rawMarker === "simulated" && !pills ? null : rawMarker;
  const tone = markerTone(marker);

  const openCase = () => {
    setBusy(true);
    setMessage(null);
    api
      .openOpportunityCase(detail.opportunity_id)
      .then((response) => {
        onChanged();
        const caseId = response.data.case?.case_id;
        if (caseId) onOpenCase(caseId);
      })
      .catch((error) => {
        const code = errorCode(error);
        setMessage(t(code === "already_converted" ? "opportunities.case.error.already_converted" : "opportunities.case.error"));
      })
      .finally(() => setBusy(false));
  };

  const setState = (action: "dismiss" | "restore" | "watch" | "unwatch") => {
    setBusy(true);
    setMessage(null);
    api
      .setOpportunityState(detail.opportunity_id, action === "dismiss" ? { action, reason } : { action })
      .then(() => {
        setRevision((value) => value + 1);
        onChanged();
      })
      .catch(() => setMessage(t("opportunities.state.error")))
      .finally(() => setBusy(false));
  };

  const dismissed = isDismissed(detail);
  const watched = isWatched(detail);

  return (
    <aside className="opportunity-detail" aria-labelledby="opportunity-claim" data-opportunity={detail.opportunity_id}>
      <header className="opportunity-detail-head">
        <p id="opportunity-claim" className="opportunity-claim">
          {detail.claim}
        </p>
        <Button variant="quiet" onClick={onClose} aria-label={t("opportunities.detail.close")}>
          ×
        </Button>
      </header>
      <p className="opportunity-figures">
        <strong>{formatMeasure(detail.headline, { signed: true })}</strong>
        {detail.value && <span>{formatValue(detail.value)}</span>}
        {detail.volume && formatMeasure(detail.volume) !== formatMeasure(detail.headline) && <span>{formatMeasure(detail.volume)}</span>}
        <span>{periodLabel(detail.period)}</span>
        {marker && tone && <StatusBadge tone={tone}>{t(`opportunities.class.${marker}`)}</StatusBadge>}
        <StatusBadge tone={detail.state === "blocked" ? "breach" : detail.state === "actionable" ? "ok" : "neutral"}>
          {t(`opportunities.state.${detail.state}`)}
        </StatusBadge>
      </p>
      {detail.rank && <p className="opportunities-muted">{detail.rank.reason}</p>}
      {group && memberCount(group) > 1 && (
        <MonthsTable t={t} group={group} current={opportunityId} onSelect={onSelectMember} />
      )}
      {detail.blocked && (
        <p className="opportunity-blocked" role="note">
          <strong>{detail.blocked.text}</strong> {detail.blocked.fix}
        </p>
      )}

      <div className="opportunity-actions">
        {canOpenCase(detail) && (
          <Button variant="primary" onClick={openCase} disabled={busy}>
            {t("opportunities.open_case")}
          </Button>
        )}
        {detail.case && <span className="opportunities-muted">{t("opportunities.case.opened", { id: detail.case.case_id })}</span>}
        {detail.next_steps.includes("watch") && (
          <Button variant="secondary" onClick={() => setState(watched ? "unwatch" : "watch")} disabled={busy}>
            {watched ? t("opportunities.unwatch") : t("opportunities.watch")}
          </Button>
        )}
        {dismissed ? (
          <Button variant="secondary" onClick={() => setState("restore")} disabled={busy}>
            {t("opportunities.restore")}
          </Button>
        ) : (
          detail.next_steps.includes("dismiss") && (
            <span className="opportunity-dismiss">
              <Select
                aria-label={t("opportunities.dismiss.reason")}
                value={reason}
                options={DISMISS_REASONS.map((value) => ({ value, label: t(`opportunities.dismiss.${value}`) }))}
                onChange={setReason}
              />
              <Button variant="quiet" onClick={() => setState("dismiss")} disabled={busy}>
                {t("opportunities.dismiss")}
              </Button>
            </span>
          )
        )}
      </div>
      {message && (
        <p className="opportunity-message" role="alert">
          {message}
        </p>
      )}

      {object && (
        <>
          <h4>{t("opportunities.detail.arithmetic")}</h4>
          <table className="opportunity-arithmetic">
            <tbody>
              {object.legs.map((leg, index) => (
                <tr key={`${leg.label_key}-${index}`} data-kind={leg.kind} className={legIsTotal(leg) ? "is-total" : undefined}>
                  <th scope="row">
                    {leg.label}
                    {leg.note && <span className="opportunity-leg-note">{leg.note}</span>}
                  </th>
                  <td className="opportunity-num">{legFigure(leg)}</td>
                  <td className="opportunity-source">
                    {leg.input_class && (
                      <span data-class={leg.input_class}>{t(`opportunities.class.${leg.input_class}`)}</span>
                    )}
                    {leg.source_family && <span> · {leg.source_family}</span>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>

          {object.checks.length > 0 && (
            <>
              <h4>{t("opportunities.detail.checks")}</h4>
              <ul className="opportunity-checks">
                {object.checks.map((check) => (
                  <li key={check.kind} data-result={check.result}>
                    <StatusBadge tone={checkTone(check.result)}>{t(`opportunities.check.${check.result}`)}</StatusBadge>{" "}
                    <strong>{t(`opportunities.check.kind.${check.kind}`)}</strong> {check.figure}
                  </li>
                ))}
              </ul>
            </>
          )}

          {object.falsifiers.length > 0 && (
            <>
              <h4>{t("opportunities.detail.falsifiers")}</h4>
              <ul className="opportunity-list">
                {object.falsifiers.map((item) => (
                  <li key={item.key}>{item.text}</li>
                ))}
              </ul>
            </>
          )}

          {object.sensitivity.length > 0 && (
            <>
              <h4>{t("opportunities.detail.sensitivity")}</h4>
              <ul className="opportunity-list">
                {object.sensitivity.map((item) => (
                  <li key={`${item.driver}-${item.kind}`}>{item.text}</li>
                ))}
              </ul>
            </>
          )}

          {object.assumptions.length > 0 && (
            <>
              <h4>{t("opportunities.detail.assumptions")}</h4>
              <ul className="opportunity-list">
                {object.assumptions.map((item) => (
                  <li key={item.key}>
                    <strong>{item.key}</strong> {formatMeasure(item.value)}{" "}
                    <span className="opportunities-muted">
                      {t("opportunities.assumption.set_by", { who: item.set_by, origin: item.origin })}
                    </span>
                  </li>
                ))}
              </ul>
            </>
          )}

          <details className="opportunity-quality">
            <summary>{t("opportunities.detail.quality", { label: object.quality.label })}</summary>
            <table className="opportunity-arithmetic">
              <tbody>
                {object.quality.inputs.map((input) => (
                  <tr key={input.key}>
                    <th scope="row">{input.label}</th>
                    <td className="opportunity-num">{formatMeasure({ value: input.value, unit: input.unit })}</td>
                    <td className="opportunity-source">
                      {t(`opportunities.class.${input.class}`)}
                      {input.source_family && ` · ${input.source_family}`}
                      {input.as_of_utc && (
                        <>
                          {" · "}
                          <Instant value={input.as_of_utc} date="always" />
                        </>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            <p className="opportunities-muted">
              {t("opportunities.detail.version", { version: detail.version, count: detail.versions.length })}
            </p>
          </details>
        </>
      )}
    </aside>
  );
}

const MONTHS_SHOWN = 6;

function MonthsTable({
  t,
  group,
  current,
  onSelect,
}: {
  t: Translate;
  group: OpportunityRowDTO;
  current: string;
  onSelect?: (opportunityId: string) => void;
}) {
  const members = groupMembers(group);
  const gap = group.type === "hedge_gap";
  const row = (member: (typeof members)[number]) => (
    <tr key={member.opportunity_id} aria-selected={member.opportunity_id === current} data-state={member.state}>
      <th scope="row">
        <button type="button" className="ds-inline-link" onClick={() => onSelect?.(member.opportunity_id)}>
          {periodLabel(member.period)}
        </button>
      </th>
      <td className="opportunity-num">{gap ? formatEnergy(member.volume) : formatValue(member.value)}</td>
      {!gap && <td className="opportunity-num">{formatMeasure(member.headline, { signed: true })}</td>}
      <td className="opportunity-source">{t(`opportunities.state.${member.state}`)}</td>
    </tr>
  );
  return (
    <div className="opportunity-months" aria-label={t("opportunities.detail.months")}>
      <p className="opportunities-muted">
        {t("opportunities.detail.months_total", { count: members.length, total: rowFigure(group) })}
      </p>
      <table className="opportunity-arithmetic">
        <tbody>{members.slice(0, MONTHS_SHOWN).map(row)}</tbody>
      </table>
      {members.length > MONTHS_SHOWN && (
        <details>
          <summary>{t("opportunities.detail.months_more", { count: members.length - MONTHS_SHOWN })}</summary>
          <table className="opportunity-arithmetic">
            <tbody>{members.slice(MONTHS_SHOWN).map(row)}</tbody>
          </table>
        </details>
      )}
    </div>
  );
}

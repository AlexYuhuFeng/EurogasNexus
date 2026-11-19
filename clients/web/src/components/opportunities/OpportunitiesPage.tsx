/**
 * Deals → Opportunities (CP-14, design basis 2 B.7): ways to earn or save money with the book,
 * with the arithmetic shown. Two lanes that never mix (must act, could act), each as the server
 * ranked it, and two folded groups (watching, cannot evaluate). Selecting a row opens its detail
 * beside the list. The single primary action is "Open as a case"; nothing here is an order, a
 * nomination or an instruction, and a simulated figure is always marked.
 *
 * On day one (no book, no prices) the page says why it is empty and shows what the engine needs,
 * each line with the one control that fixes it (H.1). The server builds every figure; this view
 * formats them in their native units.
 */
import { useCallback, useEffect, useState } from "react";

import { api, type OpportunityListDTO, type OpportunityRowDTO } from "@/api/client";
import {
  bucketRows,
  bucketTotal,
  dueOf,
  emptyReason,
  evaluationLine,
  groupMembers,
  memberCount,
  rowFigure,
  rowTitle,
  formatMeasure,
  formatValue,
  GROUPS,
  hasAnyOpportunity,
  LANES,
  markerTone,
  qualityMarker,
  readinessLines,
  rowLead,
  showReadiness,
  timeLeft,
  type OpportunityBucket,
} from "@/app/model/opportunitiesModel";
import { Button, EmptyState, StatusBadge } from "@/components/ui";
import { Instant } from "@/components/ui/Instant";
import { SimulatedScope, simulatedScopeOf, useSimulatedPills } from "@/components/SimulatedScope";
import { OpportunityDetail } from "./OpportunityDetail";
import { FirmMarksGrid } from "./FirmMarksGrid";

type Translate = (key: string, options?: Record<string, unknown>) => string;

export interface OpportunitiesPageProps {
  t: Translate;
  /** Whether the caller may store the firm's marks (portfolio write). */
  canEnterMarks: boolean;
  /** An opportunity to open on arrival (a link from Today or the strip). */
  initialOpportunityId?: string | null;
  onSelect?: (opportunityId: string | null) => void;
  onAddContract: () => void;
  onOpenCase: (caseId: string) => void;
}

export function OpportunitiesPage({
  t,
  canEnterMarks,
  initialOpportunityId = null,
  onSelect,
  onAddContract,
  onOpenCase,
}: OpportunitiesPageProps) {
  const [list, setList] = useState<OpportunityListDTO | null>(null);
  const [failed, setFailed] = useState(false);
  const [selected, setSelected] = useState<string | null>(initialOpportunityId);
  const [evaluating, setEvaluating] = useState(false);
  const [marksOpen, setMarksOpen] = useState(false);
  const [revision, setRevision] = useState(0);

  useEffect(() => {
    setSelected(initialOpportunityId);
  }, [initialOpportunityId]);

  useEffect(() => {
    const controller = new AbortController();
    api
      .opportunities({ signal: controller.signal })
      .then((response) => {
        setList(response.data);
        setFailed(false);
      })
      .catch(() => {
        if (!controller.signal.aborted) setFailed(true);
      });
    return () => controller.abort();
  }, [revision]);

  const reload = useCallback(() => setRevision((value) => value + 1), []);

  const select = (id: string | null) => {
    setSelected(id);
    onSelect?.(id);
  };

  const evaluate = () => {
    setEvaluating(true);
    api
      .evaluateOpportunities()
      .then(reload)
      .catch(() => setFailed(true))
      .finally(() => setEvaluating(false));
  };

  const now = new Date();
  const evaluation = evaluationLine(list);
  const allRows = [...LANES, ...GROUPS].flatMap((bucket) => bucketRows(list, bucket));
  const scope = simulatedScopeOf(allRows.map((row) => row.simulated));
  const selectedRow = allRows.find(
    (row) => row.opportunity_id === selected || groupMembers(row).some((m) => m.opportunity_id === selected),
  );

  return (
    <section className="opportunities-page" aria-label={t("opportunities.title")} data-opportunities-page="true">
      {/* The task's name and purpose line are the Deals header's (PageIntro, design H.1). */}
      <header className="opportunities-head">
        <div className="opportunities-head-side">
          <span className="opportunities-asof" data-evaluation-trigger={evaluation.trigger ?? undefined}>
            {list?.as_of_utc ? (
              <>
                <Instant value={list.as_of_utc} prefix={t("opportunities.as_of")} />
                {evaluation.trigger && ` · ${t(`opportunities.trigger.${evaluation.trigger === "schedule" ? "schedule" : "on_demand"}`)}`}
                {evaluation.pending.length > 0 &&
                  ` · ${t("opportunities.pending", { inputs: evaluation.pending.map((item) => t(`opportunities.input.${item}`)).join(", ") })}`}
              </>
            ) : (
              t("opportunities.not_evaluated")
            )}
          </span>
          <Button variant="secondary" onClick={evaluate} disabled={evaluating}>
            {evaluating ? t("opportunities.evaluating") : t("opportunities.evaluate_now")}
          </Button>
        </div>
      </header>

      <SimulatedScope scope={scope} notice={t("opportunities.banner.simulated")}>

      {failed && !list && (
        <EmptyState id="opportunities-unavailable" reason={t("opportunities.unavailable")} next={t("opportunities.unavailable_next")} />
      )}

      {list && !showReadiness(list) && list.evaluation && (
        <p className="opportunities-muted" data-readiness="ready">
          {t("opportunities.ready.all")}
        </p>
      )}
      {list && showReadiness(list) && (
        <Readiness
          t={t}
          list={list}
          canEnterMarks={canEnterMarks}
          onAddContract={onAddContract}
          onEnterMarks={() => setMarksOpen(true)}
        />
      )}

      {marksOpen && (
        <FirmMarksGrid
          t={t}
          onClose={() => setMarksOpen(false)}
          onSaved={() => {
            setMarksOpen(false);
            reload();
          }}
        />
      )}

      {list && !hasAnyOpportunity(list) && (
        <EmptyState
          id="opportunities-empty"
          reason={t(emptyReason(list))}
          next={list.evaluation ? undefined : t("opportunities.empty.next")}
        />
      )}

      {list && hasAnyOpportunity(list) && (
        <div className={selected ? "opportunities-body has-detail" : "opportunities-body"}>
          <div className="opportunities-list">
            {LANES.map((lane) => (
              <Lane key={lane} t={t} list={list} bucket={lane} selected={selected} now={now} onSelect={select} />
            ))}
            {GROUPS.map((group) =>
              bucketTotal(list, group) > 0 ? (
                <details key={group} className="opportunities-group" data-group={group}>
                  <summary>{t(`opportunities.group.${group}`, { count: bucketTotal(list, group) })}</summary>
                  <Rows t={t} rows={bucketRows(list, group)} bucket={group} selected={selected} now={now} onSelect={select} />
                </details>
              ) : null,
            )}
            {(list.confirming > 0 || list.hidden_by_you > 0) && (
              <p className="opportunities-footnote">
                {list.confirming > 0 && t("opportunities.confirming", { count: list.confirming })}
                {list.confirming > 0 && list.hidden_by_you > 0 && " · "}
                {list.hidden_by_you > 0 && t("opportunities.hidden", { count: list.hidden_by_you })}
              </p>
            )}
          </div>
          {selected && (
            <OpportunityDetail
              key={selected}
              t={t}
              opportunityId={selected}
              group={selectedRow}
              onSelectMember={select}
              onClose={() => select(null)}
              onChanged={reload}
              onOpenCase={onOpenCase}
            />
          )}
        </div>
      )}
      </SimulatedScope>
    </section>
  );
}

function Lane({
  t,
  list,
  bucket,
  selected,
  now,
  onSelect,
}: {
  t: Translate;
  list: OpportunityListDTO;
  bucket: OpportunityBucket;
  selected: string | null;
  now: Date;
  onSelect: (id: string) => void;
}) {
  const rows = bucketRows(list, bucket);
  const total = bucketTotal(list, bucket);
  return (
    <section className="opportunities-lane" data-lane={bucket} aria-label={t(`opportunities.lane.${bucket}`, { count: total })}>
      <h3>{t(`opportunities.lane.${bucket}`, { count: total })}</h3>
      {rows.length === 0 ? (
        <p className="opportunities-lane-empty">{t(`opportunities.lane.${bucket}.none`)}</p>
      ) : (
        <Rows t={t} rows={rows} bucket={bucket} selected={selected} now={now} onSelect={onSelect} />
      )}
      {total > rows.length && <p className="opportunities-more">{t("opportunities.more", { count: total - rows.length })}</p>}
    </section>
  );
}

function Rows({
  t,
  rows,
  bucket,
  selected,
  now,
  onSelect,
}: {
  t: Translate;
  rows: OpportunityRowDTO[];
  bucket: OpportunityBucket;
  selected: string | null;
  now: Date;
  onSelect: (id: string) => void;
}) {
  const pills = useSimulatedPills();
  return (
    <ol className="opportunities-rows">
      {rows.map((row) => {
        const marker = qualityMarker(row);
        const tone = markerTone(marker);
        const shownMarker = marker === "simulated" && !pills ? null : marker;
        const due = dueOf(row, now);
        const title = rowTitle(row);
        const active = selected === row.opportunity_id || groupMembers(row).some((m) => m.opportunity_id === selected);
        return (
          <li key={row.opportunity_id} data-state={row.state} data-type={row.type_code} data-months={memberCount(row)}>
            <button
              type="button"
              className="opportunities-row"
              aria-pressed={active}
              onClick={() => onSelect(row.opportunity_id)}
              title={row.rank?.reason ?? undefined}
            >
              <span className="opportunities-lead" aria-hidden={bucket === "must_act" ? true : undefined}>
                {rowLead(row, bucket)}
              </span>
              <span className="opportunities-claim">{t(title.key, title.values)}</span>
              <span className="opportunities-figure opportunities-value">{rowFigure(row)}</span>
              <span className="opportunities-quality">
                {shownMarker && tone && <StatusBadge tone={tone}>{t(`opportunities.class.${shownMarker}`)}</StatusBadge>}
                {bucket === "blocked" && row.blocked && <span className="opportunities-blocker">{row.blocked.text}</span>}
              </span>
              <span className="opportunities-due">
                {due && t(due.key, { ...due.values, when: due.values.whenKey ? t(String(due.values.whenKey), { count: due.values.count }) : "" })}
              </span>
            </button>
          </li>
        );
      })}
    </ol>
  );
}

function Readiness({
  t,
  list,
  canEnterMarks,
  onAddContract,
  onEnterMarks,
}: {
  t: Translate;
  list: OpportunityListDTO;
  canEnterMarks: boolean;
  onAddContract: () => void;
  onEnterMarks: () => void;
}) {
  const lines = readinessLines(list.readiness);
  return (
    <section className="opportunities-readiness" aria-labelledby="opportunities-readiness-title" data-readiness="true">
      <h3 id="opportunities-readiness-title">{t("opportunities.ready.title")}</h3>
      <ol>
        {lines.map((line) => (
          <li key={line.key} data-ready={line.ready}>
            <span className="opportunities-tick" aria-hidden="true">
              {line.ready ? "✓" : "○"}
            </span>
            <span className="opportunities-ready-name">{t(`opportunities.ready.${line.key}`)}</span>
            <span className="opportunities-ready-state">{t(line.stateKey, line.values)}</span>
            <span className="opportunities-ready-fix">
              {line.fix === "add_contract" && (
                <Button variant="secondary" onClick={onAddContract}>
                  {t("opportunities.ready.add_contract")}
                </Button>
              )}
              {line.fix === "enter_marks" &&
                (canEnterMarks ? (
                  <>
                    <Button variant="secondary" onClick={onEnterMarks}>
                      {t("opportunities.ready.enter_marks")}
                    </Button>{" "}
                    <span className="opportunities-muted">{t("opportunities.ready.feed_admin")}</span>
                  </>
                ) : (
                  <span className="opportunities-muted">{t("opportunities.ready.marks_who")}</span>
                ))}
              {line.ready && <span className="opportunities-muted">{t("opportunities.ready.ok")}</span>}
            </span>
          </li>
        ))}
      </ol>
      <p className="opportunities-muted">{t("opportunities.ready.finds")}</p>
    </section>
  );
}

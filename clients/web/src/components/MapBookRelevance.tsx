import { useState } from "react";
import type { BookOpportunityPathDTO, BookProposalDTO, BookRelevanceDTO } from "@/api/client";
import { benefitLabel, groupOpportunities, opportunityLabel, reachableLine, reasonLine, signedMargin, type Translate } from "@/app/mapBookRelevance";
import { formatDeliveryMonth, formatInstant } from "@/app/time/timeFormat";
import { formatMeasure } from "@/app/time/valueFormat";
import { Icon } from "@/components/ui/Icon";

/** The reasons the opportunity core accepts for a dismissal (domain DismissReason). */
const DISMISS_REASONS = [
  "not_relevant",
  "already_covered",
  "margin_too_thin",
  "not_executable",
  "outside_mandate",
  "data_wrong",
  "other",
] as const;

function navigate(search: string) {
  window.history.pushState({}, "", search);
  window.dispatchEvent(new PopStateEvent("popstate"));
}

/**
 * Now against proposed, the record's own texts side by side; a figure it does not state reads
 * "not stated". Then the inputs it rests on, with source and time.
 */
function ProposalTable({ proposal, t, language }: { proposal: BookProposalDTO; t: Translate; language: string }) {
  const stated = (value: string | null) => value ?? t("map.book.not_stated");
  const route = (side: BookProposalDTO["now"], isNow: boolean) =>
    side.via.length
      ? `${t("map.book.via", { via: side.via.join(" / ") })}${side.to_hub ? ` → ${side.to_hub}` : ""}`
      : isNow && side.to_hub
        ? t("map.book.sold_locally", { hub: side.to_hub })
        : t("map.book.not_stated");
  const rows: Array<[string, string, string]> = [
    [t("map.book.row.route"), route(proposal.now, true), route(proposal.proposed, false)],
    [t("map.book.row.tariff"), stated(proposal.now.tariff), stated(proposal.proposed.tariff)],
    [t("map.book.row.capacity"), stated(proposal.now.capacity), stated(proposal.proposed.capacity)],
    [t("map.book.row.margin"), stated(proposal.now.margin), stated(proposal.proposed.margin)],
    [t("map.book.row.period"), proposal.now.period, proposal.proposed.period],
    [t("map.book.row.input_class"), proposal.now.input_class.label, proposal.proposed.input_class.label],
  ];
  const at = (iso: string | null) =>
    formatInstant(iso, { language, preference: "device", date: "always" })?.text ?? null;
  return (
    <>
      <table className="map-proposal-table" data-figure="now-vs-proposed">
        <thead>
          <tr>
            <th scope="col"><span className="visually-hidden">{t("map.book.row.label")}</span></th>
            <th scope="col">{t("map.book.now")}</th>
            <th scope="col">{t("map.book.proposed")}</th>
          </tr>
        </thead>
        <tbody>
          {rows.map(([label, now, proposed]) => (
            <tr key={label}>
              <th scope="row">{label}</th>
              <td>{now}</td>
              <td>{proposed}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="map-proposal-evidence muted">
        {proposal.evidence.length
          ? `${t("map.book.rests_on")} ${proposal.evidence
              .map((item) => [item.label, item.source_family, item.source_ref, at(item.as_of_utc)].filter(Boolean).join(", "))
              .join("; ")}`
          : t("map.book.rests_on_not_stated")}
      </p>
    </>
  );
}

/**
 * One opportunity's card: the core's claim and figures, the path it runs along; for a
 * re-route or locational alternative, now against proposed. Three actions, none of which
 * books, nominates or executes anything: open it in Deals → Opportunities, open a Review case
 * (the frozen arithmetic as evidence), or dismiss it for me.
 */
export function OpportunityCard({
  item,
  t,
  language = "en",
  windowLeft = null,
  onClose,
  onOpenCase,
  onDismiss,
}: {
  item: BookOpportunityPathDTO;
  t: Translate;
  language?: string;
  /** Time left to act ("2 h 10 min"), or null when no window is stated. */
  windowLeft?: string | null;
  onClose: () => void;
  /** Resolves with the new case id (or null). */
  onOpenCase?: () => Promise<string | null>;
  onDismiss?: (reason: string) => Promise<void>;
}) {
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [caseId, setCaseId] = useState<string | null>(null);
  const [dismissing, setDismissing] = useState(false);
  const [reason, setReason] = useState<string>(DISMISS_REASONS[0]);
  const deals = `?mode=deals&task=opportunities&opportunity=${encodeURIComponent(item.opportunity_id)}`;
  const run = async (action: () => Promise<void>) => {
    setBusy(true);
    setMessage(null);
    try {
      await action();
    } catch {
      setMessage(t("map.book.action_failed"));
    } finally {
      setBusy(false);
    }
  };
  return (
    <aside className="map-detail-panel map-opportunity-card" aria-label={t("map.book.opportunity")}>
      <button type="button" className="map-detail-close link-button" onClick={onClose} aria-label={t("map.detail.close")} title={t("map.detail.close")}><Icon name="close" /></button>
      <header className="map-detail-header">
        <h3>{item.claim}</h3>
        <div className="map-detail-roles">
          <span className="map-role is-own">{t(`map.book.opportunity_state.${item.state}`)}</span>
          <span className="map-role is-neutral">{item.from_hub} → {item.to_hub}</span>
          {item.simulated && <span className="map-role is-watch">{t("map.detail.simulated")}</span>}
        </div>
      </header>
      <p className="map-opportunity-headline" data-figure="opportunity-headline">
        {item.proposal ? benefitLabel(item, t) : opportunityLabel(item)}
      </p>
      {item.proposal ? (
        <ProposalTable proposal={item.proposal} t={t} language={language} />
      ) : (
        <>
          <p className="muted">{t("map.book.opportunity_period", { period: formatDeliveryMonth(item.period) })}</p>
          <p className="muted">{t("map.book.opportunity_via", { via: item.via.join(", ") })}</p>
        </>
      )}
      {item.route_stated === false && <p className="muted">{t("map.book.route_not_stated")}</p>}
      {item.blocked && (
        <p className="map-opportunity-blocked" data-figure="opportunity-blocked">
          {item.blocked.text !== item.claim ? item.blocked.text : null}
          {item.blocked.fix ? <small> {item.blocked.fix}</small> : null}
        </p>
      )}
      {item.window_closes_utc && (
        <p className={windowLeft ? "map-opportunity-window" : "map-opportunity-window is-closed"} data-figure="opportunity-window">
          {windowLeft ? t("map.book.window_closes", { time: windowLeft }) : t("map.book.window_closed")}
        </p>
      )}
      <div className="map-opportunity-actions">
        <a
          className="ds-button secondary-button ds-size-sm"
          href={deals}
          onClick={(event) => {
            // In-app navigation to Deals → Opportunities (CP-14) on this opportunity.
            event.preventDefault();
            navigate(deals);
          }}
        >
          {t("map.book.open_in_deals")}
        </a>
        {onOpenCase && (
          caseId ? (
            <a
              className="ds-button secondary-button ds-size-sm"
              href="?mode=deals&task=review"
              onClick={(event) => {
                event.preventDefault();
                navigate("?mode=deals&task=review");
              }}
            >
              {t("map.book.case_opened", { id: caseId })}
            </a>
          ) : (
            <button
              type="button"
              className="ds-button secondary-button ds-size-sm"
              disabled={busy}
              onClick={() => void run(async () => setCaseId((await onOpenCase()) ?? "–"))}
            >
              {t("map.book.open_case")}
            </button>
          )
        )}
        {onDismiss && !dismissing && (
          <button type="button" className="ds-button quiet-button ds-size-sm" disabled={busy} onClick={() => setDismissing(true)}>
            {t("map.book.dismiss")}
          </button>
        )}
      </div>
      {onDismiss && dismissing && (
        <div className="map-opportunity-dismiss">
          <label>
            <span>{t("map.book.dismiss_reason")}</span>
            <select value={reason} onChange={(event) => setReason(event.target.value)}>
              {DISMISS_REASONS.map((code) => (
                <option key={code} value={code}>{t(`map.book.dismiss_reason_${code}`)}</option>
              ))}
            </select>
          </label>
          <button type="button" className="ds-button secondary-button ds-size-sm" disabled={busy} onClick={() => void run(() => onDismiss(reason))}>
            {t("map.book.dismiss_confirm")}
          </button>
          <button type="button" className="link-button" onClick={() => setDismissing(false)}>
            {t("map.book.dismiss_cancel")}
          </button>
        </div>
      )}
      {message && <p className="map-opportunity-message" role="status">{message}</p>}
      <footer className="map-detail-footer muted">{t("map.book.opportunity_core")}</footer>
    </aside>
  );
}

/** "Dec-26 +0.34 · Jan-27 +0.355": each period once (its best figure), in delivery order. */
function periodFigures(members: readonly BookOpportunityPathDTO[]): string {
  const best = new Map<string, number>();
  for (const member of members) {
    const value = Number(member.headline.value);
    if (!Number.isFinite(value)) continue;
    best.set(member.period, Math.max(best.get(member.period) ?? Number.NEGATIVE_INFINITY, value));
  }
  return [...best.entries()]
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([period, value]) => `${formatDeliveryMonth(period)} ${signedMargin(value)}`)
    .join(" · ");
}

/** One "What needs me" item with a place on the map. */
export interface NeedsYouRow {
  key: string;
  kind: "outage" | "opportunity" | "limit";
  id: string;
  title: string;
  line: string;
  simulated: boolean;
  /** A limit's hub node. */
  refId?: string;
}

/**
 * The "Our book" tab's relevance lists (design basis 2, J.5): what is on the book view and
 * why, and the neighbouring market areas our hubs reach with the indicative spread net of
 * the published tariffs. Selecting a row selects it on the map. No advice, no order entry.
 */
export function MapBookRelevance({
  relevance,
  t,
  onSelectHub,
  onSelectPlace,
  onSelectOpportunity,
  language,
  needsYou = [],
  activeNeed = null,
  activeOpportunity = null,
  onSelectNeed,
}: {
  /** The opportunity open on the map, highlighted in the list. */
  activeOpportunity?: string | null;
  /** Today's items that have a place on the map; selecting one flies there and opens it. */
  needsYou?: NeedsYouRow[];
  /** The row of what is open on the map (selected there or here). */
  activeNeed?: string | null;
  onSelectNeed?: (row: NeedsYouRow) => void;
  relevance: BookRelevanceDTO | null | undefined;
  t: Translate;
  /** App language, for number grouping. */
  language: string;
  /** A hub, by its node id. */
  onSelectHub: (hubNodeId: string) => void;
  onSelectPlace: (refId: string) => void;
  onSelectOpportunity: (opportunityId: string) => void;
}) {
  if (!relevance) return null;
  const places = relevance.ours.filter((item) => item.kind !== "cargo");
  return (
    <div className="map-book-relevance">
      <p className="muted map-book-hint">{t("map.book.legend")}</p>
      {needsYou.length > 0 && (
        <section aria-labelledby="map-book-needs-title" className="map-book-needs">
          <h3 id="map-book-needs-title">{t("map.book.needs_you_title")}</h3>
          <ul className="map-book-rows">
            {needsYou.map((row) => (
              <li key={row.key}>
                <button
                  type="button"
                  className={row.key === activeNeed ? "map-book-row is-active" : "map-book-row"}
                  aria-current={row.key === activeNeed ? "true" : undefined}
                  onClick={() => onSelectNeed?.(row)}
                >
                  <strong>
                    <span className={`map-need-kind is-${row.kind}`}>{t(`map.book.need_kind.${row.kind}`)}</span>{" "}
                    {row.title}{row.simulated ? <small> sim</small> : null}
                  </strong>
                  <small>{row.line}</small>
                </button>
              </li>
            ))}
          </ul>
        </section>
      )}
      <section aria-labelledby="map-book-opportunities-title">
        <h3 id="map-book-opportunities-title">{t("map.book.opportunities_title")}</h3>
        {(relevance.opportunities ?? []).length === 0 ? (
          <p className="muted">{t("map.book.opportunities_empty")}</p>
        ) : (
          <ul className="map-book-rows">
            {/* One row per path: the strongest stands for the periods on it. */}
            {groupOpportunities(relevance.opportunities).map(({ lead: item, members }) => (
              <li key={item.opportunity_id}>
                <button
                  type="button"
                  className={item.opportunity_id === activeOpportunity ? "map-book-row is-active" : "map-book-row"}
                  aria-current={item.opportunity_id === activeOpportunity ? "true" : undefined}
                  onClick={() => onSelectOpportunity(item.opportunity_id)}
                >
                  <strong>
                    {item.from_hub} → {item.to_hub}{" "}
                    <span className="map-book-net">{opportunityLabel(item)}</span>
                  </strong>
                  <small>
                    {t(`map.book.opportunity_state.${item.state}`)} ·{" "}
                    {members.length > 1 ? periodFigures(members) : item.claim}
                  </small>
                </button>
              </li>
            ))}
          </ul>
        )}
      </section>
      <section aria-labelledby="map-book-ours-title">
        <h3 id="map-book-ours-title">{t("map.book.ours_title")}</h3>
        {places.length === 0 ? (
          <p className="muted">{t("map.book.ours_empty")}</p>
        ) : (
          <ul className="map-book-rows">
            {places.map((item) => (
              <li key={`${item.kind}-${item.ref}`}>
                <button
                  type="button"
                  className="map-book-row"
                  onClick={() => (item.kind === "hub" ? onSelectHub(item.ref) : onSelectPlace(item.ref))}
                >
                  <strong>{item.name}</strong>
                  <small>{item.reasons.map((reason) => reasonLine(reason, t, language)).join(" · ")}</small>
                </button>
              </li>
            ))}
          </ul>
        )}
      </section>
      {(relevance.arrivals ?? []).length > 0 && (
        <section aria-labelledby="map-book-arrivals-title">
          <h3 id="map-book-arrivals-title">{t("map.book.arrivals_title")}</h3>
          <ul className="map-book-rows">
            {relevance.arrivals!.map((item) => (
              <li key={item.cargo_id} className="map-book-row is-static">
                <strong>{item.vessel}{item.simulated ? <small> sim</small> : null}</strong>
                <small>{t("map.book.arrival", { terminal: item.terminal ?? "–", eta: (item.eta_utc ?? "").slice(0, 10) })}</small>
              </li>
            ))}
          </ul>
        </section>
      )}
      <section aria-labelledby="map-book-reachable-title">
        <h3 id="map-book-reachable-title">{t("map.book.reachable_title")}</h3>
        <p className="muted map-book-hint">{t("map.book.reachable_hint")}</p>
        {relevance.reachable.length === 0 ? (
          <p className="muted">{t("map.book.reachable_empty")}</p>
        ) : (
          <ul className="map-book-rows">
            {relevance.reachable.map((path) => (
              <li key={`${path.from_hub}-${path.to_hub}`}>
                <button type="button" className="map-book-row" onClick={() => onSelectHub(path.path_node_ids[path.path_node_ids.length - 1] ?? "")}>
                  <strong>
                    {path.from_hub} → {path.to_hub}
                    {path.net_gbp_mwh !== null && (
                      <span className="map-book-net" data-figure="book-net-gbp-mwh">
                        {" "}{formatMeasure("unit_value", path.net_gbp_mwh, { unit: "GBP/MWh" })}{path.simulated ? <small> sim</small> : null}
                      </span>
                    )}
                  </strong>
                  <small>{reachableLine(path, t)}</small>
                </button>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}

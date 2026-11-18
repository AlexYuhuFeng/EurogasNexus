import type { BookOpportunityPathDTO, BookRelevanceDTO } from "@/api/client";
import { opportunityLabel, reachableLine, reasonLine, type Translate } from "@/app/mapBookRelevance";

/** One opportunity's card: the core's claim and figures, the path it runs along. */
export function OpportunityCard({
  item,
  t,
  onClose,
}: {
  item: BookOpportunityPathDTO;
  t: Translate;
  onClose: () => void;
}) {
  return (
    <aside className="map-detail-panel map-opportunity-card" aria-label={t("map.book.opportunity")}>
      <button type="button" className="map-detail-close link-button" onClick={onClose} aria-label={t("map.detail.close")}>×</button>
      <header className="map-detail-header">
        <h3>{item.claim}</h3>
        <div className="map-detail-roles">
          <span className="map-role is-own">{t(`map.book.opportunity_state.${item.state}`)}</span>
          <span className="map-role is-neutral">{item.from_hub} → {item.to_hub}</span>
          {item.simulated && <span className="map-role is-watch">{t("map.detail.simulated")}</span>}
        </div>
      </header>
      <p className="map-opportunity-headline" data-figure="opportunity-headline">{opportunityLabel(item)}</p>
      <p className="muted">{t("map.book.opportunity_period", { period: item.period })}</p>
      <p className="muted">{t("map.book.opportunity_via", { via: item.via.join(", ") })}</p>
      {item.route_stated === false && <p className="muted">{t("map.book.route_not_stated")}</p>}
      <a
        className="map-detail-link"
        href={`?mode=deals&task=opportunities&opportunity=${encodeURIComponent(item.opportunity_id)}`}
        onClick={(event) => {
          // In-app navigation to Deals → Opportunities (CP-14) on this opportunity.
          event.preventDefault();
          window.history.pushState({}, "", `?mode=deals&task=opportunities&opportunity=${encodeURIComponent(item.opportunity_id)}`);
          window.dispatchEvent(new PopStateEvent("popstate"));
        }}
      >
        {t("map.book.open_in_deals")}
      </a>
      <footer className="map-detail-footer muted">{t("map.book.opportunity_core")}</footer>
    </aside>
  );
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
}: {
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
      <section aria-labelledby="map-book-opportunities-title">
        <h3 id="map-book-opportunities-title">{t("map.book.opportunities_title")}</h3>
        {(relevance.opportunities ?? []).length === 0 ? (
          <p className="muted">{t("map.book.opportunities_empty")}</p>
        ) : (
          <ul className="map-book-rows">
            {relevance.opportunities.map((item) => (
              <li key={item.opportunity_id}>
                <button type="button" className="map-book-row" onClick={() => onSelectOpportunity(item.opportunity_id)}>
                  <strong>
                    {item.from_hub} → {item.to_hub}{" "}
                    <span className="map-book-net">{opportunityLabel(item)}</span>
                  </strong>
                  <small>{t(`map.book.opportunity_state.${item.state}`)} · {item.claim}</small>
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
                        {" "}{path.net_gbp_mwh.toFixed(2)} GBP/MWh{path.simulated ? <small> sim</small> : null}
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

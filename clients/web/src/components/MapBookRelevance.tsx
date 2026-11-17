import type { BookRelevanceDTO } from "@/api/client";
import { reachableLine, reasonLine, type Translate } from "@/app/mapBookRelevance";

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
}: {
  relevance: BookRelevanceDTO | null | undefined;
  t: Translate;
  /** A hub, by its node id. */
  onSelectHub: (hubNodeId: string) => void;
  onSelectPlace: (refId: string) => void;
}) {
  if (!relevance) return null;
  const places = relevance.ours.filter((item) => item.kind !== "cargo");
  return (
    <div className="map-book-relevance">
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
                  <small>{item.reasons.map((reason) => reasonLine(reason, t)).join(" · ")}</small>
                </button>
              </li>
            ))}
          </ul>
        )}
      </section>
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

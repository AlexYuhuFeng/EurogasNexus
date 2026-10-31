import { useId, useMemo, useState } from "react";
import { findPlaces, type MapFinderPlace } from "@/app/mapFinder";

export type { MapFinderPlace };

type Translate = (key: string) => string;

/**
 * "Where is ...?" for the map: type a hub, terminal, field or vessel and the map flies there.
 * A combobox in the ARIA sense: arrows move, Enter picks, Escape clears.
 */
export function MapFinder({ places, onPick, t }: { places: MapFinderPlace[]; onPick: (place: MapFinderPlace) => void; t: Translate }) {
  const [query, setQuery] = useState("");
  const [active, setActive] = useState(0);
  const listId = useId();
  const matches = useMemo(() => findPlaces(places, query), [places, query]);
  const pick = (place: MapFinderPlace | undefined) => {
    if (!place) return;
    onPick(place);
    setQuery("");
    setActive(0);
  };

  return (
    <div className="map-finder">
      <input
        type="search"
        role="combobox"
        aria-expanded={matches.length > 0}
        aria-controls={listId}
        aria-activedescendant={matches[active] ? `${listId}-${active}` : undefined}
        aria-label={t("map.find.label")}
        placeholder={t("map.find.placeholder")}
        value={query}
        onChange={(event) => {
          setQuery(event.target.value);
          setActive(0);
        }}
        onKeyDown={(event) => {
          if (event.key === "ArrowDown") {
            event.preventDefault();
            setActive((index) => Math.min(index + 1, Math.max(matches.length - 1, 0)));
          } else if (event.key === "ArrowUp") {
            event.preventDefault();
            setActive((index) => Math.max(index - 1, 0));
          } else if (event.key === "Enter") {
            event.preventDefault();
            pick(matches[active]);
          } else if (event.key === "Escape") {
            setQuery("");
          }
        }}
      />
      {query.trim() && (
        <ul id={listId} role="listbox" className="map-finder-results">
          {matches.length === 0 && <li className="is-empty">{t("map.find.no_match")}</li>}
          {matches.map((place, index) => (
            <li
              key={`${place.kind}-${place.id}`}
              id={`${listId}-${index}`}
              role="option"
              aria-selected={index === active}
              onMouseDown={(event) => {
                event.preventDefault();
                pick(place);
              }}
            >
              <span>{place.name}</span>
              <small>{place.kind}</small>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

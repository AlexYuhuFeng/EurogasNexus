import { useCallback, useEffect, useRef, useState } from "react";

import { api } from "@/api/client";
import { PanelHeader } from "@/components/ui";
import { describeFailure, presentError } from "@/app/experience/errorPresentation";
import {
  declaredCapacityCounts,
  facilityCountryOptions,
  facilityRows,
  facilityTypeKey,
  facilityTypeOptions,
  marketHubRows,
  type FacilityRow,
  type MarketHubRow,
} from "@/app/model/referenceNetworkModel";
import {
  readMayBeTruncated,
  readState,
  type ReadState,
} from "@/app/model/readPosture";

type Translate = (key: string) => string;

interface ReferenceNetworkCatalogueProps {
  t: Translate;
}

const UNREAD: ReadState = { posture: "not-read", missingInputs: [], source: null };

/**
 * The reference-network catalogue (slice D of the D3 decision).
 *
 * `GET /api/reference-network/facilities` and `GET /api/reference-network/market-hubs` declare the
 * register the map's topology is drawn against, and neither had a consumer. The map draws what it
 * can place; this is the list behind those placements - every facility with its declared kind,
 * country and capacity, and every market hub the deployment recognises - including the rows the
 * map does not draw at all.
 *
 * Four things it refuses to do:
 *
 * - an unconfigured runtime database is not an empty register. The routes answer with an empty list
 *   plus `missing_inputs`, so the panel says the read did not happen and names what it lacked,
 *   instead of rendering "0 facilities";
 * - a facility whose capacity is not declared shows as undeclared, never as zero, and the panel
 *   counts the two;
 * - a bound is not a total. The read asks for the route's own maximum (2,000 rows) and the panel
 *   says so when it comes back full, rather than implying the list is everything;
 * - the filters are the route's, not a local sieve over part of the data: choosing a type or a
 *   country re-reads through the parameters the route declares.
 */
export function ReferenceNetworkCatalogue({ t }: ReferenceNetworkCatalogueProps) {
  const [facilities, setFacilities] = useState<FacilityRow[]>([]);
  // The unfiltered read, kept for the filter options and for the count the filters narrow.
  const [declaredFacilities, setDeclaredFacilities] = useState<FacilityRow[]>([]);
  const [hubs, setHubs] = useState<MarketHubRow[]>([]);
  const [facilityRead, setFacilityRead] = useState<ReadState>(UNREAD);
  const [hubRead, setHubRead] = useState<ReadState>(UNREAD);
  const [facilityType, setFacilityType] = useState("all");
  const [country, setCountry] = useState("all");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<unknown>(null);
  const failure = error ? presentError(t, describeFailure(error)) : null;
  const firstFilterRead = useRef(true);

  useEffect(() => {
    let active = true;
    void Promise.all([api.facilities(), api.marketHubs()])
      .then(([facilityResponse, hubResponse]) => {
        if (!active) return;
        const rows = facilityRows(facilityResponse.data);
        setFacilities(rows);
        setDeclaredFacilities(rows);
        setFacilityRead(readState(facilityResponse.meta));
        setHubs(marketHubRows(hubResponse.data));
        setHubRead(readState(hubResponse.meta));
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

  const loadFilteredFacilities = useCallback(async () => {
    setError(null);
    try {
      const response = await api.facilities({
        facility_type: facilityType === "all" ? undefined : facilityType,
        country: country === "all" ? undefined : country,
      });
      setFacilities(facilityRows(response.data));
      setFacilityRead(readState(response.meta));
    } catch (reason) {
      setError(reason);
    }
  }, [country, facilityType]);

  useEffect(() => {
    // The mount read already asked for the unfiltered list, so the first run of this effect is the
    // one that would repeat it.
    if (firstFilterRead.current) {
      firstFilterRead.current = false;
      return;
    }
    void loadFilteredFacilities();
  }, [loadFilteredFacilities]);

  const types = facilityTypeOptions(declaredFacilities);
  const countries = facilityCountryOptions(declaredFacilities);
  const capacity = declaredCapacityCounts(facilities);
  const filtered = facilityType !== "all" || country !== "all";

  return (
    <section className="workspace-panel span-3 reference-network-panel" aria-label={t("network.reference.title")}>
      <PanelHeader
        title={t("network.reference.title")}
        meta={facilityRead.source ?? t("status.unknown")}
      />
      <p className="panel-copy">{t("network.reference.note")}</p>
      {/* This panel's own read, named as such: the workspace is not loading because one panel is. */}
      {loading && <p className="muted">{t("network.reference.loading")}</p>}
      {failure && (
        <div className="alert">
          <strong>{failure.title}</strong>
          <p>{failure.action}</p>
        </div>
      )}

      {facilityRead.posture === "runtime-db-not-configured" ? (
        <div className="reference-network-unavailable">
          <strong>{t("network.reference.not_configured")}</strong>
          <p>
            {t("network.reference.missing_inputs")}:{" "}
            {facilityRead.missingInputs.join(", ") || t("data.unavailable")}
          </p>
        </div>
      ) : (
        <>
          <div className="reference-network-filters">
            <label className="field-label" htmlFor="reference-facility-type">
              {t("network.reference.type")}
            </label>
            <select
              id="reference-facility-type"
              value={facilityType}
              onChange={(event) => setFacilityType(event.target.value)}
            >
              <option value="all">{t("network.reference.all_types")}</option>
              {types.map((value) => (
                <option key={value} value={value}>
                  {t(facilityTypeKey(value) ?? value)}
                </option>
              ))}
            </select>
            <label className="field-label" htmlFor="reference-facility-country">
              {t("panel.country")}
            </label>
            <select
              id="reference-facility-country"
              value={country}
              onChange={(event) => setCountry(event.target.value)}
            >
              <option value="all">{t("capacity.all_countries")}</option>
              {countries.map((value) => (
                <option key={value} value={value}>
                  {value}
                </option>
              ))}
            </select>
            <span className="muted">
              {filtered
                ? `${facilities.length} / ${declaredFacilities.length} ${t("network.reference.facilities")}`
                : `${declaredFacilities.length} ${t("network.reference.facilities")}`}
            </span>
          </div>

          {facilities.length === 0 ? (
            <p className="muted">
              {filtered ? t("network.reference.no_match") : t("network.reference.no_facilities")}
            </p>
          ) : (
            <div className="research-table data-table" tabIndex={0}>
              <div className="data-table-row header five">
                <span>{t("network.reference.name")}</span>
                <span>{t("network.reference.type")}</span>
                <span>{t("panel.country")}</span>
                <span>{t("network.reference.capacity")}</span>
                <span>{t("network.reference.source")}</span>
              </div>
              {facilities.map((facility) => (
                <div key={facility.id} className="data-table-row five">
                  <strong>{facility.name}</strong>
                  <span className="status-badge">
                    {t(facilityTypeKey(facility.facilityType) ?? facility.facilityType)}
                  </span>
                  <span>{facility.country}</span>
                  <span>
                    {facility.capacityBoeD === null
                      ? t("network.reference.capacity_undeclared")
                      : `${facility.capacityBoeD.toLocaleString()} boe/d`}
                  </span>
                  <span className="muted">{facility.source ?? t("data.unavailable")}</span>
                </div>
              ))}
            </div>
          )}

          {facilities.length > 0 && (
            <p className="muted">
              {t("network.reference.capacity_declared")}: {capacity.declared} ·{" "}
              {t("network.reference.capacity_undeclared_count")}: {capacity.undeclared}
            </p>
          )}
          {readMayBeTruncated(facilities.length) && (
            <p className="muted">{t("network.reference.bounded")}</p>
          )}

          <div className="reference-network-hubs">
            <PanelHeader
              title={t("network.reference.hubs")}
              meta={hubRead.source ?? t("data.unavailable")}
            />
            {hubRead.posture === "runtime-db-not-configured" ? (
              <p className="muted">{t("network.reference.not_configured")}</p>
            ) : hubs.length === 0 ? (
              <p className="muted">{t("network.reference.no_hubs")}</p>
            ) : (
              <div className="research-table data-table" tabIndex={0}>
                <div className="data-table-row header four">
                  <span>{t("network.reference.hub")}</span>
                  <span>{t("network.reference.hub_code")}</span>
                  <span>{t("panel.country")}</span>
                  <span>{t("network.reference.hub_description")}</span>
                </div>
                {hubs.map((hub) => (
                  <div key={hub.id} className="data-table-row four">
                    <strong>{hub.name}</strong>
                    <span className="status-badge">{hub.hubCode}</span>
                    <span>{hub.country}</span>
                    <span className="muted">{hub.description ?? t("data.unavailable")}</span>
                  </div>
                ))}
              </div>
            )}
          </div>
        </>
      )}
    </section>
  );
}

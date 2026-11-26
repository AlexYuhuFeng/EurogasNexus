/**
 * Every country's season against its own history as small multiples (design basis 2, D.2:
 * "one panel per country, small multiples, shared axis"). One scale for all panels by default
 * (stated, with "independent scales" as the toggle); each panel carries its headline and its own
 * readout; ordered as the server orders them (by size); "Show all" past eight. A narrow
 * container gets the list form with sparklines. Used by Research → Fundamentals for storage
 * fill and LNG send-out alike.
 */
import { useMemo } from "react";

import { commonLabel, seasonChart, type SeasonEntity } from "@/app/model/storageByCountry";
import { SmallMultiples, type MultipleCell } from "@/components/ui/charts";
import { historyLabel } from "@/app/model/historyLabel";
import { placeName } from "@/app/model/placeName";

type Translate = (key: string, options?: Record<string, unknown>) => string;

export interface MultipleEntity extends SeasonEntity {
  code: string;
  name: string;
}

export function CountryMultiples<E extends MultipleEntity>({
  id,
  title,
  entities,
  unit,
  headline,
  spark,
  onSelect,
  selected,
  t,
}: {
  id: string;
  title: string;
  entities: readonly E[];
  unit: string;
  headline: (entity: E) => string;
  spark: (entity: E) => { values: (number | null)[]; days: string[] };
  onSelect?: (code: string) => void;
  selected?: string | null;
  t: Translate;
}) {
  // The history most panels share is said once above the grid; a panel names its own only
  // where it differs ("3 prior years held").
  const common = useMemo(() => commonLabel(entities.map((entity) => historyLabel(entity.history, t))), [entities]);
  const cells = useMemo<MultipleCell[]>(
    () =>
      entities.flatMap((entity) => {
        const chart = seasonChart(
          entity,
          {
            lastYear: (year) => t("storage_panel.last_year", { year }),
            thisYear: (year) => year,
            mean: (count) => t("chart.history.mean", { count }),
            history: (history) => historyLabel(history, t),
            range: (years) => t("chart.history.range", { count: years.length, first: years[0] ?? "", last: years[years.length - 1] ?? "" }),
            target: (pct) => t("storage_panel.target_rule", { pct }),
            xTitle: t("storage_panel.day_of_gas_year"),
          },
          entity.season?.band ? t("storage_panel.compare_mean", { count: entity.season.band.years.length }) : t("storage_panel.compare_last_year"),
          unit,
        );
        if (!chart) return [];
        const points = spark(entity);
        return [{
          id: entity.code,
          title: placeName(entity, t),
          headline: historyLabel(entity.history, t) === common ? headline(entity) : `${headline(entity)} · ${historyLabel(entity.history, t)}`,
          data: chart.data,
          simulated: entity.simulated,
          compare: chart.compare,
          spark: { values: points.values, days: points.days, unit, decimals: 1 },
          onSelect: onSelect ? () => onSelect(entity.code) : undefined,
          selected: selected === entity.code,
        }];
      }),
    [common, entities, headline, onSelect, selected, spark, t, unit],
  );
  if (cells.length === 0) return null;
  return <SmallMultiples id={id} title={title} subtitle={common ?? undefined} cells={cells} t={t} height={120} />;
}

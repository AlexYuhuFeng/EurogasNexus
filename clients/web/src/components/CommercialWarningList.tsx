import { useMemo } from "react";

import { displayTime } from "@/app/time/displayTime";
import type { CommercialDiagnosticItem } from "@/app/model/commercialWarnings";
import { lineageNames, resourceName, type LineageLookup } from "@/app/model/lineageNames";
import { warningLabel } from "@/app/warningLabel";
import { enumWordsIn } from "@/app/model/enumLabels";
import { useApiStore } from "@/stores/api";

type Translate = (key: string, options?: Record<string, unknown>) => string;

/** Names this page already holds for resources, contracts and routes (no extra request). */
function useLineageLookup(): LineageLookup {
  const pool = useApiStore((state) => state.resourcePoolOptions);
  const contracts = useApiStore((state) => state.upstreamContracts);
  const routes = useApiStore((state) => state.routeCandidates);
  return useMemo(() => {
    const resources = new Map<string, string>();
    for (const contract of contracts ?? []) resources.set(contract.contract_id, contract.contract_name);
    for (const resource of pool?.portfolio_resources ?? []) resources.set(resource.resource_id, resource.resource_name);
    const routeNames = new Map<string, string>();
    for (const route of routes ?? []) routeNames.set(route.route_id, route.route_name);
    return { resources, routes: routeNames };
  }, [pool, contracts, routes]);
}

/** A warning's own text with any resource id it quotes replaced by the resource's name. */
function withNames(text: string, lookup: LineageLookup): string {
  let result = text;
  for (const [id, name] of lookup.resources ?? []) {
    if (id && result.includes(id)) result = result.split(id).join(name);
  }
  return result;
}

interface CommercialWarningListProps {
  items: readonly CommercialDiagnosticItem[];
  t: Translate;
  limit?: number;
  emptyLabel?: string;
}

function formatUtc(value: string | null): string | null {
  if (!value) return null;
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return displayTime(value, value);
}

function label(item: CommercialDiagnosticItem, t: Translate, lookup: LineageLookup): string {
  return enumWordsIn(withNames(item.code ? warningLabel(item.raw, t) : item.detail, lookup));
}

export function CommercialWarningList({
  items,
  t,
  limit = 12,
  emptyLabel,
}: CommercialWarningListProps) {
  const lookup = useLineageLookup();
  if (items.length === 0) {
    return emptyLabel ? <p className="muted">{emptyLabel}</p> : null;
  }

  return (
    <ul className="commercial-diagnostic-list">
      {items.slice(0, limit).map((item, index) => {
        const observedAt = formatUtc(item.observedAtUtc);
        return (
          <li key={`${item.level}-${item.raw}-${item.affectedResourceId ?? ""}-${item.affectedRouteId ?? ""}-${index}`}>
            <div className="commercial-diagnostic-heading">
              <span className={`commercial-diagnostic-level level-${item.level}`}>
                {t(`commercial.warning.level.${item.level}`)}
              </span>
              {/* The code stays for support (tooltip and data attribute), never in the copy. */}
              <strong title={item.code ?? undefined} data-warning-code={item.code ?? undefined}>{label(item, t, lookup)}</strong>
            </div>
            <div className="commercial-diagnostic-evidence">
              <span>
                {t("commercial.warning.origin")}:{" "}
                {item.origins.map((origin) => t(`commercial.warning.origin.${origin}`)).join(" / ")}
              </span>
              {item.affectedResourceId && (
                <span title={item.affectedResourceId}>{t("commercial.warning.resource")}: {resourceName(item.affectedResourceId, lookup)}</span>
              )}
              {item.affectedRouteId && <span>{t("commercial.warning.route")}: {item.affectedRouteId}</span>}
              {item.sourceSystem && (
                <span>
                  {t("commercial.warning.source")}: {item.sourceSystem}
                  {item.simulated ? ` · ${t("market.simulated_source")}` : ""}
                </span>
              )}
              {item.freshness && <span>{t("commercial.warning.freshness")}: {item.freshness}</span>}
              {observedAt && <span>{t("commercial.warning.observed")}: {observedAt}</span>}
              {item.sourceReference && <span>{t("commercial.warning.source_ref")}: {item.sourceReference}</span>}
              {item.sourceRefs.length > 0 && <Lineage refs={item.sourceRefs} lookup={lookup} t={t} />}
            </div>
          </li>
        );
      })}
      {items.length > limit && (
        <li className="commercial-diagnostic-more">
          {t("commercial.warning.more")}: {items.length - limit}
        </li>
      )}
    </ul>
  );
}

/**
 * What a warning rests on, by name ("Haldor supply (Easington) contract · TTF MA price"); the
 * record identifiers are one disclosure away, selectable and copyable for support.
 */
function Lineage({ refs, lookup, t }: { refs: readonly string[]; lookup: LineageLookup; t: Translate }) {
  const names = lineageNames(refs, lookup, t);
  return (
    <span className="commercial-diagnostic-lineage" data-lineage-count={names.length}>
      {t("lineage.based_on")}: {names.map((entry) => entry.name).join(" · ")}
      <details className="commercial-diagnostic-ids">
        <summary>{t("lineage.identifiers")}</summary>
        <code>{names.map((entry) => entry.ref).join("\n")}</code>
        <button
          type="button"
          className="ds-inline-link"
          onClick={(event) => {
            const button = event.currentTarget;
            void navigator.clipboard?.writeText(names.map((entry) => entry.ref).join("\n")).then(() => {
              button.textContent = t("lineage.copied");
            });
          }}
        >
          {t("lineage.copy")}
        </button>
      </details>
    </span>
  );
}

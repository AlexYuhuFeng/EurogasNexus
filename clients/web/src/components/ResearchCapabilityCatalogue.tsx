import { useEffect, useState } from "react";

import { api } from "@/api/client";
import { PanelHeader } from "@/components/ui";
import { describeFailure, presentError } from "@/app/experience/errorPresentation";
import {
  readWriteClassKey,
  researchCapabilityRows,
  sideEffectClassKey,
  type ResearchCapabilityRow,
} from "@/app/model/accessCatalogueModel";

type Translate = (key: string) => string;

interface ResearchCapabilityCatalogueProps {
  t: Translate;
}

/**
 * The research capability catalogue (slice E of the D3 decision).
 *
 * `GET /api/research/capabilities` declares what the research domain can do - resolve an entity, read
 * series metadata, read observations as of a cutoff - with the posture each one carries: whether it
 * computes or only reads, whether it is deterministic, what it may change, the permission it needs
 * and whether it returns provenance. The route had no consumer, so the declaration was invisible
 * even though it is what makes a research result reproducible: a figure can only be checked against
 * the capability that produced it.
 *
 * It reads only. Nothing here invokes anything: invocation is the capability runtime's own surface,
 * under the caller's authority, and this catalogue is the declaration those calls are made against.
 */
export function ResearchCapabilityCatalogue({ t }: ResearchCapabilityCatalogueProps) {
  const [capabilities, setCapabilities] = useState<ResearchCapabilityRow[]>([]);
  const [source, setSource] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const failure = error ? presentError(t, describeFailure(error)) : null;

  useEffect(() => {
    let active = true;
    void api
      .researchCapabilities()
      .then((response) => {
        if (!active) return;
        setCapabilities(researchCapabilityRows(response.data));
        setSource(response.meta?.source_references?.[0] ?? null);
      })
      .catch((reason) => active && setError(reason));
    return () => {
      active = false;
    };
  }, []);

  return (
    <section className="workspace-panel" aria-label={t("research.capabilities.title")}>
      <PanelHeader
        title={t("research.capabilities.title")}
        meta={
          source
            ? `${t("research.capabilities.declared_by")}: ${source}`
            : t("data.unavailable")
        }
      />
      <p className="panel-copy">{t("research.capabilities.note")}</p>
      {failure && <p className="strategy-error">{failure.title}</p>}
      {capabilities.length === 0 ? (
        <p className="muted">{t("research.capabilities.empty")}</p>
      ) : (
        <div className="data-table" tabIndex={0}>
          <div className="data-table-row header six">
            <span>{t("research.capabilities.name")}</span>
            <span>{t("research.capabilities.class")}</span>
            <span>{t("research.capabilities.determinism")}</span>
            <span>{t("research.capabilities.side_effect")}</span>
            <span>{t("research.capabilities.permission")}</span>
            <span>{t("research.capabilities.provenance")}</span>
          </div>
          {capabilities.map((capability) => (
            <div key={capability.name} className="data-table-row six">
              <strong title={capability.description}>{capability.name}</strong>
              <span className="status-badge">
                {t(readWriteClassKey(capability.readWriteClass) ?? capability.readWriteClass)}
              </span>
              <span className="status-badge">
                {capability.deterministic
                  ? t("research.capabilities.deterministic")
                  : t("research.capabilities.non_deterministic")}
              </span>
              <span className="status-badge">
                {t(sideEffectClassKey(capability.sideEffectClass) ?? capability.sideEffectClass)}
              </span>
              <span>{capability.requiredPermission}</span>
              <span>{capability.provenanceBehavior}</span>
            </div>
          ))}
        </div>
      )}
    </section>
  );
}

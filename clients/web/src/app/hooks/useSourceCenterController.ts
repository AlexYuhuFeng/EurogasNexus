import { useEffect, useMemo, useState } from "react";
import type { FormEvent } from "react";
import type { TFunction } from "i18next";
import { formatUtcTimestamp } from "@/app/model/evidencePresentation";
import type {
  CredentialProviderDTO,
  SourceCategoryPostureDTO,
  SourceSystemDTO,
} from "@/api/client";
import {
  buildSourceCategoryCounts,
  buildSourcePostureRows,
  buildSourcesByCategory,
  buildSourceStats,
  filterSourcesByCategory,
  SOURCE_CATEGORIES,
  sourceNextActionKey,
} from "@/app/index";
import {
  sourceRegistryReadSurface,
  type SourceRegistryReadFacts,
} from "@/app/model/sourceRegistryRead";
import {
  canSubmitCredential,
  credentialConnectionForProvider,
  isExternallyManagedCredential,
} from "@/app/model/credentialProviderModel";
import type { ApiState } from "@/stores/api";
import { useUrlObject } from "@/app/navigation/useUrlView";

/**
 * The registry lane's own read state, straight from the store: whether the workspace batch (or
 * its bounded retry pass) is in flight, whether a pass has committed in this session, the failure
 * recorded for the sources endpoint with its safe code, and the retry's bookkeeping. The surface
 * the controller derives from it never prints a count for a read that has not answered.
 */
export type SourceCenterRegistryReadParams = Pick<
  SourceRegistryReadFacts,
  "loading" | "committedPasses" | "error" | "errorCode"
> & {
  retryBusy: boolean;
  retryAttempts: number;
  retryLastAttemptAtUtc: string | null;
};

interface SourceCenterControllerParams {
  sources: SourceSystemDTO[];
  credentialProviders: CredentialProviderDTO[];
  sourcePostureCategories: SourceCategoryPostureDTO[] | undefined;
  saveProviderCredential: ApiState["saveProviderCredential"];
  testProviderConnection: ApiState["testProviderConnection"];
  /** The backend's own bounded connection-test aggregate for the last GIE probe. */
  credentialConnection: ApiState["credentialConnection"];
  registryRead: SourceCenterRegistryReadParams;
  /** The store's existing bounded retry path; this surface only scopes the control to itself. */
  retryFailedWorkspaceEndpoints: ApiState["retryFailedWorkspaceEndpoints"];
  language: string;
  t: TFunction;
}

function credentialProviderIdForSource(
  source: SourceSystemDTO | null | undefined,
  credentialProviders: CredentialProviderDTO[],
) {
  if (!source) return null;
  if (source.credential_provider_id) return source.credential_provider_id;
  const sourceSystem = source.source_system.toLocaleLowerCase();
  return credentialProviders.find(
    (provider) => provider.provider_id.toLocaleLowerCase() === sourceSystem,
  )?.provider_id ?? null;
}

/**
 * Development and UAT test sources (the simulated price generators, `*_Sim`). They are kept,
 * with their history and lineage, but a customer's daily source list, its counts and its
 * to-do queue are about real suppliers (#22): test sources are shown only on request.
 */
export function isTestSource(source: SourceSystemDTO): boolean {
  return /_sim$/i.test(source.source_system);
}

export function useSourceCenterController({
  sources: allSources,
  credentialProviders,
  sourcePostureCategories,
  saveProviderCredential,
  testProviderConnection,
  credentialConnection,
  registryRead,
  retryFailedWorkspaceEndpoints,
  language,
  t,
}: SourceCenterControllerParams) {
  const [credentialProvider, setCredentialProvider] = useState("");
  const [credentialLabel, setCredentialLabel] = useState("default");
  const [credentialValue, setCredentialValue] = useState("");
  const [sourceCategory, setSourceCategory] = useState("all");
  // The selected source is in the URL (#31): a link or a refresh opens that source.
  const [selectedSourceId, setSelectedSourceId] = useUrlObject("sources", "source");
  const [showTestSources, setShowTestSources] = useState(false);
  const testSourceCount = useMemo(() => allSources.filter(isTestSource).length, [allSources]);
  const sources = useMemo(
    () => (showTestSources ? allSources : allSources.filter((source) => !isTestSource(source))),
    [allSources, showTestSources],
  );

  const selectedCredentialProvider = useMemo(
    () => credentialProviders.find((provider) => provider.provider_id === credentialProvider),
    [credentialProvider, credentialProviders],
  );
  const sourceStats = useMemo(() => buildSourceStats(sources), [sources]);
  const sourcePostureRows = useMemo(
    () => buildSourcePostureRows(sources, sourcePostureCategories),
    [sourcePostureCategories, sources],
  );
  const filteredSources = useMemo(
    () => filterSourcesByCategory(sources, sourceCategory),
    [sourceCategory, sources],
  );
  const selectedSource = useMemo(
    () => sources.find((source) => source.source_id === selectedSourceId) ?? filteredSources[0] ?? sources[0] ?? null,
    [filteredSources, selectedSourceId, sources],
  );
  /**
   * A source the URL asked for that is not in the list (unknown, hidden test source, or not
   * readable for this identity). The detail falls back to the first source, and the page says
   * so instead of presenting that one as the one asked for.
   */
  const missingSourceId = useMemo(
    () => (selectedSourceId && allSources.length > 0 && !sources.some((source) => source.source_id === selectedSourceId)
      ? selectedSourceId
      : null),
    [allSources.length, selectedSourceId, sources],
  );
  const selectedSourceCredentialProvider = useMemo(() => {
    const providerId = credentialProviderIdForSource(selectedSource, credentialProviders);
    return providerId
      ? credentialProviders.find((provider) => provider.provider_id === providerId) ?? null
      : null;
  }, [credentialProviders, selectedSource]);
  const sourceCategoryCounts = useMemo(() => buildSourceCategoryCounts(sources), [sources]);
  const sourcesByCategory = useMemo(() => buildSourcesByCategory(sources), [sources]);
  const registryReadSurface = sourceRegistryReadSurface(
    {
      rowCount: sources.length,
      loading: registryRead.loading,
      committedPasses: registryRead.committedPasses,
      error: registryRead.error,
      errorCode: registryRead.errorCode,
      retry: {
        busy: registryRead.retryBusy,
        attempts: registryRead.retryAttempts,
        lastAttemptAtUtc: registryRead.retryLastAttemptAtUtc,
      },
    },
    t,
  );

  useEffect(() => {
    if (!selectedSourceCredentialProvider?.provider_id) return;
    setCredentialProvider(selectedSourceCredentialProvider.provider_id);
  }, [selectedSourceCredentialProvider?.provider_id]);

  async function submitCredential(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    // The handler enforces the same rule as the rendered control: an ineffective
    // rotation of an externally managed (env/file) key is refused even if a caller
    // submits the form directly.
    if (!canSubmitCredential(selectedCredentialProvider, credentialValue)) return;
    try {
      await saveProviderCredential(credentialProvider, credentialValue.trim(), credentialLabel || "default");
      setCredentialValue("");
    } catch {
      // Keep the write-only value in the field so the operator can retry after fixing runtime configuration.
    }
  }

  function selectSource(sourceId: string) {
    const source = sources.find((item) => item.source_id === sourceId);
    setSelectedSourceId(sourceId);
    const providerId = credentialProviderIdForSource(source, credentialProviders);
    if (providerId) setCredentialProvider(providerId);
  }

  function selectSourceCategory(category: string, nextSourceId: string | null) {
    setSourceCategory(category);
    if (nextSourceId) selectSource(nextSourceId);
  }

  function sourceLabel(prefix: string, value: string | null | undefined) {
    if (!value) return "n/a";
    const key = `${prefix}.${value}`;
    const translated = t(key);
    return translated === key ? value.replace(/_/g, " ") : translated;
  }

  function categoryProviderSummary(category: string) {
    if (category === "all") return t("sources.all_categories");
    const systems = sourcesByCategory.get(category) ?? [];
    return systems.length > 0 ? systems.join(", ") : t("sources.no_registered_feeds");
  }

  function sourceNextAction(source: SourceSystemDTO | null) {
    return t(sourceNextActionKey(source));
  }

  function formatSourceTimestamp(value: string | null | undefined) {
    return formatUtcTimestamp(value);
  }

  return {
    visibleSources: sources,
    testSourceCount,
    showTestSources,
    setShowTestSources,
    sourceCategories: SOURCE_CATEGORIES,
    sourceCategory,
    sourceCategoryCounts,
    sourceStats,
    sourcePostureRows,
    registryRead: registryReadSurface,
    filteredSources,
    selectedSource,
    missingSourceId,
    selectedCredentialProvider,
    selectedSourceCredentialProvider,
    credentialProvider,
    credentialLabel,
    credentialValue,
    // Scoped to the selected provider: a stale aggregate from a previously selected
    // provider is never surfaced as the current provider's connection.
    credentialConnection: credentialConnectionForProvider(
      credentialConnection,
      selectedCredentialProvider?.provider_id,
    ),
    // An active env/file key is operator-managed: the entry form must not offer an
    // ineffective rotation for it.
    credentialEntryReadonly: isExternallyManagedCredential(selectedCredentialProvider),
    setCredentialProvider,
    setCredentialLabel,
    setCredentialValue,
    selectSourceCategory,
    selectSource,
    submitCredential,
    testProviderConnection: () => {
      if (credentialProvider) void testProviderConnection(credentialProvider);
    },
    retryRegistryRead: () => {
      void retryFailedWorkspaceEndpoints();
    },
    sourceLabel,
    categoryProviderSummary,
    sourceNextAction,
    formatSourceTimestamp,
  };
}

import { useEffect, useMemo, useState } from "react";
import type { FormEvent } from "react";
import type { TFunction } from "i18next";
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
import type { ApiState } from "@/stores/api";

interface SourceCenterControllerParams {
  sources: SourceSystemDTO[];
  credentialProviders: CredentialProviderDTO[];
  sourcePostureCategories: SourceCategoryPostureDTO[] | undefined;
  saveProviderCredential: ApiState["saveProviderCredential"];
  testProviderConnection: ApiState["testProviderConnection"];
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

export function useSourceCenterController({
  sources,
  credentialProviders,
  sourcePostureCategories,
  saveProviderCredential,
  testProviderConnection,
  language,
  t,
}: SourceCenterControllerParams) {
  const [credentialProvider, setCredentialProvider] = useState("");
  const [credentialLabel, setCredentialLabel] = useState("default");
  const [credentialValue, setCredentialValue] = useState("");
  const [sourceCategory, setSourceCategory] = useState("all");
  const [selectedSourceId, setSelectedSourceId] = useState<string | null>(null);

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
  const selectedSourceCredentialProvider = useMemo(() => {
    const providerId = credentialProviderIdForSource(selectedSource, credentialProviders);
    return providerId
      ? credentialProviders.find((provider) => provider.provider_id === providerId) ?? null
      : null;
  }, [credentialProviders, selectedSource]);
  const sourceCategoryCounts = useMemo(() => buildSourceCategoryCounts(sources), [sources]);
  const sourcesByCategory = useMemo(() => buildSourcesByCategory(sources), [sources]);

  useEffect(() => {
    if (!selectedSourceCredentialProvider?.provider_id) return;
    setCredentialProvider(selectedSourceCredentialProvider.provider_id);
  }, [selectedSourceCredentialProvider?.provider_id]);

  async function submitCredential(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedCredentialProvider?.credential_required || !credentialValue.trim()) return;
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
    if (!value) return "n/a";
    return new Intl.DateTimeFormat(language, {
      month: "short",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
    }).format(new Date(value));
  }

  return {
    sourceCategories: SOURCE_CATEGORIES,
    sourceCategory,
    sourceCategoryCounts,
    sourceStats,
    sourcePostureRows,
    filteredSources,
    selectedSource,
    selectedCredentialProvider,
    selectedSourceCredentialProvider,
    credentialProvider,
    credentialLabel,
    credentialValue,
    setCredentialProvider,
    setCredentialLabel,
    setCredentialValue,
    selectSourceCategory,
    selectSource,
    submitCredential,
    testProviderConnection: () => {
      if (credentialProvider) void testProviderConnection(credentialProvider);
    },
    sourceLabel,
    categoryProviderSummary,
    sourceNextAction,
    formatSourceTimestamp,
  };
}

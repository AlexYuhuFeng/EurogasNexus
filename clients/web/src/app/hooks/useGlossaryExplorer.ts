import { useEffect, useMemo, useState } from "react";
import type { GlossaryTermDTO } from "@/api/client";
import type { ApiState } from "@/stores/api";
import { gasDayReadWindow, resolveGlossaryTerm } from "@/app/model/glossaryEntry";

interface GlossaryExplorerParams {
  glossaryTerms: GlossaryTermDTO[];
  fetchGlossaryContext: ApiState["fetchGlossaryContext"];
  language: string;
  /** The glossary is the page on screen: only then is an entry's context read. */
  active: boolean;
  /** Bumped on every navigation, so a link to a term opens it while the glossary is showing. */
  locationRevision: number;
  /** Whether the entry is an object with figures; only those read their context. */
  needsContext: (term: GlossaryTermDTO) => boolean;
}

function termFromLocation(): string | null {
  try {
    return new URLSearchParams(window.location.search).get("term");
  } catch {
    return null;
  }
}

export function useGlossaryExplorer({
  glossaryTerms,
  fetchGlossaryContext,
  language,
  active,
  locationRevision,
  needsContext,
}: GlossaryExplorerParams) {
  const [query, setQuery] = useState("");
  const [category, setCategory] = useState("all");
  // A link (or a palette result) names the term to open: ?workspace=glossary&term=NBP. The term,
  // an alias or the term id, in any case.
  const [selectedTerm, setSelectedTerm] = useState<string | null>(termFromLocation);
  // The gas day an entity's figures are for; empty is the latest held.
  const [gasDay, setGasDay] = useState("");
  const glossaryLanguage = language.startsWith("zh") ? "zh-CN" : "en";

  useEffect(() => {
    if (!active) return;
    const linked = termFromLocation();
    if (linked) setSelectedTerm(linked);
  }, [active, locationRevision]);

  const categories = useMemo(
    () => Array.from(new Set(glossaryTerms.map((term) => term.category))).sort(),
    [glossaryTerms],
  );

  const terms = useMemo(() => {
    const trimmed = query.trim();
    const normalizedQuery = trimmed.toLowerCase();
    return glossaryTerms
      .filter((term) => category === "all" || term.category === category)
      .filter((term) => {
        if (!normalizedQuery) return true;
        return (
          term.term.toLowerCase().includes(normalizedQuery) ||
          term.category.toLowerCase().includes(normalizedQuery) ||
          term.definition_en.toLowerCase().includes(normalizedQuery) ||
          term.definition_zh_cn.includes(trimmed) ||
          term.aliases.some((alias) => alias.toLowerCase().includes(normalizedQuery))
        );
      })
      .slice(0, 40);
  }, [category, glossaryTerms, query]);

  const selectedTermRecord = useMemo(
    () => resolveGlossaryTerm(selectedTerm, glossaryTerms) ?? terms[0] ?? glossaryTerms[0] ?? null,
    [glossaryTerms, selectedTerm, terms],
  );

  const contextTerm = selectedTermRecord && needsContext(selectedTermRecord) ? selectedTermRecord.term : null;
  useEffect(() => {
    if (!active || !contextTerm) return;
    void fetchGlossaryContext(contextTerm, { lang: glossaryLanguage, ...gasDayReadWindow(gasDay) });
  }, [active, contextTerm, fetchGlossaryContext, gasDay, glossaryLanguage]);

  function openTerm(name: string) {
    const record = resolveGlossaryTerm(name, glossaryTerms);
    const canonical = record?.term ?? name;
    setSelectedTerm(canonical);
    // The address names the open entry, so it can be copied, shared and reopened.
    try {
      const url = new URL(window.location.href);
      if (url.searchParams.get("term") !== canonical) {
        url.searchParams.set("term", canonical);
        window.history.replaceState(window.history.state, "", url);
      }
    } catch {
      // No address to keep; the selection still holds on the page.
    }
  }

  return {
    query,
    category,
    selectedTerm,
    gasDay,
    categories,
    terms,
    selectedTermRecord,
    setQuery,
    setCategory,
    setGasDay,
    selectTerm: (term: { term: string }) => openTerm(term.term),
    openTerm,
  };
}

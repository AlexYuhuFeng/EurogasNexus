import { useMemo, useState } from "react";
import type { GlossaryTermDTO } from "@/api/client";
import type { ApiState } from "@/stores/api";

export const GLOSSARY_SHORTCUT_TERMS = ["TTF", "NBP", "ICE OCM", "Entry Capacity"];

interface GlossaryExplorerParams {
  glossaryTerms: GlossaryTermDTO[];
  fetchGlossaryContext: ApiState["fetchGlossaryContext"];
  language: string;
}

export function formatContextValue(value: unknown) {
  if (value === null || value === undefined || value === "") return "n/a";
  if (typeof value === "number") return Number.isInteger(value) ? value.toLocaleString() : value.toFixed(2);
  if (Array.isArray(value)) return value.join(", ");
  return String(value);
}

export function useGlossaryExplorer({
  glossaryTerms,
  fetchGlossaryContext,
  language,
}: GlossaryExplorerParams) {
  const [query, setQuery] = useState("");
  const [category, setCategory] = useState("all");
  const [selectedTerm, setSelectedTerm] = useState<string | null>(null);
  const [durationStart, setDurationStart] = useState("2026-05-31T06:00");
  const [durationEnd, setDurationEnd] = useState("2026-06-01T06:00");
  const glossaryLanguage = language.startsWith("zh") ? "zh-CN" : "en";

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
    () =>
      terms.find((term) => term.term === selectedTerm) ??
      glossaryTerms.find((term) => term.term === selectedTerm) ??
      terms[0] ??
      glossaryTerms[0] ??
      null,
    [glossaryTerms, selectedTerm, terms],
  );

  function contextParams() {
    return {
      lang: glossaryLanguage,
      duration_start_utc: durationStart ? new Date(durationStart).toISOString() : undefined,
      duration_end_utc: durationEnd ? new Date(durationEnd).toISOString() : undefined,
    };
  }

  function openContext(term: string) {
    setSelectedTerm(term);
    void fetchGlossaryContext(term, contextParams());
  }

  function selectTerm(term: { term: string }) {
    openContext(term.term);
  }

  return {
    query,
    category,
    selectedTerm,
    durationStart,
    durationEnd,
    categories,
    terms,
    selectedTermRecord,
    shortcutTerms: GLOSSARY_SHORTCUT_TERMS,
    setQuery,
    setCategory,
    setDurationStart,
    setDurationEnd,
    selectTerm,
    openContext,
    formatContextValue,
  };
}

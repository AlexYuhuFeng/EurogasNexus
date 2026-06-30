import type { GlossaryContextDTO, GlossaryTermDTO } from "@/api/client";

type Translate = (key: string) => string;

interface GlossaryWikiProps {
  terms: GlossaryTermDTO[];
  context: GlossaryContextDTO | null;
  selectedTerm: GlossaryTermDTO | null;
  categories: string[];
  activeCategory: string;
  query: string;
  language: string;
  durationStart: string;
  durationEnd: string;
  shortcutTerms: string[];
  loading: boolean;
  t: Translate;
  onCategoryChange: (category: string) => void;
  onQueryChange: (query: string) => void;
  onDurationStartChange: (value: string) => void;
  onDurationEndChange: (value: string) => void;
  onSelectTerm: (term: GlossaryTermDTO) => void;
  onOpenContext: (term: string) => void;
  formatContextValue: (value: unknown) => string;
}

function localizedDefinition(term: GlossaryTermDTO, language: string): string {
  return language.startsWith("zh") ? term.definition_zh_cn : term.definition_en;
}

function contextMatchesTerm(context: GlossaryContextDTO | null, term: GlossaryTermDTO | null): boolean {
  if (!context || !term) return false;
  return context.term.toLowerCase() === term.term.toLowerCase();
}

const contextLabelKeys = [
  "label",
  "name",
  "term",
  "title",
  "entity_name",
  "point_name",
  "route_name",
  "contract_name",
  "source_reference",
  "source_system",
  "venue",
  "hub",
  "country",
  "id",
  "entity_id",
  "point_id",
  "section_id",
];

const contextValueKeys = [
  "value",
  "amount",
  "count",
  "status",
  "context_type",
  "capacity_mcm_d",
  "capacity_mwh_per_day",
  "inventory_twh",
  "price",
  "price_gbp_mwh",
  "quantity_mwh",
  "available_quantity_mwh_per_day",
];

function objectRecord(value: unknown): Record<string, unknown> | null {
  return value && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null;
}

function readablePrimitive(value: unknown): string | null {
  if (typeof value === "string") {
    const trimmed = value.trim();
    return trimmed.length > 0 ? trimmed : null;
  }
  if (typeof value === "number" && Number.isFinite(value)) return String(value);
  if (typeof value === "boolean") return value ? "true" : "false";
  return null;
}

function firstRecordText(record: Record<string, unknown>, keys: string[]): string | null {
  for (const key of keys) {
    const value = readablePrimitive(record[key]);
    if (value) return value;
  }
  return null;
}

function displayContextObject(value: unknown, formatContextValue: (value: unknown) => string): string {
  if (value === null || value === undefined || value === "") return "n/a";
  if (Array.isArray(value)) {
    const values = value
      .map((item) => displayContextObject(item, formatContextValue))
      .filter((item) => item !== "n/a");
    return values.length > 0 ? values.join(" / ") : "n/a";
  }

  const record = objectRecord(value);
  if (record) {
    const label = firstRecordText(record, contextLabelKeys);
    const valueText = firstRecordText(record, contextValueKeys);
    const unit = firstRecordText(record, ["unit", "currency", "original_unit"]);
    if (label && valueText && label !== valueText) return unit ? `${label}: ${valueText} ${unit}` : `${label}: ${valueText}`;
    if (label) return label;
    if (valueText) return unit ? `${valueText} ${unit}` : valueText;

    const compactEntries = Object.entries(record)
      .map(([key, item]) => {
        const text = readablePrimitive(item);
        return text ? `${key.replace(/_/g, " ")}: ${text}` : null;
      })
      .filter((item): item is string => Boolean(item))
      .slice(0, 3);
    return compactEntries.length > 0 ? compactEntries.join(" / ") : "record";
  }

  return formatContextValue(value);
}

function shortValue(value: unknown, formatContextValue: (value: unknown) => string): string {
  const formatted = displayContextObject(value, formatContextValue);
  return formatted.length > 96 ? `${formatted.slice(0, 93)}...` : formatted;
}

export function GlossaryWiki({
  terms,
  context,
  selectedTerm,
  categories,
  activeCategory,
  query,
  language,
  durationStart,
  durationEnd,
  shortcutTerms,
  loading,
  t,
  onCategoryChange,
  onQueryChange,
  onDurationStartChange,
  onDurationEndChange,
  onSelectTerm,
  onOpenContext,
  formatContextValue,
}: GlossaryWikiProps) {
  const matchingContext = contextMatchesTerm(context, selectedTerm) ? context : null;
  const selectedDefinition = selectedTerm ? localizedDefinition(selectedTerm, language) : t("status.loading");

  return (
    <div className="workspace-grid glossary-page glossary-wiki-shell glossary-codex-shell">
      <section className="workspace-panel glossary-left-rail glossary-term-list" aria-label={t("panel.glossary")}>
        <div className="panel-title-row">
          <div>
            <span className="eyebrow">{t("glossary.term_count")}</span>
            <h3>{t("panel.glossary")}</h3>
          </div>
          <strong>{terms.length}</strong>
        </div>
        <div className="glossary-list-toolbar">
          <input
            value={query}
            onChange={(event) => onQueryChange(event.target.value)}
            placeholder={t("glossary.search")}
          />
          <span className="status-badge">{loading ? t("status.loading") : t("data.runtime")}</span>
        </div>
        <div className="glossary-category-tabs" aria-label={t("glossary.category")}>
          <button
            type="button"
            className={activeCategory === "all" ? "active" : ""}
            onClick={() => onCategoryChange("all")}
          >
            <span>{t("glossary.all")}</span>
            <strong>{terms.length}</strong>
          </button>
          {categories.map((category) => {
            const count = terms.filter((term) => term.category === category).length;
            return (
              <button
                key={`glossary-category-${category}`}
                type="button"
                className={activeCategory === category ? "active" : ""}
                onClick={() => onCategoryChange(category)}
              >
                <span>{category}</span>
                <strong>{count}</strong>
              </button>
            );
          })}
        </div>

        <div className="glossary-term-card-list">
          {terms.map((term) => (
            <button
              key={`glossary-term-${term.term_id}`}
              type="button"
              className={`glossary-term-card ${selectedTerm?.term_id === term.term_id ? "active" : ""}`}
              onClick={() => onSelectTerm(term)}
            >
              <span>{term.category}</span>
              <strong>{term.term}</strong>
              <p>{localizedDefinition(term, language)}</p>
              {term.aliases.length > 0 && (
                <small>{term.aliases.slice(0, 3).join(" / ")}</small>
              )}
            </button>
          ))}
          {terms.length === 0 && (
            <div className="glossary-empty-state">
              <strong>{t("data.unavailable")}</strong>
              <span>{t("glossary.search")}</span>
            </div>
          )}
        </div>
      </section>

      <article className="workspace-panel glossary-wiki-article">
        <div className="panel-title-row">
          <div>
            <span className="eyebrow">{t("glossary.term_wiki")}</span>
            <h3>{selectedTerm?.term ?? t("panel.glossary")}</h3>
          </div>
          {selectedTerm && <span className="status-badge">{selectedTerm.category}</span>}
        </div>

        <p className="glossary-definition">{selectedDefinition}</p>

        {selectedTerm && (
          <div className="glossary-chip-section">
            {selectedTerm.aliases.length > 0 && (
              <div>
                <span>{t("glossary.aliases")}</span>
                <div>
                  {selectedTerm.aliases.map((alias) => (
                    <strong key={`alias-${selectedTerm.term_id}-${alias}`} className="glossary-related-chip">
                      {alias}
                    </strong>
                  ))}
                </div>
              </div>
            )}
            {selectedTerm.related_terms.length > 0 && (
              <div>
                <span>{t("glossary.related")}</span>
                <div>
                  {selectedTerm.related_terms.map((related) => (
                    <button
                      key={`related-${selectedTerm.term_id}-${related}`}
                      type="button"
                      className="glossary-related-chip"
                      onClick={() => onOpenContext(related)}
                    >
                      {related}
                    </button>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}

        {selectedTerm && selectedTerm.source_refs.length > 0 && (
          <div className="glossary-source-list">
            <span>{t("glossary.source_refs")}</span>
            {selectedTerm.source_refs.map((source) => (
              <strong key={`source-${selectedTerm.term_id}-${source}`}>{source}</strong>
            ))}
          </div>
        )}

        <div className="glossary-controls">
          <label>
            {t("glossary.duration_start")}
            <input
              type="datetime-local"
              value={durationStart}
              onChange={(event) => onDurationStartChange(event.target.value)}
            />
          </label>
          <label>
            {t("glossary.duration_end")}
            <input
              type="datetime-local"
              value={durationEnd}
              onChange={(event) => onDurationEndChange(event.target.value)}
            />
          </label>
        </div>
        <div className="context-shortcuts">
          {shortcutTerms.map((term) => (
            <button key={`glossary-shortcut-${term}`} type="button" onClick={() => onOpenContext(term)}>
              {term}
            </button>
          ))}
          {selectedTerm && (
            <button type="button" onClick={() => onOpenContext(selectedTerm.term)}>
              {t("glossary.context")}
            </button>
          )}
        </div>

        <section className="glossary-wiki-context">
          <div className="context-heading">
            <div>
              <strong>{t("glossary.operational_context")}</strong>
              <span>{matchingContext?.context_type ?? t("data.partial")}</span>
            </div>
            <span>{matchingContext?.data_quality.runtime_db ? t("data.runtime") : t("data.partial")}</span>
          </div>

          {matchingContext ? (
            <>
              <p>{language.startsWith("zh") ? matchingContext.description_zh_cn ?? matchingContext.description : matchingContext.description_en ?? matchingContext.description}</p>
              {matchingContext.metrics.length > 0 && (
                <div className="metric-grid glossary-metrics">
                  {matchingContext.metrics.slice(0, 8).map((metric, index) => (
                    <div key={`glossary-context-metric-${index}`}>
                      <span>{shortValue(metric.label, formatContextValue)}</span>
                      <strong>{shortValue(metric.value, formatContextValue)} {shortValue(metric.unit, formatContextValue)}</strong>
                    </div>
                  ))}
                </div>
              )}
              {matchingContext.matched_entities.length > 0 && (
                <div className="glossary-entity-list">
                  <span>{t("glossary.matched_entities")}</span>
                  <div>
                    {matchingContext.matched_entities.slice(0, 8).map((entity, index) => (
                      <strong key={`matched-entity-${index}`}>
                        {shortValue(entity, formatContextValue)}
                      </strong>
                    ))}
                  </div>
                </div>
              )}
              {matchingContext.context_sections.length > 0 && (
                <div className="glossary-context-section-list">
                  {matchingContext.context_sections.slice(0, 4).map((section) => (
                    <div key={`glossary-section-${section.section_id}`} className="glossary-context-section">
                      <strong>{section.title}</strong>
                      {section.items.slice(0, 5).map((item, index) => (
                        <span key={`glossary-section-item-${section.section_id}-${index}`}>
                          {shortValue(item, formatContextValue)}
                        </span>
                      ))}
                    </div>
                  ))}
                </div>
              )}
              {(matchingContext.related_sources.length > 0 || matchingContext.warnings.length > 0) && (
                <div className="glossary-source-list">
                  <span>{t("glossary.data_quality")}</span>
                  {matchingContext.related_sources.map((source) => (
                    <strong key={`context-source-${source}`}>{source}</strong>
                  ))}
                  {matchingContext.warnings.map((warning) => (
                    <em key={`context-warning-${warning}`}>{warning}</em>
                  ))}
                </div>
              )}
            </>
          ) : (
            <p>{selectedTerm ? t("glossary.context_empty") : t("status.loading")}</p>
          )}
        </section>
      </article>
    </div>
  );
}

import { Button, Instant, KeyFigure, PeriodPicker, Skeleton } from "@/components/ui";
import type { GlossaryContextDTO, GlossaryTermDTO, NodeDTO, NormalizedMarketObsDTO } from "@/api/client";
import {
  contextAnswers,
  entryCapacity,
  entryLinks,
  entryPrices,
  glossaryHubCode,
  glossaryMapPlace,
  isEntityTerm,
  resolveGlossaryTerm,
  uniqueSources,
  type EntryFigure,
} from "@/app/model/glossaryEntry";
import { gasDayLabelForUtc } from "@/app/tradingContext";

type Translate = (key: string, options?: Record<string, unknown>) => string;

interface GlossaryWikiProps {
  terms: GlossaryTermDTO[];
  /** Every term, so a related term or a link resolves even when the list is filtered. */
  allTerms: GlossaryTermDTO[];
  context: GlossaryContextDTO | null;
  selectedTerm: GlossaryTermDTO | null;
  categories: string[];
  activeCategory: string;
  query: string;
  language: string;
  /** The gas day the entity's figures are for; empty is the latest held. */
  gasDay: string;
  /** The map's reference points and the board's price rows (the map card's own reads). */
  nodes: readonly NodeDTO[];
  boardRows: readonly NormalizedMarketObsDTO[];
  loading: boolean;
  /** The context read failed (the page then says so instead of waiting). */
  contextError: boolean;
  t: Translate;
  onCategoryChange: (category: string) => void;
  onQueryChange: (query: string) => void;
  onGasDayChange: (value: string) => void;
  onSelectTerm: (term: GlossaryTermDTO) => void;
  onOpenTerm: (term: string) => void;
  /** Open the network map on the place (a network node id). */
  onShowOnMap: (nodeId: string) => void;
}

function localizedDefinition(term: GlossaryTermDTO, language: string): string {
  return language.startsWith("zh") ? term.definition_zh_cn || term.definition_en : term.definition_en;
}

function categoryLabel(category: string, t: Translate): string {
  return t(`glossary.cat.${category}`, { defaultValue: category });
}

function nextDay(day: string): string {
  const date = new Date(`${day}T12:00:00Z`);
  date.setUTCDate(date.getUTCDate() + 1);
  return date.toISOString().slice(0, 10);
}

function figureLabel(figure: EntryFigure, t: Translate): string {
  if (figure.tenor === "day-ahead") return t("map.detail.day_ahead");
  if (figure.tenor === "month-ahead") return t("map.detail.month_ahead");
  if (figure.id === "capacity") return figure.label ? `${t("glossary.capacity")} · ${figure.label}` : t("glossary.capacity");
  if (figure.id === "capacity_used") return t("glossary.capacity_usage");
  return figure.label;
}

function Figures({ figures, language, t }: { figures: EntryFigure[]; language: string; t: Translate }) {
  const locale = language.startsWith("zh") ? "zh-CN" : "en-GB";
  const format = (value: number) => value.toLocaleString(locale, { maximumFractionDigits: 3 });
  return (
    <div className="glossary-figures">
      {figures.map((figure) => (
        <KeyFigure
          key={figure.id}
          label={figureLabel(figure, t)}
          value={format(figure.value)}
          unit={figure.unit}
          delta={figure.change != null ? { text: `${figure.change >= 0 ? "+" : "−"}${format(Math.abs(figure.change))}`, value: figure.change } : undefined}
          detail={
            <span className="glossary-figure-source">
              {figure.detail ? <span>{figure.detail}</span> : null}
              {figure.source ? <span>{figure.source}</span> : null}
              {figure.asOf ? <Instant value={figure.asOf} /> : null}
            </span>
          }
        />
      ))}
    </div>
  );
}

export function GlossaryWiki({
  terms,
  allTerms,
  context,
  selectedTerm,
  categories,
  activeCategory,
  query,
  language,
  gasDay,
  nodes,
  boardRows,
  loading,
  contextError,
  t,
  onCategoryChange,
  onQueryChange,
  onGasDayChange,
  onSelectTerm,
  onOpenTerm,
  onShowOnMap,
}: GlossaryWikiProps) {
  const mapPlace = glossaryMapPlace(selectedTerm, nodes);
  const hub = glossaryHubCode(selectedTerm, nodes);
  const answered = contextAnswers(context, selectedTerm, gasDay) ? context : null;
  const entity = isEntityTerm(selectedTerm, mapPlace, answered) || Boolean(hub);
  const waiting = entity && !answered && !contextError;
  const prices = entity
    ? entryPrices(answered, { hub, gasDay, boardRows })
    : [];
  const capacity = entity ? entryCapacity(answered) : [];
  const links = entity ? entryLinks(answered) : { routes: [], contracts: [] };
  const figures = [...prices, ...capacity];
  const sources = selectedTerm ? uniqueSources(selectedTerm.source_refs) : [];
  const latestDay = nextDay(gasDayLabelForUtc(new Date()));

  return (
    <div className="workspace-grid glossary-page glossary-wiki-shell glossary-codex-shell">
      <section className="workspace-panel glossary-left-rail glossary-term-list" aria-label={t("panel.glossary")}>
        <div className="panel-title-row">
          <h2>{t("panel.glossary")}</h2>
          <strong aria-label={t("glossary.term_count")}>{terms.length}</strong>
        </div>
        <div className="glossary-list-toolbar">
          <input
            type="search"
            value={query}
            onChange={(event) => onQueryChange(event.target.value)}
            placeholder={t("glossary.search")}
            aria-label={t("glossary.search")}
          />
        </div>
        <div className="glossary-category-tabs" aria-label={t("glossary.category")}>
          <button
            type="button"
            className={activeCategory === "all" ? "active" : ""}
            onClick={() => onCategoryChange("all")}
          >
            <span>{t("glossary.all")}</span>
          </button>
          {categories.map((category) => (
            <button
              key={`glossary-category-${category}`}
              type="button"
              className={activeCategory === category ? "active" : ""}
              onClick={() => onCategoryChange(category)}
            >
              <span>{categoryLabel(category, t)}</span>
            </button>
          ))}
        </div>

        <div className="glossary-term-card-list">
          {terms.map((term) => (
            <button
              key={`glossary-term-${term.term_id}`}
              type="button"
              // The card carries the term's own id, so the acceptance sweep compares the term
              // index with the glossary read by exact id rather than by page text
              // (`scripts/uat/readToRender.mjs`).
              data-record="glossary-term"
              data-record-id={term.term_id}
              className={`glossary-term-card ${selectedTerm?.term_id === term.term_id ? "active" : ""}`}
              aria-current={selectedTerm?.term_id === term.term_id ? "true" : undefined}
              onClick={() => onSelectTerm(term)}
            >
              <span>{categoryLabel(term.category, t)}</span>
              <strong>{term.term}</strong>
              <p>{localizedDefinition(term, language)}</p>
            </button>
          ))}
          {terms.length === 0 && loading && <Skeleton label={t("status.loading")} rows={6} />}
          {terms.length === 0 && !loading && (
            <div className="glossary-empty-state" data-empty-state="glossary-terms">
              <strong>{t("glossary.no_match")}</strong>
            </div>
          )}
        </div>
      </section>

      <article
        className="workspace-panel glossary-wiki-article"
        // The article declares the term it is showing, so the browser sweep's glossary
        // interaction can hold the selection to the exact record the index selected instead of
        // comparing the page's own copy with itself (`browser_workflow_smoke.mjs`).
        data-record="glossary-article"
        data-record-id={selectedTerm?.term_id}
        // A stable anchor for the entry: `?workspace=glossary&term=<term>` opens it.
        id={selectedTerm ? `glossary-${selectedTerm.term_id}` : undefined}
      >
        {!selectedTerm ? (
          <Skeleton label={t("status.loading")} rows={4} variant="text" />
        ) : (
          <>
            <div className="panel-title-row">
              <div>
                <h2>{selectedTerm.term}</h2>
                {selectedTerm.aliases.length > 0 && (
                  <p className="glossary-aliases muted">{selectedTerm.aliases.join(" · ")}</p>
                )}
              </div>
              <span className="status-badge">{categoryLabel(selectedTerm.category, t)}</span>
            </div>

            <p className="glossary-definition">{localizedDefinition(selectedTerm, language)}</p>
            {(selectedTerm.unit || selectedTerm.formula || selectedTerm.example) && (
              <dl className="glossary-facts">
                {selectedTerm.unit && <div><dt>{t("glossary.unit")}</dt><dd>{selectedTerm.unit}</dd></div>}
                {selectedTerm.formula && <div><dt>{t("glossary.formula")}</dt><dd><code>{selectedTerm.formula}</code></dd></div>}
                {selectedTerm.example && <div><dt>{t("glossary.example")}</dt><dd>{selectedTerm.example}</dd></div>}
              </dl>
            )}

            {entity && (
              <section className="glossary-entity" aria-label={t("glossary.facts_title")} aria-busy={waiting || undefined}>
                <div className="glossary-entity-head">
                  <h3>{t("glossary.facts_title")}</h3>
                  <div className="glossary-entity-controls">
                    <PeriodPicker
                      kind="day"
                      label={t("glossary.gas_day")}
                      value={gasDay}
                      placeholder={t("glossary.latest")}
                      max={latestDay}
                      clearable
                      onChange={onGasDayChange}
                    />
                    {mapPlace && (
                      <Button size="sm" variant="secondary" onClick={() => onShowOnMap(mapPlace)}>
                        {t("glossary.show_on_map")}
                      </Button>
                    )}
                  </div>
                </div>
                {waiting && figures.length === 0 ? (
                  <Skeleton label={t("glossary.loading_figures")} rows={2} />
                ) : figures.length > 0 ? (
                  <Figures figures={figures} language={language} t={t} />
                ) : (
                  <p className="muted glossary-no-figures">
                    {contextError ? t("data.unavailable") : gasDay ? t("glossary.no_figures_day") : t("glossary.no_figures")}
                  </p>
                )}
                {(links.routes.length > 0 || links.contracts.length > 0) && (
                  <dl className="glossary-facts glossary-entity-links">
                    {links.routes.length > 0 && <div><dt>{t("glossary.routes")}</dt><dd>{links.routes.join(" · ")}</dd></div>}
                    {links.contracts.length > 0 && <div><dt>{t("glossary.contracts")}</dt><dd>{links.contracts.join(" · ")}</dd></div>}
                  </dl>
                )}
              </section>
            )}

            {selectedTerm.related_terms.length > 0 && (
              <div className="glossary-chip-section">
                <div>
                  <span>{t("glossary.related")}</span>
                  <div>
                    {selectedTerm.related_terms.map((related) =>
                      resolveGlossaryTerm(related, allTerms) ? (
                        <button
                          key={`related-${selectedTerm.term_id}-${related}`}
                          type="button"
                          className="glossary-related-chip"
                          onClick={() => onOpenTerm(related)}
                        >
                          {related}
                        </button>
                      ) : (
                        <span key={`related-${selectedTerm.term_id}-${related}`} className="glossary-related-chip">
                          {related}
                        </span>
                      ),
                    )}
                  </div>
                </div>
              </div>
            )}

            {selectedTerm.where_in_app && selectedTerm.where_in_app.length > 0 && (
              <p className="glossary-where">
                <span>{t("glossary.where_in_app")}</span> {selectedTerm.where_in_app.join(" · ")}
              </p>
            )}
            {sources.length > 0 && (
              <p className="glossary-where muted"><span>{t("glossary.sources")}</span> {sources.join(" · ")}</p>
            )}
          </>
        )}
      </article>
    </div>
  );
}

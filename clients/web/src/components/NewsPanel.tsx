/**
 * NEWS-1: news and events from registered public sources (REMIT messages the platform holds,
 * official feeds whose terms permit reuse). Filter by hub, country and event type; the items
 * that touch my book come first. An item opens with its source link and terms, the exposures it
 * touches, related items and the note "what this means for my book": the rule note, each
 * sentence citing its lines; on request, the AI note, shown only when every sentence passed the
 * grounding check, and labelled. Decision support: nothing is traded, nominated or sent.
 */
import { useState } from "react";

import { api, type NewsFilterInput, type NewsItemDTO, type NewsNoteDTO } from "@/api/client";
import { useCachedRead } from "@/app/data/readCache";
import {
  NEWS_EVENT_TYPES,
  NEWS_HUBS,
  isAiNote,
  newsKey,
  noteSentences,
  noteStatusKey,
  safeHref,
  touchesBook,
} from "@/app/model/newsModel";
import { Button, Field, Instant, Panel, Segmented, Select, Skeleton, StatusBadge, UpdatingMark } from "@/components/ui";

type Translate = (key: string, options?: Record<string, unknown>) => string;
type Scope = "all" | "mine";

function NoteView({ note, t }: { note: NewsNoteDTO; t: Translate }) {
  const sentences = noteSentences(note);
  const status = noteStatusKey(note);
  return (
    <section className="news-note" data-note-basis={note.basis} aria-label={t("news.note.title")}>
      <header className="news-note-head">
        <strong>{t("news.note.title")}</strong>
        {isAiNote(note) ? (
          <StatusBadge tone="info" title={note.ai.prompt_version ?? undefined}>
            {note.label}
          </StatusBadge>
        ) : (
          <StatusBadge tone="neutral">{t("news.note.rule_label")}</StatusBadge>
        )}
      </header>
      <ol className="news-note-sentences">
        {sentences.map((sentence, index) => (
          <li key={index}>
            {sentence.text}{" "}
            {sentence.citations.map((citation) =>
              citation.href ? (
                <a key={citation.id} className="news-cite" href={citation.href} target="_blank" rel="noopener noreferrer" title={citation.title}>
                  [{citation.id}]
                </a>
              ) : (
                <span key={citation.id} className="news-cite" title={citation.title}>
                  [{citation.id}]
                </span>
              ),
            )}
          </li>
        ))}
      </ol>
      <details className="news-note-lines">
        <summary>{t("news.note.lines")}</summary>
        <dl>
          {note.citations.map((citation) => (
            <div key={citation.id}>
              <dt>{citation.id}</dt>
              <dd>{citation.text}</dd>
            </div>
          ))}
        </dl>
      </details>
      {status && <p className="news-muted">{t(status)}</p>}
      <p className="news-muted">{t("news.advisory")}</p>
    </section>
  );
}

function ItemDetail({ itemId, t, language }: { itemId: string; t: Translate; language: string }) {
  const read = useCachedRead(`/news/${itemId}`, (signal) => api.newsItem(itemId, { signal }));
  const [aiNote, setAiNote] = useState<NewsNoteDTO | null>(null);
  const [asking, setAsking] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const item = read.data?.data;
  if (read.error && !item) return <p className="news-error" role="alert">{t("news.load_failed")}</p>;
  if (!item) return <Skeleton label={t("news.loading")} rows={5} variant="text" />;
  const href = safeHref(item.url);
  const ask = () => {
    setAsking(true);
    setError(null);
    api
      .newsNote(itemId, language.toLowerCase().startsWith("zh") ? "zh-CN" : "en")
      .then((response) => setAiNote(response.data))
      .catch((caught: unknown) => setError(caught instanceof Error ? caught.message : String(caught)))
      .finally(() => setAsking(false));
  };
  return (
    <article className="news-detail" data-news-item={item.item_id}>
      <h3>{item.title}</h3>
      <p className="news-meta">
        {item.publisher} · <Instant value={item.published_at_utc} date="always" fallback={t("news.time_unknown")} />
        {href && (
          <>
            {" · "}
            <a href={href} target="_blank" rel="noopener noreferrer">
              {t("news.open_source")}
            </a>
          </>
        )}
      </p>
      {item.summary && <p className="news-summary">{item.summary}</p>}
      <p className="news-muted">
        {t("news.source_terms", { source: item.source?.title ?? item.source_title, licence: item.licence_note })}
      </p>
      <section className="news-exposures" aria-label={t("news.exposures")}>
        <strong>{t("news.exposures")}</strong>
        {item.book_hidden ? (
          <p className="news-muted">{t("news.book_hidden")}</p>
        ) : item.linked_exposures.length === 0 ? (
          <p className="news-muted">{t("news.no_exposures")}</p>
        ) : (
          <ul>
            {item.linked_exposures.map((match) => (
              <li key={`${match.kind}:${match.ref}`} data-exposure-kind={match.kind}>
                <StatusBadge tone="watch">{t(`news.role.${match.role}`)}</StatusBadge> {match.figure}
                <span className="news-muted"> · {match.reason}</span>
              </li>
            ))}
          </ul>
        )}
      </section>
      {item.related.length > 0 && (
        <section className="news-related" aria-label={t("news.related")}>
          <strong>{t("news.related")}</strong>
          <ul>
            {item.related.map((other) => (
              <li key={other.item_id}>
                {other.publisher}: {other.title}
              </li>
            ))}
          </ul>
        </section>
      )}
      <NoteView note={aiNote ?? item.note} t={t} />
      {error && <p className="news-error" role="alert">{error}</p>}
      {!aiNote && (
        <div className="news-actions">
          <Button variant="secondary" size="sm" loading={asking} disabled={asking} onClick={ask}>
            {t("news.note.ask")}
          </Button>
          <span className="news-muted">{t("news.note.ask_hint")}</span>
        </div>
      )}
    </article>
  );
}

function ItemRow({ item, selected, onSelect, t }: { item: NewsItemDTO; selected: boolean; onSelect: () => void; t: Translate }) {
  return (
    <li className="news-row" data-selected={selected || undefined} data-touches-book={touchesBook(item) || undefined}>
      <button type="button" className="news-row-button" aria-pressed={selected} onClick={onSelect}>
        <span className="news-row-title">{item.title}</span>
        <span className="news-meta">
          {item.publisher} · <Instant value={item.published_at_utc ?? item.first_seen_at_utc} date="always" />
        </span>
        <span className="news-tags">
          {touchesBook(item) && <StatusBadge tone="watch">{t("news.touches_book", { count: item.relevance.matches })}</StatusBadge>}
          {item.event_types.map((kind) => (
            <StatusBadge key={kind} tone="neutral">
              {t(`news.type.${kind}`)}
            </StatusBadge>
          ))}
          {item.hubs.slice(0, 3).map((hub) => (
            <span key={hub} className="news-hub">
              {hub}
            </span>
          ))}
        </span>
      </button>
    </li>
  );
}

export function NewsPanel({ t, language }: { t: Translate; language: string }) {
  const [hub, setHub] = useState("");
  const [country, setCountry] = useState("");
  const [type, setType] = useState("");
  const [scope, setScope] = useState<Scope>("all");
  const [selected, setSelected] = useState<string | null>(null);
  const filters: NewsFilterInput = { hub, country, type, mine: scope === "mine", limit: 50 };
  const read = useCachedRead(newsKey(filters), (signal) => api.news(filters, { signal }));
  const items = read.data?.data ?? [];
  const countries = Array.from(new Set(items.flatMap((item) => item.countries))).sort();
  return (
    <Panel
      className="span-3 news-panel"
      title={t("news.title")}
      titleHint={t("news.purpose")}
      actions={
        <>
          <UpdatingMark active={read.updating} label={t("status.updating")} />
          <Segmented<Scope>
            label={t("news.scope")}
            value={scope}
            onChange={setScope}
            options={[
              { value: "all", label: t("news.scope_all") },
              { value: "mine", label: t("news.scope_mine") },
            ]}
          />
        </>
      }
    >
      <div className="news-filters">
        <Field label={t("news.filter.hub")} inline>
          <Select value={hub} onChange={setHub} options={[{ value: "", label: t("news.filter.any") }, ...NEWS_HUBS.map((value) => ({ value, label: value }))]} />
        </Field>
        <Field label={t("news.filter.country")} inline>
          <Select
            value={country}
            onChange={setCountry}
            options={[{ value: "", label: t("news.filter.any") }, ...Array.from(new Set([...countries, ...(country ? [country] : [])])).map((value) => ({ value, label: value }))]}
          />
        </Field>
        <Field label={t("news.filter.type")} inline>
          <Select value={type} onChange={setType} options={[{ value: "", label: t("news.filter.any") }, ...NEWS_EVENT_TYPES.map((value) => ({ value, label: t(`news.type.${value}`) }))]} />
        </Field>
      </div>
      {Boolean(read.error) && !read.data && <p className="news-error" role="alert">{t("news.load_failed")}</p>}
      {read.loading && !read.data && <Skeleton label={t("news.list_loading")} rows={5} />}
      {read.data && items.length === 0 && <p className="news-muted" data-empty-state="news">{t("news.empty")}</p>}
      <div className="news-body">
        <ul className="news-list" aria-label={t("news.title")}>
          {items.map((item) => (
            <ItemRow key={item.item_id} item={item} selected={item.item_id === selected} onSelect={() => setSelected(item.item_id)} t={t} />
          ))}
        </ul>
        {selected && <ItemDetail key={selected} itemId={selected} t={t} language={language} />}
      </div>
    </Panel>
  );
}

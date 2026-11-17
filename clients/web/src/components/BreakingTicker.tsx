/**
 * The situational strip under the top bar (role-first redesign §5.1): a calm instrument line,
 * not a news ticker.
 *
 * - **Hidden**: nothing qualifies and the role has no quiet fact. Nothing is rendered, so there
 *   is no band at all (`[data-shell-region="ticker"]` is absent); the bell keeps the count.
 * - **Quiet**: one static line in muted text, no colour, no motion (booked today, the next
 *   window, the counts a risk manager starts from).
 * - **Urgent**: one static line: severity mark, the top item, "+n more". A coloured edge. No
 *   marquee (decision D3) and nothing to pause.
 * - **Expanded**: at most seven items over the page (a popover on a desktop, a sheet on a
 *   phone), each with its link and the actions Hide, Acknowledge (only with the permission),
 *   Why and Report, and a line saying why this person sees it. Escape closes; the arrow keys
 *   move between items.
 *
 * A new urgent item is announced once to screen readers (by the shell's announcer) and the
 * edge brightens once; a standing state is never announced again.
 */
import { useRef, useState, type KeyboardEvent } from "react";

import type { Phrase, Situation, SituationItem, SituationTarget } from "@/app/model/tickerItems";
import { Popover } from "@/components/ui/Popover";
import { Sheet } from "@/components/ui/Dialog";
import { WhyButton } from "@/components/WhyButton";
import { ReportLink } from "@/components/ReportLink";
import "./situationStrip.css";

type Translate = (key: string, options?: Record<string, unknown>) => string;

const MINUTE = 60_000;
const HOUR = 60 * MINUTE;
const DAY = 24 * HOUR;

/** "42 min", "3 h", "2 d": the time to go or the age of an item, without a clock. */
export function spanText(ms: number, t: Translate): string {
  const span = Number.isFinite(ms) ? Math.max(0, ms) : 0;
  if (span < HOUR) return t("strip.span.minutes", { count: Math.max(1, Math.round(span / MINUTE)) });
  if (span < DAY) return t("strip.span.hours", { count: Math.round(span / HOUR) });
  return t("strip.span.days", { count: Math.round(span / DAY) });
}

function clockText(iso: string, language: string): string {
  const at = new Date(iso);
  if (Number.isNaN(at.getTime())) return "";
  return at.toLocaleTimeString(language.toLowerCase().startsWith("zh") ? "zh-CN" : "en-GB", { hour: "2-digit", minute: "2-digit" });
}

/** A phrase in the person's language; an instant in it becomes "in 42 min (14:00)". */
export function phraseText(phrase: Phrase, t: Translate, language: string, nowMs: number): string {
  const values: Record<string, unknown> = { ...phrase.values };
  for (const name of ["close", "due"] as const) {
    const iso = phrase.values[name];
    if (typeof iso !== "string") continue;
    values.until = spanText(Date.parse(iso) - nowMs, t);
    values.clock = clockText(iso, language);
  }
  return t(phrase.key, values);
}

export interface SituationStripProps {
  situation: Situation;
  t: Translate;
  language: string;
  nowMs: number;
  /** Phone width: the list opens as a sheet from the bottom. */
  compact: boolean;
  /** The person holds the governed acknowledge permission (D5: offered only then). */
  canAcknowledge: boolean;
  /** The edge brightens once when a new urgent item arrives. */
  flash: boolean;
  onOpen: (target: SituationTarget) => void;
  onHide: (item: SituationItem) => void;
  onAcknowledge: (alertId: string) => Promise<void> | void;
}

function SimMark({ t }: { t: Translate }) {
  return (
    <abbr className="strip-sim" data-state="simulated" title={t("strip.simulated")}>
      {t("strip.sim")}
    </abbr>
  );
}

function ItemLine({ item, t, language, nowMs, sim = true }: { item: SituationItem; t: Translate; language: string; nowMs: number; sim?: boolean }) {
  return (
    <>
      <span className="strip-headline">{phraseText(item.headline, t, language, nowMs)}</span>
      {item.comparison && <span className="strip-comparison"> · {phraseText(item.comparison, t, language, nowMs)}</span>}
      {sim && item.simulated && <SimMark t={t} />}
    </>
  );
}

function StripList({
  situation,
  t,
  language,
  nowMs,
  canAcknowledge,
  onOpen,
  onHide,
  onAcknowledge,
  close,
}: Omit<SituationStripProps, "compact" | "flash"> & { close: () => void }) {
  const list = useRef<HTMLUListElement | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  // Up and Down move between the items' links; Home and End go to the ends.
  const move = (event: KeyboardEvent<HTMLUListElement>) => {
    if (!["ArrowDown", "ArrowUp", "Home", "End"].includes(event.key)) return;
    const links = [...(list.current?.querySelectorAll<HTMLButtonElement>("[data-strip-open]") ?? [])];
    if (!links.length) return;
    event.preventDefault();
    const index = links.indexOf(document.activeElement as HTMLButtonElement);
    const next =
      event.key === "Home" ? 0
      : event.key === "End" ? links.length - 1
      : event.key === "ArrowDown" ? Math.min(links.length - 1, index + 1)
      : Math.max(0, index - 1);
    links[next]?.focus();
  };
  return (
    <div className="strip-list" data-strip-list>
      <ul ref={list} onKeyDown={move} aria-label={t("strip.list_title")}>
        {situation.items.map((item) => {
          const label = phraseText(item.headline, t, language, nowMs);
          return (
            <li key={item.id} className={`strip-list-item is-${item.severity}`} data-strip-item={item.kind} data-strip-rule={item.audience}>
              <i className="strip-mark" aria-hidden="true" />
              <div className="strip-list-body">
                <button
                  type="button"
                  className="strip-open"
                  data-strip-open
                  onClick={() => {
                    close();
                    onOpen(item.target);
                  }}
                >
                  <span className="visually-hidden">{t(`strip.severity.${item.severity}`)}: </span>
                  <ItemLine item={item} t={t} language={language} nowMs={nowMs} />
                </button>
                <p className="strip-meta">
                  {t("strip.source", { source: t(`strip.source_name.${item.source.name}`, { defaultValue: item.source.name }) })} · {t("strip.age", { age: spanText(nowMs - Date.parse(item.occurredAt), t) })}
                </p>
                <p className="strip-meta strip-why-line" data-strip-why>{t(`strip.why.${item.audience}`)}</p>
                <div className="strip-actions">
                  <button type="button" className="ds-inline-link" data-strip-action="hide" onClick={() => onHide(item)} aria-label={t("strip.hide_label", { item: label })}>
                    {t("strip.hide")}
                  </button>
                  {canAcknowledge && item.alertId && (
                    <button
                      type="button"
                      className="ds-inline-link"
                      data-strip-action="acknowledge"
                      disabled={busy === item.alertId}
                      aria-label={t("strip.acknowledge_label", { item: label })}
                      onClick={async () => {
                        const alertId = item.alertId;
                        if (!alertId) return;
                        setBusy(alertId);
                        try {
                          await onAcknowledge(alertId);
                        } finally {
                          setBusy(null);
                        }
                      }}
                    >
                      {t("strip.acknowledge")}
                    </button>
                  )}
                  {item.explain && <WhyButton subject={item.explain.subject} id={item.explain.id} label={label} language={language} t={t} />}
                  {item.report && <ReportLink subject={item.report} label={label} t={t} />}
                </div>
              </div>
            </li>
          );
        })}
      </ul>
      {situation.more > 0 && <p className="strip-meta strip-not-listed">{t("strip.not_listed", { count: situation.more })}</p>}
    </div>
  );
}

export function SituationStrip(props: SituationStripProps) {
  const { situation, t, language, nowMs, compact, flash, onOpen } = props;
  const [sheetOpen, setSheetOpen] = useState(false);

  if (situation.state === "hidden") return null;

  if (situation.state === "quiet" && situation.quiet) {
    const quiet = situation.quiet;
    const text = phraseText(quiet.phrase, t, language, nowMs);
    const target = quiet.target;
    return (
      <section className="situation-strip is-quiet" aria-label={t("strip.label")} data-shell-region="ticker" data-strip-state="quiet">
        {target ? (
          <button type="button" className="strip-quiet-line" data-strip-open onClick={() => onOpen(target)} title={t("strip.source", { source: t(`strip.source_name.${quiet.source}`, { defaultValue: quiet.source }) })}>
            {text}
          </button>
        ) : (
          <span className="strip-quiet-line">{text}</span>
        )}
      </section>
    );
  }

  const top = situation.items[0];
  if (!top) return null;
  const others = situation.items.length - 1 + situation.more;
  const expandLabel = others > 0 ? t("strip.more", { count: others }) : t("strip.details");
  const expandName = t("strip.expand_label");

  return (
    <section
      className={`situation-strip is-urgent is-${top.severity}${flash ? " is-flash" : ""}`}
      aria-label={t("strip.label")}
      data-shell-region="ticker"
      data-strip-state="urgent"
    >
      <i className="strip-mark" aria-hidden="true" />
      <button type="button" className="strip-top" data-strip-open onClick={() => onOpen(top.target)}>
        <span className="visually-hidden">{t(`strip.severity.${top.severity}`)}: </span>
        <ItemLine item={top} t={t} language={language} nowMs={nowMs} sim={false} />
      </button>
      {/* Outside the line that truncates, so a narrow screen never cuts the simulated mark off. */}
      {top.simulated && <SimMark t={t} />}
      {compact ? (
        <>
          <button
            type="button"
            className="strip-expand"
            data-strip-expand
            aria-haspopup="dialog"
            aria-expanded={sheetOpen}
            title={expandName}
            onClick={() => setSheetOpen(true)}
          >
            {expandLabel}
          </button>
          <Sheet open={sheetOpen} onClose={() => setSheetOpen(false)} side="bottom" title={t("strip.list_title")} closeLabel={t("strip.close")} id="situation-strip">
            <StripList {...props} close={() => setSheetOpen(false)} />
          </Sheet>
        </>
      ) : (
        <Popover
          label={t("strip.list_title")}
          placement="bottom-end"
          width="md"
          className="strip-popover"
          id="situation-strip"
          trigger={(triggerProps) => (
            <button {...triggerProps} type="button" className="strip-expand" data-strip-expand title={expandName}>
              {expandLabel}
            </button>
          )}
        >
          {(close) => <StripList {...props} close={close} />}
        </Popover>
      )}
    </section>
  );
}

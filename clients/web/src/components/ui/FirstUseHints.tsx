import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";

import { useHintsSeenStore } from "@/stores/hintsSeen";
import { hintsToShow, type FirstUseHint } from "./firstUseHintsModel";

export type { FirstUseHint } from "./firstUseHintsModel";

/**
 * First-use hints (design basis H.1): one small card at a time, beside the real control it is
 * about, "1 of 3", with "Got it" and "Skip tips". Shown once per person (the `hints_seen`
 * preference); Account -> Preferences replays them. A hint whose control is not on the page is
 * skipped, never shown floating.
 */
export function FirstUseHints({ hints }: { hints: readonly FirstUseHint[] }) {
  const { t } = useTranslation();
  const seen = useHintsSeenStore((state) => state.seen);
  const off = useHintsSeenStore((state) => state.off);
  const dismiss = useHintsSeenStore((state) => state.dismiss);
  const pending = hintsToShow(hints, seen, { off });
  const [anchorFound, setAnchorFound] = useState<{ hint: FirstUseHint; element: HTMLElement } | null>(null);
  const cardRef = useRef<HTMLDivElement | null>(null);

  // The first pending hint whose control is on the page (controls can render after a read).
  useEffect(() => {
    if (pending.length === 0) {
      setAnchorFound(null);
      return undefined;
    }
    let cancelled = false;
    const find = () => {
      if (cancelled) return;
      for (const hint of pending) {
        const element = document.querySelector<HTMLElement>(hint.anchor);
        if (element && element.getBoundingClientRect().width > 0) {
          setAnchorFound((current) => (current?.hint.id === hint.id && current.element === element ? current : { hint, element }));
          return;
        }
      }
      setAnchorFound(null);
    };
    find();
    const timer = window.setInterval(find, 800);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
    // The ids, not the array identity, decide what to look for.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pending.map((hint) => hint.id).join(",")]);

  // Place the card beside its control, inside the viewport; follow scroll, resize and the page's
  // own layout (a read arriving above the control moves it without a scroll or a resize).
  useLayoutEffect(() => {
    if (!anchorFound) return undefined;
    const { element } = anchorFound;
    element.classList.add("has-first-use-hint");
    let frame = 0;
    const place = () => {
      const card = cardRef.current;
      if (!card) return;
      const box = element.getBoundingClientRect();
      const width = card.offsetWidth;
      const left = Math.min(Math.max(8, box.left), window.innerWidth - width - 8);
      // Above the control, so the card never hides the figure the control names; below when
      // there is no room above.
      const above = box.top - card.offsetHeight - 8;
      const top = above >= 8 ? above : Math.min(box.bottom + 8, window.innerHeight - card.offsetHeight - 8);
      card.style.left = `${left}px`;
      card.style.top = `${top}px`;
    };
    const schedule = () => {
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(place);
    };
    place();
    window.addEventListener("scroll", schedule, true);
    window.addEventListener("resize", schedule);
    const observer = typeof ResizeObserver === "undefined" ? null : new ResizeObserver(schedule);
    observer?.observe(document.body);
    observer?.observe(element);
    return () => {
      element.classList.remove("has-first-use-hint");
      observer?.disconnect();
      cancelAnimationFrame(frame);
      window.removeEventListener("scroll", schedule, true);
      window.removeEventListener("resize", schedule);
    };
  }, [anchorFound]);

  if (!anchorFound) return null;
  const index = pending.findIndex((hint) => hint.id === anchorFound.hint.id);
  return (
    <div ref={cardRef} className="first-use-hint" role="note" aria-live="polite" data-first-use-hint={anchorFound.hint.id}>
      <p>{t(anchorFound.hint.textKey)}</p>
      <div className="first-use-hint-actions">
        <span className="first-use-hint-step">{t("hints.step", { n: index + 1, total: pending.length })}</span>
        <button type="button" className="ds-inline-link" onClick={() => dismiss(pending.map((hint) => hint.id))}>
          {t("hints.skip")}
        </button>
        <button type="button" className="first-use-hint-ok" onClick={() => dismiss([anchorFound.hint.id])}>
          {t("hints.got_it")}
        </button>
      </div>
    </div>
  );
}

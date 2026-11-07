/**
 * "Why?" next to the number: two or three sentences on why an alert, an outage, a credit
 * line, a mandate or a P&L figure matters, with the sources they rest on.
 *
 * - The server loads the evidence from the object's id; the button sends nothing else.
 * - The note opens over the page (fixed, clamped to the viewport), so a table that scrolls
 *   inside its box never clips it; Escape, a click elsewhere or the button closes it.
 * - It says whether the text came from the rules or is a checked model summary, and when
 *   the figures use simulated demo prices.
 */
import { useEffect, useId, useLayoutEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { api, type ExplainSubject, type ExplanationDTO } from "@/api/client";
import i18n from "@/i18n";

type Translate = (key: string, options?: Record<string, unknown>) => string;

const PANEL_WIDTH = 360;
const GUTTER = 12;

export function WhyButton({
  subject,
  id,
  label,
  language,
  t,
}: {
  subject: ExplainSubject;
  id: string;
  /** What is being explained, for the screen-reader label ("Rhinmark credit"). */
  label: string;
  /** Defaults to the app language. */
  language?: string;
  t: Translate;
}) {
  const [open, setOpen] = useState(false);
  const [state, setState] = useState<
    { kind: "loading" } | { kind: "ready"; data: ExplanationDTO } | { kind: "failed" }
  >({ kind: "loading" });
  const [place, setPlace] = useState<{ top: number; left: number; width: number } | null>(null);
  const button = useRef<HTMLButtonElement>(null);
  const panel = useRef<HTMLDivElement>(null);
  const panelId = useId();
  const lang = (language ?? i18n.language ?? "en").toLowerCase().startsWith("zh") ? "zh-CN" : "en";

  useEffect(() => {
    if (!open) return undefined;
    let live = true;
    setState({ kind: "loading" });
    api
      .explain(subject, id, lang)
      .then((response) => live && setState({ kind: "ready", data: response.data }))
      .catch(() => live && setState({ kind: "failed" }));
    return () => {
      live = false;
    };
  }, [open, subject, id, lang]);

  useLayoutEffect(() => {
    if (!open || !button.current) return;
    const box = button.current.getBoundingClientRect();
    const width = Math.min(PANEL_WIDTH, window.innerWidth - 2 * GUTTER);
    const left = Math.min(Math.max(GUTTER, box.right - width), window.innerWidth - width - GUTTER);
    const below = box.bottom + 6;
    // Open upwards when there is no room below (the panel is about 160 px tall).
    const top = below + 180 > window.innerHeight ? Math.max(GUTTER, box.top - 186) : below;
    setPlace({ top, left, width });
  }, [open, state.kind]);

  useEffect(() => {
    if (!open) return undefined;
    const close = (event: Event) => {
      if (event instanceof KeyboardEvent) {
        if (event.key !== "Escape") return;
        button.current?.focus();
      } else if (
        panel.current?.contains(event.target as Node) ||
        button.current?.contains(event.target as Node)
      ) {
        return;
      }
      setOpen(false);
    };
    const dismiss = () => setOpen(false);
    document.addEventListener("keydown", close);
    document.addEventListener("pointerdown", close);
    window.addEventListener("resize", dismiss);
    return () => {
      document.removeEventListener("keydown", close);
      document.removeEventListener("pointerdown", close);
      window.removeEventListener("resize", dismiss);
    };
  }, [open]);

  return (
    <>
      <button
        ref={button}
        type="button"
        className="why-button"
        aria-expanded={open}
        aria-controls={open ? panelId : undefined}
        aria-label={t("why.label", { subject: label })}
        title={t("why.label", { subject: label })}
        onClick={() => setOpen((value) => !value)}
      >
        {t("why.button")}
      </button>
      {open &&
        place &&
        createPortal(
          <div
            ref={panel}
            id={panelId}
            className="why-panel"
            role="dialog"
            aria-label={t("why.label", { subject: label })}
            style={{ top: place.top, left: place.left, width: place.width }}
          >
            {state.kind === "loading" && <p className="why-text is-muted">{t("why.loading")}</p>}
            {state.kind === "failed" && <p className="why-text is-muted">{t("why.failed")}</p>}
            {state.kind === "ready" && (
              <>
                <p className="why-text" aria-live="polite">{state.data.text}</p>
                <div className="why-meta">
                  <span>{t(state.data.basis === "model" ? "why.basis_model" : "why.basis_rule")}</span>
                  {state.data.simulated && <span className="why-flag">{t("why.simulated")}</span>}
                </div>
                <p className="why-sources">
                  {t("why.sources")}: {state.data.sources.join(", ")}
                </p>
              </>
            )}
          </div>,
          document.body,
        )}
    </>
  );
}

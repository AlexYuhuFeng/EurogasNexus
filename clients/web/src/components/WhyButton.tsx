/**
 * "Why?" next to the number: two or three sentences on why an alert, an outage, a credit
 * line, a mandate or a P&L figure matters, with the sources they rest on.
 *
 * - The server loads the evidence from the object's id; the button sends nothing else.
 * - The note is a Popover: drawn in the top layer, so a table that scrolls inside its box
 *   never clips it; placed against collisions; Escape, a click elsewhere or the button closes
 *   it and focus returns to the button.
 * - It says whether the text came from the rules or is a checked model summary, and when
 *   the figures use simulated demo prices.
 */
import { useEffect, useState } from "react";
import { api, type ExplainSubject, type ExplanationDTO } from "@/api/client";
import { Popover } from "@/components/ui";
import i18n from "@/i18n";

type Translate = (key: string, options?: Record<string, unknown>) => string;

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

  const name = t("why.label", { subject: label });
  return (
    <Popover
      label={name}
      id="why"
      placement="bottom-end"
      onOpenChange={setOpen}
      trigger={(props) => (
        <button {...props} type="button" className="why-button ds-note-trigger" aria-label={name} title={name}>
          {t("why.button")}
        </button>
      )}
    >
      {state.kind === "loading" && <p className="why-text is-muted">{t("why.loading")}</p>}
      {state.kind === "failed" && <p className="why-text is-muted">{t("why.failed")}</p>}
      {state.kind === "ready" && (
        <>
          <p className="why-text" aria-live="polite">{state.data.text}</p>
          <p className="ds-popover-meta why-meta">
            <span>{t(state.data.basis === "model" ? "why.basis_model" : "why.basis_rule")}</span>
            {state.data.simulated && <span className="why-flag"> · {t("why.simulated")}</span>}
          </p>
          <p className="ds-popover-meta why-sources">
            {t("why.sources")}: {state.data.sources.join(", ")}
          </p>
        </>
      )}
    </Popover>
  );
}

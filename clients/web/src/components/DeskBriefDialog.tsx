/**
 * The desk brief: a morning brief or end-of-day report drafted from the desk's own data,
 * for a person to edit and send. Nothing is sent from here: Copy, a .txt download, or the
 * user's own email client (mailto) with the edited text.
 *
 * Opened from the search box (Ctrl K: "Draft the morning brief") or the Market overview,
 * through the `egn:open-brief` event so any surface can ask for it without owning it.
 */
import { useEffect, useRef, useState } from "react";
import { api, type DeskBriefDTO } from "@/api/client";

type Translate = (key: string, options?: Record<string, unknown>) => string;
export type BriefKind = "morning" | "eod";

export const OPEN_BRIEF_EVENT = "egn:open-brief";

/** Ask the shell to open the brief dialog. */
export function openDeskBrief(kind: BriefKind): void {
  window.dispatchEvent(new CustomEvent(OPEN_BRIEF_EVENT, { detail: { kind } }));
}

export function DeskBriefDialog({ language, t }: { language: string; t: Translate }) {
  const [kind, setKind] = useState<BriefKind | null>(null);
  const [brief, setBrief] = useState<DeskBriefDTO | null>(null);
  const [text, setText] = useState("");
  const [status, setStatus] = useState<"idle" | "loading" | "failed">("idle");
  const [copied, setCopied] = useState(false);
  const dialog = useRef<HTMLDialogElement>(null);

  useEffect(() => {
    const open = (event: Event) => {
      const detail = (event as CustomEvent<{ kind?: BriefKind }>).detail;
      setKind(detail?.kind === "eod" ? "eod" : "morning");
    };
    window.addEventListener(OPEN_BRIEF_EVENT, open);
    return () => window.removeEventListener(OPEN_BRIEF_EVENT, open);
  }, []);

  useEffect(() => {
    if (!kind) return undefined;
    if (!dialog.current?.open) dialog.current?.showModal();
    let live = true;
    setStatus("loading");
    setBrief(null);
    setCopied(false);
    api
      .deskBrief(kind, language.toLowerCase().startsWith("zh") ? "zh-CN" : "en")
      .then((response) => {
        if (!live) return;
        setBrief(response.data);
        setText(response.data.text);
        setStatus("idle");
      })
      .catch(() => live && setStatus("failed"));
    return () => {
      live = false;
    };
  }, [kind, language]);

  const close = () => {
    dialog.current?.close();
    setKind(null);
  };

  const copy = () => {
    void navigator.clipboard?.writeText(text).then(() => setCopied(true));
  };

  const download = () => {
    const blob = new Blob([text], { type: "text/plain;charset=utf-8" });
    const link = document.createElement("a");
    link.href = URL.createObjectURL(blob);
    link.download = `desk-brief-${kind}-${(brief?.as_of ?? "").slice(0, 10) || "draft"}.txt`;
    link.click();
    URL.revokeObjectURL(link.href);
  };

  const mail = `mailto:?subject=${encodeURIComponent(brief?.title ?? "")}&body=${encodeURIComponent(text)}`;

  return (
    <dialog ref={dialog} className="desk-brief" aria-labelledby="desk-brief-title" onClose={() => setKind(null)}>
      <header className="desk-brief-head">
        <h2 id="desk-brief-title">{t("brief.title")}</h2>
        <div className="desk-brief-kinds" role="group" aria-label={t("brief.title")}>
          {(["morning", "eod"] as const).map((option) => (
            <button
              key={option}
              type="button"
              aria-pressed={kind === option}
              onClick={() => setKind(option)}
            >
              {t(`brief.kind_${option}`)}
            </button>
          ))}
        </div>
        <button type="button" className="desk-brief-close" aria-label={t("brief.close")} onClick={close}>
          ×
        </button>
      </header>
      {status === "loading" && <p className="muted">{t("brief.loading")}</p>}
      {status === "failed" && <p role="alert">{t("brief.failed")}</p>}
      {brief && status === "idle" && (
        <>
          <p className="desk-brief-hint">
            {t("brief.edit_hint")}
            {brief.lead_basis === "model" && <> {t("brief.lead_model")}</>}
          </p>
          <textarea
            className="desk-brief-text"
            value={text}
            spellCheck
            aria-label={brief.title}
            onChange={(event) => {
              setText(event.target.value);
              setCopied(false);
            }}
          />
          <footer className="desk-brief-actions">
            <button type="button" onClick={copy}>{t(copied ? "brief.copied" : "brief.copy")}</button>
            <button type="button" onClick={download}>{t("brief.download")}</button>
            <a className="button-link" href={mail}>{t("brief.email")}</a>
          </footer>
        </>
      )}
    </dialog>
  );
}

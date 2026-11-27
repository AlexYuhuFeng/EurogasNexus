/**
 * The desk brief: a morning brief or end-of-day report drafted from the desk's own data,
 * for a person to edit and send. Nothing is sent from here: Copy, a .txt download, or the
 * user's own email client (mailto) with the edited text.
 *
 * Opened from the search box (Ctrl K: "Draft the morning brief") or the Market overview,
 * through the `egn:open-brief` event so any surface can ask for it without owning it.
 */
import { useEffect, useState } from "react";
import { api, type DeskBriefDTO } from "@/api/client";
import { Button, Dialog, Segmented, WorkProgress } from "@/components/ui";
import { useStagedProgress } from "@/app/hooks/useWorkProgress";
import { useAiAvailability } from "@/app/model/aiAvailability";

/** What drafting a brief reads, in order: shown while it works (UX_REFERENCE rule 18). */
const BRIEF_STAGES = ["brief.stage.prices", "brief.stage.outages", "brief.stage.position", "brief.stage.writing"] as const;

type Translate = (key: string, options?: Record<string, unknown>) => string;
export type BriefKind = "morning" | "eod";

export const OPEN_BRIEF_EVENT = "egn:open-brief";

/** Ask the shell to open the brief dialog. */
export function openDeskBrief(kind: BriefKind): void {
  window.dispatchEvent(new CustomEvent(OPEN_BRIEF_EVENT, { detail: { kind } }));
}

export function DeskBriefDialog({ language, t }: { language: string; t: Translate }) {
  const aiOn = useAiAvailability().available;
  const [kind, setKind] = useState<BriefKind | null>(null);
  const [brief, setBrief] = useState<DeskBriefDTO | null>(null);
  const [text, setText] = useState("");
  const [status, setStatus] = useState<"idle" | "loading" | "failed">("idle");
  const [copied, setCopied] = useState(false);

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

  const progress = useStagedProgress(status === "loading", BRIEF_STAGES.length, 1500);
  const close = () => setKind(null);

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
    <Dialog
      open={kind !== null}
      onClose={close}
      title={t("brief.title")}
      closeLabel={t("brief.close")}
      size="lg"
      className="desk-brief"
      id="desk-brief"
      headerActions={
        <Segmented
          label={t("brief.kind")}
          options={(["morning", "eod"] as const).map((option) => ({ value: option, label: t(`brief.kind_${option}`) }))}
          value={kind}
          onChange={setKind}
        />
      }
      footer={
        brief && status === "idle" ? (
          <>
            <Button onClick={copy}>{t(copied ? "brief.copied" : "brief.copy")}</Button>
            <Button onClick={download}>{t("brief.download")}</Button>
            <a className="ds-button secondary-button ds-size-sm" href={mail}>{t("brief.email")}</a>
          </>
        ) : undefined
      }
    >
      {status === "loading" && (
        // The space the draft will take is kept, so the dialog does not jump when it arrives.
        <WorkProgress
          label={t("brief.loading")}
          stages={BRIEF_STAGES.map((stage) => t(stage))}
          current={progress.stage}
          reserve="340px"
        />
      )}
      {status === "failed" && <p role="alert">{t("brief.failed")}</p>}
      {brief && status === "idle" && (
        <>
          <p className="desk-brief-hint">
            {t("brief.edit_hint")}
            {brief.lead_basis === "model" && <> {t("brief.lead_model")}</>}
            {brief.lead_basis !== "model" && !aiOn && <> {t("ai.off.brief")}</>}
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
        </>
      )}
    </Dialog>
  );
}

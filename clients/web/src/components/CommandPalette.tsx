/**
 * Command palette (Architecture V2 Wave 9, extended by Wave 7).
 *
 * One keyboard-first entry point to the product surface: navigation, object
 * inspection, shell utilities and the five canonical AI actions, derived from the
 * Wave 1 command contract rather than a hand-maintained list. The palette is a
 * shell element, so it renders the same commands from any workspace.
 *
 * Wave 7 makes the AI commands real: choosing one opens the Copilot surface inside
 * this overlay instead of closing the palette and doing nothing. A host that owns
 * its own AI invocation surface passes `onAiAction` to the controller and this
 * component then defers to it; a host that has none gets the mounted Copilot, which
 * is why no AI command is offered without an invocation surface.
 *
 * Accessibility: a modal dialog with a labelled search input, an option list driven
 * by the contract's ranking, arrow/Enter/Escape keyboard handling, unavailable
 * commands shown with their reason instead of being hidden, and Escape dissolving
 * only the innermost surface (Copilot first, palette second).
 */

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";

import type { AnswerTarget } from "@/app/answer/answerModel";
import { paletteShortcut, paletteTagKey, type PaletteCommand } from "@/app/experience/commandPalette";
import type { AiActionKind } from "@/app/experience/vocabulary";
import type { AnswerBarController } from "@/app/hooks/useAnswerBar";
import {
  ANSWER_ROW_ID,
  ASK_ROW_ID,
  AnswerRow,
  AskPanel,
  AskRow,
  answerAnnouncement,
  answerText,
} from "@/components/AnswerBar";
import { CopilotHost } from "@/components/CopilotPanel";
import "./CommandPalette.css";

interface CommandPaletteProps {
  open: boolean;
  query: string;
  results: readonly PaletteCommand[];
  activeIndex: number;
  unavailable: ReadonlySet<string>;
  labelFor: (command: PaletteCommand) => string;
  reasonFor: (command: PaletteCommand) => string | null;
  t: (key: string) => string;
  onQueryChange: (value: string) => void;
  /** Move the selection by `delta` over `count` rows (the answer rows and the results). */
  onMove: (delta: number, count?: number) => void;
  onRunActive: () => void;
  onRun: (command: PaletteCommand) => void;
  onClose: () => void;
  /**
   * Controlled Copilot action. Absent means the palette owns it, which is how the
   * shell mounts the Copilot without a second shell region.
   */
  aiAction?: AiActionKind | null;
  onAiActionChange?: (action: AiActionKind | null) => void;
  /**
   * Who invokes a canonical AI action. `"palette"` (the default) means this overlay
   * hosts the Copilot surface; `"host"` means the host supplied `onAiAction` to the
   * controller and this component defers to it.
   */
  aiSurface?: "palette" | "host";
  /**
   * The answer bar (instant answers, look-ups and Ask) above the results. Absent, the
   * palette is the command list it was.
   */
  answerBar?: AnswerBarController;
  /** Open where an answer's number lives (a mode's task, a glossary entry). */
  onAnswerOpen?: (target: AnswerTarget) => void;
  /** Hand an asked question to Research → Reports. */
  onOpenReport?: (question: string) => void;
}

export function CommandPalette({
  open,
  query,
  results,
  activeIndex,
  unavailable,
  labelFor,
  reasonFor,
  t,
  onQueryChange,
  onMove,
  onRunActive,
  onRun,
  onClose,
  aiAction,
  onAiActionChange,
  aiSurface = "palette",
  answerBar,
  onAnswerOpen,
  onOpenReport,
}: CommandPaletteProps) {
  const { t: translate } = useTranslation();
  const [copied, setCopied] = useState<string | null>(null);
  const ask = answerBar?.ask ?? { status: "idle" as const };
  const askOpen = ask.status !== "idle";
  const answer = askOpen ? null : answerBar?.answer ?? null;
  const askRow = !askOpen && answerBar?.askOffered ? answerBar.askQuestion : null;
  /** The rows above the results: the answer, then the Ask offer. */
  const leading = useMemo(
    () => [...(answer ? (["answer"] as const) : []), ...(askRow ? (["ask"] as const) : [])],
    [answer, askRow],
  );
  const rowCount = askOpen ? 0 : leading.length + results.length;
  const rowId = (index: number) =>
    index < leading.length
      ? leading[index] === "answer" ? ANSWER_ROW_ID : ASK_ROW_ID
      : results[index - leading.length] ? `palette-${results[index - leading.length].id}` : undefined;
  const announcement = copied ?? (answer ? answerAnnouncement(answer, translate) : "");
  useEffect(() => { setCopied(null); }, [query]);
  const dialogRef = useRef<HTMLDivElement>(null);
  const returnFocus = useRef<HTMLElement | null>(null);
  useEffect(() => {
    function rememberFocus(event: FocusEvent) {
      if (event.target instanceof HTMLElement && !event.target.closest(".command-palette")) {
        returnFocus.current = event.target;
      }
    }
    document.addEventListener("focusin", rememberFocus);
    return () => document.removeEventListener("focusin", rememberFocus);
  }, []);
  const [ownAiAction, setOwnAiAction] = useState<AiActionKind | null>(null);
  const copilotAction = aiAction === undefined ? ownAiAction : aiAction;

  const setCopilotAction = useCallback(
    (action: AiActionKind | null) => {
      if (aiAction === undefined) setOwnAiAction(action);
      onAiActionChange?.(action);
    },
    [aiAction, onAiActionChange],
  );

  // Closing the palette closes the surface it hosted; nothing stays mounted behind it.
  useEffect(() => {
    if (!open) setOwnAiAction(null);
  }, [open]);

  // Escape dissolves the innermost surface first: the Copilot returns to the command
  // list, and a second Escape closes the palette. The capture listener runs before
  // the controller's bubble-phase shortcut handler, so one keypress has one effect.
  useEffect(() => {
    if (!open || !copilotAction) return;
    function onKeyDown(event: KeyboardEvent) {
      if (event.key !== "Escape") return;
      event.preventDefault();
      event.stopPropagation();
      setCopilotAction(null);
    }
    window.addEventListener("keydown", onKeyDown, true);
    return () => window.removeEventListener("keydown", onKeyDown, true);
  }, [open, copilotAction, setCopilotAction]);

  // Escape leaves an asked answer (and cancels a running one) before it closes the palette.
  useEffect(() => {
    if (!open || !askOpen || !answerBar) return;
    const cancel = answerBar.cancelAsk;
    function onKeyDown(event: KeyboardEvent) {
      if (event.key !== "Escape") return;
      event.preventDefault();
      event.stopPropagation();
      cancel();
    }
    window.addEventListener("keydown", onKeyDown, true);
    return () => window.removeEventListener("keydown", onKeyDown, true);
  }, [open, askOpen, answerBar]);

  useEffect(() => {
    if (!open) return;
    const previous = returnFocus.current;
    function trapFocus(event: KeyboardEvent) {
      if (event.key !== "Tab") return;
      const controls = Array.from(dialogRef.current?.querySelectorAll<HTMLElement>(
        'button:not(:disabled), input:not(:disabled), select:not(:disabled), textarea:not(:disabled), a[href], [tabindex="0"]',
      ) ?? []).filter((element) => element.getClientRects().length > 0);
      if (!controls.length) return;
      const first = controls[0], last = controls[controls.length - 1];
      if (event.shiftKey && (document.activeElement === first || !dialogRef.current?.contains(document.activeElement))) {
        event.preventDefault(); last.focus();
      } else if (!event.shiftKey && (document.activeElement === last || !dialogRef.current?.contains(document.activeElement))) {
        event.preventDefault(); first.focus();
      }
    }
    window.addEventListener("keydown", trapFocus, true);
    return () => {
      window.removeEventListener("keydown", trapFocus, true);
      if (previous instanceof HTMLElement && previous.isConnected) previous.focus();
    };
  }, [open]);

  const activeRowId = rowId(activeIndex);
  useEffect(() => {
    if (open && activeRowId) document.getElementById(activeRowId)?.scrollIntoView?.({ block: "nearest" });
  }, [open, activeRowId]);

  if (!open) return null;

  function copyAnswer(withUnit: boolean) {
    if (!answer?.copy) return;
    const text = withUnit ? answer.copy.withUnit : answer.copy.value;
    void globalThis.navigator?.clipboard?.writeText(text).catch(() => undefined);
    setCopied(translate("answer.copied", { value: text }));
  }

  /** Enter or a click on one of the rows above the results. */
  function chooseLeading(row: "answer" | "ask") {
    if (row === "ask") {
      answerBar?.runAsk();
      return;
    }
    if (answer?.target) onAnswerOpen?.(answer.target);
    else copyAnswer(false);
  }

  /** Tab accepts the answer into the field: the term, the instrument, or the result to go on with. */
  function completion(): string | null {
    if (!answer) return null;
    if (answer.kind === "calc" && answer.copy) return answer.copy.value;
    if (answer.kind === "glossary" || answer.kind === "price") {
      const label = answerText(answer.label, translate);
      return label && label !== query ? label : null;
    }
    return null;
  }

  /** Run a command, or open the Copilot for a canonical AI action. */
  function activate(command: PaletteCommand) {
    if (unavailable.has(command.id)) return;
    if (command.target.aiAction && aiSurface === "palette") {
      setCopilotAction(command.target.aiAction);
      return;
    }
    onRun(command);
  }

  if (copilotAction) {
    return (
      <div className="command-palette-backdrop" role="presentation" onClick={onClose}>
        <div
          ref={dialogRef}
          className="command-palette copilot"
          role="dialog"
          aria-modal="true"
          aria-label={t("experience.copilot.title")}
          onClick={(event) => event.stopPropagation()}
        >
          <CopilotHost
            action={copilotAction}
            t={t}
            onClose={() => setCopilotAction(null)}
            onSelectAction={setCopilotAction}
          />
        </div>
      </div>
    );
  }

  return (
    <div className="command-palette-backdrop" role="presentation" onClick={onClose}>
      <div
        ref={dialogRef}
        className={askOpen ? "command-palette answer-asking" : "command-palette"}
        role="dialog"
        aria-modal="true"
        aria-label={t("experience.palette.title")}
        onClick={(event) => event.stopPropagation()}
      >
        <input
          className="command-palette-input"
          type="text"
          autoFocus
          value={query}
          placeholder={t("experience.palette.placeholder")}
          aria-label={t("experience.palette.placeholder")}
          aria-controls="command-palette-results"
          role="combobox"
          aria-expanded={!askOpen}
          aria-autocomplete="list"
          aria-activedescendant={askOpen ? undefined : activeRowId}
          onChange={(event) => {
            if (askOpen) answerBar?.cancelAsk();
            onQueryChange(event.target.value);
          }}
          onKeyDown={(event) => {
            if (event.nativeEvent.isComposing) return;
            const input = event.currentTarget;
            if (event.key === "ArrowDown") {
              event.preventDefault();
              onMove(1, rowCount);
            } else if (event.key === "ArrowUp") {
              event.preventDefault();
              onMove(-1, rowCount);
            } else if (event.key === "Enter") {
              event.preventDefault();
              if (askOpen) return;
              if (activeIndex < leading.length) {
                chooseLeading(leading[activeIndex]);
                return;
              }
              const active = results[activeIndex - leading.length];
              if (active) activate(active);
              else if (!leading.length) onRunActive();
            } else if (
              (event.ctrlKey || event.metaKey) && !event.altKey && event.key.toLowerCase() === "c" &&
              leading[activeIndex] === "answer" && answer?.copy && input.selectionStart === input.selectionEnd
            ) {
              event.preventDefault();
              copyAnswer(event.shiftKey);
            } else if (event.key === "Tab" && !event.shiftKey && completion()) {
              event.preventDefault();
              onQueryChange(completion() as string);
            } else if (event.key === "Escape") {
              event.preventDefault();
              onClose();
            }
          }}
        />
        <div className="answer-live" aria-live="polite" aria-atomic="true">{announcement}</div>
        {ask.status !== "idle" && answerBar ? (
          <AskPanel
            state={ask}
            onCancel={answerBar.cancelAsk}
            onRetry={() => answerBar.runAsk(ask.question)}
            onOpen={(target) => onAnswerOpen?.(target)}
            onOpenReport={(question) => onOpenReport?.(question)}
          />
        ) : (
        <ul
          className="command-palette-results"
          id="command-palette-results"
          role="listbox"
          aria-label={t("experience.palette.title")}
        >
          {answer && (
            <AnswerRow
              answer={answer}
              active={activeIndex === 0}
              onHover={() => onMove(0 - activeIndex, rowCount)}
              onChoose={() => chooseLeading("answer")}
            />
          )}
          {askRow && answerBar && (
            <AskRow
              question={askRow}
              aiAllowed={answerBar.aiAllowed}
              active={activeIndex === leading.indexOf("ask")}
              onHover={() => onMove(leading.indexOf("ask") - activeIndex, rowCount)}
              onChoose={() => chooseLeading("ask")}
            />
          )}
          {results.map((command, resultIndex) => {
            const index = resultIndex + leading.length;
            const disabled = unavailable.has(command.id);
            // An AI command is disabled for exactly three reasons, and the host
            // already names the first two; the third is the missing evidence the
            // host cannot see, so it is named here instead of left blank.
            const reason =
              reasonFor(command) ??
              (disabled && command.group === "ai"
                ? "experience.palette.unavailable_evidence"
                : null);
            return (
              <li key={command.id}>
                <button
                  type="button"
                  id={`palette-${command.id}`}
                  role="option"
                  aria-selected={index === activeIndex}
                  aria-disabled={disabled}
                  className={index === activeIndex ? "active" : undefined}
                  onMouseEnter={() => onMove(index - activeIndex, rowCount)}
                  onClick={() => activate(command)}
                >
                  <span className="command-palette-group" data-palette-kind={command.kind ?? command.group}>{t(paletteTagKey(command))}</span>
                  <span className="command-palette-label">{labelFor(command)}</span>
                  {/* The shortcut, from the declaration the key handler reads (#34). */}
                  {paletteShortcut(command, /Mac|iPhone|iPad/.test(globalThis.navigator?.platform ?? "")) && (
                    <kbd className="command-palette-kbd">
                      {paletteShortcut(command, /Mac|iPhone|iPad/.test(globalThis.navigator?.platform ?? ""))}
                    </kbd>
                  )}
                  {reason && <span className="command-palette-reason">{t(reason)}</span>}
                </button>
              </li>
            );
          })}
          {results.length === 0 && leading.length === 0 && (
            <li className="command-palette-empty">{t("experience.palette.empty")}</li>
          )}
        </ul>
        )}
        <footer className="command-palette-help">{t("experience.palette.keyboard_help")}</footer>
      </div>
    </div>
  );
}

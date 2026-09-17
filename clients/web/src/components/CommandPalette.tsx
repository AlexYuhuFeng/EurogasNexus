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

import { useCallback, useEffect, useState } from "react";

import type { PaletteCommand } from "@/app/experience/commandPalette";
import type { AiActionKind } from "@/app/experience/vocabulary";
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
  onMove: (delta: number) => void;
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
}: CommandPaletteProps) {
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

  if (!open) return null;

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
        className="command-palette"
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
          aria-activedescendant={results[activeIndex] ? `palette-${results[activeIndex].id}` : undefined}
          onChange={(event) => onQueryChange(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "ArrowDown") {
              event.preventDefault();
              onMove(1);
            } else if (event.key === "ArrowUp") {
              event.preventDefault();
              onMove(-1);
            } else if (event.key === "Enter") {
              event.preventDefault();
              const active = results[activeIndex];
              if (active) activate(active);
              else onRunActive();
            } else if (event.key === "Escape") {
              event.preventDefault();
              onClose();
            }
          }}
        />
        <ul
          className="command-palette-results"
          id="command-palette-results"
          role="listbox"
          aria-label={t("experience.palette.title")}
        >
          {results.map((command, index) => {
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
                  onMouseEnter={() => onMove(index - activeIndex)}
                  onClick={() => activate(command)}
                >
                  <span className="command-palette-group">{t(`experience.palette.group.${command.group}`)}</span>
                  <span className="command-palette-label">{labelFor(command)}</span>
                  {reason && <span className="command-palette-reason">{t(reason)}</span>}
                </button>
              </li>
            );
          })}
          {results.length === 0 && (
            <li className="command-palette-empty">{t("experience.palette.empty")}</li>
          )}
        </ul>
      </div>
    </div>
  );
}

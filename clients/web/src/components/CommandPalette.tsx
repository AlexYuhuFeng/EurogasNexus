/**
 * Command palette (Architecture V2 Wave 9).
 *
 * One keyboard-first entry point to the product surface: navigation, object
 * inspection and shell utilities, derived from the Wave 1 command contract rather
 * than a hand-maintained list. The palette is a shell element, so it renders the
 * same commands from any workspace.
 *
 * Accessibility: a modal dialog with a labelled search input, an option list
 * driven by the contract's ranking, arrow/Enter/Escape keyboard handling and
 * unavailable commands shown with their reason instead of being hidden.
 */

import type { PaletteCommand } from "@/app/experience/commandPalette";
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
}: CommandPaletteProps) {
  if (!open) return null;

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
              onRunActive();
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
            const reason = reasonFor(command);
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
                  onClick={() => onRun(command)}
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

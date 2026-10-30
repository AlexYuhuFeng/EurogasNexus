import { useEffect, useRef } from "react";

import { WORKSTATION_SHORTCUTS } from "@/app/host/workstation";

type Translate = (key: string) => string;

/** Shortcuts that act inside one surface rather than on the shell. */
const SURFACE_SHORTCUTS = [
  { id: "ladder-move", binding: "← ↑ → ↓", scope: "ladder" },
  { id: "palette-close", binding: "Escape", scope: "palette" },
  { id: "shortcuts-open", binding: "?", scope: "shell" },
] as const;

function isMac(): boolean {
  return typeof navigator !== "undefined" && /Mac|iPhone|iPad/.test(navigator.platform);
}

/** Show Cmd for Ctrl on macOS, so the table matches the keyboard in front of the user. */
export function displayBinding(binding: string, mac = isMac()): string {
  return mac ? binding.replace(/Ctrl\+/g, "⌘").replace(/Alt\+/g, "⌥").replace(/Shift\+/g, "⇧") : binding;
}

interface KeyboardShortcutsDialogProps {
  open: boolean;
  onClose: () => void;
  t: Translate;
}

export function KeyboardShortcutsDialog({ open, onClose, t }: KeyboardShortcutsDialogProps) {
  const closeRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (!open) return;
    const previous = document.activeElement as HTMLElement | null;
    closeRef.current?.focus();
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        onClose();
      }
    };
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("keydown", onKeyDown);
      previous?.focus?.();
    };
  }, [open, onClose]);

  if (!open) return null;
  const rows = [...WORKSTATION_SHORTCUTS, ...SURFACE_SHORTCUTS];
  return (
    <div className="shortcuts-backdrop" onPointerDown={(event) => event.target === event.currentTarget && onClose()}>
      <div className="shortcuts-dialog" role="dialog" aria-modal="true" aria-labelledby="shortcuts-title">
        <div className="shortcuts-header">
          <h2 id="shortcuts-title">{t("shortcuts.title")}</h2>
          <button ref={closeRef} type="button" className="ghost" onClick={onClose} aria-label={t("shortcuts.close")}>
            ×
          </button>
        </div>
        <table className="shortcuts-table">
          <tbody>
            {rows.map((row) => (
              <tr key={row.id}>
                <th scope="row">{t(`shortcuts.${row.id}`)}</th>
                <td><kbd>{displayBinding(row.binding)}</kbd></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

/** "?" opens the shortcut list unless the user is typing. */
export function isShortcutHelpKey(event: KeyboardEvent): boolean {
  const target = event.target as HTMLElement | null;
  const typing = Boolean(target?.closest("input, textarea, select, [contenteditable='true']"));
  return !typing && !event.ctrlKey && !event.metaKey && !event.altKey && event.key === "?";
}

import { WORKSTATION_SHORTCUTS } from "@/app/host/workstation";
import { Dialog } from "@/components/ui";

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

/** The shortcut list, in the one Dialog (native modal: Escape, backdrop, focus kept inside). */
export function KeyboardShortcutsDialog({ open, onClose, t }: KeyboardShortcutsDialogProps) {
  const rows = [...WORKSTATION_SHORTCUTS, ...SURFACE_SHORTCUTS];
  return (
    <Dialog open={open} onClose={onClose} title={t("shortcuts.title")} closeLabel={t("shortcuts.close")} size="sm" id="shortcuts">
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
    </Dialog>
  );
}

/** "?" opens the shortcut list unless the user is typing. */
export function isShortcutHelpKey(event: KeyboardEvent): boolean {
  const target = event.target as HTMLElement | null;
  const typing = Boolean(target?.closest("input, textarea, select, [contenteditable='true']"));
  return !typing && !event.ctrlKey && !event.metaKey && !event.altKey && event.key === "?";
}

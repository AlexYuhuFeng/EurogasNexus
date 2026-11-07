import { useEffect } from "react";

/**
 * Ask before the page unloads (refresh, tab close, sign-out redirect) while an editor holds
 * unsaved changes (#32). Moving between pages inside the app keeps drafts in memory, so only
 * a real unload can lose them; the browser shows its own wording for the prompt.
 */
export function useUnsavedChangesGuard(dirty: boolean): void {
  useEffect(() => {
    if (!dirty) return undefined;
    const warn = (event: BeforeUnloadEvent) => {
      event.preventDefault();
      // Older engines show the prompt only when returnValue is set.
      event.returnValue = "";
    };
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [dirty]);
}

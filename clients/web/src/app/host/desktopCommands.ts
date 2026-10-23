/** Native menu events carry command IDs only, never data or authority. */
import { resolveHostKind } from "./hostCapabilities";

export async function listenDesktopCommands(onCommand: (id: string) => void): Promise<() => void> {
  if (resolveHostKind() !== "desktop") return () => {};
  const { listen } = await import("@tauri-apps/api/event");
  return listen<string>("workstation-command", (event) => {
    if (typeof event.payload === "string") onCommand(event.payload);
  });
}

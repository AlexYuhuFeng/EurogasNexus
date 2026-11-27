/**
 * Whether AI can be used for the signed-in person now, and why not (`GET /api/me` → `ai`).
 *
 * Small-desk plan 3.6: an administrator can switch every AI feature off. Then every AI control
 * disappears or says plainly that AI is off, and every feature still works by rule (the server
 * sends nothing to a model and answers with the rule text). This grants nothing: the server
 * decides each call again.
 *
 * `reason`: `on`, `switched_off` (the administrator or the installation), `not_configured` (no
 * model endpoint), `no_key`, `role`. A server older than this field reads as available, so
 * the controls behave as before and the server's own answer says when AI was not used.
 */
import { useApiStore } from "@/stores/api";

export interface AiAvailability {
  available: boolean;
  reason: string;
}

export function aiAvailabilityOf(user: { ai?: AiAvailability | null } | null | undefined): AiAvailability {
  const ai = user?.ai;
  if (!ai || typeof ai.available !== "boolean") return { available: true, reason: "on" };
  return { available: ai.available, reason: String(ai.reason ?? (ai.available ? "on" : "switched_off")) };
}

export function useAiAvailability(): AiAvailability {
  const user = useApiStore((state) => state.currentUser);
  return aiAvailabilityOf(user);
}

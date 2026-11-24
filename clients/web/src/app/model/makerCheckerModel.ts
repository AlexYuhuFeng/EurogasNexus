/**
 * Maker-checker on limits and reference data (P-17): what a save answered, how a proposed
 * change reads (each field before and after), and who set and approved a figure.
 *
 * A write under four eyes answers 202 with the proposal and changes nothing until a different
 * authorised person approves it; these helpers turn that answer into words. Pure, no React.
 */

import type { ChangeRequestDTO, FigureProvenanceDTO, GovernedSaveDTO } from "../../api/client.ts";

export type SaveOutcome = "saved" | "proposed" | "unchanged";

/** What a save did: applied at once, proposed for approval, or nothing to change. */
export function saveOutcome(answer: GovernedSaveDTO | null | undefined): SaveOutcome {
  if (answer?.pending_approval) return "proposed";
  if (answer && Array.isArray(answer.changed) && answer.changed.length === 0 && answer.created === false) {
    return "unchanged";
  }
  return "saved";
}

/** A field's value as text: a dash for none, lists joined, booleans in words supplied. */
export function changeValueText(value: unknown, words: { yes: string; no: string } = { yes: "yes", no: "no" }): string {
  if (value === null || value === undefined || value === "") return "–";
  if (typeof value === "boolean") return value ? words.yes : words.no;
  if (Array.isArray(value)) return value.length ? value.map((item) => changeValueText(item, words)).join(", ") : "–";
  if (typeof value === "object") {
    return Object.entries(value as Record<string, unknown>)
      .map(([key, item]) => `${key}: ${changeValueText(item, words)}`)
      .join(", ");
  }
  return String(value);
}

/** A field name as words ("limit_amount" → "limit amount"). */
export function fieldLabel(name: string): string {
  return name.replace(/_/g, " ");
}

/** The open proposals for one kind, by the record they would change. */
export function pendingByTarget(
  changes: readonly ChangeRequestDTO[] | null | undefined,
  kind: string,
): Map<string, ChangeRequestDTO> {
  const found = new Map<string, ChangeRequestDTO>();
  for (const change of changes ?? []) {
    if (change.state === "pending" && change.kind === kind) found.set(change.target_key, change);
  }
  return found;
}

/** The person's name when the server gave one, else their principal id. */
export function personName(name: string | null | undefined, id: string | null | undefined): string {
  return (name ?? "").trim() || (id ?? "").trim() || "–";
}

export interface ProvenanceWords {
  /** Set by one person and approved by another. */
  approved: { setBy: string; approvedBy: string; at: string | null };
  /** Set by one person without a second approval (four eyes off, or before P-17). */
  single: { setBy: string; at: string | null };
}

/** Who set a figure and, when a second person approved it, who; null when nothing is known. */
export function provenanceParts(
  provenance: FigureProvenanceDTO | null | undefined,
): { kind: "approved"; value: ProvenanceWords["approved"] } | { kind: "single"; value: ProvenanceWords["single"] } | null {
  if (!provenance || (!provenance.set_by && !provenance.approved_by)) return null;
  const setBy = personName(provenance.set_by_name, provenance.set_by);
  if (provenance.second_approval && provenance.approved_by) {
    return {
      kind: "approved",
      value: {
        setBy,
        approvedBy: personName(provenance.approved_by_name, provenance.approved_by),
        at: provenance.approved_at_utc ?? provenance.set_at_utc,
      },
    };
  }
  return { kind: "single", value: { setBy, at: provenance.set_at_utc } };
}

/** Pending first (oldest first, so the longest waiting is on top), then decided newest first. */
export function orderChanges(changes: readonly ChangeRequestDTO[]): ChangeRequestDTO[] {
  const time = (value: string | null) => (value ? Date.parse(value) || 0 : 0);
  const pending = changes
    .filter((change) => change.state === "pending")
    .sort((a, b) => time(a.proposed_at_utc) - time(b.proposed_at_utc));
  const decided = changes
    .filter((change) => change.state !== "pending")
    .sort((a, b) => time(b.decided_at_utc) - time(a.decided_at_utc));
  return [...pending, ...decided];
}

/** Refusal codes the change endpoints answer, each with its own sentence on screen. */
export const CHANGE_ERROR_CODES = [
  "four_eyes_required",
  "own_mandate",
  "segregation_of_duties",
  "permission_denied",
  "named_principal_required",
  "change_pending",
  "change_not_pending",
  "change_stale",
  "change_not_found",
  "note_required",
  "not_the_proposer",
  "withdraw_own_change",
] as const;

/** The i18n key for a refusal's code (`changes.error.<code>`), or null for any other failure. */
export function changeErrorKey(detail: unknown): string | null {
  const code = detail && typeof detail === "object" ? (detail as { code?: unknown }).code : null;
  return typeof code === "string" && (CHANGE_ERROR_CODES as readonly string[]).includes(code)
    ? `changes.error.${code}`
    : null;
}

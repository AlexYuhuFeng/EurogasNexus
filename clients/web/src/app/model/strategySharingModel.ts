/** Sharing is read access inside this deployment, never a grant to write or export. */
export type SharingVisibility = "PRIVATE" | "PUBLIC" | "GROUPS";
export interface SharingDraft { visibility: SharingVisibility; group_ids: string[] }
export function sharingRequest(
  canManage: boolean,
  draft: SharingDraft,
  availableGroupIds: readonly string[] | null,
): SharingDraft | null {
  if (!canManage || !["PRIVATE", "PUBLIC", "GROUPS"].includes(draft.visibility)) return null;
  if (draft.visibility !== "GROUPS") return { visibility: draft.visibility, group_ids: [] };
  const ids = [...new Set(draft.group_ids)];
  if (!availableGroupIds || ids.length === 0 || ids.length > 100 ||
      ids.some((id) => !availableGroupIds.includes(id))) return null;
  return { visibility: "GROUPS", group_ids: ids };
}

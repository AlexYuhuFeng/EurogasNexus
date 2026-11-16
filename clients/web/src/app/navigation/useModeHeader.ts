/**
 * The task row of the mode the user is in (WF-05). Every workspace that renders a mode's page
 * draws the same row: the mode's name as the page title and the mode's tasks as tabs, filtered by
 * what the caller's identity can use. A tab that belongs to another page opens that page; one on
 * the same page switches the page's own task. The URL stays the page's address.
 */
import { useApiStore } from "@/stores/api";
import type { WorkspacePageId } from "@/workspaceNavigation";

import { modeLocationFor, visibleModes, type ModeTask } from "./modeNavigation";

type Translate = (key: string, options?: Record<string, unknown>) => string;

export interface ModeHeader {
  /** The mode's name (the page title), or null on a utility page. */
  title: string | null;
  modeId: string | null;
  tabs: { id: string; label: string; shortLabel?: string }[];
  activeId: string;
  tabLabel: string;
  activeTask: ModeTask | null;
  onActivate: (id: string) => void;
}

export function useModeHeader(
  page: WorkspacePageId,
  pageTask: string | undefined,
  openWorkspace: (page: WorkspacePageId, task?: string) => void,
  t: Translate,
): ModeHeader {
  const user = useApiStore((state) => state.currentUser);
  const location = modeLocationFor(page, pageTask);
  const mode = location ? visibleModes(user).find((item) => item.id === location.mode.id) ?? null : null;
  const tasks = mode?.tasks ?? [];
  return {
    title: mode ? t(mode.labelKey) : null,
    modeId: mode?.id ?? null,
    tabs: tasks.map((task) => ({ id: task.id, label: t(task.labelKey), shortLabel: task.shortLabelKey ? t(task.shortLabelKey) : undefined })),
    activeId: location?.task.id ?? "",
    tabLabel: mode ? t("nav.mode.tasks", { mode: t(mode.labelKey) }) : "",
    activeTask: location?.task ?? null,
    onActivate: (id) => {
      const task = tasks.find((item) => item.id === id);
      if (task) openWorkspace(task.page, task.pageTask);
    },
  };
}

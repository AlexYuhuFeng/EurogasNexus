export function workspaceTabButtonId(idPrefix: string, tabId: string): string {
  return `${idPrefix}-${tabId}`;
}

export function getNextWorkspaceTabIndex(
  currentIndex: number,
  tabCount: number,
  key: string,
): number | null {
  if (!Number.isInteger(currentIndex) || currentIndex < 0 || tabCount <= 0) return null;
  if (key === "ArrowRight") return (currentIndex + 1) % tabCount;
  if (key === "ArrowLeft") return (currentIndex - 1 + tabCount) % tabCount;
  if (key === "Home") return 0;
  if (key === "End") return tabCount - 1;
  return null;
}

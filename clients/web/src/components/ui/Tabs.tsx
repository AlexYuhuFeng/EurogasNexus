/**
 * Tabs (UX-02): the one tab list. Every task-tab row and the top bar's primary destinations
 * use it (through WorkspaceTabs), so they share one behaviour:
 *
 * - a `tablist` of `tab` buttons, the active one `aria-selected` and the only Tab stop
 *   (roving tabindex), each pointing at the panel it controls;
 * - Left/Right move and activate (automatic activation: a tab switch is cheap and local),
 *   Home/End go to the ends, wrapping at either end;
 * - a short label at compact width, the full label staying the accessible name.
 *
 * `variant` picks the look only: `line` (task tabs under a page title) or `nav` (the top bar).
 * A choice that changes the view of the same data is not a tab: use Segmented.
 */
import { type KeyboardEvent, type ReactNode } from "react";

import { rovingIndex } from "./keyboard";

export interface TabItem<T extends string> {
  id: T;
  label: ReactNode;
  /** Shown at compact width; the full label stays the accessible name. */
  shortLabel?: string;
  /** The panel this tab controls, when it is not the shared panel. */
  controls?: string;
  /** A count or marker after the label (open alerts). */
  badge?: ReactNode;
}

export interface TabsProps<T extends string> {
  idPrefix: string;
  label: string;
  tabs: readonly TabItem<T>[];
  activeId: T;
  panelId?: string;
  onChange: (id: T) => void;
  variant?: "line" | "nav";
  className?: string;
  /** Extra attributes on the list (a shell-region marker). */
  dataAttributes?: Record<string, string | undefined>;
  /** Render as a `<nav>` landmark holding the tablist (the top bar). */
  landmark?: boolean;
}

export function tabId(idPrefix: string, id: string): string {
  return `${idPrefix}-${id}`;
}

export function Tabs<T extends string>({
  idPrefix,
  label,
  tabs,
  activeId,
  panelId,
  onChange,
  variant = "line",
  className,
  dataAttributes,
  landmark = false,
}: TabsProps<T>) {
  const activeIndex = Math.max(0, tabs.findIndex((tab) => tab.id === activeId));

  const onKeyDown = (event: KeyboardEvent<HTMLButtonElement>, index: number) => {
    const next = rovingIndex(index, tabs.length, event.key);
    if (next === null) return;
    event.preventDefault();
    const target = tabs[next];
    if (!target) return;
    onChange(target.id);
    // Focus the new tab now; the parent's re-render keeps it the Tab stop.
    const list = event.currentTarget.parentElement;
    list?.querySelectorAll<HTMLButtonElement>('[role="tab"]')[next]?.focus();
  };

  const Element = landmark ? "nav" : "div";
  return (
    <Element
      className={["ds-tabs", `ds-tabs-${variant}`, className].filter(Boolean).join(" ")}
      role="tablist"
      aria-label={label}
      {...dataAttributes}
    >
      {tabs.map((tab, index) => {
        const selected = index === activeIndex;
        return (
          <button
            key={tab.id}
            id={tabId(idPrefix, tab.id)}
            type="button"
            role="tab"
            aria-selected={selected}
            aria-controls={tab.controls ?? panelId}
            tabIndex={selected ? 0 : -1}
            className={selected ? "active" : undefined}
            onClick={() => onChange(tab.id)}
            onKeyDown={(event) => onKeyDown(event, index)}
            aria-label={tab.shortLabel && typeof tab.label === "string" ? tab.label : undefined}
          >
            {tab.shortLabel ? (
              <>
                <span className="tab-label-full">{tab.label}</span>
                <span className="tab-label-short" aria-hidden="true">
                  {tab.shortLabel}
                </span>
              </>
            ) : (
              tab.label
            )}
            {tab.badge}
          </button>
        );
      })}
    </Element>
  );
}

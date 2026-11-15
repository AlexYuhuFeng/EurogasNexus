/**
 * Toolbar (UX-02): one dense row of controls over a table or a map (28 px controls, 8 px gaps,
 * wrapping only on a narrow screen), with a start group and an end group.
 *
 * It is a labelled `toolbar`. Left/Right move between its buttons when a button has focus;
 * inputs and selects keep their own arrow keys. Every control stays in the Tab order: a desk
 * toolbar mixes selects, inputs and buttons, and Tab must reach each of them directly. That is
 * a recorded choice (DESIGN_TOKENS.md), not the single-Tab-stop toolbar of the ARIA practices.
 */
import type { KeyboardEvent, ReactNode } from "react";

import { rovingIndex } from "./keyboard";

export interface ToolbarProps {
  label: string;
  children: ReactNode;
  /** Pushed to the end of the row (refresh, export, last-updated). */
  end?: ReactNode;
  className?: string;
}

export function Toolbar({ label, children, end, className }: ToolbarProps) {
  const onKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    const target = event.target as HTMLElement;
    if (target.tagName !== "BUTTON" || (event.key !== "ArrowLeft" && event.key !== "ArrowRight")) return;
    const buttons = [...event.currentTarget.querySelectorAll<HTMLButtonElement>("button:not([disabled])")];
    const index = buttons.indexOf(target as HTMLButtonElement);
    const next = rovingIndex(index, buttons.length, event.key, { wrap: false });
    if (next === null || next === index) return;
    event.preventDefault();
    buttons[next]?.focus();
  };
  return (
    <div className={["ds-toolbar", className].filter(Boolean).join(" ")} role="toolbar" aria-label={label} onKeyDown={onKeyDown}>
      <div className="ds-toolbar-start">{children}</div>
      {end ? <div className="ds-toolbar-end">{end}</div> : null}
    </div>
  );
}

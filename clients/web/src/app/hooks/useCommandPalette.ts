/**
 * Command palette controller (Architecture V2 Wave 9).
 *
 * Binds the keyboard model from the Wave 1 contract
 * (`app/experience/commandPalette.ts`) to the shell: Ctrl/Cmd+K opens, Escape
 * closes, arrows move the selection and Enter runs the highlighted command. The
 * command set is derived - navigation from the navigation registry, AI actions
 * from the canonical five, inspection commands from the Active Context - so the
 * palette cannot drift from the product surface.
 *
 * Running a command is a client action: navigation, opening the Inspector, a
 * utility, or an AI action the caller is entitled to. Nothing here bypasses
 * authorisation; the backend re-authorises every request.
 */

import { useCallback, useEffect, useMemo, useState } from "react";

import {
  DEFAULT_PALETTE_LIMIT,
  buildPaletteCommands,
  filterPaletteCommands,
  inspectionCommands,
  isPaletteDismissKey,
  isPaletteShortcut,
  paletteCommandAvailable,
  type PaletteCommand,
} from "@/app/experience/commandPalette";
import type { InspectorSubjectKind } from "@/app/experience/vocabulary";
import { copilotEvidenceRefs, type CopilotEvidenceRef } from "@/app/model/copilotModel";
import type { WorkspacePageId } from "@/workspaceNavigation";

const GROUP_ORDER = ["navigate", "inspect", "ai", "utility"] as const;

export interface CommandPaletteOptions {
  activeWorkspace: WorkspacePageId;
  context: {
    routeId?: string | null;
    resourceId?: string | null;
    strategyVersionId?: string | null;
    strategyRunId?: string | null;
  };
  capabilities: readonly string[];
  activeContextComplete: boolean;
  /**
   * Canonical AI actions are part of the contract and, since Wave 7, they have an
   * invocation surface: either the Copilot this palette mounts itself, or a handler
   * the host supplies through `onAiAction`. They are therefore offered by default,
   * so no command is offered that would do nothing when chosen; `false` remains the
   * explicit opt-out.
   */
  includeAiActions?: boolean;
  /**
   * Evidence references the Active Context holds. Defaults to the selection the
   * shell already passed, so the AI commands are gated by the same rule the Copilot
   * surface applies instead of being offered for an action that would be withheld.
   */
  evidenceRefs?: readonly CopilotEvidenceRef[];
  labels: (command: PaletteCommand) => string;
  onNavigate: (command: PaletteCommand) => void;
  onInspect: (kind: InspectorSubjectKind, ref: string) => void;
  onUtility: (utility: "access-identity" | "sign-out") => void;
  onAiAction?: (command: PaletteCommand) => void;
}

export interface CommandPaletteController {
  open: boolean;
  query: string;
  results: PaletteCommand[];
  activeIndex: number;
  unavailable: ReadonlySet<string>;
  setQuery: (value: string) => void;
  setOpen: (value: boolean) => void;
  move: (delta: number) => void;
  run: (command: PaletteCommand) => void;
  runActive: () => void;
}

export function useCommandPalette(options: CommandPaletteOptions): CommandPaletteController {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [activeIndex, setActiveIndex] = useState(0);

  const offersAiCommands = options.includeAiActions !== false;

  const commands = useMemo(
    () => [
      ...buildPaletteCommands().filter(
        (command) =>
          command.group === "navigate" ||
          command.group === "utility" ||
          (offersAiCommands && command.group === "ai"),
      ),
      ...inspectionCommands(options.context, options.activeWorkspace),
    ],
    [
      offersAiCommands,
      options.activeWorkspace,
      options.context.routeId,
      options.context.resourceId,
      options.context.strategyVersionId,
      options.context.strategyRunId,
    ],
  );

  const evidenceRefs = useMemo(
    () => options.evidenceRefs ?? copilotEvidenceRefs(options.context),
    [
      options.evidenceRefs,
      options.context.routeId,
      options.context.resourceId,
      options.context.strategyVersionId,
      options.context.strategyRunId,
    ],
  );

  const availability = useMemo(
    () => ({
      capabilities: options.capabilities,
      activeContextComplete: options.activeContextComplete,
      evidenceRefCount: evidenceRefs.length,
    }),
    [options.capabilities, options.activeContextComplete, evidenceRefs],
  );

  const results = useMemo(() => {
    const filtered = filterPaletteCommands(commands, query, options.labels, Number.MAX_SAFE_INTEGER);
    return [...filtered]
      .sort((left, right) => GROUP_ORDER.indexOf(left.group) - GROUP_ORDER.indexOf(right.group))
      .slice(0, DEFAULT_PALETTE_LIMIT * 3);
  }, [commands, query, options.labels]);

  const unavailable = useMemo(
    () =>
      new Set(
        results.filter((command) => !paletteCommandAvailable(command, availability)).map((c) => c.id),
      ),
    [results, availability],
  );

  useEffect(() => {
    setActiveIndex(0);
  }, [query, open]);

  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      if (isPaletteShortcut(event)) {
        event.preventDefault();
        setOpen((current) => !current);
        return;
      }
      if (!open) return;
      if (isPaletteDismissKey(event)) {
        event.preventDefault();
        setOpen(false);
      }
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [open]);

  const run = useCallback(
    (command: PaletteCommand) => {
      if (!paletteCommandAvailable(command, availability)) return;
      if (command.target.inspector) {
        const ref =
          command.target.inspector === "route"
            ? options.context.routeId
            : command.target.inspector === "resource"
              ? options.context.resourceId
              : command.target.inspector === "strategy-version"
                ? options.context.strategyVersionId
                : options.context.strategyRunId;
        if (ref) options.onInspect(command.target.inspector, ref);
      } else if (command.target.page) {
        options.onNavigate(command);
      } else if (command.target.utility) {
        options.onUtility(command.target.utility);
      } else if (command.target.aiAction) {
        options.onAiAction?.(command);
      }
      setOpen(false);
      setQuery("");
    },
    [availability, options],
  );

  const runActive = useCallback(() => {
    const command = results[activeIndex];
    if (command) run(command);
  }, [results, activeIndex, run]);

  const move = useCallback(
    (delta: number) => {
      setActiveIndex((current) => {
        if (results.length === 0) return 0;
        const next = (current + delta + results.length) % results.length;
        return next;
      });
    },
    [results.length],
  );

  return {
    open,
    query,
    results,
    activeIndex,
    unavailable,
    setQuery,
    setOpen,
    move,
    run,
    runActive,
  };
}

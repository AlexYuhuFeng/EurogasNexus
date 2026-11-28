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
  cargoCommands,
  glossaryCommands,
  hubCommands,
  orderPaletteResults,
  inspectionCommands,
  isPaletteDismissKey,
  isPaletteShortcut,
  workspaceShortcutCommand,
  currentCommandId,
  paletteCommandAvailable,
  type PaletteAvailability,
  type PaletteCargo,
  type PaletteCommand,
} from "@/app/experience/commandPalette";
import type { InspectorSubjectKind } from "@/app/experience/vocabulary";
import { HUBS } from "@/app/answer/intent";
import { copilotEvidenceRefs, type CopilotEvidenceRef } from "@/app/model/copilotModel";
import type { WorkspacePageId } from "@/workspaceNavigation";

import { listenDesktopCommands } from "@/app/host/desktopCommands";

const GROUP_ORDER = ["navigate", "glossary", "inspect", "ai", "utility"] as const;

export interface CommandPaletteOptions {
  activeWorkspace: WorkspacePageId;
  context: {
    routeId?: string | null;
    resourceId?: string | null;
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
  /** Earlier names of a command, translated (found as aliases; WF-05). */
  aliases?: (command: PaletteCommand) => readonly string[];
  /** Whether the caller's identity is offered a command at all (absent, not disabled). */
  visible?: (command: PaletteCommand) => boolean;
  /** Glossary terms the palette can find. */
  glossaryTerms?: ReadonlyArray<{ term: string; aliases?: readonly string[] }>;
  /** The book's cargoes the palette can find by id, vessel or IMO (QA-L-05). */
  cargoes?: readonly PaletteCargo[];
  onNavigate: (command: PaletteCommand) => void;
  onInspect: (kind: InspectorSubjectKind, ref: string) => void;
  onUtility: (utility: NonNullable<PaletteCommand["target"]["utility"]>) => void;
  onAiAction?: (command: PaletteCommand) => void;
}

export interface CommandPaletteController {
  open: boolean;
  query: string;
  results: PaletteCommand[];
  activeIndex: number;
  unavailable: ReadonlySet<string>;
  /**
   * The availability the controller gated on, evidence count included. The shell explains
   * a withheld command from *this* object rather than rebuilding one, so the reason a user
   * reads is the reason the command was actually withheld.
   */
  availability: PaletteAvailability;
  setQuery: (value: string) => void;
  setOpen: (value: boolean) => void;
  /** Move by `delta` over `count` rows: the results, plus the answer rows a host shows above them. */
  move: (delta: number, count?: number) => void;
  run: (command: PaletteCommand) => void;
  runActive: () => void;
}

export function useCommandPalette(options: CommandPaletteOptions): CommandPaletteController {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [activeIndex, setActiveIndex] = useState(0);

  const offersAiCommands = options.includeAiActions !== false;

  const visible = options.visible;
  const commands = useMemo(
    () => [
      ...buildPaletteCommands().filter(
        (command) =>
          (command.group === "navigate" ||
            command.group === "utility" ||
            (offersAiCommands && command.group === "ai")) &&
          (visible ? visible(command) : true),
      ),
      ...inspectionCommands(options.context, options.activeWorkspace),
      // Glossary terms are found by name or alias (#34); they never show for an empty query.
      ...glossaryCommands(options.glossaryTerms ?? []),
      ...cargoCommands(options.cargoes ?? []).filter((command) => (visible ? visible(command) : true)),
      // Hubs by code: "NBP" offers NBP · Prices (found only, where the Prices task is offered).
      ...hubCommands(HUBS).filter((command) => (visible ? visible(command) : true)),
    ],
    [
      offersAiCommands,
      visible,
      options.glossaryTerms,
      options.cargoes,
      options.activeWorkspace,
      options.context.routeId,
      options.context.resourceId,
    ],
  );

  const evidenceRefs = useMemo(
    () => options.evidenceRefs ?? copilotEvidenceRefs(options.context),
    [
      options.evidenceRefs,
      options.context.routeId,
      options.context.resourceId,
    ],
  );

  const availability = useMemo<PaletteAvailability>(
    () => ({
      capabilities: options.capabilities,
      activeContextComplete: options.activeContextComplete,
      evidenceRefCount: evidenceRefs.length,
    }),
    [options.capabilities, options.activeContextComplete, evidenceRefs],
  );

  const results = useMemo(() => {
    const filtered = filterPaletteCommands(commands, query, options.labels, Number.MAX_SAFE_INTEGER, options.aliases);
    // An exact match leads whatever its group ("NBP": NBP · Prices, then the NBP glossary entry).
    return orderPaletteResults(filtered, query, options.labels, GROUP_ORDER, options.aliases)
      .slice(0, DEFAULT_PALETTE_LIMIT * 3);
  }, [commands, query, options.labels, options.aliases]);

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
            : options.context.resourceId;
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

  useEffect(() => {
    function editing() {
      const target = document.activeElement;
      return target instanceof HTMLElement && Boolean(target.closest(
        "input, textarea, select, [contenteditable]:not([contenteditable=false]), [role=dialog]",
      ));
    }
    function onKeyDown(event: KeyboardEvent) {
      if (open || event.defaultPrevented) return;
      const id = workspaceShortcutCommand(event, editing());
      const command = commands.find((item) => item.id === id);
      if (command && paletteCommandAvailable(command, availability)) {
        event.preventDefault();
        run(command);
      }
    }
    let disposed = false;
    let unlisten: (() => void) | undefined;
    void listenDesktopCommands((id) => {
      if (id === "palette.toggle") { setOpen(true); return; }
      if (open || editing()) return;
      const wanted = currentCommandId(id);
      const command = commands.find((item) => item.id === wanted);
      if (command) run(command);
    }).then((cleanup) => { if (disposed) cleanup(); else unlisten = cleanup; })
      .catch(() => { /* Older hosts still support the keyboard and on-screen entry. */ });
    window.addEventListener("keydown", onKeyDown);
    return () => { disposed = true; unlisten?.(); window.removeEventListener("keydown", onKeyDown); };
  }, [open, commands, availability, run]);

  const runActive = useCallback(() => {
    const command = results[activeIndex];
    if (command) run(command);
  }, [results, activeIndex, run]);

  const move = useCallback(
    (delta: number, count: number = results.length) => {
      setActiveIndex((current) => {
        if (count === 0) return 0;
        const next = (((current + delta) % count) + count) % count;
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
    availability,
    setQuery,
    setOpen,
    move,
    run,
    runActive,
  };
}

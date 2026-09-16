/**
 * Command palette and keyboard interaction model (Architecture V2 Wave 1).
 *
 * Architecture V2 section 3 of
 * `docs/engineering/Architecture-V2/04_PRODUCT_EXPERIENCE_ARCHITECTURE.md` lists the
 * command palette as a persistent cross-product element, and the W0-01 client
 * inventory records that no palette or global keyboard model exists today.
 *
 * Wave 1 fixes the contract: the command set is *derived* from the navigation
 * registry, the canonical AI actions and the shell utilities rather than maintained
 * as a second, drifting list of product surfaces. A command carries where it belongs
 * and what it does, never what it is allowed to do; capability questions stay with
 * the backend.
 *
 * Keyboard grammar: the palette uses Ctrl/Cmd+K, which the existing tab keyboard
 * model (`clients/web/src/components/ui/tabKeyboard.ts`) does not claim, and Escape
 * closes without side effects. The registry is pure data so Wave 9 can render it
 * without re-deciding any of this.
 */

import {
  primaryWorkspaces,
  type PrimaryWorkspaceId,
} from "../navigation/productNavigation.ts";
import { workspacePageIds, type WorkspacePageId } from "../../workspaceNavigation.ts";
import { actionPlacement, type ActionConsequence } from "./actionGeography.ts";
import { aiActions } from "./aiActions.ts";
import type { ActionPlacement, AiActionKind } from "./vocabulary.ts";

export type PaletteCommandGroup = "navigate" | "ai" | "utility";

export interface PaletteCommand {
  readonly id: string;
  readonly group: PaletteCommandGroup;
  /** Translation key; navigation commands reuse the existing `nav.*` vocabulary. */
  readonly labelKey: string;
  readonly consequence: ActionConsequence;
  readonly placement: ActionPlacement;
  readonly target: {
    readonly page?: WorkspacePageId;
    readonly primary?: PrimaryWorkspaceId;
    readonly aiAction?: AiActionKind;
    readonly utility?: "access-identity" | "sign-out";
  };
}

/** One command per durable work domain, then one per technical page. */
export function navigationCommands(): PaletteCommand[] {
  const primaries: PaletteCommand[] = primaryWorkspaces.map((primary) => ({
    id: `navigate.primary.${primary.id}`,
    group: "navigate",
    labelKey: primary.labelKey,
    consequence: "read",
    placement: actionPlacement("read"),
    target: { primary: primary.id, page: primary.defaultPage },
  }));
  const pages: PaletteCommand[] = workspacePageIds.map((page) => ({
    id: `navigate.page.${page}`,
    group: "navigate",
    labelKey: `nav.${page}`,
    consequence: "read",
    placement: actionPlacement("read"),
    target: { page },
  }));
  return [...primaries, ...pages];
}

/** One command per canonical AI action; availability is decided at call time. */
export function aiCommands(): PaletteCommand[] {
  return aiActions.map((contract) => ({
    id: `ai.${contract.action}`,
    group: "ai",
    labelKey: `experience.ai.${contract.action}`,
    consequence: "compute",
    placement: actionPlacement("compute"),
    target: { aiAction: contract.action },
  }));
}

/**
 * Shell utilities. These reuse existing translation keys on purpose: the palette
 * must speak the same vocabulary as the top bar, not introduce synonyms.
 */
export function utilityCommands(): PaletteCommand[] {
  return [
    {
      id: "utility.access-identity",
      group: "utility",
      labelKey: "topbar.access_identity",
      consequence: "read",
      placement: actionPlacement("utility"),
      target: { utility: "access-identity", page: "access" },
    },
    {
      id: "utility.sign-out",
      group: "utility",
      labelKey: "topbar.sign_out",
      consequence: "utility",
      placement: actionPlacement("utility"),
      target: { utility: "sign-out" },
    },
  ];
}

export function buildPaletteCommands(): PaletteCommand[] {
  return [...navigationCommands(), ...aiCommands(), ...utilityCommands()];
}

export const DEFAULT_PALETTE_LIMIT = 8;

/**
 * Rank matches for a query: label prefix first, then substring, then the rest.
 * The caller supplies `labelFor` so this module stays independent of i18n and of the
 * React tree, and so tests can rank with fixture labels.
 */
export function filterPaletteCommands(
  commands: readonly PaletteCommand[],
  query: string,
  labelFor: (command: PaletteCommand) => string,
  limit: number = DEFAULT_PALETTE_LIMIT,
): PaletteCommand[] {
  const needle = query.trim().toLowerCase();
  if (!needle) return commands.slice(0, limit);
  const prefix: PaletteCommand[] = [];
  const contains: PaletteCommand[] = [];
  for (const command of commands) {
    const label = labelFor(command).toLowerCase();
    if (label.startsWith(needle)) prefix.push(command);
    else if (label.includes(needle) || command.id.toLowerCase().includes(needle)) {
      contains.push(command);
    }
  }
  return [...prefix, ...contains].slice(0, limit);
}

export interface PaletteKeyEvent {
  readonly key: string;
  readonly ctrlKey?: boolean;
  readonly metaKey?: boolean;
  readonly altKey?: boolean;
  readonly shiftKey?: boolean;
}

/** Ctrl+K (Windows/Linux) or Cmd+K (macOS): one palette shortcut, no chords. */
export function isPaletteShortcut(event: PaletteKeyEvent): boolean {
  const modified = Boolean(event.ctrlKey) || Boolean(event.metaKey);
  return modified && !event.altKey && !event.shiftKey && event.key.toLowerCase() === "k";
}

export function isPaletteDismissKey(event: PaletteKeyEvent): boolean {
  return event.key === "Escape";
}

export function commandById(id: string): PaletteCommand | undefined {
  return buildPaletteCommands().find((command) => command.id === id);
}

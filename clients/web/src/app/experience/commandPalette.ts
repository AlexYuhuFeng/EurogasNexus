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
import { registeredViews } from "../navigation/viewRegistry.ts";
import { actionPlacement, detailPlacement, type ActionConsequence } from "./actionGeography.ts";
import { ADMINISTRATION_CAPABILITIES } from "./experienceProfile.ts";
import { aiActionIsAvailable, aiActions } from "./aiActions.ts";
import type {
  ActionPlacement,
  AiActionKind,
  InspectorSubjectKind,
} from "./vocabulary.ts";

export type PaletteCommandGroup = "navigate" | "glossary" | "inspect" | "ai" | "utility";

export interface PaletteCommand {
  readonly id: string;
  readonly group: PaletteCommandGroup;
  /** Translation key; navigation commands reuse the existing `nav.*` vocabulary. */
  readonly labelKey: string;
  readonly consequence: ActionConsequence;
  readonly placement: ActionPlacement;
  /** A literal label (a glossary term) used instead of translating `labelKey`. */
  readonly label?: string;
  /** A second translation key shown after the first ("Sources · Catalog"). */
  readonly subLabelKey?: string;
  /** Extra words that find this command (a term's aliases, in either language). */
  readonly keywords?: readonly string[];
  readonly target: {
    /** A glossary term to open the glossary at. */
    readonly term?: string;
    readonly page?: WorkspacePageId;
    /** A sub-view of `page` from the view registry (#31). */
    readonly view?: string;
    readonly primary?: PrimaryWorkspaceId;
    readonly aiAction?: AiActionKind;
    readonly inspector?: InspectorSubjectKind;
    readonly utility?: "access-identity" | "sign-out";
  };
}

/** Glossary terms as palette results (#34): "NBP" finds the NBP entry, aliases included. */
export function glossaryCommands(
  terms: ReadonlyArray<{ term: string; aliases?: readonly string[]; definition_zh_cn?: string }>,
): PaletteCommand[] {
  return terms.map((entry) => ({
    id: `glossary.${entry.term}`,
    group: "glossary" as const,
    labelKey: "palette.glossary_term",
    label: entry.term,
    keywords: [...(entry.aliases ?? [])],
    consequence: "read" as const,
    placement: actionPlacement("read"),
    target: { page: "glossary" as WorkspacePageId, term: entry.term },
  }));
}

/**
 * The keyboard shortcut a command has, from the same declaration the key handler reads
 * (`workspaceShortcutCommand`): the n-th primary workspace is Ctrl+Shift+n (⌘ on a Mac).
 */
export function paletteShortcut(command: PaletteCommand, mac: boolean): string | null {
  const match = /^navigate\.primary\.(.+)$/.exec(command.id);
  if (!match) return null;
  const index = primaryWorkspaces.findIndex((primary) => primary.id === match[1]);
  if (index < 0 || index > 5) return null;
  return `${mac ? "⌘" : "Ctrl"}+Shift+${index + 1}`;
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
  // Every sub-view the URL registry declares, so the palette, links and tabs share one
  // list of destinations (#31). The glossary's single view adds nothing over its page.
  const views: PaletteCommand[] = registeredViews()
    .filter((entry) => entry.page !== "glossary")
    .map((entry) => ({
      id: `navigate.view.${entry.page}.${entry.view}`,
      group: "navigate",
      labelKey: `nav.${entry.page}`,
      subLabelKey: entry.labelKey,
      keywords: [entry.view],
      consequence: "read",
      placement: actionPlacement("read"),
      target: { page: entry.page, view: entry.view },
    }));
  return [...primaries, ...pages, ...views];
}

/** The text a command is listed under, translated. */
export function paletteLabel(command: PaletteCommand, t: (key: string) => string): string {
  if (command.label) return command.label;
  const main = t(command.labelKey);
  return command.subLabelKey ? `${main} · ${t(command.subLabelKey)}` : main;
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

/**
 * Inspector commands for the objects the Active Context currently holds. Object
 * detail belongs in the canonical Inspector (V2 04 section 6), so the palette is
 * the one entry point that does not require redesigning a surface first.
 */
export function inspectionCommands(
  context: {
    routeId?: string | null;
    resourceId?: string | null;
    strategyVersionId?: string | null;
    strategyRunId?: string | null;
  },
  originPage: WorkspacePageId,
): PaletteCommand[] {
  const candidates: Array<[InspectorSubjectKind, string | null | undefined]> = [
    ["route", context.routeId],
    ["resource", context.resourceId],
    ["strategy-version", context.strategyVersionId],
    ["strategy-run", context.strategyRunId],
  ];
  return candidates
    .filter(([, ref]) => Boolean(ref))
    .map(([kind]) => ({
      id: `inspect.${kind}`,
      group: "inspect" as const,
      labelKey: `experience.inspect.${kind}`,
      consequence: "read" as const,
      placement: detailPlacement(),
      target: { inspector: kind, page: originPage },
    }));
}

/** What the client knows when deciding whether a command may be offered. */
export interface PaletteAvailability {
  /** Capability names from the ExperienceProfile composition. */
  readonly capabilities: readonly string[];
  /** Whether the Active Context carries the identifiers a command needs. */
  readonly activeContextComplete: boolean;
  /**
   * Evidence references the Active Context holds, when the caller can supply them.
   * Wave 7 added this additively: an AI command is then gated by the same rule the
   * Copilot surface applies (`aiActionIsAvailable`), so a command is never offered
   * while the action it would invoke is withheld. Callers that do not pass it keep
   * the previous behaviour, where the AI gate is capability plus context.
   */
  readonly evidenceRefCount?: number;
}

const AI_ACTION_CAPABILITY: Readonly<Record<AiActionKind, string>> = {
  ask: "research.query",
  explain: "research.query",
  compare: "research.query",
  challenge: "research.query",
  draft: "strategy.design",
};

/**
 * Whether a command may be offered. Unavailability is shown, never hidden
 * silently: the palette explains what is missing. This is presentation - the
 * backend still authorises the corresponding request.
 */
export function paletteCommandAvailable(
  command: PaletteCommand,
  availability: PaletteAvailability,
): boolean {
  if (command.group === "navigate" && (command.target.primary === "administration" || ["access", "sources", "runtime"].includes(command.target.page ?? ""))) {
    return ADMINISTRATION_CAPABILITIES.some((capability) => availability.capabilities.includes(capability));
  }
  if (command.target.aiAction) {
    const capability = AI_ACTION_CAPABILITY[command.target.aiAction];
    if (!availability.capabilities.includes(capability)) return false;
    if (availability.evidenceRefCount === undefined) return availability.activeContextComplete;
    return aiActionIsAvailable(command.target.aiAction, {
      activeContextComplete: availability.activeContextComplete,
      evidenceRefCount: availability.evidenceRefCount,
    });
  }
  if (command.target.utility === "access-identity") {
    return availability.capabilities.includes("access.manage");
  }
  return true;
}

/** Reason key explaining why a command is unavailable (empty when it is available). */
export function paletteUnavailableReasonKey(
  command: PaletteCommand,
  availability: PaletteAvailability,
): string | null {
  if (paletteCommandAvailable(command, availability)) return null;
  if (command.target.aiAction) {
    if (!availability.capabilities.includes(AI_ACTION_CAPABILITY[command.target.aiAction])) {
      return "experience.palette.unavailable_capability";
    }
    if (!availability.activeContextComplete) return "experience.palette.unavailable_context";
    return "experience.palette.unavailable_evidence";
  }
  return "experience.palette.unavailable_capability";
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
  // One row per destination and label: a primary and the page it opens under the same
  // name ("Market" and "Market") are one result (#34).
  const seen = new Set<string>();
  const unique = commands.filter((command) => {
    const key = `${labelFor(command).toLowerCase()}|${command.target.page ?? command.id}|${command.target.view ?? ""}|${command.target.term ?? ""}`;
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
  const needle = query.trim().toLowerCase();
  if (!needle) return unique.filter((command) => command.group !== "glossary").slice(0, limit);
  const prefix: PaletteCommand[] = [];
  const contains: PaletteCommand[] = [];
  for (const command of unique) {
    const label = labelFor(command).toLowerCase();
    const keywords = (command.keywords ?? []).map((word) => word.toLowerCase());
    if (label.startsWith(needle) || keywords.some((word) => word.startsWith(needle))) prefix.push(command);
    else if (
      label.includes(needle) ||
      keywords.some((word) => word.includes(needle)) ||
      // "runtime deliv" finds "Runtime · Delivery": every word appears somewhere.
      (needle.includes(" ") && needle.split(/\s+/).every((part) => label.includes(part))) ||
      (command.group !== "glossary" && command.id.toLowerCase().includes(needle))
    ) {
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
  readonly code?: string;
  readonly isComposing?: boolean;
  readonly repeat?: boolean;
}

/** Ctrl+K (Windows/Linux) or Cmd+K (macOS): one palette shortcut, no chords. */
export function isPaletteShortcut(event: PaletteKeyEvent): boolean {
  const modified = Boolean(event.ctrlKey) || Boolean(event.metaKey);
  return !event.isComposing && !event.repeat && modified && !event.altKey && !event.shiftKey && event.key.toLowerCase() === "k";
}

export function isPaletteDismissKey(event: PaletteKeyEvent): boolean {
  return event.key === "Escape";
}

export function commandById(id: string): PaletteCommand | undefined {
  return buildPaletteCommands().find((command) => command.id === id);
}

/** Physical number keys work across keyboard layouts; never navigate while editing. */
export function workspaceShortcutCommand(event: PaletteKeyEvent, editing: boolean): string | null {
  if (editing || event.isComposing || event.repeat || event.altKey || !event.shiftKey ||
      !(event.ctrlKey || event.metaKey)) return null;
  const digit = /^(?:Digit)?([1-6])$/.exec(event.code ?? event.key)?.[1];
  const primary = digit ? primaryWorkspaces[Number(digit) - 1] : undefined;
  return primary ? `navigate.primary.${primary.id}` : null;
}

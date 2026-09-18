/**
 * Desktop workstation contract (Architecture V2 Wave 10).
 *
 * Architecture V2 keeps Tauri a thin, replaceable host
 * (`docs/engineering/Architecture-V2/05_CLIENT_HOST_CROSS_PLATFORM.md` sections 2 and
 * 5) and requires platform differences to flow through `HostCapabilities` rather than
 * scattered OS checks. Wave 1 declared *what a host may expose*; this module declares
 * *what the workstation does with it* - window profiles, notification policy, deep
 * links, the shortcut model and the diagnostics bundle - as data a thin host can
 * execute and a test can pin.
 *
 * The rules this module exists to make structural:
 *
 * - a window profile is a layout, never an authority: every window in a profile
 *   shares one identity and one entitlement, and a persisted layout contains no
 *   identity, capability or commercial value at all;
 * - a native notification carries codes and references, never a commercial value:
 *   the payload type has no field a price, volume, margin or position could travel in,
 *   so a notification cannot leak entitlement-restricted data onto the OS;
 * - a deep link can only open a declared page, and refuses any parameter that claims
 *   an authority (entitlement, role, capability, scope);
 * - a diagnostics bundle is an allowlist: it is composed from named safe fields, and
 *   the forbidden names are declared next to the allowed ones so the exclusion is
 *   reviewable rather than incidental.
 *
 * The host executes; it never decides. Nothing here grants access, computes a value or
 * stores a credential.
 */

import {
  DEFAULT_WORKSPACE_PAGE_ID,
  isWorkspacePageId,
  type WorkspacePageId,
} from "../../workspaceNavigation.ts";
import type { PrimaryWorkspaceId } from "../navigation/productNavigation.ts";
import type { HostCapabilityName } from "./hostCapabilities.ts";

/** Every workspace profile the workstation may open. */
export const WORKSTATION_PROFILE_IDS = [
  "trading-desk",
  "market-monitor",
  "research-desk",
  "review-desk",
  "administration",
] as const;

export type WorkstationProfileId = (typeof WORKSTATION_PROFILE_IDS)[number];

export interface WorkstationWindow {
  /** Stable window id inside the profile; also the layout-persistence key. */
  readonly windowId: string;
  readonly page: WorkspacePageId;
  /** Task id inside the page, when the surface is URL-addressable by task. */
  readonly task: string | null;
  /** The primary window owns the profile's focus; supporting windows follow it. */
  readonly role: "primary" | "supporting";
  /** Capability the host must expose for this window to exist at all. */
  readonly requires: readonly HostCapabilityName[];
}

export interface WorkstationProfile {
  readonly id: WorkstationProfileId;
  /** Translation key of the profile name. */
  readonly labelKey: string;
  /** Primary workspace the profile is built around. */
  readonly primary: PrimaryWorkspaceId;
  readonly windows: readonly WorkstationWindow[];
}

export const WORKSTATION_PROFILES: readonly WorkstationProfile[] = [
  {
    id: "trading-desk",
    labelKey: "experience.workstation.profile.trading_desk",
    primary: "market",
    windows: [
      { windowId: "market", page: "market", task: "curves", role: "primary", requires: ["multiWindow"] },
      { windowId: "orders", page: "orders", task: null, role: "supporting", requires: ["multiWindow"] },
      {
        windowId: "contracts",
        page: "contracts",
        task: "resources",
        role: "supporting",
        requires: ["multiWindow"],
      },
    ],
  },
  {
    id: "market-monitor",
    labelKey: "experience.workstation.profile.market_monitor",
    primary: "market",
    windows: [
      { windowId: "market", page: "market", task: "overview", role: "primary", requires: ["multiWindow"] },
      {
        windowId: "capacity",
        page: "capacity",
        task: null,
        role: "supporting",
        requires: ["multiWindow", "notifications"],
      },
    ],
  },
  {
    id: "research-desk",
    labelKey: "experience.workstation.profile.research_desk",
    primary: "system",
    windows: [
      { windowId: "research", page: "research", task: null, role: "primary", requires: ["multiWindow"] },
      {
        windowId: "glossary",
        page: "glossary",
        task: null,
        role: "supporting",
        requires: ["multiWindow"],
      },
    ],
  },
  {
    id: "review-desk",
    labelKey: "experience.workstation.profile.review_desk",
    primary: "decision",
    windows: [
      { windowId: "review", page: "review", task: null, role: "primary", requires: ["multiWindow"] },
      {
        windowId: "scenario",
        page: "scenario",
        task: null,
        role: "supporting",
        requires: ["multiWindow"],
      },
    ],
  },
  {
    id: "administration",
    labelKey: "experience.workstation.profile.administration",
    primary: "administration",
    windows: [
      {
        windowId: "runtime",
        page: "runtime",
        task: null,
        role: "primary",
        requires: ["multiWindow"],
      },
    ],
  },
];

const profileById = new Map<WorkstationProfileId, WorkstationProfile>(
  WORKSTATION_PROFILES.map((profile) => [profile.id, profile]),
);

export function workstationProfile(id: WorkstationProfileId): WorkstationProfile {
  const profile = profileById.get(id);
  if (!profile) throw new Error(`No workstation profile declared for '${id}'.`);
  return profile;
}

/** The windows of a profile the given host can actually open. */
export function openableWindows(
  profile: WorkstationProfile,
  supported: (capability: HostCapabilityName) => boolean,
): WorkstationWindow[] {
  return profile.windows.filter((window) => window.requires.every(supported));
}

export interface WorkstationPlan {
  readonly profile: WorkstationProfile;
  /** Whether the host can host the profile at all (a workstation needs multi-window). */
  readonly supported: boolean;
  /** The windows the host can open; empty when the profile is not supported here. */
  readonly windows: readonly WorkstationWindow[];
  /**
   * Where the caller goes when the profile cannot be hosted: the profile's primary
   * window, opened in the current one. A desk degrades to a page, never to a refusal.
   */
  readonly fallback: { readonly page: WorkspacePageId; readonly task: string | null };
}

/**
 * Plan a profile against a host's capabilities.
 *
 * A host that cannot open multiple windows is not a host that has failed: it is a host
 * that gets the profile's primary view in the window it has. Returning that plan is
 * what keeps the desktop a *thin* host - the Web workspace decides what degrades to
 * what, and the native side only opens the windows it is told to open.
 */
export function planWorkstation(
  profileId: WorkstationProfileId,
  supported: (capability: HostCapabilityName) => boolean,
): WorkstationPlan {
  const profile = workstationProfile(profileId);
  const primary = profile.windows.find((window) => window.role === "primary");
  const fallback = {
    page: primary?.page ?? DEFAULT_WORKSPACE_PAGE_ID,
    task: primary?.task ?? null,
  };
  if (!supported("multiWindow")) {
    return { profile, supported: false, windows: [], fallback };
  }
  return { profile, supported: true, windows: openableWindows(profile, supported), fallback };
}

/**
 * The profile's persisted layout key. It is derived from the profile and window ids
 * only: a layout must never become a place where identity, capability or commercial
 * state is remembered, because the next person at the same machine would inherit it.
 */
export function windowStateKey(profile: WorkstationProfileId, windowId: string): string {
  return `eurogas.window.${profile}.${windowId}`;
}

/** Notification families the workstation may raise. */
export const NOTIFICATION_EVENT_KINDS = [
  "monitoring-alert",
  "job-completed",
  "job-failed",
  "decision-case-blocked",
  "freshness-breach",
] as const;

export type NotificationEventKind = (typeof NOTIFICATION_EVENT_KINDS)[number];

export type NotificationSeverity = "info" | "warning" | "critical";

const SEVERITY_RANK: Readonly<Record<NotificationSeverity, number>> = {
  info: 0,
  warning: 1,
  critical: 2,
};

export interface NotificationPolicy {
  readonly kind: NotificationEventKind;
  /** Whether the workstation may notify at all for this family. */
  readonly notify: boolean;
  /** Lowest severity the family may notify at; below it the event stays in-app. */
  readonly minimumSeverity: NotificationSeverity;
  /** The event always needs a human decision, so the notification says so. */
  readonly humanReviewRequired: boolean;
}

export const NOTIFICATION_POLICIES: readonly NotificationPolicy[] = [
  { kind: "monitoring-alert", notify: true, minimumSeverity: "warning", humanReviewRequired: true },
  { kind: "job-completed", notify: true, minimumSeverity: "info", humanReviewRequired: false },
  { kind: "job-failed", notify: true, minimumSeverity: "warning", humanReviewRequired: false },
  { kind: "decision-case-blocked", notify: true, minimumSeverity: "warning", humanReviewRequired: true },
  { kind: "freshness-breach", notify: true, minimumSeverity: "warning", humanReviewRequired: true },
];

const policyByKind = new Map<NotificationEventKind, NotificationPolicy>(
  NOTIFICATION_POLICIES.map((policy) => [policy.kind, policy]),
);

export function notificationPolicy(kind: NotificationEventKind): NotificationPolicy {
  const policy = policyByKind.get(kind);
  if (!policy) throw new Error(`No notification policy declared for '${kind}'.`);
  return policy;
}

export function notificationIsAllowed(
  kind: NotificationEventKind,
  severity: NotificationSeverity,
): boolean {
  const policy = notificationPolicy(kind);
  return policy.notify && SEVERITY_RANK[severity] >= SEVERITY_RANK[policy.minimumSeverity];
}

/**
 * What a native notification may carry.
 *
 * The payload has no field a commercial value could travel in: only codes and
 * references. The host renders it from the two translation keys, so the copy is
 * localised by the client while the values stay on screen, under the identity and
 * entitlement that fetched them.
 */
export interface NotificationPayload {
  readonly kind: NotificationEventKind;
  readonly severity: NotificationSeverity;
  readonly titleKey: string;
  readonly bodyKey: string;
  /** Stable references of the subject (ids only, never values). */
  readonly refs: readonly string[];
  /** Condition codes the event reported. */
  readonly codes: readonly string[];
  readonly humanReviewRequired: boolean;
}

/** Fields a caller must not smuggle into a notification payload. */
const NOTIFICATION_ALLOWED_FIELDS: ReadonlySet<string> = new Set([
  "kind",
  "severity",
  "titleKey",
  "bodyKey",
  "refs",
  "codes",
]);

/**
 * Build the notification payload from an untrusted input object, keeping only the
 * declared fields. A caller that passes a price, a volume or a whole record gets a
 * payload without it: the allowlist is the mechanism, not a review convention.
 *
 * The two translation keys are required: the client composes the copy (it owns the
 * localisation), and a notification without copy would have to be rendered by the host
 * from data it should not hold.
 */
export function buildNotificationPayload(input: Record<string, unknown>): NotificationPayload | null {
  const kind = input.kind as NotificationEventKind;
  const severity = input.severity as NotificationSeverity;
  if (!NOTIFICATION_EVENT_KINDS.includes(kind)) return null;
  if (!(severity in SEVERITY_RANK)) return null;
  if (!notificationIsAllowed(kind, severity)) return null;

  const safe: Record<string, unknown> = {};
  for (const [field, value] of Object.entries(input)) {
    if (NOTIFICATION_ALLOWED_FIELDS.has(field)) safe[field] = value;
  }
  const titleKey = typeof safe.titleKey === "string" ? safe.titleKey : "";
  const bodyKey = typeof safe.bodyKey === "string" ? safe.bodyKey : "";
  if (!titleKey || !bodyKey) return null;

  const refs = Array.isArray(safe.refs) ? safe.refs.filter((ref) => typeof ref === "string") : [];
  const codes = Array.isArray(safe.codes) ? safe.codes.filter((code) => typeof code === "string") : [];
  return {
    kind,
    severity,
    titleKey,
    bodyKey,
    refs: refs as string[],
    codes: codes as string[],
    humanReviewRequired: notificationPolicy(kind).humanReviewRequired,
  };
}

/** The URL scheme a desktop deep link uses. */
export const DEEP_LINK_SCHEME = "eurogas";

/** Query parameters a deep link must never carry: they would claim an authority. */
export const DEEP_LINK_FORBIDDEN_PARAMS = [
  "role",
  "roles",
  "permission",
  "permissions",
  "capability",
  "capabilities",
  "entitlement",
  "entitlements",
  "scope",
  "principal",
  "token",
] as const;

export interface DeepLinkTarget {
  readonly page: WorkspacePageId;
  readonly task: string | null;
  /** Non-authority context the link may carry (gas day, product, hub, selection ids). */
  readonly context: Readonly<Record<string, string>>;
}

/** Context keys a deep link may carry; every other key is dropped. */
export const DEEP_LINK_CONTEXT_KEYS = [
  "task",
  "gasDay",
  "product",
  "hub",
  "route",
  "resource",
  "strategyVersion",
  "strategyRun",
  "case",
] as const;

/**
 * Parse a deep link into a workspace target.
 *
 * Returns `null` for anything the product does not declare: an unknown scheme, an
 * unknown page, or a link that tries to carry an authority parameter. A refused link
 * is refused loudly (nothing opens) rather than opened with the parameter ignored,
 * because ignoring it would let a caller believe it had been honoured.
 *
 * The refusal is inspected in **both** places a parameter can live. A link is declared as
 * `eurogas://<page>?<context>`, but a fragment is still a place a caller can write
 * `#role=ADMIN`, and a link that opens while silently dropping an authority claim is the
 * outcome this function exists to prevent.
 */
export function parseDeepLink(url: string): DeepLinkTarget | null {
  let parsed: URL;
  try {
    parsed = new URL(url);
  } catch {
    return null;
  }
  if (parsed.protocol !== `${DEEP_LINK_SCHEME}:`) return null;
  const segments = [parsed.hostname, ...parsed.pathname.split("/")].filter(Boolean);
  const page = segments[0] ?? null;
  if (!isWorkspacePageId(page)) return null;
  // `?a=1&b=2`, and `#a=1&b=2` when the fragment is written as parameters.
  const parameterSources = [parsed.searchParams, new URLSearchParams(parsed.hash.replace(/^#/, ""))];
  for (const source of parameterSources) {
    for (const forbidden of DEEP_LINK_FORBIDDEN_PARAMS) {
      if (source.has(forbidden)) return null;
    }
  }
  const context: Record<string, string> = {};
  for (const key of DEEP_LINK_CONTEXT_KEYS) {
    const value = parsed.searchParams.get(key);
    if (value !== null && value !== "") context[key] = value;
  }
  return { page, task: context.task ?? null, context };
}

/** Build a deep link for a declared page; unknown pages fall back to the default page. */
export function buildDeepLink(
  page: WorkspacePageId,
  context: Readonly<Record<string, string>> = {},
): string {
  const target = isWorkspacePageId(page) ? page : DEFAULT_WORKSPACE_PAGE_ID;
  const params = new URLSearchParams();
  for (const key of DEEP_LINK_CONTEXT_KEYS) {
    const value = context[key];
    if (value !== undefined && value !== "") params.set(key, value);
  }
  const query = params.toString();
  return `${DEEP_LINK_SCHEME}://${target}${query ? `?${query}` : ""}`;
}

/** Canonical workstation shortcuts. One binding, one scope, one command. */
export const WORKSTATION_SHORTCUTS = [
  { id: "command-palette", binding: "Ctrl+K", scope: "shell", commandId: "palette.toggle" },
  { id: "inspector-close", binding: "Escape", scope: "inspector", commandId: "inspector.close" },
  { id: "inspector-back", binding: "Alt+ArrowLeft", scope: "inspector", commandId: "inspector.back" },
  { id: "profile-next-window", binding: "Ctrl+Alt+ArrowRight", scope: "shell", commandId: "window.focus-next" },
  { id: "profile-previous-window", binding: "Ctrl+Alt+ArrowLeft", scope: "shell", commandId: "window.focus-previous" },
] as const;

export type WorkstationShortcut = (typeof WORKSTATION_SHORTCUTS)[number];

/** Bindings that collide inside one scope. Empty means the model is unambiguous. */
export function shortcutConflicts(): string[] {
  const seen = new Map<string, string>();
  const conflicts: string[] = [];
  for (const shortcut of WORKSTATION_SHORTCUTS) {
    const key = `${shortcut.scope}:${shortcut.binding}`;
    const owner = seen.get(key);
    if (owner) conflicts.push(`${key} is bound by ${owner} and ${shortcut.id}`);
    else seen.set(key, shortcut.id);
  }
  return conflicts;
}

/**
 * Fields a diagnostics bundle may contain. Version, host and failure information the
 * client already holds - never a credential, a token or a commercial value.
 */
export const DIAGNOSTICS_ALLOWED_FIELDS = [
  "clientVersion",
  "serverVersion",
  "releaseCompatibility",
  "schemaRevision",
  "hostKind",
  "capabilities",
  "language",
  "dataStatus",
  "endpointFailureCodes",
  "degradedSlices",
  "jobStates",
  "generatedAtUtc",
] as const;

/**
 * Names that must never appear in a diagnostics bundle. A few are listed because the
 * source object the client reads from carries them nearby, so the exclusion is
 * explicit and reviewable rather than a property of the current code path.
 */
export const DIAGNOSTICS_FORBIDDEN_FIELDS = [
  "accessToken",
  "refreshToken",
  "token",
  "apiKey",
  "credential",
  "password",
  "secret",
  "price",
  "priceGbpMwh",
  "volumeMwh",
  "pnlGbp",
  "margin",
  "position",
  "counterparty",
  "contractPrice",
] as const;

/**
 * Compose the diagnostics bundle from an object holding more than it may export.
 * Only declared fields survive, and a declared field whose name is forbidden is a
 * programming error rather than a silent leak.
 */
export function buildDiagnosticsBundle(input: Record<string, unknown>): Record<string, unknown> {
  const bundle: Record<string, unknown> = {};
  for (const field of DIAGNOSTICS_ALLOWED_FIELDS) {
    if ((DIAGNOSTICS_FORBIDDEN_FIELDS as readonly string[]).includes(field)) {
      throw new Error(`Diagnostics field '${field}' is declared both allowed and forbidden.`);
    }
    const value = input[field];
    if (value !== undefined) bundle[field] = value;
  }
  return bundle;
}

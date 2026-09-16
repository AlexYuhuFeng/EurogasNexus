/**
 * HostCapabilities contract (Architecture V2 Wave 1).
 *
 * Architecture V2 keeps Tauri as a thin, replaceable host
 * (`docs/engineering/Architecture-V2/05_CLIENT_HOST_CROSS_PLATFORM.md` sections 2 and
 * 5) and the Constitution requires platform differences to be expressed through
 * HostCapabilities rather than scattered OS checks (rule 50). The W0-01 client
 * inventory found the opposite in two places: desktop detection was written twice
 * (`clients/web/src/api/client.ts` and `clients/web/src/stores/api.ts`) and the
 * native bridge was invoked directly from both.
 *
 * This module is the single owner of that boundary:
 *
 * - `resolveHostKind` is the only place that inspects Tauri markers;
 * - `hostCapabilities` declares, per host, what the product may rely on;
 * - `HOST_COMMANDS` is the bounded allowlist of native commands the Web workspace may
 *   invoke, so a new native call cannot be added by accident;
 * - `tryHostCommand` fails soft (browser, or a shell that predates the command),
 *   while `requireHostCommand` throws, because a login handshake that silently
 *   returns nothing would be worse than an error.
 *
 * The host stays a host: no business rule, calculation, credential or data source
 * may live on the native side. The module holds no secret and stores no token.
 */

export type HostKind = "browser" | "desktop";

/** Capabilities a host may expose. A browser either implements them or reports false. */
export interface HostCapabilities {
  readonly kind: HostKind;
  readonly notifications: boolean;
  readonly fileDialogs: boolean;
  readonly multiWindow: boolean;
  readonly windowPersistence: boolean;
  readonly secureStorage: boolean;
  readonly autoUpdate: boolean;
  readonly deepLinks: boolean;
  readonly systemTray: boolean;
  readonly diagnosticsExport: boolean;
  /** Read the deployment-provided API base URL (managed deployment configuration). */
  readonly deploymentConfig: boolean;
  /** Run the desktop OIDC loopback handshake (open the browser, receive the callback). */
  readonly oidcLoopbackAuth: boolean;
}

/** A capability name, i.e. every `HostCapabilities` key except `kind`. */
export type HostCapabilityName = Exclude<keyof HostCapabilities, "kind">;

/** The minimum browser surface the detector needs; kept explicit so tests can inject one. */
export interface HostScope {
  readonly protocol?: string;
  readonly hostname?: string;
  readonly hasTauriInternals?: boolean;
}

/**
 * Bounded allowlist of native commands the Web workspace may invoke. Adding a
 * command here is a client/host contract change, not a local convenience.
 */
export const HOST_COMMANDS = {
  readDeploymentConfig: "read_deployment_config",
  notifyClientReady: "notify_client_ready",
  clearSessionData: "clear_client_session_data",
  startLoopbackAuth: "start_loopback_auth",
  openBrowserLoginAndWait: "open_browser_login_and_wait",
} as const;

export type HostCommand = (typeof HOST_COMMANDS)[keyof typeof HOST_COMMANDS];

const HOST_COMMAND_SET: ReadonlySet<string> = new Set(Object.values(HOST_COMMANDS));

export function isHostCommand(value: string): value is HostCommand {
  return HOST_COMMAND_SET.has(value);
}

/**
 * The capability each allowlisted command belongs to. This is the missing link the
 * W0-03 fitness inventory recorded as gap FF6-G1: a bounded command list is not the
 * same as "commands stay within HostCapabilities" until every command is classified.
 * Adding a command now requires naming its capability class here.
 */
export const HOST_COMMAND_CAPABILITIES: Readonly<Record<HostCommand, HostCapabilityName>> = {
  read_deployment_config: "deploymentConfig",
  notify_client_ready: "notifications",
  clear_client_session_data: "secureStorage",
  start_loopback_auth: "oidcLoopbackAuth",
  open_browser_login_and_wait: "oidcLoopbackAuth",
};

export function hostCommandCapability(command: HostCommand): HostCapabilityName {
  return HOST_COMMAND_CAPABILITIES[command];
}

/** Tauri marks its WebView through the protocol, the hostname or an injected global. */
export function resolveHostKind(scope: HostScope = currentHostScope()): HostKind {
  if (scope.hasTauriInternals) return "desktop";
  if (scope.protocol === "tauri:") return "desktop";
  if (scope.hostname === "tauri.localhost") return "desktop";
  return "browser";
}

export function currentHostScope(): HostScope {
  if (typeof window === "undefined") return {};
  return {
    protocol: window.location?.protocol,
    hostname: window.location?.hostname,
    hasTauriInternals:
      typeof window === "object" && window !== null && "__TAURI_INTERNALS__" in window,
  };
}

/** Capabilities by host. A browser deployment is complete without a native shell. */
export function hostCapabilities(kind: HostKind = resolveHostKind()): HostCapabilities {
  const desktop = kind === "desktop";
  return {
    kind,
    notifications: desktop,
    fileDialogs: desktop,
    multiWindow: desktop,
    windowPersistence: desktop,
    secureStorage: desktop,
    autoUpdate: desktop,
    deepLinks: desktop,
    systemTray: desktop,
    diagnosticsExport: desktop,
    // Deployment configuration and the OIDC loopback handshake are desktop-only:
    // a browser receives its base URL from the same origin it was served from and
    // authenticates inside the browser rather than through a loopback redirect.
    deploymentConfig: desktop,
    oidcLoopbackAuth: desktop,
  };
}

export function hostSupports(capability: HostCapabilityName, kind: HostKind = resolveHostKind()): boolean {
  return hostCapabilities(kind)[capability];
}

/** Whether a host may invoke a command, by the capability class the command belongs to. */
export function hostSupportsCommand(command: HostCommand, kind: HostKind = resolveHostKind()): boolean {
  return isHostCommand(command) && hostCapabilities(kind)[hostCommandCapability(command)];
}

/** Convenience read used by call sites that only branch on shell presence. */
export function isDesktopHost(kind: HostKind = resolveHostKind()): boolean {
  return kind === "desktop";
}

async function invokeNative<T>(command: HostCommand, args?: Record<string, unknown>): Promise<T> {
  const { invoke } = await import("@tauri-apps/api/core");
  return args ? invoke<T>(command, args) : invoke<T>(command);
}

/**
 * Best-effort native call. Returns `null` in a browser, for an unknown command, for a
 * command whose capability the host does not expose, or when the shell refuses - the
 * Web workspace must stay usable without a native side.
 */
export async function tryHostCommand<T>(
  command: HostCommand,
  args?: Record<string, unknown>,
  kind: HostKind = resolveHostKind(),
): Promise<T | null> {
  if (kind !== "desktop" || !isHostCommand(command)) return null;
  if (!hostSupportsCommand(command, kind)) return null;
  try {
    return await invokeNative<T>(command, args);
  } catch {
    return null;
  }
}

/**
 * Native call whose result the caller needs. Throws rather than returning a value
 * that would let a caller continue with a half-finished handshake.
 */
export async function requireHostCommand<T>(
  command: HostCommand,
  args?: Record<string, unknown>,
  kind: HostKind = resolveHostKind(),
): Promise<T> {
  if (kind !== "desktop" || !isHostCommand(command) || !hostSupportsCommand(command, kind)) {
    throw new Error(`Host command '${command}' requires the desktop shell.`);
  }
  return invokeNative<T>(command, args);
}

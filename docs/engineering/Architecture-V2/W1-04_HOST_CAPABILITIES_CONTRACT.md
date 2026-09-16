# W1-04 — HostCapabilities Contract

Status: **delivered contract and seam (Wave 1)**. Authority: Architecture V2
[05_CLIENT_HOST_CROSS_PLATFORM.md](05_CLIENT_HOST_CROSS_PLATFORM.md) sections 2, 5 and 7, and
[02_ARCHITECTURE_CONSTITUTION.md](02_ARCHITECTURE_CONSTITUTION.md) rules 48-50.

Machine-readable form: `clients/web/src/app/host/hostCapabilities.ts`.
Focused checks: `clients/web/tests/experienceArchitecture.test.ts`,
`clients/web/tests/authGate.test.ts`.

## 1. Problem this closes

The W0-01 client inventory found desktop detection written twice, in
`clients/web/src/api/client.ts` and `clients/web/src/stores/api.ts`, with the native bridge invoked
directly from both. That is the pattern Architecture V2 rule 50 forbids: platform differences belong
to one declared boundary, not to scattered checks.

After Wave 1 there is exactly one owner. The focused test scans every TypeScript file under
`clients/web/src` and fails if a Tauri marker (`__TAURI_INTERNALS__`, `tauri:` protocol,
`tauri.localhost`), a direct `@tauri-apps/api/core` import, or a raw `invoke("<command>")` call
appears outside `app/host/hostCapabilities.ts` (the ambient declaration in `vite-env.d.ts` is a type
only and is excluded).

## 2. Contract

| Element | Meaning |
|---|---|
| `HostKind` | `"browser"` or `"desktop"`. |
| `resolveHostKind(scope?)` | The only place that inspects Tauri markers. The scope is injectable, so the rule is testable without a browser. |
| `HostCapabilities` | `notifications`, `fileDialogs`, `multiWindow`, `windowPersistence`, `secureStorage`, `autoUpdate`, `deepLinks`, `systemTray`, `diagnosticsExport`, `deploymentConfig`, `oidcLoopbackAuth`, plus `kind`. A browser reports `false`; the product stays complete without a native shell. |
| `HOST_COMMANDS` | The bounded allowlist of native commands the Web workspace may invoke: `read_deployment_config`, `notify_client_ready`, `clear_client_session_data`, `start_loopback_auth`, `open_browser_login_and_wait`. |
| `HOST_COMMAND_CAPABILITIES` | The capability class of each allowlisted command, so "commands stay within HostCapabilities" is machine-checked rather than implied (closes the W0-03 gap FF6-G1 on the client side). |
| `hostSupportsCommand(command, kind?)` | Whether a host may invoke a command, by its capability class. |
| `tryHostCommand<T>` | Best effort: returns `null` in a browser, for a non-allowlisted command, for a command whose capability the host does not expose, or when the shell refuses. Used for optional native behaviour. |
| `requireHostCommand<T>` | Throws under the same conditions. Used where continuing with a half-finished handshake would be worse than an error. |

### Command to capability mapping

| Command | Capability class | Why |
|---|---|---|
| `read_deployment_config` | `deploymentConfig` | Reads the deployment-provided API base URL; a browser is served from the origin it should call. |
| `notify_client_ready` | `notifications` | Reveals the main window once identity resolves (shell lifecycle signal). |
| `clear_client_session_data` | `secureStorage` | Drops WebView cookies, caches and local storage after sign-out. |
| `start_loopback_auth` | `oidcLoopbackAuth` | Starts the desktop OIDC loopback handshake. |
| `open_browser_login_and_wait` | `oidcLoopbackAuth` | Opens the system browser and receives the callback. |

Rules:

1. Native detection and native invocation SHALL live only in this module. A new call site MUST use
   the module; adding a command to the allowlist is a client/host contract change, not a local
   convenience, and it MUST declare its capability class in the same change.
2. Native calls that are optional SHALL use `tryHostCommand` and fail soft. Calls the caller depends
   on SHALL use `requireHostCommand` and surface the failure.
3. The host SHALL remain a thin, replaceable host: no business rule, calculation, credential, vendor
   call or data source may live on the native side
   ([05_CLIENT_HOST_CROSS_PLATFORM.md](05_CLIENT_HOST_CROSS_PLATFORM.md) section 2).
4. Web and desktop SHALL share the same business UI and produce the same governed result for the
   same context. This contract expresses platform differences only.
5. Architecture support is not GA support. The support matrix stays with the release documentation;
   this contract does not claim packaging, signing or installer evidence.

## 3. Call sites migrated in Wave 1

| Call site | Before | After |
|---|---|---|
| `clients/web/src/api/client.ts` | local `isDesktopShell` with three marker checks | `resolveHostKind() === "desktop"` |
| `client.ts` deployment config | direct `invoke("read_deployment_config")` | `tryHostCommand(HOST_COMMANDS.readDeploymentConfig)` |
| `client.ts` window reveal | direct `invoke("notify_client_ready")` | `tryHostCommand(HOST_COMMANDS.notifyClientReady)` |
| `client.ts` session scrub | direct `invoke("clear_client_session_data")` | `tryHostCommand(HOST_COMMANDS.clearSessionData)` |
| `clients/web/src/stores/api.ts` desktop SSO | second copy of the marker checks plus two direct invokes | `isDesktopHost()`, `requireHostCommand(...)` for `start_loopback_auth` and `open_browser_login_and_wait` |

Behaviour is unchanged: the exported bridge functions keep their names, guards and fail-soft
semantics, and the browser path still leaves the client for SSO instead of invoking anything.

## 4. Verification

- `clients/web/tests/experienceArchitecture.test.ts` — host-kind resolution for all four marker
  shapes, capability values per host, allowlist enforcement, the single-owner source scan, the
  migrated call sites, and fail-soft / required behaviours.
- `clients/web/tests/authGate.test.ts` — the desktop window is still revealed only after identity
  resolves, and the native command name now lives in the host boundary.

## 5. Compatibility and non-goals

- No change to the desktop Tauri commands, the deployment-config schema, the SSO flow or the
  sign-out sequence. The migration is a seam extraction.
- No new native capability is added; Wave 10 (desktop terminal) is where multi-window, layout
  persistence, notifications and diagnostics are delivered against this contract.
- No offline or local business datastore is introduced. Desktop continues to use the same backend
  API.

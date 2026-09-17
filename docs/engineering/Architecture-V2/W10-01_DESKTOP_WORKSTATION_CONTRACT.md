# W10-01 — Desktop Workstation Contract

Status: **delivered (Wave 10, contract slice; native implementation deferred)**. Authority:
[05_CLIENT_HOST_CROSS_PLATFORM.md](05_CLIENT_HOST_CROSS_PLATFORM.md) sections 2, 4 and 5,
[04_PRODUCT_EXPERIENCE_ARCHITECTURE.md](04_PRODUCT_EXPERIENCE_ARCHITECTURE.md) section 11,
[12_MIGRATION_ROADMAP.md](12_MIGRATION_ROADMAP.md) Wave 10, and the Wave 1 host contract
[W1-04](W1-04_HOST_CAPABILITIES_CONTRACT.md).

## 1. What Wave 10 asks for, and what this slice can honestly deliver

Wave 10 lists multi-window, multi-monitor persistence, workspace profiles, native
notifications, file integration, deep links, desktop diagnostics and a shortcut model -
under the rule "do not fork business logic".

The native side of that work is Rust inside `clients/desktop/src-tauri`, and this
environment has **no Rust toolchain** (`cargo` is not installed), so no Tauri build,
package or runtime behaviour can be verified here. Shipping unverifiable Rust would
violate this programme's evidence rule, so this slice delivers the part that can be
verified and that the native side must obey: the **workstation contract**.

- `clients/web/src/app/host/workstation.ts` declares window profiles, notification
  policy and payload, deep-link parsing, the shortcut model and the diagnostics
  allowlist as data.
- The host executes that data. Every rule below is enforced in the Web workspace, so a
  thin host cannot widen it, and the same rules hold in a browser with the
  corresponding capabilities absent.

## 2. Window profiles and multi-monitor persistence

Five desk profiles are declared: `trading-desk`, `market-monitor`, `research-desk`,
`review-desk`, `administration`. Each names its primary workspace and its windows; each
window names a **declared** `WorkspacePageId`, an optional task, a role (`primary` or
`supporting`) and the capabilities it requires.

- A profile is a **layout, not an authority.** Every window in a profile shares one
  identity and one entitlement; nothing in the contract can express a different one.
  A profile that needs a capability the host does not expose simply does not open that
  window: `openableWindows(profile, supported)` returns only what the host can serve,
  instead of opening an empty window that reads like a permission problem.
- `planWorkstation(profileId, supported)` turns that into an actionable plan: the
  windows to open on a capable host, and - on a host without multi-window - the
  profile's primary page and task to open in the window it has. A desk degrades to a
  page, never to a refusal, and the Web workspace rather than the native side decides
  what degrades to what. That is what keeps the host thin.
- Persistence keys are derived from ids only
  (`eurogas.window.<profile>.<window>`). A persisted layout therefore cannot carry an
  identity, a capability or a commercial value, because the next person at the same
  machine would inherit it. Multi-monitor geometry is host state under that key.
- Exactly one window per profile is `primary`, so "focus follows the desk" has one
  definition rather than one per surface.

## 3. Native notifications

Notification families are declared families, not call sites:
`monitoring-alert`, `job-completed`, `job-failed`, `decision-case-blocked`,
`freshness-breach`. Each has a policy: whether the family may notify at all, the
minimum severity that may interrupt the user, and whether the event always needs a human
decision.

The payload type is the security property:

- it has fields for codes and references only - `kind`, `severity`, `titleKey`,
  `bodyKey`, `refs`, `codes` - and **no field a price, volume, margin or position could
  travel in**;
- `buildNotificationPayload` composes it through an allowlist, so a caller that passes a
  price, a volume or a whole backend record gets a payload without them. A withheld
  row cannot reach the operating system's notification centre;
- the client composes the copy from translation keys (it owns the localisation) while
  the values stay on screen, under the identity and entitlement that fetched them;
- a severity below the family's floor produces no notification at all, rather than an
  in-app event dressed up as an OS interruption.

## 4. Deep links

`eurogas://<page>?<context>` opens a declared page with declared context keys only
(`task`, `gasDay`, `product`, `hub`, `route`, `resource`, `strategyVersion`,
`strategyRun`, `case`).

- An unknown scheme, an unknown page or a malformed URL opens nothing.
- A link carrying any declared authority parameter (`role`, `permission`, `capability`,
  `entitlement`, `scope`, `principal`, `token`) is **refused outright**, not opened with
  the parameter ignored: ignoring it would let a caller believe it had been honoured.
  A deep link is a navigation convenience, never an authentication or authorisation
  mechanism.
- Unknown query keys are dropped rather than forwarded.
- `buildDeepLink` falls back to the default page for an unknown page, so the product
  never produces a link it cannot open.

## 5. Diagnostics

`buildDiagnosticsBundle` exports an **allowlist**: client and server version, release
compatibility, schema revision, host kind, capabilities, language, data status, endpoint
failure codes, degraded projection slices, job states and the generation time.

The forbidden names are declared next to the allowed ones (`accessToken`, `refreshToken`,
`apiKey`, `credential`, `secret`, `price`, `priceGbpMwh`, `volumeMwh`, `pnlGbp`,
`margin`, `position`, `counterparty`, `contractPrice`) so the exclusion is reviewable
rather than a property of the current code path, and a field that appears in both lists
is a hard error instead of a silent leak. A diagnostics bundle is support evidence, not
a data export.

## 6. Shortcut model

`WORKSTATION_SHORTCUTS` declares the canonical bindings (command palette, Inspector
close and back, focus next/previous window) with their scope and command id.
`shortcutConflicts()` reports a binding claimed twice inside one scope, so the model
stays unambiguous as the shell grows. The workstation introduces no native command of
its own: a desktop behaviour that needed one would have to declare its capability class
in `HOST_COMMAND_CAPABILITIES` first (the Wave 1 rule that a bounded command list is not
the same as "commands stay within HostCapabilities").

## 7. Deferred (and why)

- **Native implementation.** Tauri window creation, multi-monitor geometry restore,
  native notification delivery, protocol registration, tray and file dialogs are the
  next step in `clients/desktop/src-tauri`, and must be verified on a machine with the
  Rust toolchain and platform packaging. Nothing here claims that build exists.
- **File integration** for import/export workflows (the contract side already exists in
  `HostCapabilities.fileDialogs`); the exact formats and the operator-facing flows are
  product decisions that belong with the surfaces that own them.
- **Auto-update and signing** are Wave 11 (RC/GA) items, not workstation behaviour.

## 8. Verification

- `clients/web/tests/workstation.test.ts` — profiles over declared pages with one
  primary window and capability-gated windows, layout keys that carry no authority, the
  notification allowlist (a price, a volume, a PnL and a note never reach the payload),
  severity floors, deep-link refusal of page, scheme and authority parameters, the
  shortcut conflict model, and the diagnostics allowlist with its forbidden names.
- Client suites: `node --test "tests/*.test.ts"`, `npx tsc --noEmit` and
  `npm run build` in `clients/web`; results are recorded in the execution checkpoint.
- Not verified and not claimed: any Tauri/Rust build, packaging, installer or
  platform-specific runtime behaviour.

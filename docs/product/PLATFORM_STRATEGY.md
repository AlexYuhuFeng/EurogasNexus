# Platform strategy

Which devices the product runs on, in what form, and why. One React client serves every
platform; the server and its API stay the single source of authority (AGENTS.md rule 6:
FastAPI, React, Tauri, PostgreSQL). No platform gets its own business logic.

## Summary

| Platform | Form | Status | Who uses it for what |
|---|---|---|---|
| Windows 10/11 x64 | Tauri desktop app, NSIS installer (English and Simplified Chinese) | Shipped | Traders, risk, IT: the full workstation on a multi-monitor desk |
| Any desktop browser (Edge, Chrome, Safari, Firefox) | Web client served by the deployment | Shipped | Everyone, where installing is not allowed |
| Linux x64 | Tauri `.deb` | Shipped | IT, analysts |
| macOS | Not built | Dropped 2026-11-06: the scarce macOS CI runners turned `main` red without a code fault, and few desks need it. The Tauri source still compiles for macOS if a customer asks; reinstating it means restoring the `desktop-macos` release job and its native-acceptance build. | – |
| iPadOS 16+ | Web client in Safari, added to the home screen; managed by the firm's MDM | Supported (responsive layout, 40 px touch targets) | Risk and management reviewing positions, limits and approvals away from the desk |
| iOS 16+ (phone) | Web client, monitoring views | Supported for reading | Alerts, daily balance, positions and approvals on the move; no data entry |
| Android 12+ (tablet, phone) | Web client in Chrome; managed by MDM | Supported as iPadOS / iOS | Same as iPad and iPhone |
| HarmonyOS NEXT (Huawei) | Web client in the system browser (ArkWeb) | Supported for reading; China deployments use the China basemap | Staff in China offices with Huawei devices |
| Native mobile apps (iOS, Android, HarmonyOS) | Not built | Only on a customer requirement, see below | |

## Why the desktop app is the primary client

A gas trader works on two to six monitors next to Trayport or exchange screens, with a
keyboard. The desktop app gives them window placement that survives restarts, a branded
installer the firm's IT can push silently, the firm's proxy and certificate store, and
no browser extensions in the way. Windows dominates trading floors, so Windows ships
first, with Linux beside it.

## macOS

Not built or shipped (owner decision, 2026-11-06). The universal `.dmg` job ran on
`macos-15` runners whose queue cancelled it often enough to turn `main` red with no code
fault, and trading floors run Windows. Mac users use the web client. The Tauri source is
unchanged, so a macOS build can be restored from git history (`desktop-macos` in
`release.yml`, `macos-build` in `native-acceptance.yml`, `scripts/ci/verify_macos_bundle.sh`)
if a customer needs it.

## iPad, iPhone and Android

What people actually do away from the desk is read and approve, not enter contracts:
check the daily balance, positions against limits, a breach email, a hedge approval, a
problem report. The web client already supports that:

- Layouts reflow below 900 px; the top bar folds its context into a disclosure; controls
  are 40 px on touch screens. Measured at 768 × 1024 (iPad portrait) and 390 × 844
  (iPhone): the page never scrolls sideways; a table wider than the screen (the position
  ladder, the daily balance) scrolls inside its own panel, and the workspace bar scrolls
  on a phone.
- Sign-in uses the firm's SSO in the browser, so MDM policies (conditional access,
  device compliance) apply without a store app.
- Nothing is stored on the device beyond the session cookie and display preferences.

A store app adds an App Store / Play review, a second release train and a signing
identity per store, for no capability the browser lacks today. It becomes worth it when
a customer requires one of: push notifications to the phone (today alerts go by email,
which is what the customer uses), offline reading, or distribution only through their
MDM's app catalogue. Then the route is Tauri 2's iOS and Android targets wrapping the same
client, distributed privately (Apple Business Manager custom apps, managed Google Play),
not in the public stores.

## HarmonyOS

HarmonyOS NEXT no longer runs Android apps, and Tauri does not target ArkTS. The system
browser (ArkWeb, Chromium-based) runs the web client, which is the supported route.
Deployments in mainland China use the China basemap and must be served from inside
China (see `docs/legal/` and the China deployment notes). Should a customer need an app
icon and MDM distribution, a thin ArkTS shell hosting the web client in an ArkWeb
component, distributed through Huawei AppGallery's enterprise channel, is the smallest
step; it holds no logic of its own.

## Compatibility we test

| Check | Where |
|---|---|
| No horizontal scroll, every top-bar control on screen, at 1280, 1366, 1440, 1536 (125 %), 1680, 1920 and 2560 px, for every role | Walkthrough measurement (`docs/user/manual/README.md`) |
| No page-level horizontal scroll at 768 × 1024 and 390 × 844; wide tables scroll in their panel | Same measurement |
| Wide screens use up to 1800 / 2240 px instead of a fixed column | `app.css` |
| Touch targets 40 px on coarse pointers | `design-system.css` |
| Reduced motion honoured | `docs/ux/INTERACTION_STANDARD.md` |
| Light and dark themes | design-system tokens |

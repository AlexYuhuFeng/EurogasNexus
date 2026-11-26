# DRAFT ADR: Client surfaces: web first, Windows desktop on Tauri, an Excel add-in, no Linux desktop

**Status:** DRAFT, awaiting owner review (2026-11-26). Proposed in
[ARCHITECTURE_V3_PLAN.md](../ARCHITECTURE_V3_PLAN.md) sections 3.7 and 4. On acceptance it is
appended to [ARCHITECTURE_DECISION_RECORD.md](../ARCHITECTURE_DECISION_RECORD.md). It amends
Decision 21 (Tauri stays; the Linux desktop is no longer a supported product) and adds an Excel
client under Decision 1 (all clients through `/api`).

**Context.** The web workspace (React 19, TypeScript) is the primary client; the Tauri 2 desktop
wraps it for Windows and Linux with `core:default` permissions only (Decision 21), with Linux GUI
acceptance as a release gate. No reviewer used the Linux desktop; trading desks run Windows.
Desktop teams deploy through Intune or SCCM and ask for an MSI package; the desktop content policy
allows connections to any HTTPS host (security M5). Excel is universal on trading floors; today
the product offers a Power Query how-to with keys stored in the workbook (`docs/sdk/POWER_QUERY.md`).
The technology review names an Excel add-in the highest adoption value per unit of work. Banks'
desktops often run web applications in interop containers that share context through FDC3.

**Decision.**

1. **The web application is the product.** Every client renders it or calls the same API; no
   client holds business logic.
2. **Windows desktop stays on Tauri 2**: shipped as MSI and NSIS, signed (a release refuses an
   unsigned Windows build), offline WebView2 installer available, content policy narrowed to the
   configured API origin and tile service, updates through the customer's software distribution.
3. **The Linux desktop is no longer a supported product.** Linux users use the browser. Its CI
   build may remain as a smoke test while it costs nothing; it is not a release gate.
4. **Excel add-in** built with Excel-DNA (zlib licence): RTD cells for latest price, freshness and
   alert counts; functions for curve strips, route costs, netbacks and balance lines; single sign-on
   through the firm's identity provider; no keys in workbooks; reads subject to the same
   entitlements and licensed-use metering. An Office.js variant only for a customer fully on the
   web version of Microsoft 365.
5. **Python SDK** becomes a client object (session, retry, DataFrame output), generated from the
   OpenAPI document, published to the customer's package index.
6. **FDC3** context broadcast (instrument, gas day, cargo) when a customer runs an interop desktop;
   the web application then runs inside that container directly.
7. **Electron** only if a customer's WebView2 policy blocks Tauri or a Chromium-only feature is
   needed. No WPF rewrite; no mobile application beyond read-only alerts on request.

**Alternatives.** (a) Electron everywhere: identical rendering, but installers over 100 MB, several
times the memory, a Node.js process to patch; not justified while WebView2 works. (b) Web only:
simplest, but desks lose a dedicated window and operating-system sign-on hand-off. (c) Keep the
Linux desktop: a release gate for a platform no desk asked for. (d) A Python Excel add-in (PyXLL,
xlwings): commercial licence or a Python runtime on every desk PC; Excel-DNA needs only .NET, which
Windows desks have.

**Consequences.** One fewer release gate; one new client (the add-in) with its own build and
signing on Windows; the generated SDK and client types remove the hand-written 8,459-line client
file over time.

**Migration.** (1) MSI and narrowed content policy. (2) Linux desktop removed from release gates
and support statements. (3) Excel add-in against the existing API (plan phase 3). (4) Generated SDK.
(5) FDC3 on demand.

**Tests that make it observable.** A release check that refuses an unsigned Windows build; an
add-in test that a user without the licensed family sees no licensed price and that each read is
metered; the client-type generation diff is empty in CI.

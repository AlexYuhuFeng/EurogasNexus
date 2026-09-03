# R15: Windows Desktop Client Package Report

**Milestone ID:** R15 | **Status:** COMPLETE | **Updated:** 2026-09-01

## Scope

R15 packages the shared React/Vite workspace as a Tauri 2 Windows client. The
desktop client uses the configured backend `/api` surface and never connects to
PostgreSQL, market vendors, or LLM providers directly. Completing this package
milestone does not make the whole product ready for an official V1 release.

## Delivered

- Tauri 2 application under `clients/desktop/` with the shared Web production
  bundle, splash/startup handling, CSP, icons, and deployment-role support.
- Loopback desktop API default `http://127.0.0.1:8000/api`, with governed
  configuration handled by the shared Web client and Tauri deployment command.
- Windows x64 application binary and Client-only NSIS installer.
- English/Mandarin and light/dark/system behavior inherited from the shared Web
  workspace.
- Decision-support and no-direct-database boundaries preserved in the package.

## Build Evidence

Command executed from `clients/desktop` on 2026-09-01:

```powershell
npm run build
```

The command rebuilt the Web workspace, compiled the optimized Rust application,
patched the NSIS bundle metadata, and completed successfully.

Local outputs:

- `clients/desktop/src-tauri/target/release/eurogas-nexus-desktop.exe`
  (`9,031,680` bytes; built 2026-09-01 14:09 Asia/Shanghai);
- `clients/desktop/src-tauri/target/release/bundle/nsis/Eurogas Nexus_0.5.0_x64-setup.exe`
  (`2,254,202` bytes; built 2026-09-01 14:09 Asia/Shanghai).

The current Windows bundle target is NSIS. This report does not claim that an
MSI, signed production installer, or public release artifact was produced.

## Interaction Evidence

The freshly built release executable was launched and inspected directly:

- startup completed and the application remained interactive;
- the top bar reported `RUNTIME DB` and live push while the API was connected to
  the existing PostgreSQL runtime;
- Workspace menu -> Resource Terms opened the new task-led screen;
- Library loaded the persisted
  `preview-portfolio-contract-ttf-pool-2025` record;
- Pool impact displayed the exact PostgreSQL resource id, `10,000 MWh/d`,
  contract/variable/fuel-loss values, pricing method, early-cash value, and net
  margin;
- the draft remained validation-blocked until daily volume is positive, while
  the persisted record was correctly marked ready to persist;
- no panel overlap or truncated action control was observed at the packaged
  desktop viewport.

## Remaining Release Work

These are broader commercial-release tasks, not incomplete R15 shell work:

- code signing and trusted publisher/release-channel evidence;
- full page-by-page desktop accessibility and bilingual regression automation;
- security acceptance for external deployment and official V1 release;
- remaining domain gaps listed in `docs/release/RELEASE_READINESS.md`.

## Next

Continue the page-by-page Web/desktop release audit and retain PostgreSQL as the
runtime source of truth. Do not revive the obsolete Tauri-init/toolchain blocker.

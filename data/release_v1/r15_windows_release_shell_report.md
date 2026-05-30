# R15: Windows Client Package Shell Report

**Milestone ID:** R15 | **Status:** PARTIAL | **Date:** 2026-05-29

## Status: PARTIAL

**Reason:** The Windows client requires the Tauri 2 toolchain (Rust, cargo,
tauri-cli) and the web workspace to be built first (R14 is also PARTIAL
pending npm install). These toolchains are not available in the current
offline environment.

**What was created:**
- `clients/desktop/README.md` with Tauri 2 project documentation
- Package shell structure documented

**What remains:**
- Install Rust toolchain and Tauri CLI
- Build web workspace (`npm run build` in clients/web)
- Create Tauri project wrapping the web workspace
- Configure backend base URL
- Build Windows .msi/.exe

**Internet required:** yes — Rust toolchain, Tauri CLI, and npm packages.

**Fallback applied:** Documented project structure and prerequisites. Web
workspace source exists at `clients/web/`. Once toolchains are installed,
the Tauri wrapper can be created with `cargo install tauri-cli` and
`tauri init`.

## Files

- `clients/desktop/README.md`

## Next

R16: Release Pack and Final Validation

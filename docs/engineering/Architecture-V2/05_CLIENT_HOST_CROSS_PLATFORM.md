# Client, Host and Cross-Platform Architecture

## 1. Product position

### Web
**Universal Access**

Strengths:
- zero install;
- easy deployment;
- administration;
- HQ/review access;
- shared links;
- temporary or remote access.

### Desktop / Terminal
**Professional Analytical Workstation**

Its value is not “more business logic”.
Its value is:
- persistent workspace;
- multi-window;
- multi-monitor;
- keyboard-first workflow;
- native notifications;
- file-system integration;
- deep links;
- better local diagnostics;
- workstation profiles.

## 2. Tauri decision

Retain Tauri 2.

But treat it as a thin, replaceable host.

Tauri SHALL NOT own:
- PostgreSQL;
- vendor credentials;
- provider APIs;
- authorisation;
- pricing/business logic;
- alternate domain calculations;
- duplicate workspace implementation.

## 3. Desktop differentiation

Desktop may provide:

- detachable panels;
- saved window layout;
- multi-monitor restoration;
- global/local shortcuts;
- command palette integration;
- native notifications;
- secure OS-approved token/session integration;
- native file open/save;
- drag/drop import where governed;
- deep links;
- system tray if useful;
- diagnostics bundle export;
- managed updater/installer integration.

## 4. Persistent professional workspace

Desktop should support workspace profiles such as:
- UK Gas Trading Analysis
- Europe Portfolio Oversight
- Intraday Monitoring
- Research

A profile saves layout and context preferences, not sensitive business data or credentials.

## 5. HostCapabilities

Do not scatter `if Windows`, `if macOS`, `if Linux` logic throughout React.

Expose host capabilities:

- notifications
- fileDialogs
- multiWindow
- windowPersistence
- secureStorage
- autoUpdate
- deepLinks
- systemTray
- diagnosticsExport

Web provides browser implementations or “not supported”.

## 6. Cross-platform target

Architecture should be compatible with:
- Windows x64
- macOS ARM64
- Linux x64
- Linux ARM64

But architecture support is not the same as GA support.

Use a Support Matrix.

Example:
- Windows x64 — GA
- Linux x64 — Preview/GA according to evidence
- Linux ARM64 — Preview
- macOS ARM64 — later/preview until packaging, signing and UAT exist

Do not claim support before CI/package/install evidence exists.

## 7. Avoid local-data divergence

Desktop should continue using the same backend API.

Do not introduce:
- local business database;
- local market-data source of truth;
- separate analytics engine;
- hidden offline PnL logic;

unless a future validated offline/latency use case justifies it.

Browser and Desktop must produce the same governed analytical result for the same snapshot/context.

## 8. Platform packaging

Release pipeline should eventually build/test independently for supported targets:
- Windows installer/signing
- Linux x64
- Linux ARM64
- macOS ARM64 signing/notarisation when supported

Packaging differences must not fork product logic.

# Security Policy

## Public Repository Warning

This is a public repository. Do not commit secrets, real vendor data, internal
commercial data, raw market data, contracts, or real business strategy
parameters.

## Reporting

Do not open a public issue for suspected secrets, credentials, entitlement
failures, or vulnerabilities. Report them through the private project security
channel for the repository owner.

## Runtime Guardrails

- Runtime DB URLs must never be printed in full.
- Unknown commercial-data entitlement must fail closed.
- Tests and import-time code must not call external APIs, LLM providers, live
  connectors, live databases, or live infrastructure.
- Trial and release modes must not silently fall back to local files.

## Supported Scope

The current release-candidate line supports the backend/API, PostgreSQL
runtime store, Python SDK, CLI, React Web workspace, Tauri desktop shells,
public-source ingestion, and decision-support research workflows.

Trade execution, order entry, order routing, trade capture, nomination
submission, official approval, legal advice, official trading
recommendations, auto-trading, ETRM replacement behavior, live commercial
provider connectors, multi-tenant SaaS, public signup, and SCIM are out of
scope. Interactive enterprise OIDC login is delivered in CR-10 for
single-organization deployments; live enterprise IdP acceptance remains
deployment-specific.

## Supply Chain

- Release workflows run with least privilege (`contents: read` by default) and
  publish stable only from a pushed semantic tag in the `production` GitHub
  Environment.
- Release actions are pinned to full commit SHAs; Python/Node/Rust dependencies
  are locked and installed with `--require-hashes` / `npm ci` /
  `cargo check --locked`.
- Every distributed artifact is covered by final `SHA256SUMS`; the release
  bundle carries SPDX SBOMs, a release manifest, and GitHub OIDC attestation
  where hosted publishing occurs.
- Windows code signing remains externally pending; unsigned preview/RC assets
  are labelled as such and stable promotion is blocked until verified signing
  evidence exists.
- No Tauri auto-updater ships; managed/offline installation is the only update
  path. Verify checksums before installation (see
  `docs/release/SUPPLY_CHAIN.md`).

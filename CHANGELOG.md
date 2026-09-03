# Changelog

All notable changes to Eurogas Nexus are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project does not yet use semantic versioning for public releases.

## [Unreleased]

- Standardized backend project structure:
  - consolidated research calculations under `src/eurogas_nexus/domain/research`;
  - removed empty source placeholder packages;
  - archived orphaned documentation;
  - updated directory ownership and testing documentation.
- Aligned release validation commands with the stable OpenAPI path count.

## [0.5.0] - Preview release line

The current released line remains `v0.5-preview`. It is a release candidate for
the tested local scope, not a production multi-user deployment.

Highlights:

- PostgreSQL-first backend, API, Python SDK, CLI, Web client, and Tauri desktop shells.
- DB-composed portfolio network optimization and contract-level PnL attribution.
- Intraday opportunity monitoring with persisted alerts and DeepSeek enrichment.
- Storage/nomination assessment workflows (assessment only).
- Local identities, hashed API keys, role authorization, data scopes, and OIDC verification.
- Server, Client-only, and AllInOne deployment roles.

See `docs/release/RELEASE_READINESS.md` for the current release status and
`docs/release/RELEASE_READINESS.md` for production gaps.

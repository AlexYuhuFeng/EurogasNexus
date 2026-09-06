# Changelog

All notable changes to Eurogas Nexus are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
Application artifacts use package version `0.5.0`; the current public channel is
`preview` and is not a GA/stable release.
Release tags use `vX.Y.Z`, `vX.Y.Z-rc.N`, or
`vX.Y.Z-preview.N.<shortsha>`; legacy `v0.5-preview-<run>-<sha>` tags are
historical and are no longer generated.

## Ontology version changes

Ontology versions are tracked independently of application releases and are
asserted by `tests/contract/test_ontology_version_alignment.py`.

- **0.5.0** — the executable vocabulary under
  `src/eurogas_nexus/domain/ontology/` is the semantic source of truth. It
  models the full GRM role inventory, business processes, commodity taxonomy,
  typed interaction properties, and the human-review decision-support boundary.
  `scripts/ontology/generate_grm_ttl.py` renders the model as OWL/Turtle, and
  `tests/contract/test_ontology_grm_parity.py` verifies that the published
  `docs/ontology/eurogas-nexus-grm.ttl` remains in structural parity with the
  executable vocabulary.

## [Unreleased]

- Supply-chain and release hardening (CR-12):
  - single canonical version contract enforced by
    `scripts/release/check_version_consistency.py`;
  - preview/RC/stable channel semantics with tag-only stable promotion;
  - machine-readable `release-manifest.json`, final `SHA256SUMS`, SPDX SBOMs,
    dependency vulnerability evidence, and GitHub OIDC attestations;
  - policy-aware Windows/Linux signing with explicit unsigned-pending state;
  - tag/version-derived artifact names; immutable container `sha-*` tags and
    multi-arch digest acceptance;
  - client/server compatibility contract (`/api/runtime/release`) and a
    blocking client compatibility screen;
  - managed/offline desktop update policy (no Tauri updater ships);
  - pinned runners, toolchains, and GitHub Actions in release/CI workflows.
- Standardized backend project structure:
  - consolidated research calculations under `src/eurogas_nexus/domain/research`;
  - removed empty source placeholder packages;
  - archived orphaned documentation;
  - updated directory ownership and testing documentation.
- Aligned release validation commands with the stable OpenAPI path count.

## [0.5.0] - Preview release line

The current preview line is package version `0.5.0`. It is a release candidate
for the tested local scope, not a production multi-user or GA deployment.

Highlights:

- PostgreSQL-first backend, API, Python SDK, CLI, Web client, and Tauri desktop shells.
- DB-composed portfolio network optimization and contract-level PnL attribution.
- Intraday opportunity monitoring with persisted alerts and DeepSeek enrichment.
- Storage/nomination assessment workflows (assessment only).
- Local identities, hashed API keys, role authorization, data scopes, and OIDC verification.
- Server and Client-only deployment roles.

See `docs/release/RELEASE_READINESS.md` for the current release status and
production gaps.

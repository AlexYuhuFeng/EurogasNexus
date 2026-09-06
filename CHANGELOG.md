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

- Agent-native capability layer (CR-15 / P14):
  - first-class Capability Registry with 68 versioned semantic capabilities
    (determinism, side effects, permissions, entitlement, provenance,
    timeout/retry metadata) and capability discovery API;
  - governed CapabilityRuntime with typed failure codes and
    AUTO/RESEARCH/HUMAN_CONFIRMATION/HUMAN_ONLY action policy;
  - registry-driven MCP adapter with legacy read/sandbox tool compatibility;
  - AgentRun, ToolInvocation, ResearchPlan, ResearchFinding, ResearchBudget,
    ChallengeReport, and ReviewPack persistence plus observable Agent Replay
    (no hidden chain-of-thought);
  - Strategy IR with semantic validation and compilation into the CR-03
    StrategyVersionDefinition;
  - governed ResearchOrchestrator, bounded research budget/final-holdout
    controls, Risk Challenger, and human review pack;
  - System > Agent Research UI; migration `0032_agent_capability_layer`;
    162 OpenAPI paths; 30-case deterministic agent evaluation suite.
- Research data foundation (CR-14 / P13):
  - executable `energy-ontology/v1`, canonical entities, and point-in-time
    source mappings;
  - observed_at/available_at/ingested_at temporal semantics, forecast
    vintages, and actual/forecast/assessment/simulated observation kinds;
  - versioned FeatureDefinition/TargetDefinition/ResamplingPolicy/DatasetSpec
    registries with bounded carry-forward (no unlimited ffill);
  - immutable dataset snapshots, point-in-time builder, leakage validation,
    time splits, quality reports, lineage, and entitlement-gated
    Parquet/CSV export;
  - migration `0031_research_data_foundation`, seeded research catalog,
    restrained System > Research Data UI, and MCP-free agent capability
    contracts;
  - 151 OpenAPI paths with legacy `/api/research/*` sandbox routes preserved.
- Commercial UAT convergence (CR-13):
  - PostgreSQL 16 browser Golden Workflows for Market → Scenario,
    Portfolio → Optimize → Review, and Strategy create/freeze/backtest;
  - P0 fixed: backtest attribution persistence now flushes decision events
    before attribution rows (PostgreSQL FK ordering);
  - P1 fixed: legacy Review deep link, human-readable warning labels, TSO
    access propagation, heading/landmark/contrast accessibility across all
    workspaces;
  - deterministic development-gated UAT fixture pack, AI eval corpus (13/13
    critical cases), axe-core 0 violations, EN/zh-CN 1,259-key parity;
  - user/UAT documentation and internal GA RC acceptance report.
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

# Architecture Decision Record

## ADR Index And Process

This file is the single ADR index and record for Eurogas Nexus. Do not create a
separate architecture-decision authority. Accepted architecture changes must be
recorded here in the same change that introduces them.

The key words "MUST", "MUST NOT", "REQUIRED", "SHALL", "SHALL NOT", "SHOULD",
"SHOULD NOT", "RECOMMENDED", "MAY", and "OPTIONAL" in this section are to be
interpreted as described in RFC 2119 and RFC 8174.

### Index

| ADR | Title | Status |
| --- | --- | --- |
| ADR-0001 | Product is backend-first and multi-surface | Accepted |
| ADR-0002 | PostgreSQL is runtime truth | Accepted |
| ADR-0003 | Live PostgreSQL validation is in the current release | Accepted |
| ADR-0004 | Stable API prefix is `/api` | Accepted |
| ADR-0005 | Stack boundaries are explicit | Accepted |
| ADR-0006 | Domain work is slice-based | Accepted |
| ADR-0007 | Connectors fetch, they do not analyze | Accepted |
| ADR-0008 | SDK and CLI are API consumers | Accepted |
| ADR-0009 | Output metadata is mandatory for decision support | Accepted |
| ADR-0010 | Offline work is the default for local agents | Accepted |
| ADR-0011 | Historical projects are evidence, not source | Accepted |
| ADR-0012 | Product boundary is decision support only | Accepted |
| ADR-0013 | Documentation index, archive/RFC gates, and shared UI primitives are the baseline | Accepted |

The numbered sections below are the historical record for these ADRs. ADR-0003
corresponds to Decision 2A below; subsequent decisions shift by one in the
section numbering.

### Process

1. A proposal MUST state the decision, the alternatives considered, the
   affected owners, and the non-goals.
2. Accepted ADRs MUST be appended to this file and to the index. Existing ADR
   text MUST NOT be edited to mean something different; supersede it with a new
   ADR that links the old one.
3. An accepted ADR SHOULD have at least one contract or focused test that makes
   the decision observable where practical.

## Purpose

This record removes ambiguity for implementation agents and keeps the worktree
aligned with the current gas decision-support goal.

## Decision 1: Product Is Backend-First And Multi-Surface

Decision:

Eurogas Nexus includes a Python backend/API service, PostgreSQL runtime
store, Python SDK, CLI, React/Vite Web workspace, and Tauri desktop shell. It
is backend-first because all runtime truth and integration boundaries remain
behind `/api`, not because clients are absent.

Implication:

- Backend/API remains the authoritative runtime boundary.
- The Python SDK is a required product surface and targets `/api`.
- CLI, Web, and Windows clients consume `/api` contracts.
- Web is the primary trader workspace.
- Windows/Tauri packages the same Web workspace.
- Client work may continue under `clients/`, but clients must not connect
  directly to PostgreSQL or read backend local files.

## Decision 2: PostgreSQL Is Runtime Truth

Decision:

PostgreSQL is the runtime source of truth. Local files are not runtime truth in
trial or release modes.

Implication:

- Runtime reads/writes go through repositories.
- Alembic owns migrations.
- Local files are templates, archives, reports, fixtures, or explicit
  development fallback only.
- Preview/test data must be inserted into PostgreSQL with explicit source
  provenance. Price previews use simulated source systems such as `EEX_Sim`,
  `ICE_OCM_Sim`, and `ICIS_Sim` in `market_observations`.

## Decision 2A: Live PostgreSQL Validation Is In The Current Release

Decision:

the product supports explicit live local PostgreSQL validation when the operator
configures a safe DB URL.

Implication:

- App import, route registration, and default tests remain DB-free.
- Read-only validation against a live database is allowed through documented
  operator commands.
- Migration execution is explicit and must not run during import, startup, or
  default tests.
- Secrets and full DB URLs must never appear in output.

## Decision 3: Stable API Prefix Is `/api`

Decision:

New stable client-facing routes use `/api`.

Implication:

- SDK, CLI, Web, and Windows target `/api`.
- `/api/health` is the canonical public health endpoint.
- Internal routes use `/api/internal`.
- Development routes use `/api/dev`.

## Decision 4: Stack Boundaries Are Explicit

Decision:

Use Python/FastAPI/SQLAlchemy/Alembic for backend runtime, React/Vite/TypeScript
for Web, and Tauri/Rust only for the desktop shell.

Implication:

- Backend import paths must not depend on Node, React, Vite, Tauri, Rust,
  browser APIs, or desktop runtime APIs.
- Client code must not import backend internals.
- Electron is not approved for the current release.
- Historical Rust/React/Tauri demos are product evidence, not source code to
  copy into this repository.

## Decision 5: Domain Work Is Slice-Based

Decision:

New product capability should be added as narrow slices with clear data,
contract, API, client, test, and documentation impact.

Implication:

- Each slice needs a contract doc or documented update.
- Each slice must state DB impact, API impact, data policy, tests, validation
  commands, and rollback notes when relevant.
- UI improvements should expose real backend capability or explicit missing
  inputs, not fabricated client-side data.

## Decision 6: Connectors Fetch, They Do Not Analyze

Decision:

Connectors are transport adapters only.

Implication:

- Connector output goes to ingestion/normalization.
- Analytics belong in domain/application layers after canonical data is stored.
- Live connectors require explicit entitlement and credential approval.
- Tests and imports must not make live external provider or LLM calls.

## Decision 7: SDK And CLI Are API Consumers

Decision:

SDK and CLI must call the backend API. They must not import domain,
application, runtime store, or DB internals.

Implication:

- SDK tests assert paths and response models.
- CLI tests mock SDK/API clients, not domain functions.
- SDK implementation follows `docs/clients/SDK_CLIENT_DESIGN_SPEC.md`.
- CLI implementation follows `docs/clients/CLI_CLIENT_DESIGN_SPEC.md`.
- SDK/CLI expansion should not be bundled into unrelated Web or Windows work.

## Decision 8: Output Metadata Is Mandatory For Decision Support

Decision:

Decision-support outputs must carry enough context for human review.

Implication:

Research and intelligence result models include:

- assumptions;
- missing inputs;
- warnings;
- source references;
- lineage;
- `research_only`;
- `human_review_required`.

## Decision 9: Offline Work Is The Default For Local Agents

Decision:

Future local implementation sessions are assumed offline unless the user says
otherwise.

Implication:

- Plans must state `Internet required: no` for local work.
- Tasks needing current external docs must state `Internet required: yes` and an
  offline fallback.
- Offline fallback means mocks, interfaces, tests, and gap reports.

## Decision 10: Historical Projects Are Evidence, Not Source

Decision:

Historical Desktop projects and demos inform product intent and failure
patterns. They are not source code for the current repo.

Implication:

- Extract workflow and architecture lessons.
- Do not copy old code, assets, data, `.env`, credentials, generated reports,
  or vendor artifacts.

## Decision 11: Product Boundary Is Decision Support Only

Decision:

Eurogas Nexus supports gas-trader intelligence and review. It does not execute
or officially recommend trades.

Implication:

the product must not implement:

- order entry;
- order routing;
- order amendment or cancellation;
- trade capture;
- nomination submission;
- official approvals;
- settlement/accounting;
- legal advice;
- official trading recommendations;
- auto-trading;
- ETRM replacement behavior.

## Decision 12: Documentation And UI Baseline Is Maintained Through One Index And One Primitive Boundary

Decision:

`docs/README.md` is the authoritative documentation index; RFC, archive, and
Markdown-link gates govern documentation changes; shared Web UI primitives live
under `clients/web/src/components/ui`.

Implication:

- Root README remains a landing page, not an operations manual.
- Current, runbook, design-reference, historical, and archived documents are
  labelled in the documentation index.
- Obsolete documents move through the archive policy instead of being deleted or
  mixed with current material.
- Shared UI primitives (`WorkspaceTabs`, `PanelHeader`, `StatusBadge`,
  `MetricStrip`) are owned under `components/ui`; workspace components own domain
  rendering and may consume primitives but must not fork their markup or
  keyboard behavior.

## Current Recommended Next Step

Follow `docs/release/RELEASE_READINESS.md`. It is the active ordered
implementation queue; do not use archived milestone plans as a new work
list.

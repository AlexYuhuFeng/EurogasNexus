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
| ADR-0014 | Public RFC/ExecPlan governance replaces private milestone archives | Accepted |
| ADR-0015 | Professional workstation UI convergence contract | Accepted |
| ADR-0016 | Architecture V2 programme authority and product-experience interaction authority | Accepted (supersedes part of ADR-0015) |

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

## Decision 13: Public RFC And ExecPlan Governance Does Not Restore Private Records

Decision:

The repository provides a lightweight public RFC/ExecPlan workflow under
`docs/engineering/`. It does not restore deleted internal plans or publish a
private milestone archive. The public workflow is the current implementation
path for reusable proposals and bounded plans.

Implication:

- `docs/engineering/RFC_PROCESS.md` defines proposal and acceptance workflow.
- `docs/engineering/RFC_INDEX.md` and `EXECPLAN_INDEX.md` contain only reusable
  public records.
- README files remain descriptive navigation; normative requirements use RFC
  2119 and RFC 8174 language in policies, contracts, RFCs, or ADRs.
- The accepted ADR history above remains unchanged; future changes append or
  supersede rather than silently rewriting an accepted decision.

## Decision 14: Professional Workstation UI Convergence Contract

Decision:

[RFC-0001](../engineering/RFC-0001-UI-CONVERGENCE.md) is accepted on
2026-09-08 as the binding contract for shared Web/desktop visual and
interaction convergence. The Professional UI Constitution is the sole visual
and interaction authority; `MOTION_SYSTEM.md` is subordinate. `UI_CONTENT_STANDARDS.md`
continues to govern content, domain, time basis, rights, provenance,
entitlement, no-execution, and client-boundary rules. Architecture and API
contracts prevail for domain behavior, schemas, endpoint semantics, and
server/client boundaries. The paired EN/CN guides, `WORKSPACE_LAYOUT_STANDARD.md`,
and `ACTION_GEOGRAPHY.md` are nonnormative or subordinate implementation
companions as defined by RFC-0001.

Implication:

- Contract adoption is distinct from implementation acceptance. Screenshots,
  runtime review, tests, accessibility checks, and visual evidence remain open
  gates and are not claimed by this decision.
- The pre-refactor workflow inventory and coverage remain incomplete; its gate
  stays open.
- This decision changes no domain, API, numerical, rights, calendar, or
  execution rule beyond the authority reconciliation recorded in RFC-0001.

Review record:

- The planner reviewed the drafts, diffs, component census, runtime UI audit,
  and RFC clarifications.
- Planck independently reviewed the contract direction, and the clarifications
  were addressed.
- No human-owner review or implementation acceptance is claimed.

## Decision 15: Architecture V2 Programme Authority And Product-Experience Interaction Authority

Decision:

The Architecture V2 pack under
[`docs/engineering/Architecture-V2/`](../engineering/Architecture-V2/00_README.md)
is accepted as the binding target architecture and product-experience
authority for Eurogas Nexus, under the operating rules of
[`AUTONOMOUS_EXECUTION_POLICY.md`](../engineering/Architecture-V2/AUTONOMOUS_EXECUTION_POLICY.md).

Authority is allocated as follows:

- [Product Experience Architecture](../engineering/Architecture-V2/04_PRODUCT_EXPERIENCE_ARCHITECTURE.md)
  governs task flows, shell composition, workspace patterns, navigation
  composition, panel taxonomy, the Inspector, action geography, the canonical AI
  actions and the command/keyboard interaction model.
- [`PROFESSIONAL_UI_CONSTITUTION.md`](../clients/PROFESSIONAL_UI_CONSTITUTION.md)
  retains its authority for typography, density, spacing, component styling and
  visual motion, and is subordinate to the product-interaction contracts above
  where the two overlap.
- [`MOTION_SYSTEM.md`](../clients/MOTION_SYSTEM.md) remains the binding
  subordinate motion contract and cannot create a competing interaction model.
- [`UI_CONTENT_STANDARDS.md`](../clients/UI_CONTENT_STANDARDS.md) retains
  authority for content, domain, time basis, rights, provenance, entitlement and
  no-execution rules.
- Domain, API, data, security and release contracts retain their existing
  precedence for domain behaviour, endpoint semantics, schemas and
  server/client boundaries. A UI document cannot override them.
- Functional assignment and work mode SHALL NOT grant backend authority
  ([Constitution](../engineering/Architecture-V2/02_ARCHITECTURE_CONSTITUTION.md)
  rules 16-20, 27). Composition never creates a permission.

Implication:

- [RFC-0001](../engineering/RFC-0001-UI-CONVERGENCE.md) remains accepted. Only
  its authority-matrix row naming the Professional UI Constitution as sole
  *interaction* authority is superseded, and it is superseded by this record
  rather than by editing RFC-0001 or Decision 14. Decision 14's history, its
  implementation acceptance gates and its rights-validation matrix remain in
  force unchanged.
- The normative hierarchy conflict recorded in
  [`AUTHORITY_RECONCILIATION_PROPOSAL.md`](../engineering/Architecture-V2/AUTHORITY_RECONCILIATION_PROPOSAL.md)
  is closed. That proposal's "PROPOSED" status is historical; this decision is
  the accepted resolution.
- Wave 1 delivers the interaction authority as machine-readable contracts under
  `clients/web/src/app/experience/` with focused tests, so the authority is
  executable rather than prose: shell regions, workspace patterns, panel
  taxonomy, action geography, canonical AI actions, the Inspector contract, the
  command palette and the Active Context contract.
- Contract adoption is not implementation acceptance. RFC-0001's screenshots,
  visual review, accessibility, performance, EN/CN, entitlement and UAT gates
  stay open, and the pre-refactor workflow inventory gap is unaffected.
- No domain, API, numerical, rights, calendar, execution, permission or release
  behaviour changes by this decision.

Review record:

- Generated under `AUTONOMOUS_EXECUTION_POLICY.md` section 2, which permits
  automatic supersession of an accepted ADR when it conflicts with Architecture
  V2, provided the superseding decision links the old one and preserves its
  history. No human approval was sought or required for this reconciliation.
- Evidence reviewed: `11_CURRENT_TO_TARGET_GAP_MATRIX.md` rows 24-27 (UI
  Constitution kept but subordinate; navigation and page composition marked
  REFACTOR), the W0-01 client inventory, the W0-02 backend access inventory, and
  the Wave 1 contracts with their focused tests.
- The professional trader/product-owner review of the resulting interaction
  grammar remains an open UAT gate; this record does not claim it.

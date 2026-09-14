# Model Routing Policy — Astra + DeepSeek Flash V4.1

## 1. Default routing

### GPT-6 Astra
Use primarily for:
- architecture planning;
- cross-module decomposition;
- ADR review;
- security/entitlement decisions;
- product-experience architecture;
- data architecture;
- migration strategy;
- integration review;
- wave acceptance.

Use light planning/reasoning unless complexity requires more.

### DeepSeek Flash V4.1
Use as the **default implementation worker** for:
- Python/FastAPI implementation;
- React/TypeScript implementation;
- tests;
- adapters;
- DTOs;
- ordinary DB migrations;
- compatibility shims;
- documentation;
- repetitive UI convergence;
- lint/type/build fixes;
- fixture/golden-case support;
- focused refactors.

Because DeepSeek capacity is abundant, prefer giving it several well-bounded sequential tasks rather
than consuming Astra implementation tokens.

## 2. When DeepSeek may plan locally

DeepSeek may do **local implementation planning** inside a bounded task:
- choose helper names;
- choose local function decomposition;
- choose test fixture structure.

DeepSeek must not independently change:
- platform architecture;
- security model;
- major domain semantics;
- data-store strategy;
- UX shell/interaction grammar;
- accepted ADR direction.

If it discovers such a need, it stops and reports to Astra.

## 3. Astra escalation triggers

Astra takes over when:
- requirement is ambiguous;
- access/security/licensing is touched materially;
- DB migration is destructive or non-obvious;
- numerical semantics may change;
- worker proposes new infrastructure;
- worker needs to alter a binding contract;
- worker fails twice;
- worker finds current repo and V2 fundamentally inconsistent.

## 4. Worker brief size

A worker brief should include only:
- task ID;
- objective;
- relevant V2 authority sections;
- relevant existing repo contracts/files;
- invariants;
- expected touched area;
- focused validation;
- non-goals;
- report format.

Avoid feeding DeepSeek all V2 documents for routine work.

## 5. Cheapest-path principle

Prefer:
DeepSeek implementation -> focused tests -> Astra review

over:
Astra implementation -> Astra self-review.

Use Astra direct coding only when genuinely more efficient or safer.

## 6. Repetitive migrations

Once Astra accepts a canonical pattern, DeepSeek should own most repetitive rollout.

Examples:
- migrating additional workspaces to a shared Inspector;
- replacing inconsistent status components;
- applying HostCapabilities wrappers;
- updating docs/test fixtures;
- converting repeated endpoint composition to accepted projection clients.

Astra reviews representative samples and wave gates rather than every trivial line.

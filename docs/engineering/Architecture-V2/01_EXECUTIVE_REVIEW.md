# Executive Architecture & Product Delivery Review

## 1. Overall judgment

Eurogas Nexus is not an immature prototype.

The current repository already contains unusually strong engineering foundations:
- FastAPI backend with a stable `/api` boundary;
- React/Vite Web client;
- Tauri 2 desktop packaging;
- PostgreSQL + Alembic;
- API-only SDK/CLI clients;
- OIDC/PKCE and session infrastructure;
- route-level permission declarations;
- entitlement concepts;
- release manifests, checksums, SBOM and provenance;
- backup/restore, DR, incident-response and SLO documentation;
- research-data architecture;
- capability registry and governed agent runtime;
- explicit no-execution product boundary.

These foundations should be preserved.

## 2. Main diagnosis

The project has become **feature-rich before product architecture has fully converged**.

The main weaknesses are:

### A. Function-centric user experience
The product exposes Market, Portfolio, Scenario, Strategy, Review, Research, Agent, Source Center,
Runtime and Settings as largely independent capabilities.

This produces “feature museum” behaviour:
everything exists, but the user must mentally assemble the workflow.

### B. Inconsistent interaction model
Different pages use different:
- navigation logic;
- controls;
- information density;
- panel structure;
- action placement;
- error states;
- result presentation;
- context handling.

The existing UI Constitution improves visual consistency but does not solve the deeper problem:
**the product lacks one coherent usage model**.

### C. Role/persona/permission coupling risk
Real users overlap functions.
A person can be Trader + Analyst + Researcher.
Exclusive personas are therefore the wrong security and experience model.

### D. Control Plane leakage
Credentials, provider administration, runtime internals and platform controls should not be ordinary
business-user workspace features.

### E. Data Source is too provider-centric
Users should consume governed Data Products.
Operators should manage Provider Connections.
These are different concepts.

### F. Broad API surface creates frontend-composition risk
The existing API is valuable and should remain compatible, but React should not reconstruct critical
business state by joining many low-level endpoints with mixed timestamps.

### G. Reproducibility is not yet a universal platform invariant
Scenario, optimisation, strategy, report and AI results should bind to a coherent Analysis Snapshot.

### H. Desktop value proposition is under-defined
A Tauri shell that merely displays the same Web page has weak user value.
Desktop should become a **professional analytical workstation**, not a duplicate application.

### I. Documentation is extensive but not yet fully delivery-oriented
The problem is no longer “write documentation”.
It is:
- audience separation;
- deployment readiness;
- upgrade/support ownership;
- commercial IT handover;
- long-term maintenance clarity.

## 3. Architectural conclusion

If Eurogas Nexus were designed today from the business goal, the recommended technology stack would
still be close to the current one:

- Python/FastAPI
- React
- Tauri thin desktop host
- PostgreSQL
- background workers
- governed data layer
- API-first clients
- deterministic analytics
- governed AI

Therefore V2 is **not a stack rewrite**.

It is a convergence programme around:
- product experience;
- decision workflow;
- data governance;
- identity/access;
- control plane;
- projections;
- operations;
- maintainability.

## 4. Default architecture style

Use:

**Modular Monolith + Worker Runtime**

Do not introduce Kubernetes, Kafka, service mesh, microservices or multiple datastores merely to
appear “enterprise” or “cloud native”.

Distributed components require:
- measured need;
- clear ownership/scale/isolation reason;
- ADR;
- migration and operational-cost justification.

## 5. Most important shift

Current mental model:

`Feature / Workspace -> Endpoint -> Table / Service`

Target mental model:

`User Context -> Decision Context -> Application Projection -> Governed Capability -> Domain/Data`

This is the central Architecture V2 transformation.

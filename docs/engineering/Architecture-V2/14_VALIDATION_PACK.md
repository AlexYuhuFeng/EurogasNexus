# Architecture V2 Validation Pack

This file defines acceptance categories, not exact repository commands where paths may change.
Harness should map these to current scripts/tests.

## A. Architecture
- FastAPI remains authoritative runtime boundary.
- React remains one primary UI.
- Tauri remains thin.
- no direct client DB access.
- no direct client vendor integration.
- no new datastore/microservice without ADR.

## B. Experience
- canonical shell documented/implemented as seam.
- same interaction grammar across representative work modes.
- Active Context persists predictably.
- Inspector behaviour is consistent.
- action geography is consistent.
- no unnecessary new top-level page.
- representative user tasks have coherent click path.
- keyboard/navigation model documented.
- AI actions use canonical interaction model.

## C. Identity/security
- work mode cannot grant permission.
- effective access is server-side.
- admin does not automatically imply commercial access.
- restricted Data Products remain inaccessible.
- AI invocation re-authorises.

## D. Data
- Provider Connection separate from Data Entitlement.
- Data Product concept exists.
- user-facing freshness/provenance abstraction defined.
- Analysis Snapshot contract defined before decision convergence.

## E. Client/host
- Web and Desktop share business UI.
- HostCapabilities centralises native differences.
- no scattered OS-specific business behaviour.
- package support matrix distinguishes architecture support from GA support.

## F. Product operations
- existing release engineering preserved.
- upgrade/rollback/backup rules remain explicit.
- diagnostics contain no secret/licensed/commercial leakage.
- business health and technical health are separate.

## G. Documentation
- V2 docs linked/owned appropriately.
- no conflicting parallel normative authorities left unresolved.
- deployment/commercial readiness requirements identified.
- ADR supersession used where necessary.

## H. Testing
Focused tests during each wave.
Full acceptance only at wave/release gates.

Critical analytical calculations should eventually be protected by Golden Scenarios.

## I. UX review checklist

For each canonical prototype/workflow:
- What user task does this solve?
- What is the starting context?
- What is the minimum number of navigation changes?
- Are actions where users expect them?
- Is the same object represented consistently elsewhere?
- Are loading/empty/error/restricted states defined?
- Is evidence/provenance discoverable?
- Is the result reproducible?
- Is AI helpful but non-authoritative?
- Does Desktop add workstation value without forking logic?

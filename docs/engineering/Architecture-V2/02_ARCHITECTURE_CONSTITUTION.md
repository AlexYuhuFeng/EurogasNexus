# Architecture Constitution V2

The following rules are binding unless superseded by an accepted ADR.

## Product boundary

1. Eurogas Nexus SHALL remain a decision-support platform.
2. It SHALL NOT implement order entry, order routing, nomination submission, settlement, accounting,
   auto-trading or official trading recommendations.
3. Material commercial decisions remain human-owned.
4. Material analytical outputs SHALL carry assumptions, provenance, warnings and version context.

## Architecture style

5. Default architecture SHALL be a modular monolith plus worker runtime.
6. Microservices and distributed infrastructure require measured need and ADR.
7. Modules SHALL interact through application/domain contracts rather than table coupling.
8. No new infrastructure technology shall be added purely for architecture fashion.

## Data

9. PostgreSQL SHALL remain the principal runtime system of record where appropriate.
10. PostgreSQL SHALL NOT be interpreted as a requirement to store every future raw archive, Parquet
    dataset, large immutable artefact or binary object.
11. Users consume governed Data Products, not provider endpoints.
12. Clients and AI SHALL NOT call vendor APIs directly.
13. Provider connectivity and user data entitlement are separate.
14. Derived values preserve lineage and calculation version.
15. New storage technology requires evidence of need and ADR.

## Identity and security

16. Authentication, capability, organisational scope, commercial scope and data entitlement are distinct.
17. Functional assignment/persona/work mode SHALL NOT grant backend authority.
18. Backend enforcement is authoritative.
19. UI visibility is not a security boundary.
20. Explicit deny/licence restriction overrides grants.
21. Platform administration does not automatically grant commercial-data access.
22. AI inherits user authority and has no super-user bypass.
23. Secrets remain server/control-plane owned.

## Experience

24. There is one primary React UI implementation.
25. Web and Tauri share the same business UI.
26. Different user types share one interaction language.
27. Work modes change composition, not authority.
28. A new capability does **not** automatically earn a new page.
29. Business users see business-impact health; operators see technical internals.
30. Product behaviour SHALL be task-oriented rather than feature-page-oriented.

## Application

31. Active Context is first-class.
32. Analysis Snapshot is first-class.
33. Decision Case is first-class.
34. Application projection/query services provide coherent client read models.
35. Frontend code SHALL NOT reconstruct critical commercial state from unrelated endpoint calls.
36. Long-running work converges on a common Job model.
37. Errors use a stable taxonomy and correlation IDs.

## AI

38. Deterministic engines own calculations, optimisation, validation and numeric outputs.
39. LLMs may interpret objectives, draft plans/hypotheses, synthesise evidence, challenge and explain.
40. Agent tools are governed registered capabilities.
41. Licensed/sensitive-data policy is checked before external LLM calls.
42. Agent traces store observable actions/evidence, never hidden chain-of-thought.

## Delivery

43. Version, channel, build identity and compatibility have canonical machine-readable truth.
44. Stable releases are immutable.
45. Upgrade, rollback, backup, restore and compatibility are product contracts.
46. Documentation impact is part of Definition of Done.
47. Architecture is cloud-provider-neutral.

## Client/host

48. Tauri remains a thin, replaceable host.
49. Business/domain logic SHALL NOT diverge between Web and Desktop.
50. Platform differences are expressed through HostCapabilities, not scattered OS checks.

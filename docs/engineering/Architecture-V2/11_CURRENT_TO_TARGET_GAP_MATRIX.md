# Current-to-Target Gap Matrix

Legend: KEEP / EVOLVE / REFACTOR / REPLACE / REMOVE / DEFER

| Area | Current state | Decision | Target |
|---|---|---|---|
| FastAPI backend | Mature API-first service | KEEP | Authoritative runtime/API boundary |
| React/Vite | Shared Web workspace | KEEP | Single business UI |
| Tauri | Thin Web wrapper | KEEP/EVOLVE | Professional workstation host |
| PostgreSQL | Runtime truth | KEEP/EVOLVE | Primary system of record, not universal artefact store |
| Alembic | Explicit schema authority | KEEP | Preserve |
| SDK/CLI | API consumers | KEEP | Preserve |
| Backend layers | Domain/application/db/api | KEEP | Strengthen module boundaries |
| API surface | Broad | EVOLVE | Add application projections/query services |
| RBAC | Coarse role floors | EVOLVE | Capabilities + scopes + entitlements + constraints |
| Permission registry | Machine-declared | KEEP/EVOLVE | Finer capability mapping over time |
| Persona | Not robustly first-class | ADD | Functional Assignments + Work Modes |
| Admin | Can conceptually become too broad | REFACTOR | Platform admin separate from commercial access |
| Source Center | Provider/user concerns mixed | REFACTOR | Data Product vs Provider Administration |
| Credentials | Backend owned | KEEP/EVOLVE | Control-plane-only management UX |
| Data entitlement | Exists conceptually | EVOLVE | First-class entitlement service |
| Data architecture | Strong canonical/research base | KEEP/EVOLVE | Unified Data Platform |
| Storage | PostgreSQL-centric | KEEP/DEFER | Object storage only when justified |
| Market/Portfolio/Strategy pages | Feature-centric | REFACTOR | Task/work-mode composition |
| UI Constitution | Strong visual baseline | KEEP | Subordinate to Product Experience Architecture |
| Navigation | Functional workspace based | REFACTOR | Shell + patterns + work-mode composition |
| Cross-page UX | Inconsistent | REPLACE/REFINE | Shared interaction grammar |
| Inspector/detail | Inconsistent | ADD | Canonical Inspector |
| AI UI | Often isolated | EVOLVE | Cross-workspace canonical AI actions |
| Scenario/Review | Existing workflows | EVOLVE | Decision Platform |
| Research Data | Strong technical foundation | EVOLVE | Research-question-led experience |
| Agent architecture | Strong governed capability model | KEEP/EVOLVE | Contextual Copilot |
| Deterministic analytics | Strong | KEEP | Numeric source of truth |
| Release engineering | Strong | KEEP | Integrate V2 metadata/lifecycle |
| Backup/DR/SLO | Exists | KEEP/EVOLVE | Validate against deployment profiles |
| Deployment | Server/client oriented | EVOLVE | Developer/Small-team/Enterprise profiles |
| Observability | Health/metrics present | EVOLVE | Business health + tracing/correlation |
| Error handling | Mixed | REFACTOR | Stable error taxonomy |
| Jobs | Feature-specific run models | REFACTOR | Unified Job architecture |
| Reproducibility | Partial run/snapshot evidence | EVOLVE | Analysis Snapshot invariant |
| Docs | Extensive | KEEP/REFACTOR | Audience + handover hierarchy |
| Desktop value | Mostly packaging | EVOLVE | Persistent workstation/multi-window/notifications |
| Cross-platform | Windows/Linux emphasis | EVOLVE | HostCapabilities + support matrix incl. ARM/macOS |
| Cloud architecture | Partially implicit | ADD | Provider-neutral deployment profiles |
| Microservices | Not default | KEEP ABSENT | Avoid until justified |
| Trade execution | Absent | KEEP ABSENT | Preserve boundary |

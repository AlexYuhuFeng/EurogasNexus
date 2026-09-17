# W2-01 — Effective Access, Capabilities and the ExperienceProfile

Status: **delivered (Wave 2)**. Authority:
[06_IDENTITY_ACCESS_CONTROL_PLANE.md](06_IDENTITY_ACCESS_CONTROL_PLANE.md) sections 1-4 and 7-9,
[02_ARCHITECTURE_CONSTITUTION.md](02_ARCHITECTURE_CONSTITUTION.md) rules 16-23 and 27,
[12_MIGRATION_ROADMAP.md](12_MIGRATION_ROADMAP.md) Wave 2, ADR-0016.

## 1. The two equations

```text
identity + capability grants + scope + data entitlements + constraints -> effective access
effective access + functional assignments + selected work mode + preferences -> composition
```

Wave 2 implements the first equation explicitly and the second one as a
*composition-only* contract. The second equation never creates a permission: that
property is machine-checked (section 4).

## 2. Capability catalogue

`src/eurogas_nexus/security/capabilities.py` declares the V2 capability vocabulary
reachable in this repository today. Every capability is bound to the fine-grained
permissions that already existed (`security/authorization.py`), so a capability can
only ever be a *derived view* of the role model:

- `market.read`, `portfolio.read`, `portfolio.assumption.write`
- `scenario.design`, `optimization.run`
- `strategy.read`, `strategy.design`, `strategy.edit`, `strategy.freeze`, `strategy.retire`, `strategy.shadow.operate`
- `decision.evidence.read`, `decision.review`
- `research.query`
- `agent.capability.read`, `agent.capability.invoke`, `agent.run.read`, `agent.research.run`
- `provider.connection.view`, `provider.ingestion.operate`, `provider.backfill.operate`, `provider.credential.manage`, `provider.certification.manage`
- `runtime.read`, `access.read`, `access.manage`, `api_keys.manage`, `audit.read`, `identity.self.read`

Capabilities that Architecture V2 names but nothing implements yet (for example
`dataset.build`) are deliberately absent rather than declared with nothing behind
them.

## 3. Platform administration is not commercial access

`ROLE_PERMISSIONS[ADMIN]` is now `PLATFORM_ADMINISTRATION_PERMISSIONS`: identity,
API keys, audit, providers, runtime and the capability catalogue. It holds **no**
commercial-data permission. `COMMERCIAL_PERMISSIONS` names the commercial set
(market and monitoring data, portfolio, contracts, scenario, optimisation,
strategy, decision evidence, licensed research and agent runs).

Enforcement is per request, not per screen:

- `security/permissions.py` declares `COMMERCIAL_DATA_PREFIXES` and
  `serves_commercial_data(path)`, so the commercial surface is a reviewed list
  rather than a guess.
- `api/dependencies/commercial_access.py` runs in the authenticated profiles after
  the route-permission dependency and refuses a commercial path with 403
  `commercial_access_not_granted` when the identity holds no commercial
  capability. The response names the recovery: grant a commercial role (for
  example `ANALYST`) alongside the administration role, or request a data
  entitlement.
- Rank is unchanged: ADMIN still satisfies every route *floor*, so the control
  plane keeps working; only commercial data is refused.

Migration for deployments: an administrator who needs commercial data now holds
two overlapping assignments (`ADMIN` + `ANALYST`). Roles are functional
assignments, not exclusive personas, so this is the intended model rather than a
workaround. The UAT fixture
(`scripts/uat/seed_browser_identity.py`) was updated to `ADMIN` + `ANALYST` for the
same reason.

Deliberately outside the commercial boundary (a platform administrator needs
them): health, `/api/me`, auth, access, audit, credential metadata, sources,
source certification, ingestion runs, runtime, glossary, the reference network,
physical/storage/LNG/weather context, and the capability *catalogue*. Invoking a
capability over commercial evidence is commercial through the governed invoke path.

## 4. The ExperienceProfile

`build_experience_profile(principal)` returns the safe composition contract, served
inside `GET /api/me` as `data.experience` (additive; the existing payload is
unchanged and no new request is introduced, so the client still has one identity
call):

| Field | Meaning |
|---|---|
| `principal_id`, `role`, `roles` | The authenticated identity and its overlapping role assignments. |
| `functional_assignments` | `TRADER`, `HQ_BUSINESS_ANALYST`, `REVIEWER_MANAGEMENT`, `QUANT_RESEARCHER`, `DATA_OPERATOR`, `PLATFORM_ADMINISTRATOR` - derived, and combinable. |
| `available_work_modes` | `TRADING_ANALYSIS`, `PORTFOLIO_OVERSIGHT`, `RESEARCH`, `REVIEW`, `ADMINISTRATION`, in fixed priority order. |
| `default_work_mode` | The first available mode, or `null`. |
| `effective_capabilities` | Capability names the identity holds. |
| `commercial_capabilities` | The commercial subset, so a surface can explain a refusal. |
| `scope_refs`, `data_entitlement_refs` | The scope the backend can express today: `DATA:<family>` from `principal.data_scopes`. |
| `unsupported_scope_kinds` | `ORGANIZATION`, `PORTFOLIO`, `MARKET`, `REGION` - declared unsupported instead of fabricated. |
| `work_mode_grants_authority` | Always `false`. |

Invariants, asserted by `tests/security/test_experience_profile.py`:

1. every capability is bound to permissions some role can actually grant;
2. `profile_stays_within_role_permissions` holds for every role, so the profile can
   never widen access;
3. functional assignments and work modes are derived from capabilities and can be
   combined, never exclusive;
4. the payload carries capability names only - no secret, record or raw value;
5. a non-active principal's profile still cannot exceed its role (enforcement stays
   in `authorize`, which denies a disabled principal outright).

## 5. Client composition

`clients/web/src/app/experience/experienceProfile.ts` parses the contract into the
client's composition vocabulary:

- server `SCREAMING_SNAKE` work modes map onto the client's `kebab-case` ids;
- a work mode the client does not implement is dropped, and a default that cannot
  be composed falls back to the first usable mode;
- a profile claiming composition authority, or an absent profile, yields an
  *empty* composition rather than "every mode", so the client cannot widen itself;
- `compositionHoldsCapability` is documented as a label for access the backend
  already granted, never a client-side gate.

`clients/web/tests/experienceProfile.test.ts` pins all of the above.

## 6. Compatibility

- API: additive. `GET /api/me` gains `data.experience`; every existing field, path
  and status code is unchanged, and no new endpoint was introduced.
- DB: unchanged. No schema, migration or datastore change.
- Security: **narrowed by design** for one case only - a platform-administration
  identity no longer reaches commercial data. Every other role keeps exactly its
  previous reach, and the legacy deployment-token service principal is unchanged.
- Client: additive; the client ignores unknown payload fields until it reads them.
- Numerics, release and DR: unchanged.

## 7. Deferred (next bounded work)

- Organisation, portfolio, market and region scope do not exist in the backend;
  `unsupported_scope_kinds` reports that honestly. Expressing them is a Wave 2
  follow-up requiring a schema decision of its own.
- `GET /api/me` is served per request; a client cache of the composition and the
  Wave 9 navigation migration onto `available_work_modes` are UI work.
- MCP still runs as an environment pseudo-principal with wildcard scopes and the
  two direct LLM routes do not re-authorise against user authority
  ([W0-02](W0-02_BACKEND_ACCESS_INVENTORY.md) finding 7). Closing that is Wave 7
  work with a security review; the capability model delivered here is its
  prerequisite.
- The admin surface can still write `data_scopes` for any principal, including
  itself. Separation of duties (who may grant commercial entitlement) is a policy
  decision with its own ADR, tracked as conflict C6b.

## 8. Verification

- `tests/security/test_experience_profile.py` - capability catalogue, no-widening
  proof per role, overlapping assignments, work-mode derivation, scope honesty,
  payload shape, and `GET /api/me` for an ADMIN and an ANALYST identity.
- `tests/security/test_platform_admin_commercial_boundary.py` - the commercial
  surface declaration, ADMIN refused commercial data, ADMIN+ANALYST allowed,
  every other role and the legacy token unchanged, and the control plane still
  reachable for an administration-only identity.
- `clients/web/tests/experienceProfile.test.ts` - client composition parsing and
  fail-closed behaviour.
- Full suite: `python -m pytest tests -q --ignore=tests/integration` and
  `node --test "tests/*.test.ts"` in `clients/web`; results are recorded in the
  execution checkpoint.

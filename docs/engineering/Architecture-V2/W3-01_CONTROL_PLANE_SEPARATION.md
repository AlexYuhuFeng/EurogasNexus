# W3-01 — Control Plane Separation

Status: **delivered (Wave 3)**. Authority:
[06_IDENTITY_ACCESS_CONTROL_PLANE.md](06_IDENTITY_ACCESS_CONTROL_PLANE.md) section 8,
[11_CURRENT_TO_TARGET_GAP_MATRIX.md](11_CURRENT_TO_TARGET_GAP_MATRIX.md) row "Admin",
[12_MIGRATION_ROADMAP.md](12_MIGRATION_ROADMAP.md) Wave 3, ADR-0016, and
[W2-01](W2-01_EFFECTIVE_ACCESS_AND_EXPERIENCE_PROFILE.md) for the capability model.

## 1. What the wave required

> Administration should be a distinct product surface... Normal business users
> should not navigate through these controls.
> - `06_IDENTITY_ACCESS_CONTROL_PLANE.md` section 8

Wave 2 delivered the authority half (platform administration holds no commercial
capability). Wave 3 delivers the surface half: the control plane stops being a set
of pages inside the business workspace.

## 2. Delivered

| Element | Before | After |
|---|---|---|
| Primary navigation | Five primaries; `sources`, `runtime`, `access` inside `System` | Five business primaries plus a capability-gated **Administration** primary owning `sources`, `runtime`, `access` |
| Administration visibility | Always visible; `AccessCenter` had a client-side `identity.manage` guard only | Offered only when the identity's composition holds an administration capability; hidden otherwise |
| Deep link into a control-plane page | Mounted the workspace, whose requests the backend then refused | Renders a bounded `RestrictedSurface` notice (one `h1`, no controls, `role="alert"`) |
| Business shell | Provider/runtime/access administration one tab away from the market | Source and runtime *status* indicators stay in the business shell; the surfaces that operate them moved behind the administration boundary |
| Specification | `WORKSPACE_NAVIGATION_SPEC.md` described five primaries | Updated: six primaries, the gate, the capability list and the preserved deep links |

Definitions:

- **Administration capabilities**: `access.manage`, `api_keys.manage`,
  `provider.ingestion.operate`, `provider.backfill.operate`,
  `provider.credential.manage`, `provider.certification.manage`
  (`clients/web/src/app/experience/experienceProfile.ts`).
- **Control-plane pages**: declared once in
  `clients/web/src/app/navigation/productNavigation.ts` (`controlPlane: true`),
  so the shell never hardcodes a page list. The workspace-pattern registry agrees
  with it, and the Wave 1 conformance test fails if the two disagree.

## 3. Fails closed, and is not a security boundary

1. An absent, malformed or authority-claiming ExperienceProfile hides the
   administration surface rather than showing it.
2. Reading source or runtime status is not administration, so no role loses its
   business indicators; only the operating surfaces moved.
3. Navigation is presentation. The backend authorises every request:
   `route_permission.py` enforces the role floor, and
   `api/dependencies/commercial_access.py` refuses commercial data to a
   platform-administration identity (Wave 2). A user who forges a deep link gets a
   notice and 403 responses, never data.

## 4. Compatibility

- Every page id, deep link and route is unchanged; `?workspace=access` still
  resolves to `access`, and existing bookmarks keep working.
- The browser-acceptance matrix still sweeps the same 16 workspaces; the change is
  a navigation grouping, not a page change.
- Settings stays a business surface: display preferences, language, theme and the
  bounded backend-connection setting are user preferences, not platform
  configuration.
- `Research Data` and `Agent Research` stay in the business workspace; the V2
  Research Studio composition is Wave 7 work.

## 5. Deferred

- **C6b — separation of duties for entitlement grants.** The administration
  surface can still write `data_scopes` for any principal, including itself.
  Whether a commercial entitlement grant needs a second approver is a policy
  decision with its own ADR; it is not silently decided here.
- `SourceCenter` still mixes provider operations with user-facing data status. The
  V2 Data Product vs Provider Connection split is Wave 4 work, and the provider
  operations already moved behind the administration boundary.
- The remaining `settings` surface mixes user preferences with a bounded
  deployment-provided backend URL; the user-preference vs system-configuration
  separation is completed when the deployment profile exposes managed
  configuration (Wave 8).

## 6. Verification

- `clients/web/tests/controlPlaneSeparation.test.ts` — capability gate per
  capability and per role, fail-closed behaviour for absent and
  authority-claiming profiles, the top-bar filter, the deep-link restriction, the
  restricted notice having exactly one `h1` and no control, the control-plane page
  declaration, and EN/zh-CN label parity.
- `clients/web/tests/productNavigation.test.ts` — six primaries, defaults,
  `isControlPlanePage` coverage and stable legacy ids.
- `tests/contract/test_workspace_navigation_contract.py` — the registry contract,
  the new control-plane boundary assertions and the top-bar composition rule.
- Full suites: `node --test "tests/*.test.ts"` in `clients/web` and
  `python -m pytest tests -q --ignore=tests/integration`; results are recorded in
  the execution checkpoint.

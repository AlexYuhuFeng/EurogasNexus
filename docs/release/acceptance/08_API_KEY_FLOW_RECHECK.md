# API-key lifecycle recheck — 2026-10-08

Status: **PASS for the bounded issue/authenticate/revoke lifecycle**, 30 host-browser assertions in the corrected second attempt. Broader permissions and provider acceptance remain open.

Actual Chromium UI issuance, one-time secret display, dismissal, reload, isolated identity read, UI revocation and reload were executed on the existing local runtime. The tested fixture has ADMIN authority; this does not prove least-privilege personas, scope attenuation, commercial data entitlement or provider connectivity. No users, role assignments, principal scopes or provider credentials were changed.

## Two attempts, preserved separately

1. `DNX-UAT-20261008-unique`, key ID `e9c94872e85543e5801520f2`: UI issuance and display passed. The script incorrectly supplied only `X-Eurogas-Identity`; the deployment gate correctly returned 401 `public_api_token_missing`. This was an instrumentation error, not evidence that the new identity key was invalid. Cleanup revoked this exact key through the UI (200). The registry before this attempt had zero keys. Its original artifacts remain in `.dnx-out/uat-access-20261008/first-attempt/`.
2. `DNX-UAT-20261008-dual-header-recheck`, key ID `a856f788fb864434991550d6`: UI issue 200; after dismissal and reload the secret was absent. A fresh cookie-free request context supplied both the existing deployment credential in `X-Eurogas-Api-Key` and the new identity bearer in `X-Eurogas-Identity`, as required by the existing API-key runbook. `/api/me` returned 200 with the intended principal. UI revoke returned 200; reload showed Revoked and a disabled revoke button. The same correct two-header request then returned **403 `identity_key_revoked` with no principal**. This proves refusal at the identity-key layer, not accidental refusal by the deployment gate. All 30 assertions passed. The second attempt's one pre-existing key was the already-revoked first-attempt key; its safe fields remained unchanged.

Control requests: identity bearer in the deployment-key channel returned 403 `public_api_token_invalid`; no credentials returned 401; deployment credential alone resolved a different compatibility principal. No authentication control was changed to make the test pass.

Read-only PostgreSQL verification confirms both revocations: first at `2026-10-07T22:03:33.964457Z`, second at `2026-10-07T22:05:45.791892Z`. Both declared expiry `2026-10-08T00:00:00Z`. No active test key remains. Evidence: `.dnx-out/uat-access-20261008/evidence.json`, `cleanup-verification.json`, host logs and three PNGs. The issued-record-after-dismiss and revoked-record screenshots were visually inspected. No new key was issued during this independent cleanup verification.

## Findings still open

- The owner column is blank: the API key payload omits `principal_id`, which the UI tries to render. This is a real presentation/API contract gap.
- The issue form's selected scopes are not proven to attenuate the authenticated principal's authority. The current authentication path resolves principal roles/data scopes; dedicated security-contract review and negative role/scope tests remain required. This lifecycle pass does not claim least privilege.
- The worker's claim that the one-time secret was not shown was disproved by actual browser comparison against the volatile issuance response; no product fix for that claim was made.

Secrets must remain only in memory. No trace/HAR/video, raw issuance payload, request headers, DOM dump or unmasked secret screenshot is retained. Issued bearer is dismissed before screenshots, never saved for resume, and the owned key is revoked in cleanup. A previous active key with this test prefix stops another issuance for review. API cleanup, if needed after a UI failure, is disclosed and cannot count as successful UI revocation.

The secret remained in process memory only. A targeted scan of saved JSON/log artifacts found zero full identity-bearer matches; this is scoped evidence, not a general secret-scanning certification. Both revocations were UI actions; no emergency API cleanup was used. Script repairs addressed header selection, safe screenshot handling, response shape and case-sensitive selectors; no product permissions were modified.

The report07 historical boundary remains in place. The user approved `docs/product/BACKTEST_TEMPORAL_AMENDMENT_PROPOSAL.md` with “同意架构修改提案” (first recorded `2026-10-07T23:49:57Z`); implementation proceeds in reviewed bounded phases. This report does not claim engine/2 is implemented. Contract retirement, Hub/LNG workflows, training splits, authorization negatives and delivery acceptance remain open. No commit/push or new installation occurred in this slice.

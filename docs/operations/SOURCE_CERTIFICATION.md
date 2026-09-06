# Source Certification Runbook

## Scope

Implementation, configuration, connection verification and certification are
distinct. A provider is native-live only when a persisted certification record
for this deployment/dataset reaches `live_validated` (simulated-to-live gate)
or `certified` with explicit live-test evidence. Mocked/replayed tests can
never produce `certified`.

## Symptoms

- Source Center/Runtime shows `active_uncertified` or `certification_gaps`.
- Scheduler refuses a licensed source (fail-closed).
- Certification state is `CERTIFICATION_EXPIRED` after expiry.

## Diagnostics

- `GET /api/source-certifications` for provider/dataset/environment records.
- `GET /api/credentials/providers` for configured/missing/invalid credential
  state (no secrets returned).
- `GET /api/sources/{source_id}/health` for current certification state.

## Certification ladder

`NOT_IMPLEMENTED` -> `IMPLEMENTED` -> `CONFIGURED` ->
`CONNECTION_VERIFIED` -> `DATA_VALIDATED` -> `CERTIFIED`. `BLOCKED` and
`CERTIFICATION_EXPIRED` are explicit non-live states. The legacy gate still
accepts `unverified` -> `simulation_matched` -> `live_validated`.

## Safe action

Record evidence with
`POST /api/source-certifications/{source_id}/certify`, including dataset,
environment, adapter version, credential label (never the secret),
entitlement scope, sample period, tests performed, evidence reference and
expiry. `certified` additionally requires `evidence.live_test == "passed"`.

## Unsafe actions

- Do not mark a provider certified from mocked tests.
- Do not infer provider-wide certification from one dataset endpoint.
- Do not store plaintext credentials in certification evidence.
- Do not keep expired certification active by editing the record.

## Recovery verification

- Certification record exists with the correct provider/dataset/environment.
- Required checks are present for `live_validated`/`certified`.
- Source Center shows `certification_allows_live=true`.
- The next scheduled/manual live run succeeds.

## Escalation

Escalate to the commercial-data owner when a provider requires a live test
that cannot be performed in this environment; record
`NOT CERTIFIED — credential/entitlement unavailable` and never fake success.

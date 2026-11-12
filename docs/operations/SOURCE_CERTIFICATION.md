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

For the public sources ENTSOG and GIE, one command performs the live test and records
the evidence:

```bash
python scripts/ops/certify_public_source.py --source entsog --operator <your id>
python scripts/ops/certify_public_source.py --source gie --operator <your id>
```

It reads a bounded live sample through the transport ingestion uses (for ENTSOG flows, one
whole gas day), runs it through the same normaliser without storing an observation, and
checks that the sample normalises and carries the fields the adapter was built on. Only
then does it record `live_validated`, with the counts, the sample's SHA-256 and a 90-day
expiry. A failed or empty sample records nothing above `connection_verified` and exits 1.
`--dry-run` reports without recording. Ingestion stays blocked until this has passed.

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

# Provider Live Validation

This is the local development harness template for provider adapters.
Real provider validation requires customer credentials and entitlements.

## Simulated vs live

Simulated sources (`*_Sim`) are for local demos/tests only. They must not be
enabled or shipped in trial/release delivery unless the deployment is an
explicit demonstration environment.

## Local provider validation steps

1. Create a source-shaped fixture or canned provider response.
2. Run the adapter through the normal ingestion path.
3. Verify:
   - normalized rows match the expected schema;
   - source references and lineage are preserved;
   - credentials are never logged;
   - failures/retries are recorded in `ingestion_runs`;
   - simulated rows are labelled `*_Sim`.
4. If a real provider key is available, run the same test against the live
   provider endpoint with `EUROGAS_NEXUS_ENV=trial` or an explicit operator
   override and record the evidence.

## Validation record

Each provider should record:

- provider id
- live/simulated status
- credential owner
- validation date
- rows ingested
- retry/failure checks
- operator approval

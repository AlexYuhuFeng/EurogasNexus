# Test object store (drills and tests only)

`compose.yaml` profile `test-objectstore` runs SeaweedFS (Apache-2.0) as an S3-compatible
test double, so the backup and retention drills run on a machine without the firm's object
storage. It is never part of a deployment and nothing in the product requires it: any
S3-compatible store works, and production uses the firm's.

MinIO is deliberately not used, not even here: its server is licensed under the AGPL v3, which
the product's dependency policy refuses (`docs/legal/DEPENDENCY_LICENSE_REVIEW.md`, AGENTS.md
rule 18). An unshipped test container would still put an AGPL component in the delivery path
of every drill an operator runs, so the test double is a permissively licensed one.

`scripts/ops/ha_drill.py` writes `s3.json` (a throwaway access key) and `certs/` (a private CA
and a server certificate) into a scratch directory and points the profile at it with
`NEXUS_TEST_OBJECTSTORE_CONFIG`; nothing secret is kept in this folder.

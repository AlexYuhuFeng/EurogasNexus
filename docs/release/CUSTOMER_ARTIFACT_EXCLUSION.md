# Customer artifact simulation exclusion

Simulation producers and preview data belong only to development/test source
checkouts. They must never be delivered in a customer API image, application
wheel or Server operator ZIP. Missing real feeds remain unavailable until their
provider, entitlement, certification and connector gates pass.

## Build and acceptance contract

- [Customer wheel selection](../../setup.py) excludes the executable
  `eurogas_nexus.ingestion.simulated_market_prices` module. An incremental build
  containing stale copies of that producer refuses to build; use a fresh build
  output directory. Source-checkout tests retain the producer.
- [Runtime artifact policy](../../scripts/release/runtime_artifact_policy.json)
  explicitly lists scripts copied into the customer image. Startup/configuration,
  public ingestion, monitoring, retention, backup/restore and license tools are
  retained with their imported helpers. Development/UAT/research seed tools are
  outside the selection.
- [API Dockerfile](../../deploy/runtime/Dockerfile.api) verifies the actual wheel
  inventory before installation, then the installed distribution, copied script
  inventory, startup/migration files, API import and tool imports. The verifier
  never invokes the operational commands, database access or provider requests.
- [Artifact verifier](../../scripts/release/verify_customer_artifact.py) rejects
  missing required files, extra script payloads, local `.dnx*` artifacts,
  development directories and an importable executable simulator. The runtime
  contents are checked again in the immutable amd64 image before container
  acceptance evidence is written. Arm64 still has manifest-presence evidence
  only; its execution is not claimed.
- [Customer Compose](../../deploy/runtime/compose.yaml) contains no preview-seed
  or simulated-prices services, including opt-in profiles. The Server ZIP's
  [explicit allowlist](../../scripts/release/package_deployment_bundle.policy.json)
  excludes development seed tools, local `.dnx*` data and the separate development
  workflow. [.dockerignore](../../.dockerignore) also excludes local `.dnx*`
  directories before the Docker build context is sent.

The static historical `sim-market-v1` provenance value remains readable in
existing snapshot manifests through
[provenance metadata](../../src/eurogas_nexus/ingestion/provenance_versions.py).
Preserving that identity neither executes a simulator nor relabels earlier
simulated observations as real data. Runtime defensive filters/refusals and
source-status disclosure remain necessary even when the producer is absent.

## Development workflow and remaining evidence

Use the [development simulation procedure](../operations/SIMULATED_MARKET_PRICE_SOURCES.md)
with a dedicated test/development PostgreSQL database and a source checkout.
Customer wheels/images intentionally cannot run those source-only commands.

[Focused artifact tests](../../tests/release/test_customer_artifact_exclusion.py)
build and inspect a real wheel, install it offline without dependencies into an
isolated target, replay the exact copied customer scripts and API import, and
prove rejection of injected producers, stale build output and missing runtime
files. The host replay uses the installed local dependencies; it is not a Docker
image build or a runtime release acceptance result.

Release acceptance must still build the actual locked Docker image and execute
both content and notice verifiers at its published immutable digest. This work
does not inspect or clean an existing customer database: absence of simulated
rows, seeded contracts and development identities is a separate data/provenance
acceptance gate. It also does not constitute supplier certification, commercial
readiness or Astra integration sign-off.

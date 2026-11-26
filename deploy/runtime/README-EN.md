# Runtime Deployment Bundle

This directory is the committed server-runtime definition used by `Server` and
`Server` deployments. Operators should use `Deploy-EurogasNexus.ps1`; they
should not edit or invoke individual Compose services during normal install.

Services: PostgreSQL 16, a one-shot configuration preflight, a one-shot schema check
(`migrate`: it never upgrades here; it stops the start when the database needs the gated
upgrade, `docs/operations/DATABASE_UPGRADE.md`), a one-shot reference network seed (`reference-seed`: the shipped NWE network
bundle, offline, skipped when a live ENTSOG read is present), FastAPI, Caddy HTTPS gateway and opt-in public ingestion tools.
Simulation and preview seed services are absent from customer delivery.
PostgreSQL and the API are loopback-bound;
customer access enters through the HTTPS gateway. No secret is committed in this
directory.

`env.server.example` is the environment template for this stack. It is generated
from `src/eurogas_nexus/core/config_contract.py` by
`python scripts/ci/generate_env_template.py`, so it lists every variable the
product reads; do not hand-edit it.

The stack refuses to start on a misconfigured environment. The `config-check`
service runs `scripts/ops/check_config.py` before the migration and the API, so a
missing credential-encryption key, an incomplete OIDC block, a mistyped variable
name, or a development-only switch left enabled in a release deployment stops the
start-up instead of surfacing later as a 503 or a silently ignored setting.
Errors block the stack; warnings (an unrotatable credential key, no declared
trusted proxy hop) are reported and left to the operator. Run the same check
ahead of a deployment with:

```bash
python scripts/ops/check_config.py --env-file <your environment file> --strict
```

`--strict` treats warnings as errors and is the form a release gate should use.

The API image built from `Dockerfile.api` also carries the license/notice
texts of the locked Python runtime dependencies at
`/usr/share/licenses/eurogas-nexus/python-license-texts` (`manifest.json`
plus `texts/`), collected at build time from the image's own site-packages
against `requirements-runtime.lock`; a missing or incomplete collection fails
the image build. These are technical notices, not legal clearance. Inspect
them with `docker run --rm --entrypoint cat <image>` followed by the
`manifest.json` path above.

Verify the delivered evidence in a pulled image with
`docker run --rm --network none <image> python scripts/release/verify_python_license_texts.py`.
The verifier defaults to the paths above and the image's own
`requirements-runtime.lock` copy; it exits non-zero on tampered, incomplete,
extra or missing evidence and is a technical check, not legal clearance. The
release `container-acceptance` job runs the same command inside the
linux/amd64 image digest before writing the G19 PASS; the arm64 entry is only
checked for manifest presence and is not executed.

See `docs/deployment/DEPLOYMENT_ROLES-EN.md` for the supported workflow.

The API wheel excludes the executable market simulator. The image copies only
the scripts in `scripts/release/runtime_artifact_policy.json`, retaining the
startup, public ingestion, disaster recovery and notice tools. Both wheel and
installed image content are checked during build; container acceptance reruns
`python scripts/release/verify_customer_artifact.py` at the immutable amd64
digest. Local `.dnx*` working data is excluded from the Docker context.
These content checks do not certify an existing database as simulation-free;
customer data acceptance must inspect database provenance separately.

## Several API processes (production shape)

`compose.yaml` runs one API process with no shared cache. For a production server add
`compose.scale.yaml`: it starts a password-protected Valkey on the internal network and runs
four API processes that share it (`VALKEY_PASSWORD` must be set in the environment file):

    docker compose -f compose.yaml -f compose.scale.yaml --env-file .env up -d

The preflight refuses more than one API process without a shared cache. Each process runs
its own live-update poller; the scheduler and the other workers stay single containers (the
scheduler also holds a database lock), and database upgrades stay the gated step below. Pool
sizing, what to watch and what happens when Valkey is down: `docs/operations/API_SERVING_AND_SHARED_CACHE.md`.

## Upgrades and monitoring

- **Database upgrades** are a gated operator step, never automatic in this stack:
  `docker compose run --rm migrate python scripts/ops/upgrade_database.py upgrade --operator
  "<name>"` after a recorded backup (`docs/operations/DATABASE_UPGRADE.md`).
- **Metrics**: set `EUROGAS_NEXUS_METRICS_SCRAPE_TOKEN` and/or
  `EUROGAS_NEXUS_METRICS_ALLOWED_NETWORKS` and scrape `http://<api>:8000/metrics` from the
  monitoring network; the gateway answers `/metrics` with 404. Every API process writes its
  samples to one shared directory (`PROMETHEUS_MULTIPROC_DIR`, a tmpfs of the `api` container),
  so one scrape returns the sum over all processes, including the pool and live-update
  metrics of `compose.scale.yaml`. Alert rules ship in
  `deploy/monitoring/prometheus/` (`docs/operations/MONITORING.md`,
  `docs/operations/ALERT_RESPONSES.md`).
- **Logs** are JSON lines on standard error, rotated by Docker (5 x 20 MB per container).

# Runtime Deployment Bundle

This directory is the committed server-runtime definition used by `Server` and
`Server` deployments. Operators should use `Deploy-EurogasNexus.ps1`; they
should not edit or invoke individual Compose services during normal install.

Services: PostgreSQL 16, one-shot Alembic migration, FastAPI, Caddy HTTPS
gateway, opt-in public ingestion tools, and opt-in simulated price ingestion.
PostgreSQL and the API are loopback-bound; customer access enters through the
HTTPS gateway. No secret is committed in this directory.

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

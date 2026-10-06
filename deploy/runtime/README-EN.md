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

See `docs/deployment/DEPLOYMENT_ROLES-EN.md` for the supported workflow.

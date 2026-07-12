# Runtime Deployment Bundle

This directory is the committed server-runtime definition used by `Server` and
`AllInOne` deployments. Operators should use `Deploy-EurogasNexus.ps1`; they
should not edit or invoke individual Compose services during normal install.

Services: PostgreSQL 16, one-shot Alembic migration, FastAPI, Caddy HTTPS
gateway, opt-in public ingestion tools, and opt-in simulated price ingestion.
PostgreSQL and the API are loopback-bound; customer access enters through the
HTTPS gateway. No secret is committed in this directory.

See `docs/deployment/DEPLOYMENT_ROLES-EN.md` for the supported workflow.

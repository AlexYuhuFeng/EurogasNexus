# V1 R29 Deployment Roles ExecPlan

## 1. Goal

Define and package three explicit device roles: `Server`, `Client`, and
`AllInOne`. Server and AllInOne provision PostgreSQL, migrations, API, HTTPS
gateway, public-source ingestion, and explicitly labeled simulated market-price
workers through Docker Compose. Client installs no database and targets an
existing HTTPS backend API.

## 2. Non-goals

- Do not let clients connect directly to PostgreSQL.
- Do not silently install Docker Desktop, WSL2, PostgreSQL, or vendor software.
- Do not embed customer API keys, database passwords, or internal tokens in an
  NSIS/DEB package, Compose manifest, repository file, or log.
- Do not turn the desktop installer into a multi-user server installer.
- Do not enable trade execution, nomination submission, or auto-trading.
- Do not expose preview Server or AllInOne deployments to the public internet;
  multi-user authentication and authorization are not implemented.

## 3. Product boundary

The NSIS/DEB package installs the client. The deployment tool selects `Server`,
`Client`, or `AllInOne`. Server components are a separate, explicit runtime
installed by an idempotent bootstrapper after prerequisite and consent checks.

## 4. Files to create/modify

- `deploy/runtime/compose.yaml`
- `deploy/runtime/Dockerfile.api`
- bilingual server-runtime readmes
- bilingual deployment-role operations documentation
- `scripts/install/windows/Deploy-EurogasNexus.ps1`
- `scripts/install/windows/Install-EurogasNexusServerRuntime.ps1`
- release packaging workflow and release documentation
- contract/release tests

## 5. Dependency policy

Use PostgreSQL 16, Caddy 2, the existing Python backend, Docker Compose v2, and
existing client stacks. Docker is a customer-managed prerequisite. `pg8000`
and `uvicorn` are required by the packaged API image; `@tauri-apps/api` is
required for managed desktop endpoint discovery. Add no Kafka, Redis, or Celery.

## 6. Data policy

- PostgreSQL is the runtime source of truth.
- Generated secrets use cryptographically secure random bytes and remain under
  a restricted server runtime directory.
- ECB and ENTSOG public ingestion is opt-out when internet is available.
- GIE remains disabled until a customer configures its key through the product.
- Simulated price feeds are opt-in and retain `_Sim` provenance end to end.
- Preview server endpoints bind a specific device IP and require an explicit
  private-network-only acknowledgement; `0.0.0.0` is refused.

## 7. API impact

No new public API endpoint. Client configuration stores only the HTTPS API base
URL. AllInOne points its client to the HTTPS gateway on the same device.

## 8. DB impact

The bootstrapper runs `alembic upgrade head` explicitly through a one-shot
migration container. It never runs a migration during client or API import.

## 9. Tests

- Compose config contains PostgreSQL, migration, API, ingestion, and optional
  simulated-price services without committed passwords.
- Bootstrapper has preflight, install, repair, validate, and uninstall actions.
- Bootstrapper refuses missing Docker rather than downloading it silently.
- Release workflow packages the deployment bundle independently of clients.
- Documentation states that clients use API URLs and never DB credentials.

## 10. Validation commands

```powershell
ruff check .
pytest -q tests/contract tests/release tests/security
docker compose --env-file <generated> -f deploy/runtime/compose.yaml config
powershell -File scripts/install/windows/Deploy-EurogasNexus.ps1 -Action Preflight -Role Server -Json
```

The Compose validation is run only when Docker is already available. The
bootstrapper preflight does not start or install Docker.

## 11. Acceptance criteria

- Deployment modes are absolute and documented in English and Mandarin.
- A Client installation needs only a signed installer and HTTPS API URL.
- Server and AllInOne installation is explicit, repeatable, non-secret, and isolated.
- Missing prerequisites produce actionable errors and no partial deployment.
- Simulated feeds remain optional and clearly identified.
- Release assets include a deployment-role bundle independently of NSIS/DEB.

## 12. Rollback notes

Remove the deployment bundle and workflow packaging job. An installed
runtime can be stopped without deleting its PostgreSQL volume; data removal
requires an explicit purge flag.

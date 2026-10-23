# Simulated integration acceptance — 2026-10-23

The owner authorized synthetic dependencies to continue Linux functional acceptance.
The tested scope passed. This supplements [runtime acceptance](17_BACKEND_RUNTIME_ACCEPTANCE.md);
it does not certify a customer identity provider, supplier or production deployment.

## Executed evidence

| Scope | Result | Execution boundary |
| --- | --- | --- |
| Trader, analyst, ADMIN, viewer and reviewer workflows | 77 passed | Real HTTP to Linux release container on port 8008, isolated PostgreSQL and synthetic identities/data |
| Strategy private/public/group sharing | 25 passed | Same container/database; owner control, reader restrictions and revocation |
| Trader contract workflow | 15 passed | Same container/database; creation, editing, stale-write rejection and role restrictions |
| Strategy browser workflow | 7 passed | Linux Chromium, local web/source API, synthetic session |
| ADMIN browser workflow | 8 passed | Linux Chromium; grant persistence, injected transport failure/retry, disable/enable enforcement |
| OIDC combined regression | 35 passed | Existing tests plus new loopback discovery/JWKS/token service tests |
| Provider loopback protocol acceptance | 9 passed | Real local HTTP sockets; production parsing, pagination and retry code |
| Existing provider/ingestion regression | 236 passed | Transport, credential gates, bounded ingestion and upsert regression fixtures |
| Existing identity/provider/deployment selection | 133 passed, 17 skipped | OIDC, credential/egress gates, deployment roles/bundle/posture and restore-readiness tests |

Selections overlap; counts must not be added into a unique-test total. The 17
skipped cases remain unverified under their platform/tool conditions. Existing
Starlette/httpx and anyio deprecation warnings remain.

## New reproducible tests

Run from the repository with its installed development environment:

```bash
.venv/bin/python -m pytest tests/security/test_oidc_simulated_http.py tests/ingestion/test_simulated_provider_http_acceptance.py -q
```

OIDC uses generated RSA signatures and a real loopback discovery/JWKS/token server.
It checks API role enforcement and invalid credentials/service failures. The
application-level authorization-code/PKCE exchange persists a session in isolated
SQLite, then verifies that session through `/api/me`. Wrong PKCE, wrong nonce and
state replay are rejected. This is not an end-to-end browser redirect/callback or
customer SSO test; the separate Chromium checks use synthetic fixture sessions.

Provider tests explicitly route asserted official request identities through a
test-only transport to loopback. ENTSOG cases exercise pagination, repeat-read raw
hashes, 429/503 retry, actual socket timeout exhaustion, malformed responses,
redirect refusal, duplicate IDs and incomplete-prefix handling. GIE cases reject
HTTP-200 credential-denial payloads and redirects. Successful GIE paging/retry
remains covered by existing mocked transport regression. Repeat-read hashes do not
establish durable database idempotency. Production endpoint and licence controls
were not changed, and no real provider credentials were used.

## Evidence and recovery

Machine-local logs, JUnit and summaries are in the ignored
`.local-runtime/simulated-acceptance/` directory. Role/sharing/trader detail and
browser screenshots also remain in the existing ignored acceptance fixture
directories. No credential values are included in this report.

Initial browser attempts encountered expired fixture sessions and an unavailable
local development web server. After refreshing only synthetic sessions and
restarting Vite, both browser suites passed with no unhandled page errors. The
initial failures are retained in the local logs. No product implementation change
was required by this simulation batch; two reusable integration test modules were
added. No production service, push, release publication or cross-region transfer
was performed.

This closes the stated simulated functional scope. Native installers/signing,
full customer SSO/gateway/provider acceptance, production recovery and the broader
UI/UX refinement remain separate delivery work; simulation does not mark them as
passed. Regional EU/CN/CA/SG transport remains deferred and disabled.

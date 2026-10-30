# Local Docker Runtime

Runbook for the `.local-runtime` Docker stack. The directory itself is ignored
by Git and is created or supplied locally; never commit it.

## Development profile (default)

When the stack runs in the development profile and you open
`http://127.0.0.1:3000`:

- no API token is required;
- `/docs` and `/openapi.json` are available;
- the local public-ingestion worker runs ECB only;
- ENTSOG/GIE live workers stay disabled until provider certification and
  credentials are configured;
- preview seed data remains the local reference data.

## Release profile

If the stack is switched back to the release profile, the public API token is
required:

1. Open **Settings** in the Web workspace.
2. Set **Backend API URL** to:
   - `http://127.0.0.1:3000/api` when using the Docker Web container proxy, or
   - `http://127.0.0.1:8765/api` when connecting directly to the Docker API.
3. Set **API token** to the value of
   `EUROGAS_NEXUS_PUBLIC_API_TOKEN` in `.local-runtime/.env`.
4. Set **operator principal** to a valid name such as `operator`.
5. Save and retry.

Host-side quick check:

```bash
TOKEN=$(grep '^EUROGAS_NEXUS_PUBLIC_API_TOKEN=' .local-runtime/.env | cut -d= -f2)
curl -H "X-Eurogas-Api-Key: $TOKEN" http://127.0.0.1:3000/api/health
```

A `401 public_api_token_missing` response means the browser has not saved the
token in Settings yet.

## Release profile API docs

`/openapi.json` and `/docs` intentionally return 404 in the release profile.
For local schema inspection run a development-profile API instance. The pinned
public route list is maintained in
[`tests/contract/test_api_surface_stability.py`](../../tests/contract/test_api_surface_stability.py).

Chinese summary: [LOCAL_DOCKER_RUNTIME-CN.md](LOCAL_DOCKER_RUNTIME-CN.md).

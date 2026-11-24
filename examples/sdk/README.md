# Python SDK examples

Runnable scripts for the recipes in [docs/sdk/EXAMPLES.md](../../docs/sdk/EXAMPLES.md). Each
script reads the server address from `EUROGAS_NEXUS_BASE_URL` (default
`http://127.0.0.1:8000`); the SDK itself reads the credentials from
`EUROGAS_NEXUS_PUBLIC_API_TOKEN` and, optionally, `EUROGAS_NEXUS_IDENTITY_BEARER`.

They are written for the local demo server in [docs/sdk/QUICKSTART.md](../../docs/sdk/QUICKSTART.md):
the figures they print are simulated demo data. Against a real installation they print your
own data, and some of them print nothing if the matching data is not loaded.

```bash
export EUROGAS_NEXUS_BASE_URL=http://127.0.0.1:8000
export EUROGAS_NEXUS_PUBLIC_API_TOKEN=local-dev-token
python examples/sdk/01_first_call.py
```

`tests/docs/test_sdk_examples.py` runs every script against a live server when
`EUROGAS_NEXUS_EXAMPLES_BASE_URL` and `EUROGAS_NEXUS_EXAMPLES_API_TOKEN` are set, and skips
otherwise (the test suite pins `EUROGAS_NEXUS_PUBLIC_API_TOKEN` to a test value, hence the
separate names).

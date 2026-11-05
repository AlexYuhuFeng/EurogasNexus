# Provider credentials

One contract for every provider that needs a key
(`src/eurogas_nexus/security/provider_credentials.py`). Ingestion, the model layer and the
credentials API all resolve a key the same way.

## Where a key comes from

1. A credential an administrator **disabled** in the credential manager blocks the
   provider. An environment key never silently re-enables it; the status says so.
2. The provider's environment variable (the first listed is canonical, later ones are
   accepted aliases). A blank value counts as unset.
3. A key file named by the `*_FILE` variable, where supported. A configured file that
   cannot be read is an error, never a fall-through to another source.
4. The encrypted credential store (Settings, or `PUT /api/credentials/{provider}`).

`GET /api/credentials/providers` reports, per provider, `effective_source` (`env`,
`file`, `credential_store`, `disabled` or `missing`), the variables that can set it and
whether a connector is implemented. It never returns a key. A key set in the environment
is changed in the deployment's configuration and takes effect on restart or redeploy.

## Providers

| Provider | Variables | Connector |
|---|---|---|
| GIE AGSI+/ALSI | `GIE_API_KEY`, `GIE_API_KEY_FILE` | Implemented; also needs a certification record |
| US EIA | `EIA_API_KEY` | Implemented (Henry Hub) |
| ENTSO-E | `ENTSOE_SECURITY_TOKEN` | Implemented (power) |
| DeepSeek | `EUROGAS_NEXUS_LLM_API_KEY` (alias `DEEPSEEK_API_KEY`) | Implemented |
| Other model endpoint | `EUROGAS_NEXUS_LLM_API_KEY` | Implemented (OpenAI-compatible) |
| EEX, ICE OCM, ICIS, Argus, Trayport, Kpler, Platts, Weather | credential store only | Not implemented; a stored key is kept for a future connector |

ECB, ENTSOG, the Bank of England, the ECB's €STR and the New York Fed need no key.

## A reusable test file

`.env.testing.example` is the secret-free template. Copy it to `.env.testing` (ignored by
Git), fill the keys you have and load it explicitly:

```bash
set -a; . ./.env.testing; set +a
```

On Render, paste the same lines under the service's **Environment** ("Add from .env").
Keep provider keys apart from deployment values (database URL, session and encryption
secrets, login passwords): the Blueprint generates those, and copying them across
environments would detach the database or sign everyone out.

## Configuration is not activation

A key does not enable a source, schedule an ingestion, permit external model calls
(`EUROGAS_NEXUS_LLM_EXTERNAL_PROVIDER_ENABLED` decides) or grant a market-data licence
(the licence register decides). Each of those stays a visible, separate step.

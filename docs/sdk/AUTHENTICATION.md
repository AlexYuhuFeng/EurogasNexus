# Python SDK authentication

How the SDK proves who it is to a Eurogas Nexus server, what to ask your administrator for,
and what each refusal means.

## Summary

- Every call except `fetch_health` needs the **deployment token** in
  `EUROGAS_NEXUS_PUBLIC_API_TOKEN`.
- To act as yourself (your role and your data scopes), also set an **identity key** in
  `EUROGAS_NEXUS_IDENTITY_BEARER`. Without one, the server treats you as a shared operator
  caller that sees all data.
- The SDK reads both from the environment on every call. There is no login call, no client
  object and no credential argument.
- The SDK cannot send an OIDC access token or a browser session.

## Two credentials, two questions

A server can ask two separate questions about each request.

1. **Is this caller allowed to reach this installation at all?** The answer is the
   deployment token, one shared secret per installation. The server checks it before any
   route runs.
2. **Who is this caller?** The answer decides the role (viewer, analyst, operator, admin)
   and the data scopes (which licensed data families the caller may read). It comes from an
   identity key, an OIDC access token or a browser session.

The SDK sends the first from `EUROGAS_NEXUS_PUBLIC_API_TOKEN` and the second from
`EUROGAS_NEXUS_IDENTITY_BEARER`.

| Environment variable | Sent as | What it is | Who issues it |
|---|---|---|---|
| `EUROGAS_NEXUS_PUBLIC_API_TOKEN` | `Authorization: Bearer <token>` | Deployment token, shared by every client of one installation | The administrator who deployed the server |
| `EUROGAS_NEXUS_API_TOKEN` | same | Older name for the deployment token; used only when the first is unset | (legacy) |
| `EUROGAS_NEXUS_IDENTITY_BEARER` | `X-Eurogas-Identity: <key>` | Identity key of one user or service account, `nexus_<key_id>_<secret>` | An administrator, in Admin > Access & Identity |
| `EUROGAS_NEXUS_PRINCIPAL` | `X-Eurogas-Principal: <name>` | Name of the acting operator, for operator routes called with the deployment token alone | Your operations team |

## How the SDK resolves credentials

On every request the SDK:

1. takes `EUROGAS_NEXUS_PUBLIC_API_TOKEN`, or `EUROGAS_NEXUS_API_TOKEN` when the first is
   unset or blank, strips surrounding whitespace and, if anything is left, sends it as
   `Authorization: Bearer`;
2. sends `EUROGAS_NEXUS_IDENTITY_BEARER` as `X-Eurogas-Identity` if set;
3. sends `EUROGAS_NEXUS_PRINCIPAL` as `X-Eurogas-Principal` if set.

Unset variables send nothing. Because the variables are read per call, changing
`os.environ` inside a running notebook takes effect on the next call.

## What the server does with them

| You send | The server treats you as | You see |
|---|---|---|
| Nothing | Refused: `401 public_api_token_missing` | Only `fetch_health` works |
| Deployment token | The shared compatibility caller `public-api`, role OPERATOR, data scopes `*` | All data; actions are recorded against `public-api` |
| Deployment token and identity key | The key's owner, with the owner's role | Data in the intersection of the key's scopes and the owner's current data scopes |
| Identity key without the deployment token | Refused: `401 public_api_token_missing` | Nothing |

Use an identity key for anything a person runs. The deployment token alone identifies the
installation, not a person, so the audit trail cannot tell who acted, and it sees every
data family.

An identity key with an empty scope list sees public data only. Scopes are explained in
[API keys](../operations/API_KEYS.md#data-scope-attenuation).

## Set the credentials

On Linux or macOS:

```bash
export EUROGAS_NEXUS_PUBLIC_API_TOKEN='<deployment token>'
export EUROGAS_NEXUS_IDENTITY_BEARER='<nexus_... key>'
```

On Windows PowerShell:

```powershell
$env:EUROGAS_NEXUS_PUBLIC_API_TOKEN = '<deployment token>'
$env:EUROGAS_NEXUS_IDENTITY_BEARER = '<nexus_... key>'
```

In a long-running service, load them from your secret store into the process environment
before the first SDK call. Do not write them into notebooks, scripts, examples or logs. The
SDK never prints them.

Check who the server thinks you are with `GET /api/me`. The SDK has no function for it; the
SDK's own HTTP helper adds the same headers:

```python
from eurogas_nexus_sdk import _http

me = _http.get("http://127.0.0.1:8000/api/me").json()["data"]
print(me["name"], me["role"], me["data_scopes"])
```

`_http` is an internal module; use it for this check only.

## Get an identity key

An administrator creates the key for a user or service account in Admin > Access &
Identity, or with `POST /api/access/api-keys`. The key is shown once; store it at once.
Revoking it, or disabling its owner, stops it on the next request. See
[API keys](../operations/API_KEYS.md) for the administrator's side.

## Operator routes

A few write routes are reserved for operators (for example entering a reviewed TSO tariff,
certifying a source, running a source). An identity key whose owner has the operator role is
enough. A caller
using the deployment token alone must also name the acting operator in
`EUROGAS_NEXUS_PRINCIPAL`; without it the server answers `401 operator_principal_missing`.
The SDK has no functions for those routes; they are listed here so the variable is not a
mystery.

## OIDC access tokens and sessions

The server also accepts an OIDC access token in `X-Eurogas-Oidc-Access-Token` (RS256, issued
by your identity provider; see [OIDC access token](../operations/OIDC_ACCESS_TOKEN.md)) and a
browser or desktop session. **The SDK sends neither.** If your firm issues OIDC tokens to
service accounts instead of identity keys, call the REST API with `httpx` and send the two
headers yourself, or ask for an identity key. This path was not tested with a real identity
provider while this guide was written.

## Streaming

`streaming.stream_events` sends the same headers. The server also accepts the deployment
token as `?api_key=` for browsers, which cannot set headers on an event stream; the SDK does
not need it and does not use it.

## Refusals

Every refusal has a JSON body with a stable `error` code and a `correlation_id`; see
[Troubleshooting](TROUBLESHOOTING.md#read-the-error) for how to read it.

| Status and code | Meaning | What to do |
|---|---|---|
| `401 public_api_token_missing` | No deployment token reached the server | Set `EUROGAS_NEXUS_PUBLIC_API_TOKEN` in the environment of the Python process |
| `403 public_api_token_invalid` | The deployment token is wrong, or an identity key was put in the token variable | Check the value; identity keys go in `EUROGAS_NEXUS_IDENTITY_BEARER` |
| `503 public_api_token_not_configured` | The server has no deployment token configured | An administrator must configure it |
| `401 identity_bearer_missing` | The identity key is not in `nexus_<key_id>_<secret>` form | Copy the whole key |
| `403 identity_key_invalid` | Unknown identity key | Ask for a new key |
| `403 identity_key_revoked`, `403 identity_key_expired` | The key was revoked or has expired | Ask for a new key |
| `403 identity_principal_disabled` | The key's owner is disabled | Ask an administrator |
| `403 identity_role_forbidden` | Your role does not cover this route | Ask for the role the action needs |
| `403 commercial_access_not_granted`, `403 entitlement_denied` | Your data scopes do not cover this data family | Ask for the data scope |
| `401 operator_principal_missing` | Operator route called with the deployment token alone | Use an operator's identity key, or set `EUROGAS_NEXUS_PRINCIPAL` |
| `503 identity_store_not_configured` | The server has no database for identity keys | An administrator must configure the runtime database |
| `503 oidc_not_configured` | An OIDC token was sent to a server without OIDC configured | Use an identity key |

## Related

- [API keys runbook](../operations/API_KEYS.md): issuing, scoping and revoking keys.
- [OIDC access token](../operations/OIDC_ACCESS_TOKEN.md) and [SSO/OIDC](../operations/SSO_OIDC.md):
  the server side of single sign-on.
- [Identity, authorization and audit governance](../operations/IDENTITY_AUDIT_GOVERNANCE.md).

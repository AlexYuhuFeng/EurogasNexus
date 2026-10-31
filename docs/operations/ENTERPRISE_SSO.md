# Single sign-on in a dedicated network

Eurogas Nexus authenticates people in one of three ways; a deployment may enable more than
one. Roles and data scopes come from the same group maps in every case
(`EUROGAS_NEXUS_OIDC_GROUPS_ROLE_MAP`, `EUROGAS_NEXUS_OIDC_GROUPS_SCOPE_MAP`), so the firm
keeps one role model.

| Your SSO | Mode | Configure |
|---|---|---|
| Entra ID, Okta, Ping, Keycloak, ADFS 2016+ (OpenID Connect) | OIDC | [OIDC_ACCESS_TOKEN.md](OIDC_ACCESS_TOKEN.md) |
| SAML 2.0 IdP, Kerberos / integrated Windows authentication, SiteMinder, Oracle Access Manager, PingAccess, an in-house SSO | Authenticating gateway | this page |
| Service accounts, scripts, the SDK | Identity keys | Administration → Access → API keys |

## Authenticating gateway

A reverse proxy in front of the API authenticates the person with the firm's SSO and
forwards the request with the user and groups in headers. The API trusts those headers only
when the request also carries a shared secret and, when configured, comes from the gateway's
address.

```bash
EUROGAS_NEXUS_GATEWAY_AUTH_ENABLED=true
EUROGAS_NEXUS_GATEWAY_SECRET=<32+ random characters, stored in the secret store>
EUROGAS_NEXUS_GATEWAY_TRUSTED_PROXIES=10.20.0.10/32      # the gateway as the API sees it
EUROGAS_NEXUS_GATEWAY_USER_HEADER=X-Remote-User          # defaults shown
EUROGAS_NEXUS_GATEWAY_GROUPS_HEADER=X-Remote-Groups
EUROGAS_NEXUS_GATEWAY_EMAIL_HEADER=X-Remote-Email
EUROGAS_NEXUS_OIDC_GROUPS_ROLE_MAP={"EGN-Traders":"ANALYST","EGN-Risk":"REVIEWER","EGN-IT":"ADMIN"}
EUROGAS_NEXUS_OIDC_GROUPS_SCOPE_MAP={"EGN-Traders":["EEX","ICE_ENDEX","TRAYPORT"]}
```

`python scripts/ops/check_config.py --strict` refuses a secret shorter than 32 characters
and warns when no trusted proxy is set.

The gateway must:

1. **remove** any incoming `X-Remote-*` and `X-Eurogas-Gateway-Secret` headers from the
   client before authenticating, so a client cannot forge them;
2. set the user, groups and e-mail from the authenticated session;
3. add `X-Eurogas-Gateway-Secret`;
4. be the only route to the API (the API listens on a private address).

Apache with Kerberos (integrated Windows authentication):

```apache
<Location />
  AuthType GSSAPI
  AuthName "Eurogas Nexus"
  GssapiCredStore keytab:/etc/httpd/nexus.keytab
  Require valid-user
  RequestHeader unset X-Remote-User early
  RequestHeader unset X-Remote-Groups early
  RequestHeader unset X-Eurogas-Gateway-Secret early
  RequestHeader set X-Remote-User "%{REMOTE_USER}s"
  RequestHeader set X-Remote-Groups "%{AUTHZ_GROUPS}e"
  RequestHeader set X-Eurogas-Gateway-Secret "${NEXUS_GATEWAY_SECRET}"
  ProxyPass http://10.20.0.20:8000/
</Location>
```

SAML works the same way with `mod_auth_mellon` or Shibboleth (`MELLON_NAME_ID`,
`MELLON_groups`), and vendor agents (SiteMinder `SM_USER`, OAM `OAM_REMOTE_USER`) through
`EUROGAS_NEXUS_GATEWAY_USER_HEADER`. The web client is served from the gateway's origin, so
the browser session is the SSO session. The desktop client points at the gateway URL and
uses OIDC or an identity key where the gateway cannot authenticate a native client.

## Inheriting company accounts

By default a first sign-in creates a *pending* account that an administrator approves. A
firm that manages access in its own directory sets

```
EUROGAS_NEXUS_OIDC_PROVISIONING_MODE=directory
```

Then, for OIDC and the authenticating gateway alike:

- a person's first sign-in creates an active account named after the directory account;
- roles and data scopes are recomputed from their groups at **every** sign-in through the
  group maps, so leaving a group removes the access on the next sign-in;
- the office comes from the `office` claim (`EUROGAS_NEXUS_SSO_OFFICE_CLAIM`) or the
  `X-Remote-Office` header (`EUROGAS_NEXUS_GATEWAY_OFFICE_HEADER`);
- an account an administrator has disabled or locked stays refused whatever the directory
  says, and every created or changed account is audited as `access.directory.sync`.

Map portfolio groups to `BOOKS:` scopes to give each office its own books, for example

```
EUROGAS_NEXUS_OIDC_GROUPS_SCOPE_MAP={"GAS-HQ-RISK":["BOOKS:*","EEX"],"GAS-UK-DESK":["BOOKS:ENTITY:EGN-UK","EEX"],"GAS-CA-DESK":["BOOKS:ENTITY:EGN-CA"]}
```

with `EUROGAS_NEXUS_PORTFOLIO_ISOLATION=true` ([GLOBAL_DEPLOYMENT.md](../architecture/GLOBAL_DEPLOYMENT.md)).

## Dedicated and air-gapped networks

- **Internal certificate authority:** set `SSL_CERT_FILE` (and `REQUESTS_CA_BUNDLE`) on the
  API and workers to the firm's CA bundle; OIDC discovery, connectors and webhooks then
  trust internal TLS.
- **No internet:** leave external LLM providers off
  (`EUROGAS_NEXUS_LLM_EXTERNAL_PROVIDER_ENABLED=false`, or point the LLM adapter at an
  internal model), use file imports for market data (`import_settlements.py`,
  `import_market_quotes.py`, `import_remit_umm.py`) and schedule only sources the network
  can reach. Set `EUROGAS_NEXUS_MAP_DEFAULT_PROVIDER=none` (or `custom`, pointing
  at an internal tile server) so the map does not reach for a public basemap.
- **Installation:** the server bundle and container images install from an internal
  registry; `docs/deployment/DEPLOYMENT_ROLES-EN.md` lists what each role needs.

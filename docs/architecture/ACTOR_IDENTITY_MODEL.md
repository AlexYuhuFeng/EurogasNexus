# Actor Identity Model

Chinese companion: [ACTOR_IDENTITY_MODEL-CN.md](ACTOR_IDENTITY_MODEL-CN.md)

## Scope

Eurogas Nexus is a decision-support product. R32 adds local PostgreSQL
identities (`identity_principals` / `identity_api_keys`) with USER/SERVICE
principals, hashed bearer keys, and VIEWER/ANALYST/OPERATOR/ADMIN roles. This
document defines the actor identity model used by the trust chain (review
decisions, audit events, internal operator writes) and states what remains
deferred.

## The Actor Principal

An actor is identified by a **principal string**: a stable operator identifier
recorded on every review decision, audit event, credential change, ingestion
run, and certification write so the trust chain can answer "who did this" per
row.

Rules (single validator: `src/eurogas_nexus/domain/identity/principal.py`):

- required and trimmed, 1-64 characters;
- starts with a letter or digit;
- contains only letters, digits, and `. _ @ -`;
- empty values, control characters, and embedded whitespace are rejected.

Examples: `trader-a`, `ops-user`, `analyst.alice`, `ops@nexus`.

Enforcement points:

| Surface | Enforcement |
|---|---|
| `POST /api/review/decisions` | actor validated via `normalize_principal` before persistence |
| Internal operator writes (`/api/internal/*`) | `X-Eurogas-Principal` header validated the same way |
| R32 identity-key clients | `X-Eurogas-Identity` bearer resolves to a PostgreSQL principal; its role/name is the authenticated actor |
| Audit events | principal recorded verbatim; validated at the entry points above |
| Public ingestion scripts | principal fixed to `operator` until a run identity exists |

## R32 Delivered Scope

- Local USER/SERVICE accounts stored in PostgreSQL.
- Hashed bearer API keys (`X-Eurogas-Identity`) with one-time plaintext.
- OIDC access-token verification (`X-Eurogas-Oidc-Access-Token`, R32A) with
  RS256/JWKS/issuer/audience/expiry checks and claim-to-role mapping.
- Role-based authorization: PUBLIC/READ VIEWER+, GOVERNED ANALYST+,
  OPERATOR OPERATOR+.
- Per-identity commercial data scopes with fail-closed unknown-family checks.

## What Remains Deferred

- OIDC interactive login flows (redirect/PKCE/refresh/session) and SAML.
- Browser/password sessions.
- Removal of the private-network/VPN-only server posture; this waits for
  security acceptance.

## Evolution

Identity-key callers are already represented by their persisted
`principal_id`/`name`; legacy header-only callers keep the legacy principal
string. Audit/review rows remain readable through the same `actor` column. A
future `actor_kind` discriminator and SSO mapping are R32A scope.

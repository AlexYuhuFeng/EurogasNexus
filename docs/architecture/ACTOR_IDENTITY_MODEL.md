# Actor Identity Model

Chinese companion: [ACTOR_IDENTITY_MODEL-CN.md](ACTOR_IDENTITY_MODEL-CN.md)

## Scope

Eurogas Nexus is a single-trust-domain decision-support product in preview.
This document defines the minimal actor identity model used by the trust chain
(review decisions, audit events, internal operator writes) and states
explicitly what is NOT implemented.

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
| Audit events | principal recorded verbatim; validated at the entry points above |
| Public ingestion scripts | principal fixed to `operator` until a run identity exists |

## What Is Explicitly Out Of Scope (R32)

- User accounts, passwords, sessions, and multi-user authorization.
- Company SSO / OIDC / SAML.
- Per-user data scoping or role-based access control beyond the internal
  token + principal header.
- Removal of the private-network/VPN-only server posture.

These remain gated on the R32 authentication increment
(`NEXT_DEVELOPMENT_QUEUE.md`). Until then the identity model stays minimal,
but every sensitive row already carries a validated actor so retrofitting
real authentication does not require rewriting the trust chain.

## Evolution

When R32 lands, the principal string becomes a reference to an authenticated
identity (for example `user:<id>` or `service:<id>`), and the audit/review
schemas gain an `actor_kind` discriminator. Existing rows keep their string
principals; both are readable by the same `actor` column contract.

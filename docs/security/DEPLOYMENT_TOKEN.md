# The deployment API token

Security review 2026-11 finding H3. `EUROGAS_NEXUS_PUBLIC_API_TOKEN` identifies a deployment,
not a person. This page says what it may do, how to migrate from the old behaviour and how to
rotate it.

## What changed

| | Before | Now |
|---|---|---|
| Who the token is | OPERATOR with the `*` scope over every book and licensed dataset | `service` mode: a service principal (`service:public-api`) with a configured role and scopes |
| Who acted | any name sent in `X-Eurogas-Principal` | the service principal (`public-api`); the header is ignored |
| Where it is read | `Authorization`, `X-Eurogas-Api-Key` or `?api_key=` in the URL | the two headers only; a URL never carries it |
| Which containers hold it | every container, and the API health check's command line | the API (and the start-up configuration check) only |
| Rotation | restart with a new value, every client breaks at once | a previous value is accepted during a rotation window |

The internal profile's token (`EUROGAS_NEXUS_INTERNAL_API_TOKEN`) records its acts as
`internal-api@<claimed name>`: the claimed operator is kept for the record, marked as a claim.
The release compose file no longer passes it to any container.

## Settings

| Setting | Default | Meaning |
|---|---|---|
| `EUROGAS_NEXUS_PUBLIC_API_TOKEN_MODE` | `service` in trial/release, `legacy_operator` in development/test | `legacy_operator` is the old behaviour, deprecated, with a warning on every start |
| `EUROGAS_NEXUS_PUBLIC_API_TOKEN_ROLE` | `VIEWER` | VIEWER, SCHEDULER, ANALYST, REVIEWER or OPERATOR; ADMIN is refused at start-up |
| `EUROGAS_NEXUS_PUBLIC_API_TOKEN_SCOPES` | empty (public sources, no book) | comma-separated source families and `BOOKS:` scopes; `*` is refused at start-up |
| `EUROGAS_NEXUS_PUBLIC_API_TOKEN_PREVIOUS` | unset | the old value, accepted during a rotation |

In `legacy_operator` mode an OPERATOR route still needs `X-Eurogas-Principal`, and the act is
recorded as `public-api@<name>`, so the audit trail never presents the name as verified.

## Migration

1. List what uses the token: SDK scripts, the CLI, integrations, monitoring.
2. Give each person who runs scripts a personal API key (Settings, API keys: scoped and
   expiring), and each integration that acts on its own a service identity with its own key
   (Admin, Access).
3. Set `EUROGAS_NEXUS_PUBLIC_API_TOKEN_ROLE` and `_SCOPES` to what remains (often a read-only
   VIEWER with public sources, or nothing), keep the mode at `service`, and restart.
4. Only if an integration cannot move yet, set `EUROGAS_NEXUS_PUBLIC_API_TOKEN_MODE=legacy_operator`
   for the shortest time possible; the start-up log names it on every start.

## Rotation

1. Generate a new value: `python -c "import secrets; print(secrets.token_urlsafe(32))"`.
2. Set it in `EUROGAS_NEXUS_PUBLIC_API_TOKEN` and the old value in
   `EUROGAS_NEXUS_PUBLIC_API_TOKEN_PREVIOUS`; restart the API.
3. Move every client to the new value.
4. Clear `EUROGAS_NEXUS_PUBLIC_API_TOKEN_PREVIOUS`; restart the API. The old value is refused.

Rotate at least yearly, at once when a person who knew it leaves, and whenever it may have been
in a log, a ticket or a CI output.

## Streams

The web client reads live streams with `fetch` and a header when it holds a token; a browser
session uses its same-origin cookie. `EventSource` with `?api_key=` is no longer accepted.

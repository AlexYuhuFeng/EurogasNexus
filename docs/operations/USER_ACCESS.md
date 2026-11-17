# User Access Runbook

## Roles vs data scopes

Roles answer "what may you do"; data scopes answer "which commercial data may
you see". They are assigned separately and never encoded into one string.

## Admin actions

- `GET /api/access/users` lists principals with identity source, roles,
  scopes, last login and key metadata.
- `PATCH /api/access/users/{id}` changes status, roles, data scopes, email.
- `GET /api/access/roles` shows the built-in role/permission matrix.
- `POST /api/access/users` adds a person: `kind=sso` (pre-provisioned, `INVITED` until the
  first company sign-in) or `kind=local` (answers `one_time_password` once).
- `POST /api/access/users/{id}/reset-password` issues a new one-time password (local accounts).
- `DELETE /api/access/users/{id}` deletes a person with no history; otherwise `409` - disable.
- The last active administrator cannot be disabled, locked, demoted or deleted (`409
  last_administrator`). See [LOCAL_ACCOUNTS.md](../security/LOCAL_ACCOUNTS.md).

## Verification

After a role/scope change, the affected user re-fetches `/api/me` or starts a
new session. Audit shows `access.user.update` with safe before/after summaries.

## Failure modes

- Permission denied: the caller is not ADMIN.
- Disabled principal: sessions are revoked immediately; keys fail because owner
  status is checked on every request.
- Unknown role/scope: rejected fail-closed.

## Rollback

Re-run PATCH with the previous roles/scopes. Audit preserves the previous
values for comparison.

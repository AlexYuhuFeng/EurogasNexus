# Access Revocation Runbook

## Disable a user

`PATCH /api/access/users/{id}` with `status: "DISABLED"`:

- new OIDC logins are denied;
- all backend sessions are revoked immediately;
- owned API keys fail on next request because owner status is checked;
- audit/history rows and historical `created_by` values remain.

## Revoke a session

User: `POST /api/auth/logout` revokes the current session.
Admin emergency: disable then re-enable the user after review; re-enable does
not restore revoked sessions.

## Revoke an API key

`POST /api/access/api-keys/{id}/revoke`. The key stops working immediately.

## Verification

- `GET /api/me` with the old session/key returns 401/403.
- `GET /api/audit?action=access.user.update` shows the disable event.
- Historical strategy/review rows still display the original actor.

## Rollback

Re-enable with explicit status ACTIVE and re-issue access. Do not silently
reuse a revoked session or key.

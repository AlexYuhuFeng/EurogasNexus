# Local accounts: password storage, sign-in and threat notes

Local accounts let a firm without company SSO run the product: an administrator creates a
person in **Admin → Access & Identity → Users** (or headless with
`python -m eurogas_nexus.cli.accounts`), the product issues a one-time temporary password, and
the person chooses their own at first sign-in. Company SSO is unchanged and remains the
recommended way in; with SSO configured, local accounts are off unless
`EUROGAS_NEXUS_LOCAL_ACCOUNTS=on`.

**Since the 2026-11 security review (H6)**, in a `trial` or `release` environment local accounts
are never switched on automatically: `auto` means off there, and a server with neither company
SSO (OIDC or the authenticating gateway) nor `EUROGAS_NEXUS_LOCAL_ACCOUNTS=on` refuses to start
with an error that says so. Development and test keep the old `auto` behaviour.

Code: `security/passwords.py` (KDF and policy), `security/local_accounts_policy.py` (settings,
no database import), `application/local_accounts.py` (every rule below; the API, the CLI and the
demo start-up all go through it), `api/routes/public/auth.py` and `access.py` (routes).
Migration `0065_local_accounts` adds `identity_local_credentials`.

## Storage

| Item | Stored as |
|---|---|
| Password | `hashlib.scrypt` (standard library, RFC 7914), n = 2^15, r = 8, p = 1, 32-byte key (32 MiB per derivation); 16-byte random salt per user; NFKC-normalised UTF-8 input |
| KDF parameters | recorded per row (`kdf`, `kdf_params`), so stronger ones can be introduced; an older hash is re-derived at the next successful sign-in |
| Temporary password | the same scrypt derivation, `must_change_password`, valid 72 hours, single use |
| Password-change step | a random token, stored as SHA-256 only, valid 10 minutes, single use |
| Sessions | unchanged: the opaque session of the SSO flow, stored as SHA-256 |

Nothing stored is reversible and no plaintext is logged or audited. No third-party KDF was
added (none is in the locked dependencies, and the standard library's scrypt is memory-hard).

## Policy

12 to 128 characters (after NFKC normalisation); not the user name and not containing it; not
one of a small list of trivially common passwords or one repeated character; no composition
rules. The new password must differ from the current/temporary one.

## Sign-in

- `POST /api/auth/login` answers every refusal - unknown name, wrong password, locked, disabled,
  invited, a demo account outside the demo server - with the same `401 invalid_credentials`
  and the same message, and spends the same KDF work for an unknown name (constant-time
  comparison with `hmac.compare_digest`). The audit trail records the true reason
  (`auth.local.denied`, `reason=...`). Only the holder of a correct but expired temporary
  password learns that it expired.
- **Per account**: 5 consecutive failures lock the account for 15 minutes, doubling after each
  further 5, at most 24 hours (`auth.local.locked`). A successful sign-in resets the count; an
  administrator's **Unlock** (Enable) lifts it.
- **Per source address**: 20 failures within 15 minutes answer `429` for the rest of the
  window (process-local, like the existing auth throttle of 30 attempts per minute, which still
  applies). Behind a reverse proxy, all clients share the proxy's address unless
  `FORWARDED_ALLOW_IPS` lets uvicorn see the client address.
- **CSRF**: the sign-in and the password-change step are exempt from the session CSRF header
  (there is no session yet) and refuse a foreign `Origin` themselves (login CSRF); the change
  step is authorised by its single-use token. `POST /api/me/password` is an ordinary
  cookie-authenticated write: same-origin `Origin` and `X-Eurogas-CSRF` required.
- A temporary password opens no session: the response carries the change token, and only
  `POST /api/auth/password-change` with a policy-compliant password opens one.

## Second factor (TOTP)

Security review H6. A local account can hold a time-based one-time password (RFC 6238: SHA-1,
30 seconds, 6 digits), implemented with the Python standard library (`security/totp.py`, no new
dependency), so any authenticator app works.

- **Enrol**: `POST /api/me/mfa/enrol` answers a secret (text and `otpauth://` URI, shown once);
  `POST /api/me/mfa/confirm` with a current code activates it and answers ten single-use
  recovery codes, once. The secret is encrypted with the deployment key (rotatable); recovery
  codes are stored as hashes.
- **Sign in**: after the password, a person with a second factor receives `mfa_required` and a
  single-use, five-minute `mfa_token` instead of a session; `POST /api/auth/mfa/verify` with a
  code (or a recovery code) opens the session. A code is accepted once (its time step is
  remembered); five wrong codes end the step. Every outcome is audited.
- **Policy**: `EUROGAS_NEXUS_MFA_REQUIRED` = `all`, `privileged` (every role above VIEWER and
  SCHEDULER; the default in trial and release) or `off` (the default in development and test).
  A person the policy covers who has not enrolled signs in to an enrolment-only session: the web
  client shows the enrolment, and every other route answers 403 `mfa_enrolment_required`.
- **Reset**: an administrator removes a person's factor with
  `POST /api/access/users/{id}/mfa/reset`, under dual control (a second administrator approves);
  every session of the person ends and they enrol again.

Phishing-resistant factors (WebAuthn, hardware keys) are not implemented; with company SSO the
identity provider's own MFA applies.

## Session lifetimes

`EUROGAS_NEXUS_SESSION_IDLE_MINUTES` (default 30 in trial and release, 720 in development) and
`EUROGAS_NEXUS_SESSION_ABSOLUTE_HOURS` (default 10 in trial and release, 24 in development). The
session cookie's lifetime follows the absolute setting.

## Session revocation

A password change (first sign-in or self-service), an administrator's reset, a disable or a
lock revokes every session of the person; self-service hands the current browser a fresh
session.

## Administration

ADMIN only (route permission registry: `/api/access/users*` ADMIN; the handler re-checks
`identity.manage`); creating an account, changing roles or data scopes, issuing a service key,
resetting a password or a second factor need a second administrator in trial and release
(dual control, [SECURITY_REVIEW_REMEDIATION_2026-11.md](SECURITY_REVIEW_REMEDIATION_2026-11.md)); a job function or work mode never grants it; nobody changes their own
roles or data scopes; the last active administrator (an ACTIVE USER principal holding ADMIN)
cannot be disabled, locked, demoted or deleted (`409 last_administrator`, audited as a denial);
delete only for a person with no audit history, API key, session or sign-in (`409
user_has_history`: disable instead). Every act is audited with actor, target and change summary;
the one-time password appears only in the creating/resetting response.

## Demo test accounts

`EUROGAS_NEXUS_DEMO_TEST_ACCOUNTS` (demo server only, see
[SELF_HOSTED_DEMO.md](../deployment/SELF_HOSTED_DEMO.md)) creates local accounts with a
configured, possibly short, password through the same code path. Fences: the API refuses to
start with the setting outside the demo profile in a development/test environment
(`assert_demo_accounts_allowed`, release test `tests/release/test_demo_test_accounts_boundary.py`);
preflight reports `demo_test_accounts_outside_demo`; the accounts are marked `is_demo` and are
refused at sign-in by any server that is not the demo profile (so a demo database restored into
a customer runtime does not let them in); an account holding ADMIN must be named explicitly
(`:admin`).

## Threat notes

- **Online guessing** is bounded by the per-account back-off and the per-address throttle. A
  side effect is that anyone can lock a known user name for 15 minutes; administrators can
  unlock, and SSO remains the recommended sign-in where it exists.
- **Offline cracking** after a database theft costs 32 MiB and roughly 0.1 s per guess per
  core; the 12-character minimum and the common-password list remove the cheapest guesses.
  `EUROGAS_NEXUS_SECRET_KEY` is not mixed into the hash (a pepper would lock every user out
  if the key were rotated or lost).
- **Temporary password in transit**: it is shown once to the administrator and must be handed
  over out of band; it expires after 72 hours and works once.
- **User enumeration**: uniform refusal and equal KDF work; the users list is ADMIN only.
- **Process-local throttles**: a multi-process deployment multiplies the per-address budget by
  the number of processes; the per-account back-off is in the database and is shared.
- **Demo accounts** with a shared weak password are a deliberate convenience of a public demo:
  anyone who reads the password can sign in; never real data there.

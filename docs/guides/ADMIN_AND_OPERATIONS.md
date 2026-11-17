# Administration and data operations guide

[简体中文](ADMIN_AND_OPERATIONS-CN.md) · [Client guide](README.md)

**Outcome:** users can access their assigned work, required sources refresh, and operational
exceptions have an owner.

## Prepare the installation

Use the release's [deployment guide](../deployment/DEPLOYMENT_ROLES-EN.md) for server and
client installation. Record the service address, installed version/channel, database schema,
sign-in method, operational owner and backup/restore procedure.

Complete [Client onboarding](CLIENT_ONBOARDING.md) with the desk before handing over access.

## Configure people and access

1. Configure the firm's sign-in method using [Enterprise SSO](../operations/ENTERPRISE_SSO.md).
2. In **Admin → Access & Identity**, assign the approved roles and data scopes.
3. Set the person's job functions and office to organise the workspace.
4. Test the account using a representative permitted task.
5. Check a restricted task with a separate test identity and retain the outcome.

The business owner approves commercial access; the administrator applies the approved change.
Platform administration and commercial-data access are separate permissions.

## Add and manage users

**Admin → Access & Identity → Users** lists everyone who can sign in, how they sign in, one
state per person and their last sign-in. **Add user** offers what the deployment allows:

- **Company SSO** (when SSO is configured): add the person before their first sign-in with
  their e-mail address (or the SSO subject, if you know it), roles, job functions, office and,
  optionally, licensed data access. They show as **Invited** and become **Active** at their
  first company sign-in, with that access. The e-mail address must be the one the company
  sign-in reports; an address the provider marks unverified never claims an invite.
- **Password (local account)** (firms without SSO, or with `EUROGAS_NEXUS_LOCAL_ACCOUNTS=on`):
  give a user name and name. The product shows a **temporary password once**; give it to the
  person in person or by phone. It works once within 72 hours, and at that first sign-in they
  must choose their own password (12 to 128 characters, not their user name, not a common
  password). The product keeps no readable copy of either.

States: **Active**, **Invited** (not yet signed in), **Disabled** (an administrator turned the
account off; every session ended at once), **Locked** (five wrong passwords in a row: locked for
15 minutes, doubling after each further five, at most 24 hours; **Unlock** lifts it now),
**Awaiting approval** (an SSO first sign-in under approved-domain provisioning).

Actions per person: **Edit access** (roles, job functions, office, data access), **Disable** /
**Enable**, **Reset password** (local accounts: a new temporary password, shown once; every
session of the person ends), **Delete** (only for someone who never signed in or acted; anyone
else is kept for the audit trail and disabled instead).

Rules the server enforces whatever the screen shows: only an administrator (the ADMIN role)
does any of this; a job function never grants it; nobody changes their own roles or data
access; the last active administrator cannot be disabled, locked, demoted or deleted. Every act
is in **Audit** (`access.user.create`, `access.user.invite`, `access.user.update`,
`access.user.password_reset`, `access.user.delete`, `auth.local.*`) with who, whom and what, never
a password.

A local-account user changes their own password with `POST /api/me/password` (current password
required; their other sessions end).

## Connect a source

1. Open **Admin → Data Sources**. The **Connectors** view groups sources as Needs attention,
   Connected and Available; choose the source and read its detail panel.
2. Configure the supported credential method, if required.
3. Complete the source's access/certification checks where applicable.
4. Enable the source and confirm its ingestion schedule or import process.
5. Run or observe the first ingestion. Inspect its result, record count and source timestamp.
6. Open the corresponding market or physical view and verify one record against its source.

**Check the result:** a configured credential, an enabled source, a successful ingestion and
fresh records are distinct states. Check each one when commissioning a source.

| Data | Credential/setup | Operational reference |
| --- | --- | --- |
| ECB reference FX | Public endpoint; no API key | [Public-data ingestion](../../scripts/ops/ingest_public_sources.py) |
| ENTSOG flows, capacity and network | No API key; explicit query scope and source certification | [Scheduler](../../scripts/ops/run_dataops_scheduler.py) |
| GIE storage/LNG | GIE key and source certification | [Provider credentials](../deployment/PROVIDER_CREDENTIALS.md) |
| BoE, ECB €STR, New York Fed rates | Public endpoints | [Interest rates](../operations/INTEREST_RATES.md) |
| ENTSO-E power / EIA Henry Hub | Provider token/key | [Power](../operations/POWER_DATA.md), [market-data sourcing](../operations/MARKET_DATA_SOURCING.md) |
| Licensed quotes, settlements and FX fixings | Entitled feed or approved import | [Live prices](../operations/LIVE_PRICE_SOURCES.md), [FX fixings](../operations/FX_FIXINGS.md) |
| ECMWF forecasts and National Gas demand | Dataset-specific ingestion setup | [ECMWF](../data/ECMWF_FORECAST_OPERATIONS.md), [National Gas](../data/NATIONAL_GAS_REST_OPERATIONS.md) |

The credential catalogue identifies implemented connectors. A future connector can have a
stored credential without a working data feed. Simulation sources appear through the
explicit test-source option in Data Sources.

## Reuse test credentials

Copy the repository's `.env.testing.example` to private `.env.testing` and fill the services
you use. Load it explicitly in the test runtime. Keep database addresses and installation secrets in their own deployment
configuration.

The current credential contract supports GIE, EIA, ENTSO-E and the configured LLM endpoint.
An administrator-disabled provider remains disabled. Otherwise resolution uses the supported
environment variable, supported key file, then the encrypted store. Inspect
`effective_source` in `GET /api/credentials/providers` to identify the active method.
[Provider credentials](../deployment/PROVIDER_CREDENTIALS.md) lists exact variables and aliases.

## Monitor and recover

Check **Data Sources** for source failures and freshness, and **Admin → Runtime** for
operational readiness and problem reports. Distinguish service connectivity from actual
source coverage. A reference-rate source may update daily while a quote feed has another cadence.

For a failed source, inspect the last run, scope, provider response and next retry before
requesting another run. For a platform incident use
[Incident response](../operations/INCIDENT_RESPONSE.md), [Backup and restore](../operations/BACKUP_RESTORE.md)
and [Rollback](../operations/RELEASE_ROLLBACK.md).
[Support and updates](SUPPORT_AND_UPDATES.md) explains the evidence to collect.

Use the managed server deployment for the firm's agreed operating and recovery requirements.

# Client onboarding and handover

[简体中文](CLIENT_ONBOARDING-CN.md) · [Client guide](README.md)

Use this record to prepare a desk for its agreed installation and operating scope.
The deployment owner maintains the completed client-specific record in the firm's
approved document store.

## 1. Agree the service profile

| Record | Owner |
| --- | --- |
| Client environment, service URL, installed release/channel/build and schema revision | Deployment owner |
| Desk/book/hub scope, business users and acceptance lead | Desk owner |
| Sign-in method, access approvers and administrators | Access owner |
| Required datasets, source scopes, licences and refresh expectations | Data owner |
| Supported client/device versions and completed installation tests | IT owner |
| Support contacts, hours, incident priorities and escalation route | Service owner |
| Backup frequency, recovery objectives, restore evidence and change window | Operations owner |

Complete these fields for the installation before operational handover. Record the agreed service and recovery targets as client-approved fields for the
installation.

## 2. Prepare access and data

1. Install the approved server/client release using the [deployment guide](../deployment/DEPLOYMENT_ROLES-EN.md).
2. Configure sign-in and assign approved roles, job functions and data scopes.
3. Connect/import the required datasets and complete each source's activation checks.
4. Confirm the first successful refresh and inspect one record from each critical dataset.
5. Set organisational preferences and confirm the business calendar and display conventions.

Use [Administration and operations](ADMIN_AND_OPERATIONS.md) for the source workflow and
[Data and methodology](../user/DATA_STATUS_AND_PROVENANCE.md) for the interpretation checks.

## 3. Complete representative acceptance tasks

| Participant | Task | Evidence to retain |
| --- | --- | --- |
| Trader | Compare two prices on a common basis; inspect a contract, position and route alternative | Context, source timestamps and saved references |
| Analyst | Run a saved analysis/backtest and inspect a dataset snapshot | Version/run/snapshot IDs and coverage |
| Risk reviewer | Reconcile sample exposure and inspect one limit/approval | Selected population, exceptions and review reference |
| Administrator | Test permitted/restricted access and a source failure/retry | Role/scope assignment and observed outcomes |
| Operator | Verify backup/restore and the update/rollback process | Test date, release/schema and operational result |
| Service owner | Submit and route a test support report | Ticket reference and named receiving team |

Choose the tasks included in the agreed scope. Record pass, issue or deferred outcome,
the responsible owner and the resolution for each material issue.
[Release readiness](../release/RELEASE_READINESS.md) holds release-level approval evidence;
the handover records installation-specific acceptance.

## 4. Handover

Give users the [quick start](../user/QUICK_START.md), their role guide and the support route.
Give operators the deployment configuration reference, source schedule, recovery runbooks
and release package inventory through approved channels.

Record the release supplied, accepted scope, outstanding issues, acceptance owner and
handover date. Arrange the next access/data-quality review and confirm who owns later updates.

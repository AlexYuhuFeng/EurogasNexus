# Support, troubleshooting and updates

[简体中文](SUPPORT_AND_UPDATES-CN.md) · [Client guide](README.md)

## Choose the right support route

| Problem | First contact | Useful evidence |
| --- | --- | --- |
| Sign-in or a restricted workspace | Firm's IT/access administrator | Environment, username through the approved channel, time and visible error |
| Missing or stale source data | Data operator | Source, dataset/hub, delivery period, last successful run and timestamp |
| A questionable price, valuation or allocation | Desk/risk owner and application support | Saved result ID, context, unit, assumptions and expected comparison |
| Page, control or device issue | Application support through the IT desk | Version, browser/device, viewport/orientation and a redacted screenshot |
| Suspected security incident | Firm's security incident route | Time, affected account/service and incident reference |

The client handover identifies the firm's support contact and the vendor escalation route.
Service hours, response targets and restoration commitments come from the agreed support
arrangement; record them in the [onboarding record](CLIENT_ONBOARDING.md).

## Check common symptoms

| Symptom | Check |
| --- | --- |
| Service is reachable, prices are empty | Quote import/feed, entitlement, selected dates and the first ingestion result |
| ECB or ENTSOG is empty | Source enablement, scheduler run and query scope; ENTSOG also has a certification gate |
| Provider key was added but nothing changed | Active credential source, disabled state, connector implementation and source activation |
| Refresh shows old application code | Deployment completion and the live commit; reload after a successful deploy |
| Number differs from another screen | Currency/unit, tenor, source timestamp, FX fixing and calculation assumptions |
| A control is missing on a phone | Orientation, browser and screen size; report an unreachable control as a functional issue |

## Submit a useful report

1. Record the task and the steps that produced the issue.
2. State the expected result and the actual result.
3. Record the time with its time zone, affected environment and version/build information.
4. Include the saved case/run/source identifiers and request/correlation ID where available.
5. Attach relevant diagnostics or a screenshot through the approved support channel.

Open **Help & Settings → Settings** and use **About & Diagnostics**. Review attachments before sending;
share only the information needed for the investigation. Keep credentials and sensitive
trading information in the firm's approved channels.

If the page cannot open, send the URL path, visible error and timestamp. The operator can
find matching server events using the correlation ID or time window.

## Set the incident priority

| Level | Business impact | Initial action |
| --- | --- | --- |
| SEV1 | Widespread outage, suspected security compromise or material data-integrity incident | Contact the incident owner immediately; preserve evidence and agree containment |
| SEV2 | A major desk workflow is blocked without a reliable workaround | Escalate with affected users/books and the operational deadline |
| SEV3 | Limited degradation with a usable workaround | Record the workaround, scope and follow-up |
| Improvement | A usability or capability request without an active incident | Record the user task and expected benefit |

Priority follows impact. A misleading valuation can be more urgent than a cosmetic defect,
even when the application remains accessible.
Operators use the [incident runbook](../operations/INCIDENT_RESPONSE.md) for recovery.

## Install and update

Use the package, checksum and installation guide supplied for your release and platform.
The release manifest and acceptance evidence identify the tested build and signing state.
Package/build availability and a recorded installed-client test are different evidence.

- **Browser:** the application changes when the service successfully deploys a new build.
  Reload the page after deployment.
- **Windows/Linux desktop:** IT distributes the applicable installer
  and schedules the upgrade. The current desktop release uses managed/manual updates.
- **Server/database:** use the release's migration preflight, backup and rollback procedure.
  Restoring application code and reversing a database change require separate planning.

The compatibility screen uses release metadata, API contract and declared minimum client/server
versions. Resolve a blocking mismatch through the supplied release set.
See [Update policy](../release/UPDATE_POLICY.md), [Deployment](../deployment/DEPLOYMENT_ROLES-EN.md),
and [Rollback](../operations/RELEASE_ROLLBACK.md).

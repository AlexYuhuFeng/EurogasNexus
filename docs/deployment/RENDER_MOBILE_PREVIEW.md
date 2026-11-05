# Render mobile preview

The optional Blueprint on `main` serves the built web client and API from one
HTTPS origin, using an independent test PostgreSQL database. It provisions a
UAT identity; it imports no local database or provider credentials. This is an
owner-authorized test deployment, not production security acceptance. Keeping
this optional deployment in main does not enable it in other installations.

## Deploy

1. In Render choose **New > Blueprint**, select this repository and branch
   **main**, and use `render.yaml`. Keep both resource plans **Free**.
2. Apply the Blueprint. It creates a web service and PostgreSQL database in
   Ohio. Build installs locked Python dependencies and builds the web client.
   Startup migrates the database, provisions the test login and starts the API.
3. Open the service's `onrender.com` URL. Username: `mobile-tester`. Retrieve
   `EUROGAS_NEXUS_DEV_LOGIN_PASSWORD` from its Environment page; Render generates
   it. Never commit or put that value in an issue.
4. Test login, refresh and logout from the mobile browser.

## Automatic updates from main

The web service links directly to **main**, with **Auto-Deploy: After CI Checks
Pass** (`autoDeployTrigger: checksPass`). Keep its GitHub integration connected.
There is no synchronization workflow, personal access token, Render API secret
or permanent deployment branch to maintain.

The sequence is **main push → GitHub CI passes → Render builds and deploys →
browser refresh**. New source is not live until the Render deployment succeeds.
Failed checks prevent automatic deployment; a failed build leaves the previous
successful deployment available. Check GitHub Actions and Render Events for the
exact commit and outcome. Existing open browser tabs need to reload after the
new deployment; an API process restart cannot replace their loaded JavaScript.

Render **Restart service** restarts the currently deployed commit. It does not
fetch new source. **Deploy latest commit** is a manual deployment, so first
verify the main commit's CI result. Waking an idle Free service does not fetch
new code either. See https://render.com/docs/deploys for current semantics.

## Move an existing preview to main

The temporary `deploy/render-mobile-preview` and `automation/render-preview-sync` branches
were removed on 2026-11-05; `render.yaml` lives on **main** only. A service created from the
old branch keeps running its last deployment but receives no updates:

1. In the existing **Eurogas Nexus Blueprint > Settings**, change its tracked branch to
   **main**, keeping the path `render.yaml`. Sync the Blueprint and review its changes.
2. Check the **eurogas-mobile-preview** service now shows **main** and **After CI Checks
   Pass**. Keep the resource names, database, generated password and environment values;
   do not create a second Blueprint or replace the database.
3. Check Render Events for a successful deployment and sign in on the public URL.

Moving the branch does not reset data or environment values. Normal startup migrations
still run.

## Data in the preview

Startup loads published reference data (TSO tariffs, the public NBP to TTF route templates
over IUK and BBL, the hub master, the glossary) and starts the data scheduler beside the
web server. Every enabled source runs once at startup, then on its normal schedule:

| Source | Needs | Shows |
|---|---|---|
| ECB reference rates | nothing | FX |
| Bank of England, ECB, New York Fed | nothing | SONIA, €STR, SOFR (early-cash financing) |
| US EIA | `EIA_API_KEY` | Henry Hub daily spot |
| ENTSO-E | `ENTSOE_SECURITY_TOKEN` | Day-ahead power, load, wind and solar |
| ENTSOG | a certification record | The pipeline network, flows and capacity on the map |
| GIE AGSI+/ALSI | `GIE_API_KEY` and a certification record | Storage and LNG send-out |

Enter keys under the service's **Environment**; never commit them. ENTSOG and GIE stay
blocked until an operator records a certification (`POST
/api/source-certifications/{source_id}/certify`, stage `live_validated` with the checks
`simulated_shape_match` and `live_sample_validation`). That record states that a live
sample was checked, so it is made by a person, not by the preview. Until then the map shows
the hubs and route templates but no pipeline network. Hub prices come only from the desk's
own licensed feed or screen import; the preview has none, so price boards stay empty
rather than showing simulated prices.

The scheduler runs only while the service is awake (Free sleeps after 15 minutes).

## Free-instance scope

Render Free sleeps after 15 minutes without traffic; waking takes about a minute.
Its free PostgreSQL database expires after 30 days and only one free database is
allowed per workspace. Export anything needed before expiry. See
https://render.com/docs/free for current limits.

The preview disables anonymous callers, simulated sources and external LLM
providers. The UAT identity has ADMIN and ANALYST assignments for broad functional
testing; it does not validate other personas or commercial data entitlements.

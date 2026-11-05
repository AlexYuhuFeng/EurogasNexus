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

## Migrate the existing preview without replacing resources

After the deployment files are merged into main and main CI is green:

1. In the existing **Eurogas Nexus Blueprint > Settings**, change its tracked
   branch from `deploy/render-mobile-preview` to **main**, retaining the path
   `render.yaml`. Sync the Blueprint and review its changes.
2. Verify the existing **eurogas-mobile-preview** service now uses **main** and
   **After CI Checks Pass**. Retain the resource names, database, generated
   password and environment credentials. Do not create a second Blueprint or
   replace/delete the database to make this change.
3. Check Render Events for the successful main deployment and test login on the
   existing public URL. Only then delete the old `deploy/render-mobile-preview`
   branch. If the service is switched without the Blueprint, a later Blueprint
   sync could otherwise restore the old branch setting.

Source updates do not initialize public-source ingestion or schedule refreshes.
Existing data and environment credentials are not reset by moving the source
branch. Normal startup migrations still run; review compatibility before updates.

## Free-instance scope

Render Free sleeps after 15 minutes without traffic; waking takes about a minute.
Its free PostgreSQL database expires after 30 days and only one free database is
allowed per workspace. Export anything needed before expiry. See
https://render.com/docs/free for current limits.

The preview disables anonymous callers, simulated sources and external LLM
providers. The UAT identity has ADMIN and ANALYST assignments for broad functional
testing; it does not validate other personas or commercial data entitlements.

# Render mobile preview

This Blueprint serves the built web client and API from one HTTPS origin, using
an independent empty PostgreSQL database. It provisions only a disposable UAT
identity; it imports no local database, provider credentials or market data.
This is an owner-authorized test deployment, not production security acceptance.

## Deploy

1. In Render choose **New > Blueprint**, then this repository and the preview
   branch containing `render.yaml`. Keep both resource plans **Free**.
2. Apply the Blueprint. It creates a web service and a PostgreSQL database in
   Ohio. Build installs the locked Python dependencies and builds the web client.
   Startup migrates the database, provisions the test login and starts the API.
3. Open the web service's `onrender.com` URL. Username: `mobile-tester`.
   Retrieve `EUROGAS_NEXUS_DEV_LOGIN_PASSWORD` from that service's Environment
   page; Render generates it. Do not commit or share the password in an issue.
4. Test login, refresh and logout from the mobile browser. The API uses the
   same origin, so no separate API URL or CORS setup is required.

Render Free sleeps after 15 minutes without traffic; waking takes about a minute.
The free PostgreSQL database expires after 30 days. Export anything you want to
retain before expiry. Only one free PostgreSQL database is allowed per workspace.
See https://render.com/docs/free for current limits.

The preview explicitly disables anonymous callers, simulated sources and external
LLM providers. Do not put production data or provider keys into this environment.
The UAT identity has ADMIN and ANALYST assignments for broad functional testing;
this does not validate other personas or commercial data entitlements.

## Automatic updates from main

Once `.github/workflows/sync-render-preview.yml` is merged into `main`, a
successful **CI** push run for the current `main` commit triggers **Sync Render
preview**. The workflow merges that commit into `deploy/render-mobile-preview`,
builds the merged web client and runs the mandatory pre-push checks before
publishing. Existing preview changes are preserved by a normal merge. It never
force-pushes or automatically resolves conflicts. Concurrent preview changes,
an advanced main commit, merge conflicts or failed checks stop publication.
Inspect the Actions run's summary and logs when a sync fails.

The initial merge includes the same-origin preview entry point and configuration
in main as well, so subsequent changes can be maintained and reviewed there.
The preview branch remains a deployment target, not a separate development line.
Develop ordinary changes through main; make necessary preview-specific changes
explicitly and expect a conflict to require a reviewed resolution.

The Blueprint sets **Auto-Deploy: On Commit**. Keep the GitHub integration
connected in Render and verify this setting on the existing web service after
syncing the updated Blueprint. The GitHub workflow already gates publication;
do not select **After CI Checks Pass** for the generated preview commit, which
does not start another GitHub Actions CI run with the default workflow token.
No personal access token or Render API secret is required for normal auto-deploy.

The sequence is **main CI success → checked preview merge → Render build/deploy
success → browser refresh**. A failed or still-running build does not make new
code live. Render **Restart service** restarts the currently deployed commit;
it does not fetch new source. For a manual retry use **Deploy latest commit**.
Reload the browser after the deploy completes; an already-open client does not
replace its JavaScript simply because the server restarted. An idle Free
service waking up likewise does not pull a new commit.

For recovery, run **Sync Render preview → Run workflow** on main. It still
requires successful push CI for the exact current main SHA. Repeating it with
no new changes makes no additional deployment commit. The workflow must first
exist on main; adding it only to the preview branch cannot activate this trigger.

Source updates do not initialize public-source ingestion or schedule refreshes.
Existing Render environment secrets and database data are not copied or reset;
normal startup migrations still run and should be reviewed for compatibility.
Monitor the workflow and Render deployment separately: this automation does not
claim cloud health until Render reports a successful deployment.

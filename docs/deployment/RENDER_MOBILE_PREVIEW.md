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

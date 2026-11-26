"""Authoritative configuration contract for deployment environment variables.

Why this module exists
----------------------
The delivered ``.env.example`` used to document a handful of variables while the
code read far more, including deployment-critical ones (the runtime DB URL, the
credential-encryption key, the internal API token and the whole OIDC block). An
operator could therefore not configure a deployment from the shipped template,
and a variable that nothing reads could be documented as a working control.

This module is the single source of truth:

* :data:`CONFIG_VARS` declares every environment variable the product reads,
  with its default, sensitivity, applicability and whether it is operator-facing;
* ``scripts/ci/check_config_contract.py`` fails the build when a declaration and
  the code disagree in either direction -- an undeclared read, or a declaration
  with no read site (dead configuration);
* ``scripts/ci/generate_env_template.py`` renders the operator-facing declarations
  into the shipped templates, so a template can no longer drift from the code.

Scopes
------
``OPERATOR``
    A deployment setting an operator must be able to see and set. Rendered into
    ``.env.example``.
``BUILD_METADATA``
    Stamped by CI/release tooling to identify a build. Not operator-set, so it is
    declared (to keep the completeness gate meaningful) but not rendered.
``TOOLING``
    Read by a maintenance or release script rather than the running service.
``TEST_ONLY``
    Read only by the test suite.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from eurogas_nexus.version import APPLICATION_VERSION

ConfigScope = Literal["OPERATOR", "BUILD_METADATA", "TOOLING", "TEST_ONLY"]
Sensitivity = Literal["public", "internal", "secret"]


@dataclass(frozen=True)
class ConfigVar:
    """One environment variable the product reads.

    Attributes:
        name: Exact variable name.
        scope: Who is expected to set it (see the module docstring).
        purpose: One line stating what it controls.
        default: Rendered default, or ``None`` when unset means "feature off".
        sensitivity: ``secret`` values must never be printed, logged or committed.
        required_when: Human-readable condition under which the deployment cannot
            start or cannot serve correctly without it.
        profiles: Environments the variable applies to.
        example: Non-secret example value safe to publish in a template.
        aliases: Other names accepted for the same setting, in precedence order.
        notes: Extra operator guidance.
        emitted_only: True when the name is not read by this product but is
            written into a generated artifact, so it must still be declared (to
            keep the completeness gate honest) without being reported as dead
            configuration.
        external_reader: Name of the component outside this repository's Python
            that reads the variable (for example ``uvicorn`` or ``compose``), so
            the dead-configuration gate does not require an in-repo read site.
    """

    name: str
    scope: ConfigScope
    purpose: str
    default: str | None = None
    sensitivity: Sensitivity = "public"
    required_when: str | None = None
    profiles: tuple[str, ...] = ("development", "test", "trial", "release")
    example: str | None = None
    aliases: tuple[str, ...] = field(default_factory=tuple)
    notes: tuple[str, ...] = field(default_factory=tuple)
    emitted_only: bool = False
    external_reader: str | None = None

    def template_line(self) -> str:
        """Render this declaration as one commented template entry."""

        lines = [f"# {self.purpose}"]
        if self.required_when:
            lines.append(f"# Required: {self.required_when}")
        lines.append(f"# Applies to: {', '.join(self.profiles)}")
        if self.aliases:
            lines.append(f"# Accepted aliases: {', '.join(self.aliases)}")
        for note in self.notes:
            lines.append(f"# {note}")
        if self.sensitivity == "secret":
            lines.append("# Secret: never commit a real value; inject it at deploy time.")
            lines.append(f"# {self.name}=")
        else:
            value = self.example if self.example is not None else (self.default or "")
            lines.append(f"# {self.name}={value}")
        return "\n".join(lines)


_ALL_PROFILES = ("development", "test", "trial", "release")
_SERVED = ("development", "internal", "release")

CONFIG_VARS: tuple[ConfigVar, ...] = (
    # --- Deployment identity and profile ------------------------------------
    ConfigVar(
        name="EUROGAS_NEXUS_ENV",
        scope="OPERATOR",
        purpose="Runtime environment. Selects fail-closed behaviour (trial/release).",
        default="development",
        example="development",
    ),
    ConfigVar(
        name="EUROGAS_NEXUS_API_PROFILE",
        scope="OPERATOR",
        purpose="Route profile: which API surfaces are mounted.",
        default="development",
        example="development",
        notes=(
            "release hides /docs and /openapi.json and mounts no development routes",
            "demo is a hosted test/demo server: release surface plus the tester "
            "credential sign-in; refused in trial and release environments "
            "(docs/deployment/SELF_HOSTED_DEMO.md)",
        ),
    ),
    ConfigVar(
        name="EUROGAS_NEXUS_VERSION",
        scope="OPERATOR",
        purpose="Application version reported by the runtime and release endpoints.",
        example=APPLICATION_VERSION,
        notes=(
            "Normally stamped by the release tooling; do not hand-edit in a release",
            "Must match the packaged version or the version-consistency gate fails",
        ),
    ),
    ConfigVar(
        name="EUROGAS_NEXUS_RELEASE_CHANNEL",
        scope="OPERATOR",
        purpose="Release channel: preview, beta, rc or stable.",
        default="preview",
    ),
    # --- Runtime store ------------------------------------------------------
    ConfigVar(
        name="RUNTIME_STORE_DATABASE_URL",
        scope="OPERATOR",
        purpose="PostgreSQL DSN for the runtime store (the source of truth).",
        sensitivity="secret",
        required_when="any DB-backed workflow is used",
        example="postgresql+pg8000://user:password@host:5432/eurogas_nexus",
        aliases=("DATABASE_URL", "EUROGAS_NEXUS_DB_DSN"),
        notes=(
            "Accepted aliases are read in the order shown; the first non-blank wins.",
            "Without it the API still starts, but every DB-backed read reports a "
            "diagnostic state instead of data.",
        ),
    ),
    ConfigVar(
        name="DATABASE_URL",
        scope="OPERATOR",
        purpose="Alias for RUNTIME_STORE_DATABASE_URL (lower precedence).",
        sensitivity="secret",
        example="postgresql+pg8000://user:password@host:5432/eurogas_nexus",
    ),
    ConfigVar(
        name="EUROGAS_NEXUS_DB_DSN",
        scope="OPERATOR",
        purpose="Alias for RUNTIME_STORE_DATABASE_URL (lowest precedence).",
        sensitivity="secret",
    ),
    ConfigVar(
        name="EUROGAS_NEXUS_CENTRAL_PLATFORM_URL",
        scope="OPERATOR",
        purpose="Read-only SQLAlchemy URL of the firm's central data platform.",
        sensitivity="secret",
        required_when="scripts/ops/sync_central_platform.py subscribes to platform feeds",
        example="postgresql+pg8000://egn_reader:password@platform-host:5432/central",
        notes=(
            "Use a login that can only SELECT the published egn_* views.",
            "May be the runtime store's own server (another schema) or a separate one.",
        ),
    ),
    ConfigVar(
        name="EUROGAS_NEXUS_DB_ECHO",
        scope="OPERATOR",
        purpose="Echo SQL to the log. Development diagnosis only.",
        default="false",
        notes=("Never enable in a delivery: statements can carry business values",),
    ),
    ConfigVar(
        name="EUROGAS_NEXUS_DB_POOL_PRE_PING",
        scope="OPERATOR",
        purpose="Verify pooled connections before use.",
        default="true",
    ),
    ConfigVar(
        name="EUROGAS_NEXUS_TIMESCALE",
        scope="OPERATOR",
        purpose=(
            "Use the optional TimescaleDB Community Edition extension for the high-volume "
            "time-series tables: off, auto or require."
        ),
        default="off",
        notes=(
            "Read by migration 0092 and scripts/ops/timescale.py. off (default): plain "
            "PostgreSQL. auto: convert where the server has the Community Edition. require: "
            "stop if it does not. See docs/deployment/TIMESCALEDB.md (ADR Decision 39).",
            "A conversion is not reversed by a downgrade.",
        ),
    ),
    ConfigVar(
        name="EUROGAS_NEXUS_DB_SSL_ROOT_CERT",
        scope="OPERATOR",
        purpose="CA certificate for a verified PostgreSQL TLS connection: a path or the PEM text.",
        sensitivity="internal",
        notes=(
            "Used with sslmode=verify-ca or verify-full in the database URL (a managed "
            "service's project CA, for example). With sslmode=require it upgrades the "
            "connection to verify-ca, as libpq does.",
            "The libpq sslrootcert URL parameter is accepted too.",
        ),
    ),
    ConfigVar(
        name="EUROGAS_NEXUS_DB_POOL_SIZE",
        scope="OPERATOR",
        purpose="SQLAlchemy pool size for the runtime store.",
        default="10",
        notes=("Size against the PostgreSQL connection limit shared by every worker",),
    ),
    ConfigVar(
        name="EUROGAS_NEXUS_DB_MAX_OVERFLOW",
        scope="OPERATOR",
        purpose="Extra connections permitted above the pool size.",
        default="20",
    ),
    ConfigVar(
        name="EUROGAS_NEXUS_DB_POOL_TIMEOUT",
        scope="OPERATOR",
        purpose="Seconds to wait for a pooled connection before failing.",
        default="5.0",
    ),
    ConfigVar(
        name="EUROGAS_NEXUS_DB_POOL_RECYCLE",
        scope="OPERATOR",
        purpose="Seconds after which a pooled connection is recycled.",
        default="1800",
    ),
    # --- Caller identity ----------------------------------------------------
    ConfigVar(
        name="EUROGAS_NEXUS_PUBLIC_API_TOKEN",
        scope="OPERATOR",
        purpose="Deployment token presented by SDK, CLI and service callers.",
        sensitivity="secret",
        required_when="any non-health route is served (otherwise the API refuses with 503)",
        notes=(
            "Every route profile identifies its callers, so an unconfigured token "
            "fails closed rather than serving unauthenticated callers.",
        ),
    ),
    ConfigVar(
        name="EUROGAS_NEXUS_INTERNAL_API_TOKEN",
        scope="OPERATOR",
        purpose="Token for the internal route profile (operator and tooling actions).",
        sensitivity="secret",
        required_when="the internal profile is mounted",
    ),
    ConfigVar(
        name="EUROGAS_NEXUS_ALLOW_ANONYMOUS_CALLERS",
        scope="OPERATOR",
        purpose="Permit callers that present no credential (pre-D1 posture).",
        default="0",
        notes=(
            "Set to 1 only when the deployment really does trust its network; the "
            "health payload then reports authentication=anonymous_allowed.",
        ),
    ),
    ConfigVar(
        name="EUROGAS_NEXUS_SECRET_KEY",
        scope="OPERATOR",
        purpose="Master key encrypting provider credentials at rest and keying identity digests.",
        sensitivity="secret",
        required_when="any provider credential is stored",
        notes=(
            "A 32-byte urlsafe-base64 Fernet key is used as given; any other value "
            "is hashed to derive the key.",
            "Rotating it makes previously stored provider credentials undecryptable: "
            "re-enter them after a rotation.",
        ),
    ),
    # --- Enterprise SSO (OIDC) ---------------------------------------------
    ConfigVar(
        name="EUROGAS_NEXUS_HANDOFF_SIGNING_KEY",
        scope="OPERATOR",
        purpose=(
            "Key that signs decision hand-offs (HMAC-SHA256) read by ERP/ETRM middleware; "
            "the receiver holds the same key to verify them."
        ),
        sensitivity="secret",
        required_when="decision hand-offs are used (docs/integration/ERP_ETRM_INTEGRATION.md)",
    ),
    ConfigVar(
        name="EUROGAS_NEXUS_GATEWAY_AUTH_ENABLED",
        scope="OPERATOR",
        purpose=(
            "Accept the user and groups asserted by an authenticating reverse proxy (SAML, "
            "Kerberos/SPNEGO or a vendor SSO agent) in a dedicated network."
        ),
        example="false",
        notes=("Requires EUROGAS_NEXUS_GATEWAY_SECRET; see docs/operations/ENTERPRISE_SSO.md",),
    ),
    ConfigVar(
        name="EUROGAS_NEXUS_GATEWAY_SECRET",
        scope="OPERATOR",
        purpose="Shared secret the gateway sends in X-Eurogas-Gateway-Secret (32+ characters).",
        sensitivity="secret",
        required_when="EUROGAS_NEXUS_GATEWAY_AUTH_ENABLED is true",
    ),
    ConfigVar(
        name="EUROGAS_NEXUS_GATEWAY_TRUSTED_PROXIES",
        scope="OPERATOR",
        purpose="Comma-separated CIDRs the gateway connects from; requests from elsewhere fail.",
        example="10.20.0.0/24",
    ),
    ConfigVar(
        name="EUROGAS_NEXUS_GATEWAY_USER_HEADER",
        scope="OPERATOR",
        purpose="Header carrying the authenticated user name.",
        example="X-Remote-User",
    ),
    ConfigVar(
        name="EUROGAS_NEXUS_GATEWAY_GROUPS_HEADER",
        scope="OPERATOR",
        purpose="Header carrying the user's groups, comma or semicolon separated.",
        example="X-Remote-Groups",
    ),
    ConfigVar(
        name="EUROGAS_NEXUS_GATEWAY_OFFICE_HEADER",
        scope="OPERATOR",
        purpose="Header carrying the user's office code (directory mode sets the profile office).",
        example="X-Remote-Office",
    ),
    ConfigVar(
        name="EUROGAS_NEXUS_SSO_OFFICE_CLAIM",
        scope="OPERATOR",
        purpose="OIDC claim carrying the user's office code (directory provisioning mode).",
        example="office",
    ),
    ConfigVar(
        name="EUROGAS_NEXUS_REMIT_OWN_PARTICIPANTS",
        scope="OPERATOR",
        purpose=(
            "The firm's REMIT market participant names or ACER codes as they appear in UMMs "
            "(comma-separated), so surveillance recognises outages at the firm's own assets."
        ),
        example="Example Energy Trading Ltd,A0001234X.GB",
    ),
    ConfigVar(
        name="EUROGAS_NEXUS_SMTP_HOST",
        scope="OPERATOR",
        purpose="The firm's SMTP relay for email notifications (alerts, IT desk reports).",
        example="smtp.example-energy.internal",
    ),
    ConfigVar(
        name="EUROGAS_NEXUS_SMTP_PORT",
        scope="OPERATOR",
        purpose="SMTP relay port (default 587).",
        example="587",
    ),
    ConfigVar(
        name="EUROGAS_NEXUS_SMTP_USERNAME",
        scope="OPERATOR",
        purpose="SMTP login, when the relay requires one.",
        example="eurogas-nexus",
    ),
    ConfigVar(
        name="EUROGAS_NEXUS_SMTP_PASSWORD",
        scope="OPERATOR",
        purpose="SMTP password, when the relay requires one.",
        sensitivity="secret",
    ),
    ConfigVar(
        name="EUROGAS_NEXUS_SMTP_FROM",
        scope="OPERATOR",
        purpose="Sender address for notification emails.",
        example="eurogas-nexus@example-energy.com",
    ),
    ConfigVar(
        name="EUROGAS_NEXUS_SMTP_STARTTLS",
        scope="OPERATOR",
        purpose="Upgrade the SMTP connection with STARTTLS (default true).",
        example="true",
    ),
    ConfigVar(
        name="EUROGAS_NEXUS_OWN_LEGAL_NAMES",
        scope="OPERATOR",
        purpose=(
            "The firm's own legal entity names as they appear in contracts (comma-separated), "
            "so contract intake picks the other party as the counterparty."
        ),
        example="Example Energy Trading Ltd,Example Gas Supply BV",
    ),
    ConfigVar(
        name="EUROGAS_NEXUS_DEPLOYMENT_REGION",
        scope="OPERATOR",
        purpose="Where this installation serves users: global (default) or china.",
        example="global",
        notes=("Selects region-appropriate defaults such as the basemap",),
    ),
    ConfigVar(
        name="EUROGAS_NEXUS_MAP_DEFAULT_PROVIDER",
        scope="OPERATOR",
        purpose=(
            "Default basemap for this installation: bundled (Natural Earth land, borders and "
            "names served by the application, offline; global default), outline (bundled "
            "coastlines only; China default), openfreemap or versatiles (external open styles), "
            "tianditu (mainland China, key required), custom (own tile service) or none."
        ),
        example="bundled",
        notes=("Use none or custom in networks without internet access",),
    ),
    ConfigVar(
        name="EUROGAS_NEXUS_PORTFOLIO_ISOLATION",
        scope="OPERATOR",
        purpose=(
            "Restrict contracts, trades and books to the books named by each person's "
            "BOOKS: data scopes (head office BOOKS:*, regional heads their entity or region)."
        ),
        example="false",
        notes=("Turn on for any installation shared by more than one office",),
    ),
    ConfigVar(
        name="EUROGAS_NEXUS_GATEWAY_EMAIL_HEADER",
        scope="OPERATOR",
        purpose="Header carrying the user's e-mail address (optional).",
        example="X-Remote-Email",
    ),
    ConfigVar(
        name="EUROGAS_NEXUS_OIDC_ISSUER",
        scope="OPERATOR",
        purpose="OIDC issuer URL for interactive SSO login.",
        required_when="interactive SSO is offered",
        example="https://idp.example.com/realms/trading",
    ),
    ConfigVar(
        name="EUROGAS_NEXUS_OIDC_CLIENT_ID",
        scope="OPERATOR",
        purpose="OIDC client id registered for this deployment.",
        required_when="interactive SSO is offered",
    ),
    ConfigVar(
        name="EUROGAS_NEXUS_OIDC_CLIENT_SECRET",
        scope="OPERATOR",
        purpose="OIDC client secret for the authorization-code exchange.",
        sensitivity="secret",
        required_when="the identity provider requires a confidential client",
    ),
    ConfigVar(
        name="EUROGAS_NEXUS_OIDC_REDIRECT_URI",
        scope="OPERATOR",
        purpose="Redirect URI registered with the identity provider.",
        required_when="interactive SSO is offered",
        example="https://nexus.example.com/api/auth/oidc/callback",
    ),
    ConfigVar(
        name="EUROGAS_NEXUS_OIDC_AUDIENCE",
        scope="OPERATOR",
        purpose="Expected token audience (defaults to the client id).",
    ),
    ConfigVar(
        name="EUROGAS_NEXUS_OIDC_ROLE_CLAIM",
        scope="OPERATOR",
        purpose="Token claim carrying role names.",
        default="roles",
    ),
    ConfigVar(
        name="EUROGAS_NEXUS_OIDC_SCOPE_CLAIM",
        scope="OPERATOR",
        purpose="Token claim carrying commercial data scopes.",
        default="entitlements",
    ),
    ConfigVar(
        name="EUROGAS_NEXUS_OIDC_PROVISIONING_MODE",
        scope="OPERATOR",
        purpose=(
            "How SSO identities become users: preprovisioned, approved_domain (registered "
            "PENDING), or directory (created active; roles, scopes and office follow "
            "directory groups at every sign-in)."
        ),
        default="preprovisioned",
        notes=(
            "approved_domain registers a PENDING identity and still refuses access "
            "until an administrator activates it.",
        ),
    ),
    ConfigVar(
        name="EUROGAS_NEXUS_OIDC_APPROVED_DOMAINS",
        scope="OPERATOR",
        purpose="Comma-separated email domains eligible for just-in-time registration.",
        example="example.com,trading.example.com",
    ),
    ConfigVar(
        name="EUROGAS_NEXUS_OIDC_GROUPS_ROLE_MAP",
        scope="OPERATOR",
        purpose="Mapping from identity-provider groups to roles.",
    ),
    ConfigVar(
        name="EUROGAS_NEXUS_OIDC_GROUPS_SCOPE_MAP",
        scope="OPERATOR",
        purpose="Mapping from identity-provider groups to commercial data scopes.",
    ),
    ConfigVar(
        name="EUROGAS_NEXUS_OIDC_ALLOW_HTTP",
        scope="OPERATOR",
        purpose="Permit a plain-HTTP issuer. Development only.",
        default="0",
        notes=("Never enable in a delivery: token validation would cross cleartext",),
    ),
    # --- Browser and gateway posture ---------------------------------------
    ConfigVar(
        name="EUROGAS_NEXUS_CORS_ORIGINS",
        scope="OPERATOR",
        purpose="Extra browser origins allowed for cookie-authenticated requests.",
        required_when=(
            "the web client is served from an origin the middleware cannot derive, "
            "including any development install using the Vite dev server"
        ),
        example="https://nexus.example.com",
        notes=(
            "The origin guard also accepts a same-origin request derived from the "
            "Host header plus X-Forwarded-Proto, so a production deployment that "
            "serves the client and the API from one host needs nothing here.",
            "A development install does: the Vite dev server runs on its own port "
            "(3000 by default) while the API listens on another, so the browser's "
            "Origin names the dev-server port and the derived value does not match. "
            "Without this value every cookie-authenticated mutation is refused with "
            "origin_not_allowed, and the browser console shows the refusal without "
            "naming its cause. Set it to the origin the browser loads, for example "
            "http://127.0.0.1:3000.",
        ),
    ),
    ConfigVar(
        name="FORWARDED_ALLOW_IPS",
        scope="OPERATOR",
        purpose="Proxy addresses whose X-Forwarded-* headers are trusted (read by uvicorn).",
        required_when="the API runs behind a reverse proxy that terminates TLS",
        example="172.16.0.0/12",
        external_reader="uvicorn",
        notes=(
            "uvicorn defaults to 127.0.0.1,::1, which excludes a sidecar proxy on a "
            "container network: without this the request scheme stays http and the "
            "session cookie is issued without the Secure attribute.",
        ),
    ),
    ConfigVar(
        name="EUROGAS_NEXUS_DEPLOYMENT_POSTURE",
        scope="OPERATOR",
        purpose="Deployment network posture: private_network_preview or security_accepted.",
        default="private_network_preview",
    ),
    ConfigVar(
        name="EUROGAS_NEXUS_SECURITY_ACCEPTANCE_EVIDENCE",
        scope="OPERATOR",
        purpose="Path to the operator-reviewed security-acceptance evidence file.",
        required_when="deployment posture is security_accepted",
    ),
    ConfigVar(
        name="EUROGAS_NEXUS_RESEARCH_ARTIFACT_ROOT",
        scope="OPERATOR",
        purpose="Filesystem root for materialized research dataset artifacts.",
        example="data/snapshots",
        notes=("Defaults to the git-ignored data/snapshots directory of the deployment checkout",),
    ),
    # --- Model and source behaviour ----------------------------------------
    ConfigVar(
        name="EUROGAS_NEXUS_LLM_EXTERNAL_PROVIDER_ENABLED",
        scope="OPERATOR",
        purpose="Permit calls to an external LLM provider.",
        default="true (forced false in trial and release)",
        notes=(
            "Trial and release force this off; the override is ignored there.",
            "Enabling it in development sends the request payload to the provider.",
        ),
    ),
    ConfigVar(
        name="EUROGAS_NEXUS_CONNECTOR_PLUGINS",
        scope="OPERATOR",
        purpose=(
            "Connector plugins an administrator has enabled: comma-separated entry-point "
            "names of installed eurogas_nexus.connectors plugins."
        ),
        default="",
        example="",
        notes=(
            "Empty: no plugin runs. Example: kpler_cargo,acme_curves",
            "An installed plugin that is not listed appears as available and never runs.",
            "Enabling a plugin grants no data scope, licence or certification.",
        ),
    ),
    ConfigVar(
        name="EUROGAS_NEXUS_ENABLE_SIMULATED_SOURCES",
        scope="OPERATOR",
        purpose="Permit simulated market price sources.",
        default="true (forced false in trial and release)",
        notes=("Simulated rows are labelled and are never provider acceptance",),
    ),
    ConfigVar(
        name="EUROGAS_NEXUS_DEMO_MARKS",
        scope="OPERATOR",
        purpose="Let positions, credit and mandates value against simulated demo prices.",
        default="false (forced false in trial and release)",
        notes=(
            "For sales demos and training on scripts/demo/seed_demo_desk.py data only.",
            "Every valued response then carries a warning that marks are demo prices.",
        ),
    ),
    # --- Development-only credential login ---------------------------------
    ConfigVar(
        name="EUROGAS_NEXUS_DEV_LOGIN_USERNAME",
        scope="OPERATOR",
        purpose="Development-only credential login username.",
        sensitivity="secret",
        profiles=("development",),
        notes=(
            "Mounted by the development and demo route profiles only; never set in trial or "
            "release, and never reuse a real user password.",
            "May list several principal names separated by commas; each still has to be an "
            "ACTIVE local identity.",
        ),
    ),
    ConfigVar(
        name="EUROGAS_NEXUS_DEV_LOGIN_PASSWORD",
        scope="OPERATOR",
        purpose="Development-only credential login password.",
        sensitivity="secret",
        profiles=("development",),
        notes=(
            "The demo profile requires at least 12 characters (the tester password of a "
            "hosted test/demo server).",
        ),
    ),
    # --- Local accounts (firms without company SSO) -------------------------
    ConfigVar(
        name="EUROGAS_NEXUS_LOCAL_ACCOUNTS",
        scope="OPERATOR",
        purpose=(
            "User-name-and-password accounts managed in Admin -> Users: auto, on or off."
        ),
        default="auto",
        example="auto",
        notes=(
            "auto (default): on only when no company SSO is configured, so a firm without "
            "SSO can run the product; off when SSO is configured.",
            "on keeps local accounts next to SSO (e.g. a break-glass administrator); off "
            "refuses local sign-in and creation.",
            "Passwords are stored as salted scrypt; first administrator: "
            "python -m eurogas_nexus.cli.accounts create --admin (docs/deployment).",
        ),
    ),
    # --- Hosted test/demo server (root Dockerfile) -------------------------
    ConfigVar(
        name="EUROGAS_NEXUS_WEB_CLIENT_DIR",
        scope="OPERATOR",
        purpose="Serve the built web client from the API process at this directory.",
        notes=(
            "Single-origin hosting for a one-container test/demo server; unset in a "
            "customer deployment, where the API serves no pages.",
            "/api is never answered by the client; other paths fall back to index.html.",
        ),
    ),
    ConfigVar(
        name="EUROGAS_NEXUS_DEMO_LIVE_SOURCES",
        scope="OPERATOR",
        purpose="Live public-source refresh on the hosted test/demo server: auto, on or off.",
        default="auto",
        profiles=("development",),
        notes=(
            "auto turns it on when a public-source key (GIE, EIA, ENTSO-E) is set. A "
            "background process catches up after a pause, then repeats; ENTSOG and GIE "
            "still need their certification record.",
        ),
    ),
    ConfigVar(
        name="EUROGAS_NEXUS_DEMO_EXCHANGE_FEED",
        scope="OPERATOR",
        purpose="The demo server's simulated intraday exchange feed: on or off.",
        default="false on the hosted demo (scripts/demo/start_public_demo.py); unset reads as on",
        example="false",
        profiles=("development",),
        notes=(
            "Demo image only (scripts/demo/exchange_feed.py --continuous). Every row is "
            "simulated; 48 hours are kept. With it off the roll-forward's daily prompt snapshot "
            "stands alone.",
            "on/true: the feed writes today's WD and DA quotes and the hourly roll-forward "
            "leaves them to it (seed_demo_desk.py).",
        ),
    ),
    ConfigVar(
        name="EUROGAS_NEXUS_DEMO_CATCH_UP_MAX_DAYS",
        scope="OPERATOR",
        purpose="Longest gap, in days, one catch-up round reads after a pause.",
        default="45",
        profiles=("development",),
    ),
    ConfigVar(
        name="EUROGAS_NEXUS_DEMO_REFRESH_HOURS",
        scope="OPERATOR",
        purpose="Hours between live public-source refresh rounds on the demo server.",
        default="6",
        profiles=("development",),
    ),
    ConfigVar(
        name="EUROGAS_NEXUS_DEFERRED_CAPABILITIES",
        scope="OPERATOR",
        purpose="Serve the deferred capabilities' routes (dataset builder, agents workspace); "
        "off by default.",
        default="off",
        notes=(
            "Design basis 2, I.3 and decision L4: the backends are kept, dormant, until a desk "
            "use is proven; read by api/route_registration.py.",
        ),
    ),
    ConfigVar(
        name="EUROGAS_NEXUS_DEMO_CATCH_UP_STATUS",
        scope="OPERATOR",
        purpose="Demo server: file where the live-data catch-up writes its progress.",
        default="/tmp/eurogas-nexus-catch-up.json",
        profiles=("development",),
        notes=(
            "Written by scripts/demo/start_public_demo.py and read by GET /api/sources to "
            "tell administrators how far the catch-up has got.",
        ),
    ),
    ConfigVar(
        name="EUROGAS_NEXUS_DEMO_RESET_TOKEN",
        scope="OPERATOR",
        purpose="Change this value to re-seed the demo desk and tester identities at next start.",
        profiles=("development",),
        notes=(
            "Read by scripts/demo/start_public_demo.py. The seed runs once on an empty "
            "store; later starts keep testers' changes unless this value differs from the "
            "one recorded at the last seed.",
        ),
    ),
    ConfigVar(
        name="EUROGAS_NEXUS_DEMO_TEST_ACCOUNTS",
        scope="OPERATOR",
        purpose=(
            "Demo server only: extra local test accounts, each with its own password, "
            "which may be shorter than the password policy."
        ),
        sensitivity="secret",
        profiles=("development",),
        notes=(
            "CSV name:password[:admin] or JSON [{username, password, as, allow_admin}]; "
            "e.g. test_trader:12345678,test_risk:12345678.",
            "Refused outside the demo profile: the API will not start with it set "
            "(customer runtime). An account with the ADMIN role must be marked :admin.",
            "Anyone who reads the password can sign in: use only on a demo server.",
        ),
    ),
    ConfigVar(
        name="EUROGAS_NEXUS_UAT_FIXTURE_ALLOWED",
        scope="TOOLING",
        purpose="Acknowledge that a UAT fixture seed may write to the runtime store.",
        sensitivity="internal",
        profiles=("development",),
        notes=("The fixture gate refuses to run in trial or release regardless",),
    ),
    # --- Worker and agent identities ---------------------------------------
    ConfigVar(
        name="EUROGAS_NEXUS_WORKER_PRINCIPAL",
        scope="OPERATOR",
        purpose="Persisted SERVICE principal the headless monitoring worker acts as.",
        required_when="the monitoring worker runs with provider enrichment",
    ),
    ConfigVar(
        name="EUROGAS_NEXUS_AGENT_PRINCIPAL",
        scope="TOOLING",
        purpose="Principal id used by the stdio MCP server.",
        default="service:mcp",
    ),
    ConfigVar(
        name="EUROGAS_NEXUS_AGENT_ROLE",
        scope="TOOLING",
        purpose="Role used by the stdio MCP server.",
        default="ANALYST",
    ),
    ConfigVar(
        name="EUROGAS_NEXUS_AGENT_DATA_SCOPES",
        scope="TOOLING",
        purpose="Comma-separated data scopes used by the stdio MCP server.",
    ),
    ConfigVar(
        name="EUROGAS_NEXUS_API_BASE_URL",
        scope="TOOLING",
        purpose="Backend base URL the stdio MCP server calls.",
        default="http://127.0.0.1:8000/api",
    ),
    # --- Public and licensed source access ---------------------------------
    ConfigVar(
        name="GIE_API_KEY",
        scope="OPERATOR",
        purpose="API key for GIE AGSI/ALSI storage and LNG transparency data.",
        sensitivity="secret",
        required_when="GIE storage or LNG ingestion is enabled",
    ),
    ConfigVar(
        name="GIE_API_KEY_FILE",
        scope="OPERATOR",
        purpose="Path to a file holding the GIE API key, read at ingest time.",
        sensitivity="internal",
        required_when=(
            "GIE ingestion is enabled and GIE_API_KEY or the encrypted credential "
            "store does not hold the key"
        ),
        example="",
        notes=(
            "Precedence: GIE_API_KEY, then GIE_API_KEY_FILE, then the encrypted "
            "provider credential store.",
            "Keep the key file outside the repository and readable only by the "
            "runtime account; the file content is never logged.",
        ),
    ),
    ConfigVar(
        name="EUROGAS_NEXUS_LLM_BASE_URL",
        scope="OPERATOR",
        purpose=(
            "OpenAI-compatible chat-completions base URL of the model this installation "
            "uses (DeepSeek, OpenAI, Azure OpenAI, Mistral, Qwen, or a self-hosted "
            "vLLM/Ollama)."
        ),
        default="https://api.deepseek.com",
        notes=(
            "HTTPS required; plain HTTP only for a model on a private network. External LLM "
            "calls stay off in trial/release unless EUROGAS_NEXUS_LLM_EXTERNAL_PROVIDER_ENABLED "
            "allows them.",
        ),
    ),
    ConfigVar(
        name="EUROGAS_NEXUS_LLM_MODEL",
        scope="OPERATOR",
        purpose=("Model name sent to the LLM endpoint."),
        default="deepseek-v4-flash",
        notes=(
            "HTTPS required; plain HTTP only for a model on a private network. External LLM "
            "calls stay off in trial/release unless EUROGAS_NEXUS_LLM_EXTERNAL_PROVIDER_ENABLED "
            "allows them.",
        ),
    ),
    ConfigVar(
        name="EUROGAS_NEXUS_LLM_PROVIDER_NAME",
        scope="OPERATOR",
        purpose=("Provider label recorded in audit events and shown with LLM answers."),
        default="DEEPSEEK",
        notes=(
            "HTTPS required; plain HTTP only for a model on a private network. External LLM "
            "calls stay off in trial/release unless EUROGAS_NEXUS_LLM_EXTERNAL_PROVIDER_ENABLED "
            "allows them.",
        ),
    ),
    ConfigVar(
        name="EUROGAS_NEXUS_LLM_API_KEY",
        scope="OPERATOR",
        purpose="API key for the configured model endpoint (DeepSeek or any OpenAI-compatible).",
        sensitivity="secret",
        required_when="An external model endpoint is enabled and no key is in the credential store",
        notes=(
            "Overrides the encrypted credential store unless an administrator disabled the "
            "provider. Setting it does not permit external calls: "
            "EUROGAS_NEXUS_LLM_EXTERNAL_PROVIDER_ENABLED still decides.",
        ),
    ),
    ConfigVar(
        name="DEEPSEEK_API_KEY",
        scope="OPERATOR",
        purpose="Accepted alias of EUROGAS_NEXUS_LLM_API_KEY for the DeepSeek provider.",
        sensitivity="secret",
        notes=("Prefer EUROGAS_NEXUS_LLM_API_KEY; when both are set the canonical name wins.",),
    ),
    ConfigVar(
        name="EIA_API_KEY",
        scope="OPERATOR",
        purpose="API key for the US EIA open-data API (Henry Hub daily spot price).",
        sensitivity="secret",
        required_when="Henry Hub ingestion (scripts/ops/ingest_eia.py) fetches from EIA",
        notes=(
            "Free on registration at eia.gov/opendata; EIA data is public domain. The key "
            "is sent as a query parameter and never logged.",
        ),
    ),
    ConfigVar(
        name="ENTSOE_SECURITY_TOKEN",
        scope="OPERATOR",
        purpose=(
            "Security token for the ENTSO-E Transparency Platform (day-ahead power prices, "
            "load, wind, solar and gas-fired generation)."
        ),
        sensitivity="secret",
        required_when="power ingestion (scripts/ops/ingest_power.py) fetches from ENTSO-E",
        notes=(
            "Free after registering on transparency.entsoe.eu and requesting API access; "
            "the token is sent as a query parameter and never logged.",
        ),
    ),
    # --- The firm's own bank (TAR-2): Societe Generale rate connector -------
    ConfigVar(
        name="EUROGAS_NEXUS_SOCGEN_API_CONFIG_FILE",
        scope="OPERATOR",
        purpose=(
            "Path to the JSON endpoint configuration of the firm's Societe Generale rate API "
            "(base URL, auth scheme, token URL, client id, paths, field mapping)."
        ),
        sensitivity="internal",
        required_when=(
            "the SOCGEN institution is configured with access api and the src-bank-socgen "
            "feed is to fetch"
        ),
        example="",
        notes=(
            "Unset: the connector makes no network call and reports not connected.",
            "Every value in it comes from the firm's agreement with the bank; it holds no "
            "secret (a secret key in it is refused). Keep it outside the repository.",
        ),
    ),
    ConfigVar(
        name="EUROGAS_NEXUS_SOCGEN_API_SECRET",
        scope="OPERATOR",
        purpose=(
            "The firm's own Societe Generale API secret: the OAuth client secret or the API "
            "key, as the endpoint configuration's auth scheme says."
        ),
        sensitivity="secret",
        required_when="the src-bank-socgen feed is to fetch and no key file or stored key is set",
        notes=(
            "Precedence: this variable, then EUROGAS_NEXUS_SOCGEN_API_SECRET_FILE, then the "
            "encrypted provider credential store (provider SOCGEN).",
        ),
    ),
    ConfigVar(
        name="EUROGAS_NEXUS_SOCGEN_API_SECRET_FILE",
        scope="OPERATOR",
        purpose="Path to a file holding the firm's Societe Generale API secret.",
        sensitivity="internal",
        example="",
        notes=(
            "Keep the file outside the repository and readable only by the runtime account; "
            "its content is never logged.",
        ),
    ),
    ConfigVar(
        name="EUROGAS_NEXUS_COST_SOURCE_URL",
        scope="TOOLING",
        purpose="Endpoint the cost-observation refresh reads.",
    ),
    ConfigVar(
        name="EUROGAS_NEXUS_COST_SOURCE_SYSTEM",
        scope="TOOLING",
        purpose="Source-system label applied by the cost-observation refresh.",
        default="TSO_TARIFFS",
    ),
    # --- Release and supply-chain tooling ----------------------------------
    ConfigVar(
        name="EUROGAS_NEXUS_RELEASE_BASE_URL",
        scope="TOOLING",
        purpose="Base URL the release smoke test calls.",
        default="http://127.0.0.1:8000/api",
    ),
    ConfigVar(
        name="EUROGAS_NEXUS_SIGNTOOL_PATH",
        scope="TOOLING",
        purpose="Path to signtool.exe for Windows Authenticode signing.",
        required_when="signed Windows artifacts are produced",
    ),
    ConfigVar(
        name="EUROGAS_NEXUS_GPG_SIGNING_KEY_ID",
        scope="TOOLING",
        purpose="GPG key id used to sign release artifacts.",
        required_when="GPG-signed release artifacts are produced",
    ),
    ConfigVar(
        name="WINDOWS_SIGNING_CERT_PATH",
        scope="TOOLING",
        purpose="Path to the Windows code-signing certificate.",
        sensitivity="secret",
        required_when="signed Windows artifacts are produced",
    ),
    ConfigVar(
        name="WINDOWS_SIGNING_PASSWORD",
        scope="TOOLING",
        purpose="Password for the Windows code-signing certificate.",
        sensitivity="secret",
        required_when="signed Windows artifacts are produced",
    ),
    ConfigVar(
        name="WINDOWS_SIGNING_TIMESTAMP_URL",
        scope="TOOLING",
        purpose="RFC 3161 timestamp authority used when signing.",
        default="http://timestamp.digicert.com",
    ),
    ConfigVar(
        name="EUROGAS_NEXUS_WINDOWS_CODE_SIGNING_ENABLED",
        scope="TOOLING",
        purpose="Optionally sign the Windows artifacts with a configured certificate.",
        default="0",
        notes=("Optional; signing is not a release requirement",),
    ),
    ConfigVar(
        name="EUROGAS_NEXUS_GPG_SIGNING_ENABLED",
        scope="TOOLING",
        purpose="Request GPG signing of the release artifacts.",
        default="0",
    ),
    # --- Deployment bundle identity ----------------------------------------
    ConfigVar(
        name="EUROGAS_NEXUS_API_IMAGE",
        scope="OPERATOR",
        purpose="Container image reference the deployment compose file runs.",
        required_when="deploying with deploy/runtime/compose.yaml",
        example="registry.example.com/eurogas-nexus-api@sha256:0000...",
        external_reader="compose",
        notes=(
            "Pin by digest rather than tag so a rollback names an immutable image",
            "The operator ZIP writes this into the bundle's environment file",
        ),
    ),
    ConfigVar(
        name="EUROGAS_G8_SELECTION_EVIDENCE",
        scope="TOOLING",
        purpose="Path the security-acceptance runner reports its evidence into.",
        sensitivity="internal",
        emitted_only=True,
        notes=(
            "Read by the runner snippet this product writes into an evidence file, "
            "not by the product's own process",
        ),
    ),
    # --- SDK and CLI client-side identity ----------------------------------
    ConfigVar(
        name="EUROGAS_NEXUS_API_TOKEN",
        scope="OPERATOR",
        purpose="Alias for EUROGAS_NEXUS_PUBLIC_API_TOKEN accepted by the SDK and CLI.",
        sensitivity="secret",
        aliases=("EUROGAS_NEXUS_PUBLIC_API_TOKEN",),
        notes=(
            "The SDK reads EUROGAS_NEXUS_PUBLIC_API_TOKEN first and falls back to "
            "this older client-side name, so an existing SDK environment keeps working",
        ),
    ),
    ConfigVar(
        name="EUROGAS_NEXUS_PRINCIPAL",
        scope="OPERATOR",
        purpose="Principal name the SDK/CLI attributes its requests to.",
        sensitivity="internal",
        notes=(
            "Sent as X-Eurogas-Principal. It is an attribution label, not a "
            "credential: the deployment token is what authenticates the caller",
        ),
    ),
    ConfigVar(
        name="EUROGAS_NEXUS_IDENTITY_BEARER",
        scope="OPERATOR",
        purpose="Identity key the SDK/CLI presents as X-Eurogas-Identity.",
        sensitivity="secret",
        notes=(
            "Prefer a per-caller identity key over the shared deployment token so "
            "role floors and data scopes are actually enforced",
        ),
    ),
    # --- UAT SDK acceptance example ----------------------------------------
    ConfigVar(
        name="EUROGAS_UAT_API_BASE_URL",
        scope="TOOLING",
        purpose="Explicit API origin the UAT SDK economics example calls.",
        sensitivity="public",
        required_when="running scripts/examples/lng_capacity_economics.py",
        example="http://127.0.0.1:8000",
        notes=(
            "No implicit default: the example refuses to run without an explicit origin.",
            "Must be an http(s) origin only, with no path, query, fragment or credentials.",
            "Loopback origins (127.0.0.1, localhost, ::1) need no further opt-in.",
        ),
    ),
    ConfigVar(
        name="EUROGAS_UAT_ALLOW_NON_LOOPBACK",
        scope="TOOLING",
        purpose="Opt in to an explicit non-loopback UAT API for the SDK economics example.",
        sensitivity="public",
        notes=(
            "Unset or empty keeps the example loopback-only; exactly '1' opts in.",
            "Any other value is refused.",
            "An opted-in non-loopback API origin must use HTTPS.",
        ),
    ),
    # --- Build metadata (stamped, not operator-set) ------------------------
    ConfigVar(
        name="EUROGAS_NEXUS_BUILD_GIT_SHA",
        scope="BUILD_METADATA",
        purpose="Commit SHA stamped into the build.",
    ),
    ConfigVar(
        name="EUROGAS_NEXUS_BUILD_GIT_REF",
        scope="BUILD_METADATA",
        purpose="Git ref stamped into the build.",
    ),
    ConfigVar(
        name="EUROGAS_NEXUS_BUILD_RUN_ID",
        scope="BUILD_METADATA",
        purpose="CI run identity stamped into the build.",
    ),
    ConfigVar(
        name="EUROGAS_NEXUS_BUILD_TIMESTAMP",
        scope="BUILD_METADATA",
        purpose="Build timestamp stamped into the build.",
    ),
    # --- Test-only ----------------------------------------------------------
    ConfigVar(
        name="EUROGAS_NEXUS_TEST_TMP_ROOT",
        scope="TEST_ONLY",
        purpose="Temporary root the test suite writes into.",
        default=".tmp_work",
    ),
    ConfigVar(
        name="EUROGAS_NEXUS_TEST_ANONYMOUS",
        scope="TEST_ONLY",
        purpose="Opt a test out of the suite's automatic deployment-token header.",
    ),
    ConfigVar(
        name="EUROGAS_NEXUS_ACK_INTEGRATION_TEST",
        scope="TEST_ONLY",
        purpose="Acknowledge the PostgreSQL acknowledgement integration test.",
    ),
    ConfigVar(
        name="EUROGAS_NEXUS_CONTRACT_REVISION_INTEGRATION_TEST",
        scope="TEST_ONLY",
        purpose="Acknowledge the contract-revision PostgreSQL integration test.",
    ),
    ConfigVar(
        name="EUROGAS_NEXUS_PAYMENT_TERMS_INTEGRATION_TEST",
        scope="TEST_ONLY",
        purpose="Acknowledge the payment-terms PostgreSQL integration test.",
    ),
)

CONFIG_VARS_BY_NAME: dict[str, ConfigVar] = {var.name: var for var in CONFIG_VARS}

OPERATOR_CONFIG_VARS: tuple[ConfigVar, ...] = tuple(
    var for var in CONFIG_VARS if var.scope == "OPERATOR"
)

SECRET_CONFIG_VARS: tuple[ConfigVar, ...] = tuple(
    var for var in CONFIG_VARS if var.sensitivity == "secret"
)

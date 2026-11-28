"""Declarative public-route permission registry (Gate 1 foundation).

Every public path must resolve to a declared permission — the registry test
fails CI on any path without a declaration, so "which route needs what" is a
machine-checkable contract. Enforcement today: the release profile verifies the public API token,
resolves an optional PostgreSQL identity key, and enforces the role floor
declared for each permission category. OPERATOR routes additionally require
the legacy principal header for non-identity-key callers.
"""

from __future__ import annotations

import re
from enum import StrEnum


class Permission(StrEnum):
    """Permission category of a public route."""

    PUBLIC = "public"  # no sensitive data (health); token still applies in release
    READ = "read"  # read-only governed data
    WRITE = "write"  # creates/modifies records
    GOVERNED = "governed"  # policy evaluation (entitlement/export/LLM) applies
    REVIEW = "review"  # reviewer-gated human review recording
    OPERATOR = "operator"  # explicit operator identity required (planned)
    ADMIN = "admin"  # identity/access administration requires ADMIN


class EnforcementStatus(StrEnum):
    """How a permission is enforced today."""

    API_TOKEN = "api_token"  # enforced now (release profile token + policy gates)
    PRINCIPAL_REQUIRED = "principal_required"  # declared; enforcement in next milestone


# (path pattern, permission). Longest matching pattern wins, so exact routes
# listed here override their prefix families regardless of order.
ROUTE_PERMISSIONS: tuple[tuple[str, Permission], ...] = (
    ("/api/functional-runs", Permission.GOVERNED),
    ("/api/functional-runs/", Permission.GOVERNED),
    ("/api/functional-models", Permission.GOVERNED),
    ("/api/functional-models/", Permission.GOVERNED),
    # --- health / bootstrap ---
    ("/api/health", Permission.PUBLIC),
    ("/api/health/live", Permission.PUBLIC),
    ("/api/health/ready", Permission.PUBLIC),
    ("/api/dev/health", Permission.PUBLIC),
    # Development-only credential login; the route profile gates mounting, and
    # the credential store gating happens inside the handler.
    ("/api/dev/auth/login", Permission.PUBLIC),
    ("/api/auth/status", Permission.PUBLIC),
    # Local accounts (firms without SSO): the sign-in and the forced password change after a
    # temporary password issue a credential, so they answer without one; the handler applies
    # the uniform refusal, per-account back-off and per-address throttle.
    ("/api/auth/login", Permission.PUBLIC),
    ("/api/auth/password-change", Permission.PUBLIC),
    # The code step of a sign-in with a second factor (H6): the mfa_token is the authority.
    ("/api/auth/mfa/verify", Permission.PUBLIC),
    ("/api/auth/oidc/login", Permission.PUBLIC),
    ("/api/auth/oidc/callback", Permission.PUBLIC),
    ("/api/auth/oidc/desktop/login", Permission.PUBLIC),
    ("/api/auth/oidc/desktop/token", Permission.PUBLIC),
    ("/api/auth/logout", Permission.READ),
    ("/api/me", Permission.READ),
    ("/api/me/groups", Permission.READ),
    # Personal API keys: the handler limits them to the caller's own keys and scopes.
    ("/api/me/api-keys", Permission.READ),
    ("/api/me/api-keys/{key_id}/revoke", Permission.READ),
    # A signed-in local-account user changes their own password (needs the current one).
    ("/api/me/password", Permission.READ),
    # A person's own second factor (H6): status, enrolment and confirmation.
    ("/api/me/mfa", Permission.READ),
    ("/api/me/mfa/enrol", Permission.READ),
    ("/api/me/mfa/confirm", Permission.READ),
    # A person's own presentation choices; they grant nothing (domain/settings).
    ("/api/me/preferences", Permission.READ),
    # A person's own read and dismissed marks on alerts; the shared alert status is untouched.
    ("/api/me/alert-state", Permission.READ),
    ("/api/settings/organisation", Permission.READ),
    # AI settings in force (provider, time limits, what may be sent): administration only.
    ("/api/settings/ai", Permission.ADMIN),
    ("/api/access/groups", Permission.ADMIN),
    ("/api/access/groups/{group_id}", Permission.ADMIN),
    ("/api/access/groups/{group_id}/members/{principal_id}", Permission.ADMIN),
    ("/api/access/users", Permission.ADMIN),
    ("/api/access/users/{principal_id}", Permission.ADMIN),
    ("/api/access/users/{principal_id}/reset-password", Permission.ADMIN),
    ("/api/access/users/{principal_id}/mfa/reset", Permission.ADMIN),
    ("/api/access/roles", Permission.ADMIN),
    ("/api/access/data-scopes", Permission.ADMIN),
    ("/api/access/market-data-licences", Permission.ADMIN),
    ("/api/access/market-data-licences/{licence_id}", Permission.ADMIN),
    ("/api/access/api-keys", Permission.ADMIN),
    ("/api/access/api-keys/{key_id}/revoke", Permission.ADMIN),
    ("/api/audit", Permission.ADMIN),
    # Security review H5: verify the audit hash chain, record a signed checkpoint of its head,
    # and prune under dual control (api/dual_control.py). Administration only.
    ("/api/audit/verify", Permission.ADMIN),
    ("/api/audit/checkpoint", Permission.ADMIN),
    ("/api/audit/prune", Permission.ADMIN),
    # Security review H7: security-relevant changes awaiting a second administrator.
    ("/api/access/privileged-changes", Permission.ADMIN),
    ("/api/access/privileged-changes/{change_id}/approve", Permission.ADMIN),
    ("/api/access/privileged-changes/{change_id}/reject", Permission.ADMIN),
    ("/api/access/privileged-changes/{change_id}/withdraw", Permission.ADMIN),
    ("/api/access/sso", Permission.ADMIN),
    # First-run setup: the welcome flow's pages and state; keys and approvals go through
    # their own routes.
    ("/api/setup", Permission.ADMIN),
    # --- credentials: reads are safe metadata; every write is operator-only ---
    ("/api/credentials/providers", Permission.READ),
    ("/api/credentials/{provider_id}", Permission.OPERATOR),
    ("/api/credentials/{provider_id}/connection-test", Permission.OPERATOR),
    ("/api/credentials/{provider_id}/local-validation", Permission.OPERATOR),
    ("/api/credentials/{provider_id}/rotate", Permission.OPERATOR),
    ("/api/credentials/{provider_id}/status", Permission.OPERATOR),
    # --- analysis / reports: policy-gated (entitlement, export, LLM) ---
    ("/api/analysis/query", Permission.GOVERNED),
    ("/api/reports/portfolio", Permission.GOVERNED),
    # Live provider analysis of one alert: it spends a provider credential and returns
    # model output composed from commercial evidence, so it is policy-gated (LLM) and
    # re-authorised per call against the caller's own analysis capability
    # (api/dependencies/ai_authority.py, finding C8).
    ("/api/monitoring/alerts/{alert_id}/analysis", Permission.GOVERNED),
    # Acknowledging an alert changes governed state and records who accepted it, so it
    # carries an explicit governed-write permission, declared before the READ
    # ``/api/monitoring/`` family: reads stay READ, the write is ANALYST-floor and remains
    # inside the commercial-data boundary.
    ("/api/monitoring/alerts/{alert_id}/acknowledge", Permission.GOVERNED),
    ("/api/analysis/ontology", Permission.READ),
    # "Why?" on one object: a read of evidence the caller may already see. The model is
    # used only after the route re-checks the caller's analysis capability (ai_authority).
    ("/api/analysis/explain", Permission.READ),
    # Morning brief / end-of-day draft: the same reads, assembled; nothing is sent.
    ("/api/analysis/brief", Permission.READ),
    # A question from the answer bar: the Today facts the caller may already see, the book
    # only with portfolio.read; the model only after the ai_authority re-check.
    ("/api/analysis/ask", Permission.READ),
    # The Today read (UX-05): prices, positions, limits, alerts, outages and fundamentals
    # the caller may already see, assembled once; nothing is written.
    ("/api/desk/today", Permission.READ),
    # My gas day checklist: a status recorded by hand for a step of the caller's own gas
    # day (portfolio.write held in the handler, audited); nothing is nominated or sent.
    ("/api/desk/gas-day/status", Permission.WRITE),
    # SCHED-1: the gas day's reconciliation of trades, confirmations and nominations, a read
    # of the caller's own books (portfolio.read held in the handler); nothing is sent.
    ("/api/desk/gas-day/{gas_day}/reconciliation", Permission.READ),
    # Deal capture: reads of the caller's own books (portfolio.read in the handler; the risk
    # pack also risk.limits.read). The end-of-day check reads an uploaded ETRM export and
    # stores nothing. Writes are declared per method below.
    ("/api/desk/deals", Permission.READ),
    ("/api/desk/deals/formats", Permission.READ),
    ("/api/desk/deals/history", Permission.READ),
    ("/api/desk/deals/etrm-sheet", Permission.READ),
    ("/api/desk/deals/pnl", Permission.READ),
    ("/api/desk/deals/pack", Permission.READ),
    ("/api/desk/deals/pack-schedule", Permission.READ),
    ("/api/desk/deals/eod-check", Permission.READ),
    ("/api/desk/deals/pack/send", Permission.WRITE),
    ("/api/desk/deals/import", Permission.WRITE),
    ("/api/desk/deals/manual", Permission.WRITE),
    ("/api/desk/deals/problems/{problem_id}/resolve", Permission.WRITE),
    ("/api/desk/deals/close", Permission.WRITE),
    # A person's physical-or-financial choice for a captured deal (portfolio.write in the
    # handler, audited, recorded as entered by hand).
    ("/api/desk/deals/position-kind", Permission.WRITE),
    # Market reports (application/reports): the catalogue is a declaration; reading a stored
    # report is a read of figures the reader is re-checked for (sources and books). Proposing
    # a plan may call the model, and generating one stores a record and may call the model,
    # so both are GOVERNED (ANALYST floor) like the other analysis that records evidence.
    ("/api/reports/catalogue", Permission.READ),
    ("/api/reports/plan", Permission.GOVERNED),
    ("/api/reports/market", Permission.READ),
    ("/api/reports/market/{report_id}", Permission.READ),
    ("/api/reports/market/{report_id}/html", Permission.READ),
    # Deleting or renaming stored reports: the generating principal or an administrator,
    # checked per report in the route and audited.
    ("/api/reports/market/bulk-delete", Permission.GOVERNED),
    # Scheduled reports: anyone may see the schedules; only an administrator keeps them.
    ("/api/reports/schedules", Permission.READ),
    ("/api/review/decisions", Permission.REVIEW),
    ("/api/ingestion-runs", Permission.READ),
    # --- read families ---
    ("/api/contracts/", Permission.READ),
    ("/api/cost-observations/", Permission.READ),
    ("/api/glossary", Permission.READ),
    ("/api/glossary/{term}", Permission.READ),
    ("/api/glossary/{term}/context", Permission.READ),
    ("/api/lng/", Permission.READ),
    # The public LNG terminal tariff register (CP-11): reads are public data; reviewing a
    # candidate figure is source operation (four eyes in the handler); recording an operator's
    # reuse permission is the firm's decision, ADMIN.
    ("/api/lng/terminal-tariffs", Permission.READ),
    ("/api/lng/terminal-tariffs/price", Permission.READ),
    ("/api/lng/terminal-tariffs/{tariff_id}/review", Permission.OPERATOR),
    ("/api/lng/terminal-tariffs/operators/{operator}", Permission.ADMIN),
    ("/api/lng/freight-routes", Permission.READ),
    ("/api/lng/freight-routes/{route_id}", Permission.GOVERNED),
    ("/api/lng/cargo-economics", Permission.READ),
    # A cargo in transit as one plan (ETA, slot, send-out, hub months, hedges): reads and a
    # what-if store nothing; recording the hedges that cover a cargo is a desk write
    # (PORTFOLIO_WRITE in the handler), governed like a freight route.
    ("/api/lng/cargoes/plans", Permission.READ),
    ("/api/lng/cargoes/{cargo_id}/plan", Permission.READ),
    ("/api/lng/cargoes/{cargo_id}/plan/what-if", Permission.READ),
    ("/api/lng/cargoes/{cargo_id}/hedges", Permission.GOVERNED),
    # LNG-3: the book re-optimised around a disruption: reads value it and store nothing;
    # choosing an option records the choice (PORTFOLIO_WRITE in the handler, audited).
    ("/api/lng/cargoes/{cargo_id}/disruption-options", Permission.READ),
    ("/api/lng/cargoes/{cargo_id}/disruption-options/{option_id}", Permission.READ),
    ("/api/lng/cargoes/{cargo_id}/disruption-options/{option_id}/choose", Permission.GOVERNED),
    ("/api/lng/disruption/frontier", Permission.READ),
    # LNG-4: the REMIT outages linked to a pipeline supply (a read), and whether they curtail
    # it (PORTFOLIO_WRITE in the handler, audited): a record for valuing options, nothing sent.
    ("/api/lng/pipeline-supplies/{supply_id}/outage-links", Permission.READ),
    ("/api/lng/pipeline-supplies/{supply_id}/outage-override", Permission.GOVERNED),
    ("/api/market/", Permission.READ),
    # DATA-1 import contracts: the catalogue is a declaration everyone may read; checking a
    # file looks up books and ERP counterparties and stores nothing (ANALYST floor).
    ("/api/imports/contracts", Permission.READ),
    ("/api/imports/{contract_id}/validate", Permission.GOVERNED),
    # NEWS-1: items from registered public sources and what they touch in the caller's book
    # (reads); the AI note is an LLM call under the news_note AI use (GOVERNED).
    ("/api/news", Permission.READ),
    ("/api/news/{item_id}", Permission.READ),
    ("/api/news/{item_id}/note", Permission.GOVERNED),
    # Comparable prices: forward FX and normalisation (a computation, nothing stored) are
    # market reads like the rest of the family.
    ("/api/market/fx-forward", Permission.READ),
    ("/api/market/normalise", Permission.READ),
    # The instrument catalogue (hub → product kind → tenor) is a market read too.
    ("/api/market/instruments", Permission.READ),
    ("/api/monitoring/", Permission.READ),
    ("/api/physical/", Permission.READ),
    ("/api/portfolio/", Permission.READ),
    ("/api/reference-network/", Permission.READ),
    ("/api/runtime/", Permission.READ),
    ("/api/runtime/dependencies", Permission.READ),
    ("/api/runtime/metrics", Permission.READ),
    ("/api/runtime/source-operations", Permission.READ),
    ("/api/sources", Permission.READ),
    ("/api/sources/{source_id}", Permission.READ),
    ("/api/sources/{source_id}/health", Permission.READ),
    ("/api/sources/{source_id}/runs", Permission.READ),
    ("/api/sources/{source_id}/run", Permission.OPERATOR),
    ("/api/sources/{source_id}/backfill", Permission.OPERATOR),
    ("/api/sources/{source_id}/retry", Permission.OPERATOR),
    ("/api/sources/{source_id}/enabled", Permission.OPERATOR),
    # A public source's approval is the firm's decision on the provider's terms: ADMIN.
    ("/api/sources/{source_id}/approve", Permission.ADMIN),
    ("/api/source-certifications", Permission.READ),
    ("/api/source-certifications/{source_id}/certify", Permission.OPERATOR),
    ("/api/storage/", Permission.READ),
    ("/api/fundamentals/storage", Permission.READ),
    ("/api/fundamentals/lng", Permission.READ),
    ("/api/fundamentals/flows", Permission.READ),
    ("/api/fundamentals/forward-balance", Permission.READ),
    ("/api/stream/", Permission.READ),
    ("/api/weather/", Permission.READ),
    ("/api/optimization/runs/{run_id}", Permission.READ),
    # The declared nomination-window masters are the desk's clock: which windows exist and when
    # they close. Running a nomination assessment stays GOVERNED (it composes market material and
    # produces a schedule), while reading the declaration that the assessment is measured against
    # keeps the READ floor - a trader must be able to see the deadline being traded against.
    ("/api/optimization/nomination-windows", Permission.READ),
    # What Planning starts from: the book's contracts (portfolio scope and portfolio.read apply
    # in the route), the declared windows and the storage masters. A read; nothing is submitted.
    ("/api/optimization/planning-inputs", Permission.GOVERNED),
    ("/api/route-cost/tso-tariffs", Permission.READ),
    # TAR-1: public tariff versions, their publishers and capacity windows (reference data).
    ("/api/tariffs", Permission.READ),
    ("/api/tariffs/publishers", Permission.READ),
    ("/api/capacity/notices", Permission.READ),
    # Package G: watched publications. The calendar and the source list are reference reads;
    # confirming a changed document (the dates held are kept) is an administrator's act.
    ("/api/publications/calendar", Permission.READ),
    ("/api/publications/sources", Permission.READ),
    ("/api/publications/sources/{publication_id}/confirm", Permission.ADMIN),
    ("/api/publications/consents", Permission.READ),
    ("/api/publications/consents/{publisher_id}/withdraw", Permission.ADMIN),
    ("/api/publications/consents/{publisher_id}/restore", Permission.ADMIN),
    # TAR-2: tariff years side by side, the firm's bookings (book-scoped), capacity cost
    # contracted before public, and the source-precedence reads (FX rate, order in force).
    ("/api/tariffs/years", Permission.READ),
    ("/api/capacity/bookings", Permission.READ),
    ("/api/capacity/cost", Permission.READ),
    ("/api/pricing/fx-rate", Permission.READ),
    ("/api/pricing/source-precedence", Permission.READ),
    # Reviewed public transmission tariffs: an operator records, a second one reviews.
    ("/api/route-cost/tariff-entries", Permission.OPERATOR),
    ("/api/route-cost/tariff-entries/{entry_id}/review", Permission.OPERATOR),
    ("/api/route-cost/tariff-entries/{entry_id}/withdraw", Permission.OPERATOR),
    ("/api/route-cost/route-candidates", Permission.READ),
    # GET lists + POST upserts contracts: policy-gated write surface.
    ("/api/route-cost/upstream-contracts", Permission.GOVERNED),
    # Captured economic revisions are the evidence of the same commercial
    # contract terms, so their reads keep the GOVERNED (ANALYST) floor and the
    # commercial boundary of the contract row they belong to. Reading them is
    # not a persona/work-mode decision: only the existing commercial read
    # authority applies, and a VIEWER keeps the role refusal.
    (
        "/api/route-cost/upstream-contracts/{contract_id}/revisions",
        Permission.GOVERNED,
    ),
    (
        "/api/route-cost/upstream-contracts/{contract_id}/revisions/{contract_revision_id}",
        Permission.GOVERNED,
    ),
    ("/api/route-cost/resource-pool/options", Permission.READ),
    # --- unified data platform (Architecture V2 Wave 4) ---
    # The data product catalogue is a governed *declaration*: it names products,
    # their time basis, availability state and per-principal entitlement
    # posture, and returns values only through each product's own surface. It
    # stays outside the commercial boundary for the same reason the capability
    # catalogue does - a caller must be able to see that a product exists and
    # that its own entitlement is limited, which is the point of the surface.
    ("/api/data-products", Permission.READ),
    # Recording an Analysis Snapshot is analysed decision evidence (GOVERNED,
    # ANALYST floor). Reading a descriptor is lineage/provenance metadata with no
    # commercial values in it, so it keeps the READ floor - the same treatment as
    # /api/ingestion-runs - and every value the snapshot points at stays behind
    # its own commercial endpoint.
    ("/api/analysis-snapshots", Permission.READ),
    ("/api/analysis-snapshots/{snapshot_id}", Permission.READ),
    # --- Architecture V2 Decision Cases ---
    # Reading a case is decision evidence (READ floor: any authenticated caller who
    # may read review evidence may read the container). Opening a case and
    # attaching evidence are analysis work (GOVERNED, ANALYST floor). Recording or
    # reopening a decision is reviewer-gated (REVIEW), matching the existing
    # /api/review/decisions rule and the decision.review capability.
    ("/api/decision-cases", Permission.READ),
    ("/api/decision-cases/{case_id}", Permission.READ),
    ("/api/decision-cases/{case_id}/evidence", Permission.GOVERNED),
    ("/api/decision-cases/{case_id}/decisions", Permission.REVIEW),
    ("/api/decision-cases/{case_id}/reopen", Permission.REVIEW),
    # The signed ERP hand-off is a reviewer's act on a decided case (security review H2):
    # REVIEW floor, and the handler requires the case's author or one of its deciders.
    ("/api/decision-cases/{case_id}/handoff", Permission.REVIEW),
    # --- Commercial design basis 2, CP-07: assumption sets, firm marks, snapshots ---
    # Reading a set, a firm mark or a valuation snapshot is a commercial read (portfolio
    # read, checked again in the route; book-owned sets and book rows follow book scope).
    # Writing a draft version or a mark is analysis work (GOVERNED, ANALYST floor, and the
    # portfolio-assumption write permission in the route); approving a version is the risk
    # function's (REVIEW floor, the REVIEWER role held itself, four eyes). All audited.
    ("/api/assumption-sets", Permission.READ),
    ("/api/assumption-sets/{set_id}", Permission.READ),
    ("/api/assumption-sets/{set_id}/versions", Permission.GOVERNED),
    ("/api/assumption-sets/{set_id}/versions/{version}/approve", Permission.REVIEW),
    ("/api/market/firm-marks", Permission.READ),
    ("/api/market/valuation-snapshots/{snapshot_id}", Permission.READ),
    # --- Commercial design basis 2, CP-08: opportunities ---
    # Reading is a commercial read (portfolio read in the route; book scope and source
    # entitlement per row). A person's follow or dismissal is their own (READ). Running an
    # evaluation stores firm-wide records (GOVERNED). Opening a case uses the case
    # permission (GOVERNED, as POST /api/decision-cases). Thresholds are the risk function's
    # (REVIEW floor, REVIEWER held itself in the route). Statistics need review read.
    ("/api/opportunities", Permission.READ),
    # CP-24 role-aware discovery: findings built from reads that run under the caller.
    ("/api/discoveries", Permission.READ),
    ("/api/opportunities/evaluations", Permission.READ),
    ("/api/opportunities/settings", Permission.READ),
    ("/api/opportunities/statistics", Permission.READ),
    ("/api/opportunities/{opportunity_id}", Permission.READ),
    ("/api/opportunities/{opportunity_id}/state", Permission.READ),
    ("/api/opportunities/{opportunity_id}/case", Permission.GOVERNED),
    # --- Architecture V2 application projections ---
    # Projections are read models over the same material as the endpoints they
    # compose, so their floors match: market, portfolio and review reads stay at
    # the READ floor, while scenario/economics content keeps the GOVERNED
    # (ANALYST) floor its underlying route already declares - a projection must
    # never widen what a principal can see. They also sit inside the commercial
    # boundary (COMMERCIAL_DATA_PREFIXES).
    ("/api/projections/market-context", Permission.READ),
    ("/api/projections/portfolio-snapshot", Permission.READ),
    ("/api/projections/review-context", Permission.READ),
    ("/api/projections/scenario-context", Permission.GOVERNED),
    # --- Architecture V2 unified jobs ---
    # Job status is operational telemetry: any authenticated caller may read what
    # their deployment is running. Cancelling a job stops work, so it keeps the
    # GOVERNED (ANALYST) floor.
    ("/api/jobs", Permission.READ),
    ("/api/jobs/{job_id}", Permission.READ),
    ("/api/jobs/{job_id}/cancel", Permission.GOVERNED),
    # --- agent-native capability layer (CR-15) ---
    ("/api/capabilities", Permission.READ),
    ("/api/capabilities/search", Permission.READ),
    ("/api/capabilities/{capability_id}", Permission.READ),
    ("/api/capabilities/{capability_id}/invoke", Permission.GOVERNED),
    # --- internal operator profile (mounted only when ``include_internal``) ---
    # Owner decision D1 installs the permission gate in every profile, which is the first time
    # these paths were ever checked: the gate that reads this table simply was not installed in
    # ``internal`` before, so twelve mounted paths had no declared permission and would have
    # answered 500 ``permission_not_declared`` the moment it was. Each entry mirrors the floor the
    # route itself enforces (``validate_internal_operator_headers``: an internal token **and** an
    # explicit operator principal) rather than inventing a second, different one; the internal
    # token stays the stronger control and is still validated inside the handler, so declaring
    # OPERATOR here does not widen who can reach them. The health probe is a probe.
    ("/api/internal/health", Permission.PUBLIC),
    ("/api/internal/identities", Permission.OPERATOR),
    ("/api/internal/identities/{principal_id}/keys", Permission.OPERATOR),
    ("/api/internal/identities/{principal_id}/keys/{key_id}/rotate", Permission.OPERATOR),
    ("/api/internal/identities/{principal_id}/keys/{key_id}/revoke", Permission.OPERATOR),
    ("/api/internal/identities/{principal_id}/disable", Permission.OPERATOR),
    ("/api/internal/audit/events", Permission.OPERATOR),
    ("/api/internal/audit/prune", Permission.OPERATOR),
    ("/api/internal/portfolio/import-observations", Permission.OPERATOR),
    ("/api/internal/sources/certification", Permission.OPERATOR),
    # A licensed feed adapter (or the demo exchange simulator) delivering quotes and trade
    # prints: a data-operations act (source.run is held in the handler as well).
    ("/api/market/ticks", Permission.OPERATOR),
    # Anyone signed in may report a problem and see their own reports; the IT desk works them.
    ("/api/support/reports", Permission.READ),
    ("/api/support/reports/{report_id}", Permission.OPERATOR),
    # Notification channels hold recipients' addresses: administrators only.
    ("/api/settings/notification-channels", Permission.ADMIN),
    ("/api/settings/notification-channels/{channel_id}", Permission.ADMIN),
    ("/api/settings/notification-channels/{channel_id}/test", Permission.ADMIN),
    # --- research-data catalog is read-only; build/export are governed ---
    ("/api/research/capabilities", Permission.READ),
    ("/api/research/features", Permission.READ),
    ("/api/research/features/{feature_id}", Permission.READ),
    ("/api/research/targets", Permission.READ),
    ("/api/research/targets/{target_id}", Permission.READ),
    ("/api/research/datasets", Permission.READ),
    ("/api/research/datasets/{dataset_snapshot_id}", Permission.READ),
    ("/api/research/datasets/{dataset_snapshot_id}/quality", Permission.READ),
    ("/api/research/datasets/validate", Permission.GOVERNED),
    ("/api/research/datasets/{dataset_snapshot_id}/export", Permission.GOVERNED),
    # --- compute / persistence families: policy-gated decision support ---
    ("/api/optimization/", Permission.GOVERNED),
    ("/api/research/", Permission.GOVERNED),
    ("/api/route-cost/", Permission.GOVERNED),
)

# A small number of paths expose both read and governed methods. Keep the
# legacy path registry intact for compatibility, and resolve these overrides
# only when the caller supplies an HTTP method.
METHOD_ROUTE_PERMISSIONS: tuple[tuple[str, str, Permission], ...] = (
    ("PATCH", "/api/functional-models/{model_id}", Permission.REVIEW),
    ("POST", "/api/market/nwe-balance", Permission.GOVERNED),
    ("POST", "/api/research/datasets", Permission.GOVERNED),
    ("POST", "/api/analysis-snapshots", Permission.GOVERNED),
    ("POST", "/api/decision-cases", Permission.GOVERNED),
    ("POST", "/api/reports/market", Permission.GOVERNED),
    ("DELETE", "/api/reports/market/{report_id}", Permission.GOVERNED),
    ("PATCH", "/api/reports/market/{report_id}", Permission.GOVERNED),
    ("PUT", "/api/reports/schedules", Permission.ADMIN),
    ("PUT", "/api/settings/organisation", Permission.ADMIN),
    ("POST", "/api/assumption-sets", Permission.GOVERNED),
    ("POST", "/api/desk/gas-day/status", Permission.WRITE),
    # Deal capture writes record the desk's own deals and the day's close (portfolio.write
    # held in the handler, audited); nothing is ordered, nominated or booked (rule 8).
    ("POST", "/api/desk/deals/import", Permission.WRITE),
    ("POST", "/api/desk/deals/manual", Permission.WRITE),
    ("POST", "/api/desk/deals/problems/{problem_id}/resolve", Permission.WRITE),
    ("POST", "/api/desk/deals/close", Permission.WRITE),
    ("POST", "/api/desk/deals/pack/send", Permission.WRITE),
    ("PUT", "/api/desk/deals/pack-schedule", Permission.WRITE),
    ("POST", "/api/desk/deals/eod-check", Permission.READ),
    ("PUT", "/api/market/firm-marks", Permission.GOVERNED),
    ("POST", "/api/opportunities/evaluations", Permission.GOVERNED),
    ("PUT", "/api/opportunities/settings", Permission.REVIEW),
    # Book structure and assignment is middle-office configuration, not a market read.
    ("PUT", "/api/portfolio/books/{book_id}", Permission.OPERATOR),
    # Approved limits are the risk function's (reviewer) maintenance, audited.
    ("PUT", "/api/portfolio/credit-lines/{counterparty_id}", Permission.REVIEW),
    ("GET", "/api/portfolio/credit-lines/{counterparty_id}", Permission.REVIEW),
    ("PUT", "/api/portfolio/trader-mandates/{mandate_id}", Permission.REVIEW),
    # Terminal landing costs are LNG desk reference data (analyst, audited).
    ("PUT", "/api/portfolio/lng-terminal-terms/{terminal_id}", Permission.GOVERNED),
    # P-17 maker-checker: deciding a proposal needs at least the risk function's floor; the
    # handler checks the authority for the kind of change and that the approver is not the
    # proposer.
    ("POST", "/api/portfolio/change-requests/{change_id}/approve", Permission.REVIEW),
    ("POST", "/api/portfolio/change-requests/{change_id}/reject", Permission.REVIEW),
    ("POST", "/api/portfolio/change-requests/{change_id}/withdraw", Permission.REVIEW),
    # Reading a contract PDF into a draft (nothing stored); the save stays the governed write.
    ("POST", "/api/contracts/intake", Permission.GOVERNED),
    # The tariff publication register is reference data everyone reads; the desk maintains it.
    ("GET", "/api/route-cost/tariff-publications", Permission.READ),
    ("GET", "/api/route-cost/tariff-entries", Permission.READ),
    ("POST", "/api/publications/sources/{publication_id}/confirm", Permission.ADMIN),
    ("POST", "/api/publications/consents/{publisher_id}/withdraw", Permission.ADMIN),
    ("POST", "/api/publications/consents/{publisher_id}/restore", Permission.ADMIN),
    # Security review M2: every non-GET route is declared with its method. These were reached
    # through their path family; each keeps the floor it had, now stated explicitly.
    ("POST", "/api/functional-models/{model_id}/evaluate", Permission.GOVERNED),
    ("POST", "/api/functional-models/{model_id}/predict", Permission.GOVERNED),
    ("POST", "/api/functional-runs/reconcile", Permission.GOVERNED),
    ("POST", "/api/functional-runs/{run_id}/compare", Permission.GOVERNED),
    ("POST", "/api/functional-runs/{run_id}/replay", Permission.GOVERNED),
    ("POST", "/api/optimization/capacity", Permission.GOVERNED),
    ("POST", "/api/optimization/contracts", Permission.GOVERNED),
    ("POST", "/api/optimization/nomination-window", Permission.GOVERNED),
    ("POST", "/api/optimization/portfolio-network", Permission.GOVERNED),
    ("POST", "/api/optimization/resource-pool", Permission.GOVERNED),
    ("POST", "/api/optimization/route", Permission.GOVERNED),
    ("POST", "/api/optimization/storage-dispatch", Permission.GOVERNED),
    ("POST", "/api/research/allocation", Permission.GOVERNED),
    ("POST", "/api/research/backtest", Permission.GOVERNED),
    ("POST", "/api/research/capacity-billing", Permission.GOVERNED),
    ("POST", "/api/research/cash-valuation", Permission.GOVERNED),
    ("POST", "/api/research/feasibility", Permission.GOVERNED),
    ("POST", "/api/research/lng-economics-only", Permission.GOVERNED),
    ("POST", "/api/research/monitoring", Permission.GOVERNED),
    ("POST", "/api/research/netback", Permission.GOVERNED),
    ("POST", "/api/research/nowcast", Permission.GOVERNED),
    ("POST", "/api/research/route-cost", Permission.GOVERNED),
    ("POST", "/api/research/shadow-run", Permission.GOVERNED),
    ("POST", "/api/research/spread-analysis", Permission.GOVERNED),
    ("POST", "/api/research/spreads/evaluate", Permission.GOVERNED),
    ("POST", "/api/research/spreads/interpret", Permission.GOVERNED),
    ("POST", "/api/route-cost/calculate", Permission.GOVERNED),
    ("POST", "/api/route-cost/lng-regas/assess", Permission.GOVERNED),
    ("POST", "/api/route-cost/recommend", Permission.GOVERNED),
    ("POST", "/api/route-cost/resource-pool/optimize", Permission.GOVERNED),
    ("POST", "/api/route-cost/upstream-contracts/{contract_id}/reinstate", Permission.GOVERNED),
    ("POST", "/api/route-cost/upstream-contracts/{contract_id}/retire", Permission.GOVERNED),
    ("PUT", "/api/route-cost/tariff-publications/{publication_id}", Permission.GOVERNED),
    # What-if computations that store nothing (the handler re-checks portfolio.read).
    ("POST", "/api/portfolio/desk-replay", Permission.READ),
    ("POST", "/api/portfolio/lng-cargo-bid", Permission.READ),
    ("POST", "/api/portfolio/sell-down-plan", Permission.READ),
    ("POST", "/api/weather/degree-days", Permission.READ),
    # A deal's hedge band is the risk function's (the handler holds REVIEWER itself).
    ("PUT", "/api/portfolio/hedge-approvals/{contract_id}", Permission.REVIEW),
)

PERMISSION_ENFORCEMENT: dict[Permission, EnforcementStatus] = {
    Permission.PUBLIC: EnforcementStatus.API_TOKEN,
    Permission.READ: EnforcementStatus.API_TOKEN,
    Permission.GOVERNED: EnforcementStatus.API_TOKEN,
    Permission.REVIEW: EnforcementStatus.API_TOKEN,
    Permission.OPERATOR: EnforcementStatus.PRINCIPAL_REQUIRED,
    Permission.ADMIN: EnforcementStatus.PRINCIPAL_REQUIRED,
}

# R32 role floor per permission category. The legacy public-token service
# principal has OPERATOR and remains compatible; DB-backed identities are
# checked against these floors by the route-permission dependency.
ROLE_REQUIREMENTS: dict[Permission, str] = {
    Permission.PUBLIC: "VIEWER",
    Permission.READ: "VIEWER",
    # Records desk status (the gas-day nomination and terminal steps). The gate admits a
    # scheduler; the handler requires ``gas_day.record`` (SCHEDULER, ANALYST). Without this
    # entry every such route answered 500 (persona review B2).
    Permission.WRITE: "SCHEDULER",
    Permission.GOVERNED: "ANALYST",
    Permission.REVIEW: "REVIEWER",
    Permission.OPERATOR: "OPERATOR",
    Permission.ADMIN: "ADMIN",
}

# Architecture V2 commercial-data boundary (06_IDENTITY_ACCESS_CONTROL_PLANE.md
# section 7): platform administration is not a commercial super-user. These path
# families serve prices, contract terms, positions, PnL, strategy parameters,
# decision evidence or licensed research datasets, so they require a commercial
# capability - which a platform-admin-only identity does not hold.
#
# Deliberately excluded (platform/context/system state a platform administrator
# needs): /api/health, /api/me, /api/auth, /api/dev, /api/access, /api/audit,
# /api/credentials, /api/sources, /api/source-certifications, /api/ingestion-runs,
# /api/runtime, /api/glossary, /api/reference-network, /api/physical,
# /api/storage, /api/lng, /api/weather, /api/capabilities (the registered
# capability *catalogue* is control-plane metadata; invoking a capability over
# commercial evidence stays commercial through /api/agent/ and the governed
# invoke path).
COMMERCIAL_DATA_PREFIXES: tuple[str, ...] = (
    "/api/desk/",
    "/api/functional-runs/",
    "/api/functional-models/",
    "/api/market/",
    "/api/imports/",
    "/api/news/",
    "/api/monitoring/",
    "/api/projections/",
    "/api/stream/",
    "/api/cost-observations/",
    "/api/portfolio/",
    "/api/contracts/",
    "/api/optimization/",
    "/api/route-cost/",
    "/api/analysis/",
    "/api/reports/",
    "/api/review/",
    "/api/research/",
    "/api/assumption-sets/",
    "/api/opportunities/",
    "/api/discoveries/",
    # A decision case carries the book, hub, gas day and objective of a commercial decision:
    # platform administration alone must not read it (found reading the demo as admin).
    "/api/decision-cases/",
    # Analysis snapshots carry the portfolio version and context of a decision, and the data
    # product catalogue counts and dates the firm's own rows (security review H2).
    "/api/analysis-snapshots/",
    "/api/data-products/",
    "/api/capacity/bookings/",
    "/api/capacity/cost/",
    "/api/lng/cargoes/",
    "/api/lng/cargo-economics/",
    "/api/lng/disruption/",
    "/api/lng/pipeline-supplies/",
    "/api/lng/freight-routes/",
)


# Security review H2: the boundary was a deny-list, so a new path family (analysis snapshots,
# data products, LNG cargoes, capacity bookings) was readable by platform administration
# until someone remembered to list it. Every ``/api/`` path is now commercial unless it is
# platform, context or public-reference state listed here; the deny-list above stays as the
# explicit statement for the families that matter most, and wins over this list.
PLATFORM_PATH_PREFIXES: tuple[str, ...] = (
    "/api/health",
    "/api/me",
    "/api/auth/",
    "/api/dev/",
    "/api/access/",
    "/api/audit",
    "/api/credentials",
    "/api/sources",
    "/api/source-certifications",
    "/api/ingestion-runs",
    "/api/runtime",
    "/api/glossary",
    "/api/reference-network",
    "/api/physical/",
    "/api/storage/",
    "/api/weather/",
    "/api/capabilities",
    "/api/settings/",
    "/api/setup",
    "/api/support/",
    "/api/jobs",
    "/api/fundamentals/",
    "/api/tariffs",
    "/api/pricing/",
    "/api/internal/",
    # Public LNG reference: terminals, their published tariffs and public observations.
    "/api/lng/terminals",
    "/api/lng/terminal-tariffs",
    "/api/lng/observations",
    # Public capacity auction notices; the firm's bookings and costs are commercial.
    "/api/capacity/notices",
    # Package G: public publications (exchange holidays, auction calendars) and their state.
    "/api/publications/",
)

#: Paths inside a platform family that read the firm's books (a glossary term's context
#: names the caller's own positions).
COMMERCIAL_PATH_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"^/api/glossary/[^/]+/context$"),
)


def _under(path: str, prefix: str) -> bool:
    bare = prefix.rstrip("/")
    return path == bare or path.startswith(bare + "/") or (
        not prefix.endswith("/") and path.startswith(prefix)
    )


def matches_commercial_prefix(path: str) -> bool:
    """Whether ``path`` is in one of the explicitly declared commercial families."""

    return any(
        path == prefix.rstrip("/") or path.startswith(prefix) for prefix in COMMERCIAL_DATA_PREFIXES
    )


def serves_commercial_data(path: str) -> bool:
    """Whether a public path serves commercial data (V2 platform-admin boundary).

    Default commercial: a path is outside the boundary only when it is listed in
    :data:`PLATFORM_PATH_PREFIXES` and matches no commercial prefix or pattern.
    """

    if matches_commercial_prefix(path):
        return True
    if any(pattern.match(path) for pattern in COMMERCIAL_PATH_PATTERNS):
        return True
    if not path.startswith("/api/"):
        return False
    return not any(_under(path, prefix) for prefix in PLATFORM_PATH_PREFIXES)


UNSAFE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})


def permission_for_path(path: str, method: str | None = None) -> Permission:
    """Resolve the permission for a public path.

    Matching ranks: literal routes (0) beat templated routes (1) beat prefix
    families (2); within a rank the longest pattern wins. So
    ``/api/credentials/providers`` stays READ even though
    ``/api/credentials/{provider_id}`` is OPERATOR, and
    ``/api/optimization/runs/{run_id}`` beats the ``/api/optimization/``
    family.
    """

    normalized_method = (method or "").upper()
    best: Permission | None = None
    best_key: tuple[int, int] | None = None
    routes = (
        (pattern, permission)
        for route_method, pattern, permission in METHOD_ROUTE_PERMISSIONS
        if route_method == normalized_method
    )
    for pattern, permission in (*routes, *ROUTE_PERMISSIONS):
        rank = _pattern_rank(pattern)
        if rank == 2:
            ok = path.startswith(pattern)
        else:
            ok = _pattern_regex(pattern).match(path) is not None
        if not ok:
            continue
        key = (rank, -len(pattern))
        if best_key is None or key < best_key:
            best_key = key
            best = permission
    if best is None:
        raise KeyError(f"No permission declared for public path {path!r}")
    if normalized_method in UNSAFE_METHODS and best_key is not None and best_key[0] == 2:
        # Security review M2: a write is never authorised by a path family's (read) floor.
        # A non-GET route must be declared itself; otherwise it is refused (deny by default).
        raise KeyError(
            f"No permission declared for {normalized_method} {path!r} (only its path family)"
        )
    return best


def _pattern_rank(pattern: str) -> int:
    """0 = literal route, 1 = templated route, 2 = prefix family."""

    if pattern.endswith("/"):
        return 2
    if "{" in pattern:
        return 1
    return 0


def _pattern_regex(pattern: str) -> re.Pattern[str]:
    parts = re.split(r"(\{[^}]+\})", pattern)
    expression = "".join("[^/]+" if part.startswith("{") else re.escape(part) for part in parts)
    return re.compile(f"^{expression}$")


def role_for_permission(permission: Permission) -> str:
    """Return the minimum role required by a permission category."""

    return ROLE_REQUIREMENTS[permission]


def enforcement_status(permission: Permission) -> EnforcementStatus:
    """Return the enforcement level declared for a permission.

    返回权限声明的强制级别（identity/audit/none），供依赖注入与
    安全测试按级别施加校验。

    Args:
        permission: The permission kind.

    Returns:
        The declared EnforcementStatus.
    """

    return PERMISSION_ENFORCEMENT[permission]

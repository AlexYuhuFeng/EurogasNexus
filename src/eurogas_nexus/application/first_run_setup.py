"""First-run setup: the welcome flow's steps, what each source needs, and the flow's state.

The first administrator of a fresh installation is walked through one page per category of
data (open market data, prices and trading screens, LNG and shipping, weather, FX and rates,
the firm's own book, AI, people). Each page lists the registered sources of that category
with how this product connects to it today - read from the connector manifests, the
approval classes and the import tools that exist - never an integration that does not.

Every registered source must belong to exactly one step or be excluded with a reason
(``SOURCE_STEPS``); ``tests/unit/test_first_run_setup.py`` fails when a new connector manifest
has no step, so a new source appears in the flow instead of silently missing from it.

The flow's state is one row per installation (``installation_setup``): not started, in
progress, completed or dismissed, and who configured it (an administrator, the demo profile,
or the environment for a headless install). It never holds a key: keys go through the one
credential mechanism (``PUT /api/credentials/{provider}``, encrypted with
``EUROGAS_NEXUS_SECRET_KEY``), and approvals through ``POST /api/sources/{id}/approve``.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

#: The pages, in order. ``welcome`` and ``summary`` list no source.
STEPS: tuple[str, ...] = (
    "welcome",
    "open_data",
    "prices",
    "lng_shipping",
    "weather",
    "fx_rates",
    "book",
    "ai",
    "people",
    "summary",
)

#: Registered source -> the step that offers it; ``None`` excludes it (reason below).
SOURCE_STEPS: dict[str, str | None] = {
    # Open market data: no licence; some need an approval of the provider's terms or a key.
    "src-entsog": "open_data",
    "src-gie": "open_data",
    "src-remit-umm": "open_data",
    "src-entsog-umm": "open_data",
    "src-entsoe": "open_data",
    "src-elexon": "open_data",
    "src-national-gas-supply": "open_data",
    "src-national-gas-demand": "open_data",
    "src-eia": "open_data",
    "src-national-gas-nts": "open_data",
    "src-bbl": "open_data",
    "src-iuk": "open_data",
    "src-gts": "open_data",
    "src-natran": "open_data",
    "src-german-tso": "open_data",
    "src-fluxys-belgium": "open_data",
    "src-cnmc-enagas": "open_data",
    # Prices and trading screens: the firm's own licence and entitlement.
    "src-trayport": "prices",
    "src-ice-ocm": "prices",
    "src-ice-endex": "prices",
    "src-eex": "prices",
    "src-cme": "prices",
    "src-ngx": "prices",
    "src-argus": "prices",
    "src-platts": "prices",
    "src-icis": "prices",
    # LNG and shipping: vessel tracking, and the public terminal tariff register (CP-11).
    "src-kpler": "lng_shipping",
    "src-lng-terminal-tariffs": "lng_shipping",
    # Weather.
    "src-ecmwf-open-data": "weather",
    "src-weather": "weather",
    # FX and rates: ECB reference rates by default, licensed fixes by import.
    "src-ecb": "fx_rates",
    "src-ecb-estr": "fx_rates",
    "src-boe": "fx_rates",
    "src-nyfed": "fx_rates",
    "src-wmr": "fx_rates",
    "src-bfix": "fx_rates",
    "src-bank-rates": "fx_rates",  # TAR-2: the firm's own bank (file import)
    "src-bank-socgen": "fx_rates",  # TAR-2: Societe Generale over its API (off by default)
    # AI.
    "src-deepseek": "ai",
    # Simulated demo price sources: never part of a customer's set-up.
    "src-eex-sim": None,
    # The demo profile's simulated exchange feed: started by the demo, nothing to set up.
    "src-demo-exchange-feed": None,
    "src-ice-ocm-sim": None,
    "src-trayport-sim": None,
    "src-icis-sim": None,
    "src-ice-endex-sim": None,
}

#: Why a source is left out of the flow.
EXCLUDED_REASONS: dict[str, str] = {
    source_id: "simulated demo source, never part of a customer's set-up"
    for source_id, step in SOURCE_STEPS.items()
    if step is None
}

#: Where a firm registers for its own key (docs/legal/DATA_SOURCE_TERMS.md).
KEY_REGISTRATION_URLS: dict[str, str] = {
    "GIE": "https://agsi.gie.eu/account",
    "EIA": "https://www.eia.gov/opendata/register.php",
    "ENTSOE": "https://transparency.entsoe.eu/",
}

#: Steps that list product capabilities rather than registered sources.
STATIC_ITEMS: dict[str, tuple[dict[str, str], ...]] = {
    "book": (
        {"item_id": "etrm-trades", "connection": "import",
         "tool": "scripts/ops/import_etrm_trades.py"},
        {"item_id": "contracts", "connection": "import", "tool": "Contracts → Intake"},
        {"item_id": "lng-cargoes", "connection": "import",
         "tool": "scripts/ops/import_lng_positions.py"},
        {"item_id": "sdk-api-keys", "connection": "api_key", "tool": "Admin → Access → API keys"},
    ),
    "people": (
        {"item_id": "users", "connection": "admin", "tool": "Admin → Access → Users"},
    ),
}

#: Display order of connections within a page.
CONNECTION_ORDER: tuple[str, ...] = (
    "public_tariffs",
    "approval",
    "approval_and_key",
    "key",
    "model",
    "licensed_key",
    "licensed_import",
    "licensed_none",
    "open",
    "register",
    "template",
)

SETUP_ID = "installation"
STATUSES = ("not_started", "in_progress", "completed", "dismissed")
CONFIGURED_BY = ("admin", "demo_profile", "environment")


class SetupError(ValueError):
    """A refused state change (unknown status or step)."""


def _import_tools(system: str) -> list[str]:
    """The import commands that exist for a licensed source (derived, not hand-written)."""

    from eurogas_nexus.ingestion.commodity_settlements import SETTLEMENT_SOURCES
    from eurogas_nexus.ingestion.licensed_quote_import import LICENSED_QUOTE_SOURCES
    from eurogas_nexus.ingestion.option_settlements import OPTION_SETTLEMENT_SOURCES

    tools: list[str] = []
    if system in LICENSED_QUOTE_SOURCES:
        tools.append(f"scripts/ops/import_market_quotes.py --source {system}")
    if system in SETTLEMENT_SOURCES:
        tools.append(f"scripts/ops/import_settlements.py --source {system}")
    if system in OPTION_SETTLEMENT_SOURCES:
        tools.append(f"scripts/ops/import_option_settlements.py --source {system}")
    if system == "Kpler":
        tools.append("scripts/ops/import_lng_positions.py")
    if system in {"WMR", "BFIX"}:
        tools.append(f"scripts/ops/import_fx_fixings.py --source {system}")
    return tools


def _connection(row: dict[str, Any], manifest) -> tuple[str, str | None]:
    """How the product connects to this source today, and the key provider if any.

    ``open`` (no key, no approval), ``approval`` / ``approval_and_key`` (an administrator
    approves the provider's terms; GIE also needs the key), ``key`` (the firm's own free key),
    ``licensed_key`` (a licensed connector reads with the firm's key), ``licensed_import``
    (the firm imports its own licensed export; no connector), ``licensed_none`` (licensed;
    neither a connector nor an import exists yet: record the licence only), ``register`` (a
    tariff register operations keep), ``template`` (no vendor chosen), ``model`` (AI).
    """

    from eurogas_nexus.application.scheduled_source_keys import SCHEDULED_SOURCE_KEYS
    from eurogas_nexus.domain.ingestion.source_approval import classify_source

    if row["source_id"] == "src-lng-terminal-tariffs":
        # Shown as what the product holds (register and the firm's own terms), not as a
        # register operations keep: the owner asked for held / not held and from which source.
        return "public_tariffs", None
    kind = classify_source(row)
    specs = [spec for spec in manifest.credentials if spec.implemented]
    provider = SCHEDULED_SOURCE_KEYS.get(row["source_id"]) or (
        specs[0].provider_id if specs else None
    )
    integration = row.get("integration")
    if kind == "register":
        return "register", None
    if kind == "model":
        return "model", provider or "DEEPSEEK"
    if integration == "template":
        return "template", None
    if kind in {"approval", "approval_and_key"}:
        return kind, provider
    if kind == "key_only":
        return "key", provider
    if kind == "licensed":
        if provider:
            return "licensed_key", provider
        if _import_tools(row["source_system"]):
            return "licensed_import", None
        return "licensed_none", None
    return "open", None


def setup_catalogue() -> dict[str, Any]:
    """The flow's pages and, per page, each source with what it needs (static, no DB)."""

    from eurogas_nexus.domain.connectors.registry import connector_manifests
    from eurogas_nexus.domain.ingestion.source_registry import registered_sources

    manifests = {manifest.source_id: manifest for manifest in connector_manifests()}
    items: dict[str, list[dict[str, Any]]] = {step: [] for step in STEPS}
    for row in registered_sources():
        source_id = row["source_id"]
        if source_id not in SOURCE_STEPS:
            raise SetupError(f"{source_id} has no first-run setup step")
        step = SOURCE_STEPS[source_id]
        if step is None:
            continue
        connection, provider = _connection(row, manifests[source_id])
        items[step].append(
            {
                "item_id": source_id,
                "source_id": source_id,
                "source_system": row["source_system"],
                "category": row["category"],
                "integration": row["integration"],
                "connection": connection,
                "credential_provider": provider,
                "key_registration_url": KEY_REGISTRATION_URLS.get(provider or ""),
                # The licence-register family a licensed source is granted under.
                "licence_family": (
                    str(row["source_system"]).upper() if connection.startswith("licensed") else None
                ),
                "import_tools": _import_tools(row["source_system"]),
                "datasets": list(row["datasets"]),
            }
        )
    for step_items in items.values():
        # What needs the administrator first: approvals and keys, then licences, then the
        # sources that run on their own, then registers and templates.
        step_items.sort(key=lambda item: (CONNECTION_ORDER.index(item["connection"]),
                                          item["source_system"].lower()))
    for step, static in STATIC_ITEMS.items():
        items[step].extend(dict(item) for item in static)
    return {
        "steps": [{"step": step, "items": items[step]} for step in STEPS],
        "excluded": [
            {"source_id": source_id, "reason": reason}
            for source_id, reason in sorted(EXCLUDED_REASONS.items())
        ],
    }


def terminal_tariff_facts(session) -> dict[str, Any]:
    """Which LNG terminal tariffs the product holds, and from which source.

    ``from_operator``: terminals in the public register (operator documents, CP-11);
    ``desk_entered``: the firm's own terms the desk typed from its contracts. Also the
    operators whose reuse permission the firm has not recorded.
    """

    from eurogas_nexus.application import lng_terminal_tariff_register as register
    from eurogas_nexus.db.models import LngTerminalTariffRecord, LngTerminalTermsRecord

    public = {row.terminal_id for row in session.query(LngTerminalTariffRecord.terminal_id)}
    firm = [
        row for row in session.query(LngTerminalTermsRecord).all() if row.source_url is None
    ]
    latest = session.query(LngTerminalTariffRecord.retrieved_at_utc).order_by(
        LngTerminalTariffRecord.retrieved_at_utc.desc()
    ).first()
    facts = register.held_facts(session)
    return {
        "held": len(public | {row.terminal_id for row in firm}),
        "from_operator": len(public),
        "desk_entered": len(firm),
        "reviewed": facts["reviewed"],
        "candidate": facts["candidate"],
        "operators_needing_terms": facts["operators_needing_terms"],
        "terminals": sorted(public | {row.name for row in firm}),
        "latest_read_at_utc": latest[0].isoformat() if latest else None,
    }


# --- state --------------------------------------------------------------------------------


def _payload(row) -> dict[str, Any]:
    if row is None:
        return {
            "status": "not_started",
            "current_step": None,
            "steps_visited": [],
            "configured_by": None,
            "updated_by": None,
            "updated_at_utc": None,
        }
    return {
        "status": row.status,
        "current_step": row.current_step,
        "steps_visited": list(row.steps_visited or []),
        "configured_by": row.configured_by,
        "updated_by": row.updated_by,
        "updated_at_utc": row.updated_at_utc.isoformat() if row.updated_at_utc else None,
    }


def setup_state(session) -> dict[str, Any]:
    from eurogas_nexus.db.models import InstallationSetupRecord

    return _payload(session.get(InstallationSetupRecord, SETUP_ID))


def show_on_sign_in(state: dict[str, Any]) -> bool:
    """Shown to an administrator until the flow is completed or dismissed."""

    return state["status"] in {"not_started", "in_progress"}


def update_setup_state(
    session,
    *,
    status: str,
    step: str | None,
    actor: str,
    configured_by: str = "admin",
    now_utc: datetime | None = None,
) -> dict[str, Any]:
    """Record where the flow stands; audited (``setup.state``)."""

    from eurogas_nexus.db.models import InstallationSetupRecord
    from eurogas_nexus.db.repositories.audit import record_audit_event

    if status not in STATUSES:
        raise SetupError(f"status must be one of {', '.join(STATUSES)}")
    if step is not None and step not in STEPS:
        raise SetupError(f"unknown step {step!r}")
    if configured_by not in CONFIGURED_BY:
        raise SetupError(f"configured_by must be one of {', '.join(CONFIGURED_BY)}")
    now = now_utc or datetime.now(UTC)
    row = session.get(InstallationSetupRecord, SETUP_ID)
    before = _payload(row)
    if row is None:
        row = InstallationSetupRecord(
            setup_id=SETUP_ID,
            status=status,
            current_step=step,
            steps_visited=[],
            configured_by=configured_by,
            updated_by=actor[:80],
            created_at_utc=now,
            updated_at_utc=now,
        )
        session.add(row)
    row.status = status
    row.current_step = step
    if step and step not in (row.steps_visited or []):
        row.steps_visited = [*(row.steps_visited or []), step]
    row.configured_by = configured_by
    row.updated_by = actor[:80]
    row.updated_at_utc = now
    session.flush()
    after = _payload(row)
    if before["status"] != after["status"] or before["current_step"] != after["current_step"]:
        record_audit_event(
            session,
            event_type="governance.setup",
            principal=actor[:128],
            action="setup.state",
            resource=f"installation_setup:{SETUP_ID}",
            outcome=status,
            detail=(
                f"status: {before['status']} -> {status}; step: {before['current_step']} -> "
                f"{step}; configured_by={configured_by}"
            ),
            source_system="setup",
            now_utc=now,
        )
    return after

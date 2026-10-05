#!/usr/bin/env python
"""Seed clearly synthetic declared-payment contracts into an isolated PostgreSQL database.

This script prepares the open real-browser declared-payment visual acceptance; it
is not that acceptance and it asserts nothing about the UI. It writes two
operator-visible upstream contracts whose declared ``contract-payment-terms/v1``
schedules exercise the read-only Settlement-and-cash panel:

* ``uat-declared-payment-explicit-dates-v1`` - explicit final payable dates,
  mixed INFLOW/OUTFLOW, long clearly synthetic evidence;
* ``uat-declared-payment-anchored-rules-v1`` - anchored rules whose anchor dates
  stay deliberately unresolved (including a business-day count and explicit roll
  conventions), mixed INFLOW/OUTFLOW, long clearly synthetic evidence.

Every identifier, name, date and evidence string states that it is synthetic:
no real contract, invoice, note, calendar or counterparty document is
represented, and nothing here resolves a payable date, values cash, or touches
execution, nomination or settlement.

Isolation and safety (configuration and pre-write target refusals write nothing):

* ``EUROGAS_NEXUS_ENV`` must be set explicitly to ``development`` or ``test``
  (normalized: surrounding whitespace stripped, case-insensitive); unset, blank,
  production, staging, trial, release and any other value are refused before the
  database URL is even read;
* ``EUROGAS_NEXUS_UAT_FIXTURE_ALLOWED=1`` must acknowledge synthetic UAT data;
* ``RUNTIME_STORE_DATABASE_URL`` must be set explicitly - this script never
  falls back to ``DATABASE_URL`` or ``EUROGAS_NEXUS_DB_DSN``, so a developer's
  default runtime store is never inherited by accident;
* the target must be PostgreSQL (no SQLite, no in-memory store) and its
  database name must start with ``eurogas_uat_payment_``; the default runtime
  database ``eurogas_nexus`` is refused by name;
* the target schema must already carry the reviewed migrations (including the
  ``payment_terms_json`` carrier); the script never migrates and never creates
  a database;
* ownership is the two exact fixture contract ids: the target must hold no
  upstream contract record whose id is not exactly one of them, so a shared or
  customer database cannot be contaminated (an id that merely shares the
  ``uat-declared-payment-`` prefix is still foreign): the guard refuses and
  writes nothing.

Engine creation and connection failures - including a selected database driver
that is unavailable or invalid - are reported with one fixed, sanitized message
that echoes neither the connection URL, credentials, nor exception text.

The declarations are built with the reviewed domain types and their strict
canonical serialization, then written through the existing repository fixture
path (``upsert_upstream_contract``, the documented fixtures/seeding entry
point), so no payment-term semantics are duplicated here. The script prints only
the target database *name* (never the URL or credentials) and the seeded ids.

Exit codes: 0 seeded and verified; 2 configuration/usage refusal; 3 target
refusal (missing reviewed schema or non-fixture records); 4 the isolated database could
not be reached or written, including engine creation, an unavailable or invalid
driver selection, a failed connection and a failed read-back (sanitized
message). Configuration and target guards run before any write.

Honest limits: seeded rows are synthetic evidence for visual inspection only.
EN/ZH parity, desktop/mobile viewports and real-browser rendering remain
separate, human-run gates - see
``docs/uat/DECLARED_PAYMENT_VISUAL_ACCEPTANCE.md``.
"""

from __future__ import annotations

import os
import sys
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from sqlalchemy import inspect
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.exc import ArgumentError, SQLAlchemyError

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
for path in (ROOT, SRC):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from eurogas_nexus.db.models import UpstreamResourceContractRecord  # noqa: E402
from eurogas_nexus.db.repositories.route_cost import (  # noqa: E402
    list_upstream_contracts,
    upsert_upstream_contract,
)
from eurogas_nexus.db.session import get_engine, get_session_factory  # noqa: E402
from eurogas_nexus.domain.ontology.vocabulary import (  # noqa: E402
    BusinessDayConvention,
    PaymentAnchorEvent,
    PaymentFlowDirection,
    PaymentOffsetDayKind,
)
from eurogas_nexus.domain.research.cash_valuation import CashFlowLegCategory  # noqa: E402
from eurogas_nexus.domain.route_cost.payment_terms import (  # noqa: E402
    AnchoredPaymentRule,
    ContractPaymentTerms,
    ExplicitPaymentDate,
    PaymentScheduleItem,
)

#: Explicit database URL variable this fixture requires; no fallback variable is
#: consulted, so an operator must name the isolated target on purpose.
DATABASE_URL_ENV = "RUNTIME_STORE_DATABASE_URL"

#: The only environments in which this fixture may ever touch a database, after
#: normalization (whitespace stripped, lowercased). Everything else - unset,
#: blank, production, staging, trial, release and arbitrary values - is refused.
ALLOWED_ENVIRONMENTS = frozenset({"development", "test"})

#: The same acknowledgement the other UAT fixture scripts require.
ACKNOWLEDGEMENT_ENV = "EUROGAS_NEXUS_UAT_FIXTURE_ALLOWED"

#: Contract ids this fixture owns. Ownership is exactly these ids: the guard
#: refuses a target holding any record that is not one of them, including ids
#: that merely share the ``uat-declared-payment-`` prefix.
CONTRACT_ID_PREFIX = "uat-declared-payment-"
EXPLICIT_CONTRACT_ID = f"{CONTRACT_ID_PREFIX}explicit-dates-v1"
ANCHORED_CONTRACT_ID = f"{CONTRACT_ID_PREFIX}anchored-rules-v1"
OWNED_CONTRACT_IDS = frozenset({EXPLICIT_CONTRACT_ID, ANCHORED_CONTRACT_ID})

#: Dedicated test-database name prefix, deliberately distinct from the
#: commercial UAT scratch database and from the default runtime database.
DATABASE_NAME_PREFIX = "eurogas_uat_payment_"
DEFAULT_RUNTIME_DATABASE_NAME = "eurogas_nexus"

#: The reviewed runtime schema this fixture needs; it never creates it.
REQUIRED_TABLES = ("upstream_resource_contracts",)
REQUIRED_COLUMNS = {"upstream_resource_contracts": frozenset({"payment_terms_json"})}

EXIT_SEEDED = 0
EXIT_CONFIGURATION_REFUSAL = 2
EXIT_TARGET_REFUSAL = 3
EXIT_DATABASE_FAILURE = 4

SYNTHETIC_NOTES = (
    "uat_declared_payment_fixture:synthetic; not customer data; created only for"
    " isolated declared-payment visual acceptance"
)

_SYNTHETIC_EVIDENCE_PREAMBLE = (
    "SYNTHETIC UAT FIXTURE (not customer data, not real evidence): no real contract,"
    " invoice, note, calendar or counterparty document exists for this declared-payment item."
)
_SYNTHETIC_EVIDENCE_DETAIL = (
    "This generated string exists only to exercise long-evidence rendering and wrapping for"
    " isolated declared-payment visual acceptance and names no real transaction"
)
_EVIDENCE_REPEATS = 3


def synthetic_evidence(shape: str) -> str:
    """Return one long, deterministic, unmistakably synthetic evidence string.

    Deterministic on purpose: the fixture is compared across runs and a caller
    must never mistake a generated layout string for source evidence. The text
    stays inside the declared payment-terms text guard.
    """

    detail = f"{_SYNTHETIC_EVIDENCE_DETAIL} ({shape})."
    return " ".join([_SYNTHETIC_EVIDENCE_PREAMBLE, *([detail] * _EVIDENCE_REPEATS)])


@dataclass(frozen=True, slots=True)
class DeclaredPaymentFixture:
    """One synthetic upstream contract plus its declared payment schedule."""

    contract_id: str
    contract_name: str
    schedule_kind: str
    payment_terms: ContractPaymentTerms


def explicit_dates_terms() -> ContractPaymentTerms:
    """Return the explicit-final-payable-date schedule (mixed INFLOW/OUTFLOW).

    The dates are fixed literal declarations, not resolved from any anchor, and
    the inflow item states its direction explicitly because a credit/refund can
    reverse the usual category sign.
    """

    return ContractPaymentTerms(
        quantity_basis_reference=(
            "synthetic UAT quantity basis (declared placeholder; not a real contract basis)"
        ),
        items=(
            PaymentScheduleItem(
                item_id="uat-synthetic-explicit-01-cargo-purchase",
                cash_flow_category=CashFlowLegCategory.CARGO_PURCHASE,
                flow_direction=PaymentFlowDirection.OUTFLOW,
                source_reference=synthetic_evidence("explicit-date supply payment"),
                date_specification=ExplicitPaymentDate(
                    final_payable_date=date(2027, 1, 29),
                    source_reference=synthetic_evidence("explicit supply final payable date"),
                ),
            ),
            PaymentScheduleItem(
                item_id="uat-synthetic-explicit-02-refund-credit",
                cash_flow_category=CashFlowLegCategory.OTHER,
                flow_direction=PaymentFlowDirection.INFLOW,
                source_reference=synthetic_evidence("explicit-date refund credit"),
                date_specification=ExplicitPaymentDate(
                    final_payable_date=date(2027, 2, 12),
                    source_reference=synthetic_evidence("explicit refund credit date"),
                ),
            ),
            PaymentScheduleItem(
                item_id="uat-synthetic-explicit-03-shipping",
                cash_flow_category=CashFlowLegCategory.SHIPPING,
                flow_direction=PaymentFlowDirection.OUTFLOW,
                source_reference=synthetic_evidence("explicit-date shipping payment"),
                date_specification=ExplicitPaymentDate(
                    final_payable_date=date(2027, 3, 31),
                    source_reference=synthetic_evidence("explicit shipping final payable date"),
                ),
            ),
        ),
    )


def anchored_rules_terms() -> ContractPaymentTerms:
    """Return the unresolved anchored-rule schedule (mixed INFLOW/OUTFLOW).

    No anchor date is stated, inferred or resolved; the rule only declares the
    reviewed anchor event, the explicit offset and the convention. A business-day
    count or a roll convention carries an explicit (synthetic) calendar
    reference, as the domain requires.
    """

    synthetic_calendar = "synthetic-uat-calendar-placeholder (not a real calendar reference)"
    return ContractPaymentTerms(
        quantity_basis_reference=(
            "synthetic UAT quantity basis (declared placeholder; not a real contract basis)"
        ),
        items=(
            PaymentScheduleItem(
                item_id="uat-synthetic-anchored-01-cargo-purchase",
                cash_flow_category=CashFlowLegCategory.CARGO_PURCHASE,
                flow_direction=PaymentFlowDirection.OUTFLOW,
                source_reference=synthetic_evidence("anchored supply payment rule"),
                date_specification=AnchoredPaymentRule(
                    anchor_event=PaymentAnchorEvent.INVOICE_DATE,
                    anchor_offset_days=30,
                    offset_day_kind=PaymentOffsetDayKind.CALENDAR_DAYS,
                    business_day_convention=BusinessDayConvention.NONE,
                    calendar_reference=None,
                    source_reference=synthetic_evidence("anchored supply payment rule"),
                ),
            ),
            PaymentScheduleItem(
                item_id="uat-synthetic-anchored-02-imbalance-credit",
                cash_flow_category=CashFlowLegCategory.OTHER,
                flow_direction=PaymentFlowDirection.INFLOW,
                source_reference=synthetic_evidence("anchored imbalance credit rule"),
                date_specification=AnchoredPaymentRule(
                    anchor_event=PaymentAnchorEvent.METER_READ_DATE,
                    anchor_offset_days=10,
                    offset_day_kind=PaymentOffsetDayKind.BUSINESS_DAYS,
                    business_day_convention=BusinessDayConvention.MODIFIED_FOLLOWING,
                    calendar_reference=synthetic_calendar,
                    source_reference=synthetic_evidence("anchored imbalance credit rule"),
                ),
            ),
            PaymentScheduleItem(
                item_id="uat-synthetic-anchored-03-regas",
                cash_flow_category=CashFlowLegCategory.REGAS,
                flow_direction=PaymentFlowDirection.OUTFLOW,
                source_reference=synthetic_evidence("anchored regas payment rule"),
                date_specification=AnchoredPaymentRule(
                    anchor_event=PaymentAnchorEvent.DELIVERY_PERIOD_END,
                    anchor_offset_days=45,
                    offset_day_kind=PaymentOffsetDayKind.CALENDAR_DAYS,
                    business_day_convention=BusinessDayConvention.FOLLOWING,
                    calendar_reference=synthetic_calendar,
                    source_reference=synthetic_evidence("anchored regas payment rule"),
                ),
            ),
        ),
    )


def fixture_contracts() -> tuple[DeclaredPaymentFixture, ...]:
    """Return the two synthetic fixtures in their stable, documented order."""

    return (
        DeclaredPaymentFixture(
            contract_id=EXPLICIT_CONTRACT_ID,
            contract_name=(
                "Synthetic UAT declared-payment fixture - explicit final payable dates"
                " (not customer data)"
            ),
            schedule_kind="explicit_dates",
            payment_terms=explicit_dates_terms(),
        ),
        DeclaredPaymentFixture(
            contract_id=ANCHORED_CONTRACT_ID,
            contract_name=(
                "Synthetic UAT declared-payment fixture - anchored rules with unresolved"
                " anchor dates (not customer data)"
            ),
            schedule_kind="anchored_rules",
            payment_terms=anchored_rules_terms(),
        ),
    )


def contract_payload(fixture: DeclaredPaymentFixture) -> dict[str, object]:
    """Build one repository fixture payload (the documented seeding path shape).

    The declared terms travel as the canonical document the domain produced, so
    the repository re-validates them with the shared strict decoder instead of
    this script restating any payment-term semantics.
    """

    return {
        "contract_id": fixture.contract_id,
        "contract_name": fixture.contract_name,
        "resource_type": "PIPELINE_IMPORT",
        "delivery_point_name": "TTF",
        "gas_year": "2025+",
        "delivery_quantity_mwh_per_day": 321.5,
        "contract_price_gbp_mwh": 27.5,
        "settlement_frequency": "monthly",
        "upstream_payment_lag_days": 20,
        "screen_sale_cash_lag_days": 1,
        "delivery_tolerance_pct": 2.0,
        "nomination_tolerance_pct": 1.0,
        "tolerance_risk_allowance_gbp_mwh": 0.1,
        "annual_financing_rate_pct": 6.0,
        "owned_entry_capacity_mwh_per_day": None,
        "owned_exit_capacity_mwh_per_day": None,
        "allowed_exit_points": ["TTF"],
        "eligible_sale_modes": ["TARGET_MARKET_SALE", "LOCAL_MARKET_SALE"],
        "variable_cost_gbp_mwh": 0.75,
        "regas_fee_gbp_mwh": 1.25,
        "fuel_loss_allowance_pct": 1.5,
        "notes": SYNTHETIC_NOTES,
        "payment_terms": fixture.payment_terms.canonical_document(),
    }


def database_target_refusal(database_url: str) -> str | None:
    """Refuse any target that is not an explicitly named isolated PostgreSQL UAT database.

    The refusal text names only the database *name* (or a fixed phrase) - never
    the URL, host, user or password - and the caller is expected to print it
    verbatim. A ``None`` return means the target passed every static guard; it
    never means the schema or contents were checked.
    """

    try:
        url = make_url(database_url)
    except ArgumentError:
        return (
            "Refusing: the configured database URL could not be parsed; supply an explicit"
            " PostgreSQL URL for a dedicated isolated UAT database."
        )
    backend = url.get_backend_name()
    if backend != "postgresql":
        return (
            "Refusing: only PostgreSQL is accepted (no SQLite and no in-memory store);"
            f" the configured backend is {backend!r}."
        )
    name = url.database or ""
    if name == DEFAULT_RUNTIME_DATABASE_NAME:
        return (
            "Refusing the default runtime database"
            f" {DEFAULT_RUNTIME_DATABASE_NAME!r}: this fixture never seeds a runtime store."
        )
    if not name:
        return (
            "Refusing: the configured database URL names no database; supply an explicit"
            " PostgreSQL URL for a dedicated isolated UAT database."
        )
    if not name.startswith(DATABASE_NAME_PREFIX):
        return (
            f"Refusing database {name!r}: its name must start with {DATABASE_NAME_PREFIX!r}"
            " so the target is unambiguously a dedicated isolated UAT database."
        )
    return None


def environment_refusal(environment: str | None) -> str | None:
    """Refuse every environment except an explicit development/test declaration.

    The value is normalized (surrounding whitespace stripped, lowercased) so
    ordinary shell spelling variants are accepted, but nothing is assumed: an
    unset or blank variable, production, staging, trial, release and any
    arbitrary value are refused before the database URL is read, let alone a
    connection attempted. A ``None`` return means the environment gate passed.
    """

    normalized = (environment or "").strip().lower()
    if normalized in ALLOWED_ENVIRONMENTS:
        return None
    return (
        "Refusing: EUROGAS_NEXUS_ENV must be set explicitly to 'development' or 'test'"
        f" (normalized); received {normalized!r}. Production, staging, trial, release,"
        " unset/blank values and anything else are refused. Nothing was written."
    )


def target_owner_refusal(existing_contract_ids: Iterable[str]) -> str | None:
    """Refuse a target that already holds upstream contracts this fixture does not own.

    Ownership is the two exact fixture contract ids, never an id prefix: a
    stored record with a similar id is treated as foreign. The count is
    reported; no stored identifier is echoed, because the guard exists so an
    operator can decide what to do with their own data rather than have it
    reinterpreted as fixture data.
    """

    foreign_count = len(
        {
            contract_id
            for contract_id in existing_contract_ids
            if contract_id not in OWNED_CONTRACT_IDS
        }
    )
    if foreign_count:
        return (
            f"Refusing: the target database already holds {foreign_count} upstream contract"
            " record(s) that are not this fixture's two exact contract ids; nothing was"
            " written. Point the fixture at its own disposable database instead of reusing a"
            " shared one."
        )
    return None


def _schema_refusal(engine: Engine) -> str | None:
    """Refuse a target whose reviewed schema has not been migrated yet."""

    inspector = inspect(engine)
    missing_tables = [name for name in REQUIRED_TABLES if not inspector.has_table(name)]
    if missing_tables:
        return (
            "Refusing: the isolated database is missing the reviewed runtime schema"
            f" ({', '.join(sorted(missing_tables))}); apply the reviewed Alembic migrations"
            " (`alembic upgrade head`) to the isolated database first. This script never"
            " migrates and never creates a database."
        )
    present_columns = {
        column["name"] for column in inspector.get_columns("upstream_resource_contracts")
    }
    missing_columns = sorted(REQUIRED_COLUMNS["upstream_resource_contracts"] - present_columns)
    if missing_columns:
        return (
            "Refusing: the isolated database predates the declared payment-terms carrier"
            f" ({', '.join(missing_columns)}); apply the reviewed Alembic migrations"
            " (`alembic upgrade head`) to the isolated database first. This script never"
            " migrates and never creates a database."
        )
    return None


def _seed(engine: Engine, session_factory, database_name: str) -> int:
    """Run the schema/ownership guards, seed both fixtures, then verify by reading back."""

    refusal = _schema_refusal(engine)
    if refusal is not None:
        print(refusal)
        return EXIT_TARGET_REFUSAL

    with session_factory() as session:
        stored_ids = [
            row.contract_id
            for row in session.query(UpstreamResourceContractRecord.contract_id).all()
        ]
    refusal = target_owner_refusal(stored_ids)
    if refusal is not None:
        print(refusal)
        return EXIT_TARGET_REFUSAL

    with session_factory() as session:
        for fixture in fixture_contracts():
            upsert_upstream_contract(session, contract_payload(fixture))
        session.commit()

    with session_factory() as session:
        stored_payloads = {
            payload["contract_id"]: payload for payload in list_upstream_contracts(session)
        }
    for fixture in fixture_contracts():
        stored = stored_payloads.get(fixture.contract_id)
        if stored is None or stored["payment_terms"] != fixture.payment_terms.canonical_document():
            print(
                "Refusing: a seeded declared-payment contract could not be verified through the"
                " repository read path; inspect the isolated database before using it."
            )
            return EXIT_DATABASE_FAILURE

    print(
        "Declared-payment UAT fixture ready in isolated database"
        f" {database_name!r} (database name only; the URL is never printed):"
    )
    for fixture in fixture_contracts():
        items = fixture.payment_terms.items
        directions = ", ".join(sorted({str(item.flow_direction) for item in items}))
        print(
            f"  - {fixture.contract_id}: {len(items)} declared item(s),"
            f" {fixture.schedule_kind}, directions: {directions}"
        )
    print(
        "All identifiers, dates and evidence are clearly synthetic and no real document is"
        " represented (not customer data)."
    )
    print(
        "Seeding is not UI acceptance: the EN/ZH and desktop/mobile real-browser checks remain"
        " open - see docs/uat/DECLARED_PAYMENT_VISUAL_ACCEPTANCE.md."
    )
    return EXIT_SEEDED


def main(argv: Sequence[str] | None = None) -> int:
    """Run the fixture; every configuration and target guard refuses before any write."""

    arguments = list(sys.argv[1:] if argv is None else argv)
    if arguments:
        print(
            "Unexpected command-line arguments."
            " This script takes no arguments."
        )
        return EXIT_CONFIGURATION_REFUSAL

    refusal = environment_refusal(os.getenv("EUROGAS_NEXUS_ENV"))
    if refusal is not None:
        print(refusal)
        return EXIT_CONFIGURATION_REFUSAL

    if os.getenv(ACKNOWLEDGEMENT_ENV, "").strip() != "1":
        print(f"Set {ACKNOWLEDGEMENT_ENV}=1 to acknowledge synthetic declared-payment UAT data.")
        return EXIT_CONFIGURATION_REFUSAL

    database_url = os.getenv(DATABASE_URL_ENV, "").strip()
    if not database_url:
        print(
            f"{DATABASE_URL_ENV} must be set explicitly to the isolated PostgreSQL UAT"
            " database; this fixture never falls back to another database URL variable."
        )
        return EXIT_CONFIGURATION_REFUSAL
    refusal = database_target_refusal(database_url)
    if refusal is not None:
        print(refusal)
        return EXIT_CONFIGURATION_REFUSAL

    engine: Engine | None = None
    try:
        database_name = make_url(database_url).database or ""
        engine = get_engine(database_url=database_url)
        session_factory = get_session_factory(engine=engine)
        return _seed(engine, session_factory, database_name)
    except (SQLAlchemyError, ImportError):
        # Expected operator/configuration failure classes only. SQLAlchemyError
        # covers engine creation, unavailable databases, connection and
        # read-back failures, and an invalid driver selection
        # (``NoSuchModuleError``); ImportError/ModuleNotFoundError covers a
        # selected DBAPI driver that is not installed, which the engine imports
        # during creation. Programming defects keep propagating. The message is
        # fixed: neither the URL, a credential, nor any exception text is echoed.
        print(
            "The isolated database could not be reached or written: engine creation, the"
            " connection, or the read-back verification failed. Check that the selected database"
            " driver is installed and that the isolated target is reachable and migrated. Rows"
            " may have been committed before read-back failed; inspect the isolated target before"
            " retrying. The connection URL is never printed.",
            file=sys.stderr,
        )
        return EXIT_DATABASE_FAILURE
    finally:
        if engine is not None:
            engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())

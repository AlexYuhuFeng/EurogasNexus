"""P-17: which writes need two people, the setting that says so, and migration 0081."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, inspect

from eurogas_nexus.application.audit_service import governed_actions
from eurogas_nexus.domain.settings.preferences import (
    SettingsError,
    validate_organisation_defaults,
)
from eurogas_nexus.governance.four_eyes import (
    FOUR_EYES_SETTING,
    FOUR_EYES_WRITES,
    FourEyesSettingError,
    four_eyes_in_force,
    validate_four_eyes,
)
from eurogas_nexus.release.constants import DB_SCHEMA_REVISION

VERSIONS = Path(__file__).resolve().parents[2] / "alembic" / "versions"
PROVENANCE_TABLES = {
    "credit_lines": "CreditLineRecord",
    "trader_mandates": "TraderMandateRecord",
    "hedge_approvals": "HedgeApprovalRecord",
    "lng_terminal_terms": "LngTerminalTermsRecord",
    "firm_marks": "FirmMarkRecord",
    "freight_route": "FreightRouteRecord",
}


def test_the_money_and_risk_writes_need_two_people_by_default():
    in_force = four_eyes_in_force(None)
    assert in_force == {
        "risk.credit_line.update": True,
        "risk.mandate.update": True,
        "risk.hedge_approval.update": True,
        "market.firm_marks.update": True,
        "lng.terminal_terms.update": True,
        "lng.freight_route": True,
    }
    # Each is a governed write, and so is each step of a proposal.
    assert set(in_force) <= governed_actions()
    assert {
        "change_request.propose",
        "change_request.approve",
        "change_request.reject",
        "change_request.withdraw",
    } <= governed_actions()
    # Limits, bands and marks are approved by the risk function; desk data by the desk.
    approvers = {write.action: write.approver for write in FOUR_EYES_WRITES}
    assert approvers["market.firm_marks.update"] == "risk_function"
    assert approvers["lng.terminal_terms.update"] == "desk"


def test_a_bad_stored_setting_never_switches_the_control_off():
    assert four_eyes_in_force({"risk.credit_line.update": "no"})["risk.credit_line.update"]
    assert four_eyes_in_force(["risk.credit_line.update"])["risk.credit_line.update"]
    assert four_eyes_in_force({"risk.credit_line.update": False})["risk.credit_line.update"] is (
        False
    )
    assert "access.user.create" not in four_eyes_in_force({"access.user.create": True})


def test_the_setting_names_listed_writes_with_true_or_false():
    assert validate_four_eyes({"lng.freight_route": False}) == {"lng.freight_route": False}
    for bad in ({}, {"access.user.create": False}, {"lng.freight_route": "off"}, ["x"]):
        with pytest.raises(FourEyesSettingError):
            validate_four_eyes(bad)
    accepted = validate_organisation_defaults({FOUR_EYES_SETTING: {"lng.freight_route": False}})
    assert accepted == {FOUR_EYES_SETTING: {"lng.freight_route": False}}
    with pytest.raises(SettingsError):
        validate_organisation_defaults({FOUR_EYES_SETTING: {"nope": True}})


def test_migration_0081_chain_up_down_and_model_match():
    import eurogas_nexus.db.models as models

    spec = importlib.util.spec_from_file_location(
        "tests.migration_0081", VERSIONS / "0081_change_requests.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.down_revision == "0080_lng_eta_basis"
    assert module.revision == "0081_change_requests"
    assert DB_SCHEMA_REVISION == "0088_tar2_capacity_bookings"
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    before = sa.MetaData()
    for table_name, record in PROVENANCE_TABLES.items():
        columns = getattr(models, record).__table__.columns
        sa.Table(
            table_name,
            before,
            *[column._copy() for column in columns if column.name != "change_id"],
        )
    with engine.begin() as connection:
        before.create_all(connection)
        module.op = Operations(MigrationContext.configure(connection=connection))
        module.upgrade()
        inspector = inspect(connection)
        assert {c["name"] for c in inspector.get_columns("change_requests")} == set(
            models.ChangeRequestRecord.__table__.columns.keys()
        )
        for table_name, record in PROVENANCE_TABLES.items():
            names = {c["name"] for c in inspector.get_columns(table_name)}
            assert names == set(getattr(models, record).__table__.columns.keys()), table_name
        module.downgrade()
        inspector = inspect(connection)
        assert "change_requests" not in inspector.get_table_names()
        for table_name in PROVENANCE_TABLES:
            assert "change_id" not in {c["name"] for c in inspector.get_columns(table_name)}

"""DATA-1: versioned ETRM and ERP import contracts.

Each file is checked row by row; a refused row is reported with its line and reason code;
by default one refused row refuses the file and nothing is stored; re-importing the same file
changes nothing; nothing is booked, nominated, posted or paid.
"""

from __future__ import annotations

from datetime import UTC, date, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

import eurogas_nexus.db.models  # noqa: F401  (registers every table)
from eurogas_nexus.api.app import create_app
from eurogas_nexus.application.import_contracts import (
    CONTRACTS,
    SKIP_ROWS,
    ImportContractError,
    run_import,
)
from eurogas_nexus.db.base import Base
from eurogas_nexus.db.models import (
    ErpReferenceRecord,
    GasDayNominationEventRecord,
    GasDayScheduleLineRecord,
    LngCargoRecord,
    MarketEventRecord,
    ScreenOrderObservationRecord,
    TradingBookRecord,
)
from eurogas_nexus.db.repositories.identity import (
    create_identity_api_key,
    create_identity_principal,
)

NOW = datetime(2026, 11, 24, 12, 0, tzinfo=UTC)

DEALS_HEADER = (
    "trade_id,trade_time,book_id,hub,side,delivery_start,delivery_end,quantity,quantity_unit,"
    "price,price_unit,status,counterparty"
)
DEALS = DEALS_HEADER + """
D-1,2026-11-20T09:15:00Z,GAS-1,TTF,BUY,2027-01-01,2027-01-31,1000,MWh/d,41.25,EUR/MWh,,Kestrel
D-2,2026-11-20T10:00:00Z,GAS-1,NBP,SELL,2027-02-01,2027-02-28,10000,th/d,102.5,GBp/th,,Osprey
D-3,2026-11-20T11:00:00Z,NOPE,TTF,BUY,2027-03-01,2027-03-31,500,MWh/d,40,EUR/MWh,,Kestrel
D-4,2026-11-20T11:30:00Z,GAS-1,TTF,HOLD,2027-03-01,2027-03-31,500,MWh/d,40,EUR/MWh,,Kestrel
D-5,2026-11-20T12:00:00Z,GAS-1,TTF,BUY,2027-13-01,2027-03-31,500,MWh/d,40,EUR/MWh,,Kestrel
D-1,2026-11-20T09:15:00Z,GAS-1,TTF,BUY,2027-01-01,2027-01-31,1000,MWh/d,41.25,EUR/MWh,,Kestrel
"""


@pytest.fixture
def store(tmp_path, monkeypatch):
    url = f"sqlite+pysqlite:///{(tmp_path / 'imports.sqlite').as_posix()}"
    monkeypatch.setenv("RUNTIME_STORE_DATABASE_URL", url)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("EUROGAS_NEXUS_DB_DSN", raising=False)
    engine = create_engine(url)
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.add(
            TradingBookRecord(
                book_id="GAS-1", name="Gas 1", legal_entity="LE1", region="NWE",
                business="Gas", base_currency="EUR", commodities=["gas"], active=True,
                updated_by="test", updated_at_utc=NOW,
            )
        )
        session.commit()
    return engine


def _run(engine, contract, text, *, commit=False, on_error="reject_file", system="Endur"):
    with Session(engine) as session:
        report = run_import(
            contract, text, system=system, file_name="test.csv", session=session,
            on_error=on_error, commit=commit, now=NOW,
        )
        session.commit() if commit else session.rollback()
    return report


def _count(engine, model) -> int:
    with Session(engine) as session:
        return session.query(model).count()


def test_each_bad_row_is_refused_with_its_line_and_reason_and_the_file_stores_nothing(store):
    report = _run(store, "etrm.deals.v1", DEALS, commit=True)
    assert report.file_refused and not report.committed
    assert [(r.line, r.reason_code) for r in report.refused] == [
        (4, "book_unknown"),
        (5, "side_invalid"),
        (6, "date_invalid"),
        (7, "duplicate_key"),
    ]
    assert "line" not in report.refused[1].message  # the reason, not the parser's prefix
    assert report.rows == 6 and report.accepted == 2
    assert _count(store, ScreenOrderObservationRecord) == 0


def test_skip_rows_stores_the_good_rows_and_a_re_import_changes_nothing(store):
    first = _run(store, "etrm.deals.v1", DEALS, commit=True, on_error=SKIP_ROWS)
    assert (first.created, first.updated, first.unchanged, len(first.refused)) == (2, 0, 0, 4)
    with Session(store) as session:
        nbp = session.get(ScreenOrderObservationRecord, "etrm-endur-D-2")
        assert nbp.side == "SELL" and nbp.currency == "GBP" and nbp.book_id == "GAS-1"
    again = _run(store, "etrm.deals.v1", DEALS, commit=True, on_error=SKIP_ROWS)
    assert (again.created, again.updated, again.unchanged) == (0, 0, 2)

    amended = DEALS.splitlines()[0] + "\n" + DEALS.splitlines()[1].replace("41.25", "41.5") + "\n"
    report = _run(store, "etrm.deals.v1", amended, commit=True)
    assert (report.created, report.updated) == (0, 1)
    cancelled = amended.replace(",EUR/MWh,,Kestrel", ",EUR/MWh,CANCELLED,Kestrel")
    report = _run(store, "etrm.deals.v1", cancelled, commit=True)
    assert report.removed == 1 and _count(store, ScreenOrderObservationRecord) == 1
    assert _run(store, "etrm.deals.v1", cancelled, commit=True).unchanged == 1


def test_a_dry_run_says_what_storing_would_do_and_stores_nothing(store):
    report = _run(store, "etrm.deals.v1", DEALS, on_error=SKIP_ROWS)
    assert report.created == 2 and not report.committed
    assert _count(store, ScreenOrderObservationRecord) == 0
    assert report.as_dict()["executes_nothing"] is True


POSITIONS = """line_id,gas_day,hub,direction,kind,label,quantity_mwh,book_id,point
SCH-1,2026-11-25,TTF,out,storage_injection,Bergermeer,12000,GAS-1,Bergermeer
SCH-2,2026-11-25,THE,in,customer_offtake,Stadtwerke,8000,GAS-1,
SCH-3,2026-11-25,ATLANTIS,in,supply,Somewhere,100,GAS-1,
SCH-4,2026-11-25,TTF,in,import,Zeebrugge,-5,GAS-1,
"""


def test_physical_positions_land_in_the_gas_day_schedule(store):
    report = _run(store, "etrm.physical_positions.v1", POSITIONS, commit=True, on_error=SKIP_ROWS)
    assert [(r.line, r.reason_code) for r in report.refused] == [
        (3, "kind_direction_mismatch"),
        (4, "market_unknown"),
        (5, "quantity_negative"),
    ]
    with Session(store) as session:
        line = session.get(GasDayScheduleLineRecord, "SCH-1")
        assert (line.gas_day, line.hub, line.direction, line.quantity_mwh) == (
            date(2026, 11, 25), "TTF", "out", 12000.0
        )
        assert line.source_system == "Endur" and line.simulated is False
    again = _run(store, "etrm.physical_positions.v1", POSITIONS, commit=True, on_error=SKIP_ROWS)
    assert (again.created, again.updated, again.unchanged) == (0, 0, 1)


NOMINATIONS = """gas_day,line_ref,hub,step,status,recorded_at,quantity_mwh,agent
2026-11-25,schedule:SCH-1,TTF,nomination,sent,2026-11-24T10:00:00Z,12000,Agent A
2026-11-25,schedule:SCH-1,TTF,nomination,confirmed,2026-11-24T11:00:00Z,12000,Agent A
2026-11-25,SCH-1,TTF,nomination,confirmed,2026-11-24T11:00:00Z,12000,Agent A
2026-11-25,schedule:SCH-1,TTF,nominate,confirmed,2026-11-24T11:00:00Z,12000,Agent A
2026-11-25,schedule:SCH-1,TTF,nomination,confirmed,2026-11-24T18:00:00Z,12000,Agent A
"""


def test_nomination_statuses_are_recorded_once_and_nothing_is_nominated(store):
    report = _run(store, "etrm.nominations.v1", NOMINATIONS, commit=True, on_error=SKIP_ROWS)
    assert [(r.line, r.reason_code) for r in report.refused] == [
        (4, "line_ref_invalid"),
        (5, "step_unknown"),
        (6, "time_in_future"),
    ]
    assert report.created == 2
    with Session(store) as session:
        rows = session.query(GasDayNominationEventRecord).order_by(
            GasDayNominationEventRecord.recorded_at_utc
        ).all()
        assert [(row.status, row.origin, row.recorded_by) for row in rows] == [
            ("sent", "import", "import:Endur"),
            ("confirmed", "import", "import:Endur"),
        ]
    again = _run(store, "etrm.nominations.v1", NOMINATIONS, commit=True, on_error=SKIP_ROWS)
    assert (again.created, again.unchanged) == (0, 2)
    assert _count(store, GasDayNominationEventRecord) == 2


CARGOES = """cargo_id,vessel_name,status,load_port,eta,eta_basis,eta_confidence,energy_gwh,book_id
SAB-0420,Aurora,laden,Sabine Pass,2026-12-02T06:00:00Z,schedule,medium,1000,GAS-1
SAB-0421,Boreas,sailing,Sabine Pass,,,,,GAS-1
"""


def test_the_cargo_schedule_lands_in_the_cargo_plan_and_a_re_import_publishes_nothing(store):
    report = _run(store, "etrm.cargo_schedule.v1", CARGOES, commit=True, on_error=SKIP_ROWS)
    assert [(r.line, r.reason_code) for r in report.refused] == [(3, "status_invalid")]
    assert report.created == 1
    with Session(store) as session:
        cargo = session.get(LngCargoRecord, "SAB-0420")
        assert cargo.book_id == "GAS-1" and cargo.eta_basis == "schedule"
    events = _count(store, MarketEventRecord)
    assert events >= 1  # the firm's cargo changed: cargo.changed through the outbox
    again = _run(store, "etrm.cargo_schedule.v1", CARGOES, commit=True, on_error=SKIP_ROWS)
    assert (again.created, again.updated, again.unchanged) == (0, 0, 1)
    assert _count(store, MarketEventRecord) == events


COUNTERPARTIES = """erp_id,name,counterparty_id,country,currency,payment_terms_days,blocked
100234,Kestrel Energy BV,KESTREL,NL,EUR,20,false
100235,Osprey Gas Ltd,,GB,GBP,30,x
100236,,,,,,
"""

INVOICES = """invoice_id,counterparty_erp_id,direction,issue_date,due_date,amount,currency,\
trade_ref,status
9000001,100234,receivable,2026-11-05,2026-11-25,1250000.50,EUR,D-1,open
9000002,100299,payable,2026-11-05,2026-11-25,10,EUR,,open
9000003,100235,payable,2026-11-05,2026-10-25,10,GBP,,open
"""


def test_erp_counterparties_and_invoices_are_kept_as_references(store):
    report = _run(store, "erp.counterparties.v1", COUNTERPARTIES, commit=True,
                  on_error=SKIP_ROWS, system="SAP")
    assert [(r.line, r.reason_code) for r in report.refused] == [(4, "value_required")]
    invoices = _run(store, "erp.invoices.v1", INVOICES, commit=True, on_error=SKIP_ROWS,
                    system="SAP")
    assert [(r.line, r.reason_code) for r in invoices.refused] == [
        (3, "counterparty_unknown"),
        (4, "period_reversed"),
    ]
    with Session(store) as session:
        kestrel = session.get(ErpReferenceRecord, "sap:counterparty:100234")
        assert kestrel.counterparty_id == "KESTREL" and kestrel.fields["payment_terms_days"] == 20
        assert session.get(ErpReferenceRecord, "sap:counterparty:100235").fields["blocked"]
        invoice = session.get(ErpReferenceRecord, "sap:invoice:9000001")
        assert invoice.counterparty_external_id == "100234" and invoice.trade_ref == "D-1"
        assert invoice.fields["amount"] == pytest.approx(1250000.50)
    again = _run(store, "erp.invoices.v1", INVOICES, commit=True, on_error=SKIP_ROWS,
                 system="SAP")
    assert (again.created, again.updated, again.unchanged) == (0, 0, 1)
    paid = INVOICES.replace("D-1,open", "D-1,paid")
    assert _run(store, "erp.invoices.v1", paid, commit=True, on_error=SKIP_ROWS,
                system="SAP").updated == 1


def test_a_file_with_bank_or_tax_columns_or_missing_columns_is_refused_whole(store):
    with pytest.raises(ImportContractError) as refused:
        _run(store, "erp.counterparties.v1", "erp_id,name,iban\n1,A,NL00TEST\n", system="SAP")
    assert refused.value.code == "column_forbidden"
    with pytest.raises(ImportContractError) as missing:
        _run(store, "etrm.deals.v1", "trade_id,book_id\nD-1,GAS-1\n")
    assert missing.value.code == "column_missing"
    with pytest.raises(ImportContractError) as unknown:
        _run(store, "etrm.deals.v9", DEALS)
    assert unknown.value.code == "contract_unknown"


@pytest.fixture
def api(store):
    def client(role: str) -> TestClient:
        with Session(store) as session:
            owner = create_identity_principal(
                session, name=f"imp-{role.lower()}", display_name=role, role=role,
                data_scopes=["*"],
            )
            _, bearer = create_identity_api_key(session, owner.principal_id, scopes=["*"])
            session.commit()
        return TestClient(
            create_app(),
            headers={"X-Eurogas-Identity": bearer, "X-Eurogas-Api-Key": "test-public-api-token"},
        )

    return client


def test_the_api_lists_the_contracts_and_checks_a_file_without_storing_it(store, api):
    analyst = api("ANALYST")
    listed = analyst.get("/api/imports/contracts")
    assert listed.status_code == 200, listed.text
    assert [c["contract_id"] for c in listed.json()["data"]] == sorted(CONTRACTS)
    deals = next(c for c in listed.json()["data"] if c["contract_id"] == "etrm.deals.v1")
    assert deals["key"] == "(system, trade_id)"
    assert {"trade_id", "price_unit"} <= {c["name"] for c in deals["columns"] if c["required"]}

    checked = analyst.post(
        "/api/imports/etrm.deals.v1/validate", params={"system": "Endur"},
        content=DEALS.encode(), headers={"Content-Type": "text/csv"},
    )
    assert checked.status_code == 200, checked.text
    report = checked.json()["data"]
    assert report["file_refused"] is True and report["committed"] is False
    assert [r["reason_code"] for r in report["refused"]] == [
        "book_unknown", "side_invalid", "date_invalid", "duplicate_key"
    ]
    skipped = analyst.post(
        "/api/imports/etrm.deals.v1/validate",
        params={"system": "Endur", "on_error": "skip_rows"},
        content=DEALS.encode(), headers={"Content-Type": "text/csv"},
    ).json()["data"]
    assert skipped["created"] == 2 and skipped["committed"] is False
    assert _count(store, ScreenOrderObservationRecord) == 0  # nothing stored

    unknown = analyst.post("/api/imports/etrm.trades.v1/validate", params={"system": "Endur"},
                           content=b"x\n")
    assert unknown.status_code == 404 and unknown.json()["detail"]["code"] == "contract_unknown"
    # Checking a file is an analyst's: a viewer may read the catalogue only.
    viewer = api("VIEWER")
    assert viewer.get("/api/imports/contracts").status_code == 200
    assert viewer.post(
        "/api/imports/etrm.deals.v1/validate", params={"system": "Endur"}, content=b"x\n"
    ).status_code == 403


def test_the_operator_script_dry_runs_then_commits(store, tmp_path, capsys):
    import importlib.util
    from pathlib import Path

    script = Path(__file__).resolve().parents[2] / "scripts" / "ops" / "import_contract_file.py"
    spec = importlib.util.spec_from_file_location("import_contract_file", script)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    extract = tmp_path / "deals.csv"
    extract.write_text(DEALS, encoding="utf-8")
    args = ["--contract", "etrm.deals.v1", "--system", "Endur", "--file", str(extract)]
    assert module.main(args) == 2  # refused rows refuse the file
    assert "line 4: [book_unknown]" in capsys.readouterr().out
    assert module.main([*args, "--skip-bad-rows"]) == 0  # dry run
    assert _count(store, ScreenOrderObservationRecord) == 0
    assert module.main([*args, "--skip-bad-rows", "--commit"]) == 0
    assert _count(store, ScreenOrderObservationRecord) == 2
    assert module.main(["--list"]) == 0
    assert "erp.invoices.v1" in capsys.readouterr().out

"""Book isolation is enforced in one place and nothing book-scoped leaks across entities (H1).

Three contracts:

1. **Inventory.** Every mapped table with a book-like column is scoped by the ORM layer
   (``db/book_scope.py``), delegated to a named module, or declared not book data with a
   reason. A new table with such a column fails here until someone decides which it is.
2. **ORM enforcement.** Under a regional scope a plain session query, a join, a column query
   and ``session.get`` return only that region's rows, and a write into another entity's book
   is refused. Outside a request (a worker) nothing is narrowed.
3. **No route leaks.** Two legal entities, every scoped table filled for both; a principal
   with every commercial role but only entity NL's books calls every GET route of the
   application (path parameters filled with entity UK's ids). No response carries UK's rows.
"""

from __future__ import annotations

import re
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    Float,
    Integer,
    Numeric,
    create_engine,
    event,
)
from sqlalchemy.orm import Session

import eurogas_nexus.db.models  # noqa: F401  (registers every table, installs the events)
from eurogas_nexus.db import book_scope
from eurogas_nexus.db.base import Base
from eurogas_nexus.security import portfolio_scope

ROOT = Path(__file__).resolve().parents[2]
NOW = datetime(2026, 11, 20, 9, tzinfo=UTC)
LEAK = "LEAKUK"
NL_BOOK, UK_BOOK = "nl-book", f"{LEAK}-book"
BOOKISH = {"book_id", "book_ids", "legal_entity", "portfolio_ref", "cargo_id", "contract_id"}


def _bookish_tables() -> dict[str, set[str]]:
    found: dict[str, set[str]] = {}
    for mapper in Base.registry.mappers:
        table = mapper.local_table
        hits = BOOKISH & {column.name for column in table.columns}
        if hits:
            found[table.name] = hits
    return found


def test_every_table_with_a_book_like_column_has_a_decision():
    scoped = book_scope.scoped_tables()
    undecided = sorted(
        name
        for name in _bookish_tables()
        if name not in scoped
        and name not in book_scope.DELEGATED
        and name not in book_scope.NOT_BOOK_DATA
    )
    # Tables with a contract or cargo key that are not positions (reference data keyed by
    # contract id, e.g. tariff publications) must be declared, not silently skipped.
    assert undecided == [], (
        "scope these tables in db/book_scope.py, or declare them in DELEGATED/NOT_BOOK_DATA "
        f"with a reason: {undecided}"
    )


def test_delegated_modules_apply_their_row_rule():
    for table, module in book_scope.DELEGATED.items():
        path = ROOT / "src" / Path(*module.split(".")).with_suffix(".py")
        text = path.read_text(encoding="utf-8")
        assert "visible_book_ids" in text, f"{module} must filter {table} by visible books"


def test_no_raw_sql_reads_a_scoped_table():
    """Raw text() SQL bypasses the ORM event; only migrations and maintenance tools may."""

    tables = book_scope.scoped_tables()
    pattern = re.compile(r"\b(?:FROM|JOIN)\s+(" + "|".join(sorted(tables)) + r")\b", re.I)
    offenders = []
    allowed = {"db/timescale.py", "db/retention.py", "application/runtime_retention.py"}
    for path in (ROOT / "src" / "eurogas_nexus").rglob("*.py"):
        rel = path.relative_to(ROOT / "src" / "eurogas_nexus").as_posix()
        if rel in allowed:
            continue
        for match in pattern.finditer(path.read_text(encoding="utf-8")):
            offenders.append(f"{rel}: {match.group(0)}")
    assert offenders == []


# --- a generic two-entity fixture ---------------------------------------------------------


def _value(column, tag: str, index: int):
    kind = column.type
    name = column.name
    if isinstance(kind, DateTime):
        return NOW
    if isinstance(kind, Date):
        return date(2026, 12, 1)
    if isinstance(kind, Boolean):
        return False
    if isinstance(kind, Integer):
        return 1
    if isinstance(kind, Float):
        return 1.0
    if isinstance(kind, Numeric):
        return Decimal("1")
    if isinstance(kind, JSON) or kind.__class__.__name__ == "JSON":
        return [UK_BOOK if tag == LEAK else NL_BOOK] if name == "book_ids" else []
    length = getattr(kind, "length", None) or 64
    text = f"{tag}-{name}-{index}"
    return text[: max(1, length)]


def _row(model, tag: str, index: int, **fixed):
    values = dict(fixed)
    for column in model.__table__.columns:
        if column.name in values:
            continue
        if column.foreign_keys:
            continue
        values[column.name] = _value(column, tag, index)
    return model(**values)


def _ids(tag: str) -> dict[str, str]:
    book = UK_BOOK if tag == LEAK else NL_BOOK
    return {
        "book_id": book,
        "contract_id": f"{tag}-contract",
        "cargo_id": f"{tag}-cargo",
        "legal_entity": f"{tag}-ENT".upper(),
        "region": "europe",
        "portfolio_ref": book,
        "case_id": f"{tag}-case",
        "snapshot_id": f"{tag}-snapshot",
        "created_by": f"{tag}-author",
    }


def _seed(session: Session) -> None:
    from eurogas_nexus.db import models as m

    for tag in ("NL", LEAK):
        ids = _ids(tag)
        session.add(
            _row(m.TradingBookRecord, tag, 0, book_id=ids["book_id"],
                 legal_entity=ids["legal_entity"], region="europe")
        )
    session.flush()
    explicit = {
        "decision_case_records": m.DecisionCaseDecisionRecord,
    }
    for index, (table, model) in enumerate(
        sorted(
            {**book_scope.book_column_tables(), **{
                name: getattr(m, cls) for name, (cls, _rule) in
                book_scope._explicit_rules().items()
            }}.items()
        )
    ):
        if table in {"trading_books", *explicit}:
            continue
        for tag in ("NL", LEAK):
            ids = _ids(tag)
            fixed = {
                key: value
                for key, value in ids.items()
                if key in model.__table__.c and key != "region"
            }
            for column in model.__table__.primary_key.columns:
                fixed.setdefault(column.name, _pk_value(column, tag, table))
            if table == "analysis_snapshots":
                fixed["snapshot_id"] = ids["snapshot_id"]
            if table == "decision_cases":
                fixed["case_id"] = ids["case_id"]
                fixed["snapshot_id"] = ids["snapshot_id"]
            session.add(_row(model, tag, index, **fixed))
    session.flush()
    for tag in ("NL", LEAK):
        session.add(
            _row(m.DecisionCaseDecisionRecord, tag, 0, record_id=f"{tag}-record",
                 case_id=_ids(tag)["case_id"])
        )
    session.commit()


@pytest.fixture
def seeded(tmp_path, monkeypatch):
    url = f"sqlite+pysqlite:///{(tmp_path / 'scope.sqlite').as_posix()}"
    engine = create_engine(url, future=True)

    @event.listens_for(engine, "connect")
    def _generic_values(dbapi_connection, _record):  # the fixture fills columns generically
        dbapi_connection.execute("PRAGMA ignore_check_constraints = 1")

    Base.metadata.create_all(engine)
    with Session(engine) as session:
        _seed(session)
    monkeypatch.delenv(portfolio_scope.ISOLATION_ENV, raising=False)  # the default: on
    yield engine, url
    engine.dispose()


def _nl_scope():
    return portfolio_scope.scope_from_data_scopes(["BOOKS:ENTITY:NL-ENT"])


def test_orm_reads_are_narrowed_in_a_request_and_not_outside(seeded):
    engine, _url = seeded
    from eurogas_nexus.db import models as m

    tables = {**book_scope.book_column_tables()}
    token = portfolio_scope._current.set(_nl_scope())
    try:
        with Session(engine) as session:
            for table, model in sorted(tables.items()):
                rows = session.query(model).all()
                assert all(getattr(row, "book_id", None) != UK_BOOK for row in rows), table
                assert session.get(model, _pk(model, LEAK, table)) is None, table
            # A column query and a join are narrowed too.
            ids = [v for (v,) in session.query(m.ScreenOrderObservationRecord.book_id).all()]
            assert UK_BOOK not in ids
            joined = (
                session.query(m.ScreenOrderObservationRecord.book_id)
                .join(
                    m.TradingBookRecord,
                    m.TradingBookRecord.book_id == m.ScreenOrderObservationRecord.book_id,
                )
                .all()
            )
            assert [row[0] for row in joined] == [NL_BOOK]
            assert {row.counterparty_id for row in session.query(m.CreditLineRecord)} == {
                "NL-credit_lines-counterparty_id"
            }
            assert [row.case_id for row in session.query(m.DecisionCaseRecord)] == ["NL-case"]
            assert [r.snapshot_id for r in session.query(m.AnalysisSnapshotRecord)] == [
                "NL-snapshot"
            ]
            assert len(session.query(m.TraderMandateRecord).all()) == 1
            assert len(session.query(m.HedgeApprovalRecord).all()) == 1
            # A write into the other entity's book is refused.
            row = session.query(m.ScreenOrderObservationRecord).one()
            row.book_id = UK_BOOK
            with pytest.raises(portfolio_scope.BookScopeViolation):
                session.flush()
            session.rollback()
    finally:
        portfolio_scope._current.reset(token)
    # A worker (no request scope) acts as the system.
    with Session(engine) as session:
        assert session.query(m.ScreenOrderObservationRecord).count() == 2


def test_an_unidentified_request_sees_no_book(seeded):
    engine, _url = seeded
    from eurogas_nexus.db import models as m

    token = portfolio_scope._current.set(portfolio_scope.DENY_ALL)
    try:
        with Session(engine) as session:
            assert session.query(m.TradingBookRecord).count() == 0
            assert session.query(m.UpstreamResourceContractRecord).count() == 0
    finally:
        portfolio_scope._current.reset(token)


def _pk_value(column, tag: str, table: str):
    if isinstance(column.type, Integer):
        return 2 if tag == LEAK else 1
    if getattr(column.type, "length", None) is None and not hasattr(column.type, "collation"):
        return _value(column, tag, 0)
    return f"{tag}-{table}-{column.name}"


def _pk(model, tag, table):
    ids = _ids(tag)
    values = []
    for column in model.__table__.primary_key.columns:
        if column.name in ids and column.name != "region":
            values.append(ids[column.name])
        else:
            values.append(_pk_value(column, tag, table))
    return values[0] if len(values) == 1 else tuple(values)


def _path_value(name: str) -> str:
    ids = _ids(LEAK)
    return ids.get(name) or f"{LEAK}-{name}"


def test_no_get_route_returns_another_entitys_rows(seeded, monkeypatch):
    _engine, url = seeded
    from eurogas_nexus.api.app import create_app
    from eurogas_nexus.db.repositories.identity import (
        create_identity_api_key,
        create_identity_principal,
    )

    monkeypatch.setenv("RUNTIME_STORE_DATABASE_URL", url)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("EUROGAS_NEXUS_DB_DSN", raising=False)
    engine = create_engine(url, future=True)
    with Session(engine) as session:
        row = create_identity_principal(
            session, name="nl-desk", display_name="NL desk", role="REVIEWER",
            data_scopes=["BOOKS:ENTITY:NL-ENT", "PERM:risk.limits.read"],
        )
        row.roles = ["ANALYST", "REVIEWER", "OPERATOR"]
        _key, bearer = create_identity_api_key(
            session, row.principal_id, display_name="t", scopes=["*"]
        )
        session.commit()
    headers = {"X-Eurogas-Api-Key": "test-public-api-token", "X-Eurogas-Identity": bearer}
    app = create_app()
    client = TestClient(app, raise_server_exceptions=False)
    leaks = []
    checked = 0
    for route_path, operations in sorted(app.openapi()["paths"].items()):
        if "get" not in operations:
            continue
        if not route_path.startswith("/api/") or "stream" in route_path:
            continue
        params = re.findall(r"{(\w+)(?::\w+)?}", route_path)
        path = route_path
        for name in params:
            path = re.sub(r"{" + name + r"(?::\w+)?}", _path_value(name), path)
        response = client.get(path, headers=headers)
        checked += 1
        if response.status_code != 200:
            continue
        body = response.text
        for name in params:
            body = body.replace(_path_value(name), "")
        if LEAK in body:
            leaks.append(f"{route_path}: {body[body.index(LEAK) - 80: body.index(LEAK) + 40]}")
    assert checked > 100
    assert leaks == []


def test_a_core_insert_into_a_book_table_gets_the_flush_rule(seeded):
    """A conflict-tolerant Core INSERT passes no before_flush event; the repository asks
    ``check_core_insert`` first, so a regional caller is refused the same way as an ORM add
    rather than writing a contract it then cannot read back."""

    engine, _url = seeded
    table = "upstream_resource_contracts"
    token = portfolio_scope._current.set(_nl_scope())
    try:
        with Session(engine) as session:
            book_scope.check_core_insert(session, table, NL_BOOK)
            with pytest.raises(portfolio_scope.BookScopeViolation):
                book_scope.check_core_insert(session, table, UK_BOOK)
            with pytest.raises(portfolio_scope.BookScopeViolation):
                book_scope.check_core_insert(session, table, None)
            with pytest.raises(portfolio_scope.BookScopeViolation):
                book_scope.check_core_insert(session, table, "no-such-book")
            # Firm-wide shared reference rows with no book stay writable.
            book_scope.check_core_insert(session, "assumption_sets", None)
    finally:
        portfolio_scope._current.reset(token)
    # Outside a request (a worker) nothing is narrowed.
    with Session(engine) as session:
        book_scope.check_core_insert(session, table, None)

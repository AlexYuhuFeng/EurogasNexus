"""Book isolation enforced at the ORM layer: one place every book-scoped read passes through.

Security review H1 found isolation applied filter by filter (``portfolio_scope.restrict``),
so a new query, worker, stream or AI path that forgot the helper failed open. This module
installs a SQLAlchemy ``do_orm_execute`` event on every :class:`~sqlalchemy.orm.Session` that
adds the request's book scope to each book-bearing table wherever it appears in a statement
(top level, joins, subqueries, relationship loads, ORM ``UPDATE``/``DELETE``), and a
``before_flush`` event that refuses a write into a book outside the scope.

Which tables are scoped is declared once, in :data:`SCOPE_RULES`:

* every mapped table with a ``book_id`` column is scoped by that column automatically, so a new
  table is covered the day it is added (rows with no book are head-office only, except where
  :data:`NULL_BOOK_SHARED` says a row with no book is firm-wide shared reference);
* tables that reach a book through another key (a contract, a cargo, a legal entity, a list of
  books, the author) carry an explicit rule;
* a table whose rows span several books and that applies its own per-row rule is listed in
  :data:`DELEGATED` with the module that applies it.

``tests/security/test_book_scope_inventory.py`` fails when a table with a book-like column is
in none of these lists. Raw ``text()`` SQL bypasses the ORM and is refused for scoped tables by
the same test.

A statement can opt out with ``execution_options(book_scope="system")``, which is what
:func:`eurogas_nexus.security.portfolio_scope.firm_wide_scope` is for: a firm-wide evaluation
a person asked for stores results for every book, and each reader is filtered when reading.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from sqlalchemy import String, and_, cast, event, false, func, literal, or_, select, true
from sqlalchemy.orm import Session, with_loader_criteria

from eurogas_nexus.security.portfolio_scope import (
    BookScope,
    BookScopeViolation,
    current_principal_ids,
    current_scope,
)

#: Tables whose rows with no book are firm-wide shared reference, visible to every scope.
NULL_BOOK_SHARED: frozenset[str] = frozenset({"assumption_sets"})

#: Tables with several books per row whose own module applies the per-row rule (a row is
#: visible when its books are), with the module that does so.
DELEGATED: dict[str, str] = {
    "opportunities": "eurogas_nexus.application.opportunities.listing",
    "market_reports": "eurogas_nexus.application.reports.store",
}

#: Tables with a book-like column that are deliberately not book data, with the reason.
NOT_BOOK_DATA: dict[str, str] = {
    "erp_references": "ERP master-data codes for counterparties: reference data, no position",
    "identity_api_keys": "the caller's own keys; access is checked by the key routes",
    "identity_local_credentials": "credential store; never served",
    "agent_research_plans": "research plans; owner checks in the agent routes",
    "assumption_set_versions": "versions of a set; the set row carries the book scope",
    "backtest_experiments": "research on public and licensed prices, no position",
    "dataset_snapshots": "research datasets; licensed-family entitlement applies",
    "strategies": "strategy definitions; owner and sharing checks (strategy_access)",
    "strategy_versions": "strategy definitions; owner and sharing checks (strategy_access)",
    "strategy_shadow_monitors": "strategy monitors; owner and sharing checks",
    "valuation_snapshots": "input version lines of an evaluation, no position",
}


def _book_clause(scope: BookScope, books_table: Any) -> Any:
    """SQL: the books (``trading_books`` rows) ``scope`` allows."""

    if scope.all_books:
        return true()
    terms = []
    if scope.books:
        terms.append(func.upper(books_table.book_id).in_(sorted(scope.books)))
    if scope.entities:
        terms.append(func.upper(books_table.legal_entity).in_(sorted(scope.entities)))
    if scope.regions:
        terms.append(func.upper(books_table.region).in_(sorted(scope.regions)))
    return or_(*terms) if terms else false()


def _models() -> Any:
    from eurogas_nexus.db import models

    return models


def _visible_books(scope: BookScope) -> Any:
    tb = _models().TradingBookRecord
    return select(tb.book_id).where(_book_clause(scope, tb)).scalar_subquery()


def _visible_entities(scope: BookScope) -> Any:
    tb = _models().TradingBookRecord
    entities = select(func.upper(tb.legal_entity)).where(_book_clause(scope, tb))
    return or_(
        func.upper(_models().CreditLineRecord.legal_entity).in_(entities.scalar_subquery()),
        func.upper(_models().CreditLineRecord.legal_entity).in_(sorted(scope.entities))
        if scope.entities
        else false(),
    )


def _visible_contracts(scope: BookScope) -> Any:
    m = _models()
    books = _visible_books(scope)
    return (
        select(m.UpstreamResourceContractRecord.contract_id)
        .where(m.UpstreamResourceContractRecord.book_id.in_(books))
        .union(
            select(m.PipelineSupplyRecord.contract_id).where(
                m.PipelineSupplyRecord.book_id.in_(books)
            ),
            select(m.LngDeliveryObligationRecord.contract_id).where(
                m.LngDeliveryObligationRecord.book_id.in_(books)
            ),
        )
        .scalar_subquery()
    )


def _visible_cargoes(scope: BookScope) -> Any:
    m = _models()
    return (
        select(m.LngCargoRecord.cargo_id)
        .where(m.LngCargoRecord.book_id.in_(_visible_books(scope)))
        .scalar_subquery()
    )


def _json_names_any(column: Any, scope: BookScope) -> Any:
    """SQL: a JSON list of book ids names at least one visible book (portable LIKE)."""

    tb = _models().TradingBookRecord
    pattern = literal('%"') + tb.book_id + literal('"%')
    return (
        select(tb.book_id)
        .where(_book_clause(scope, tb), cast(column, String).like(pattern))
        .exists()
    )


def _case_clause(scope: BookScope) -> Any:
    case = _models().DecisionCaseRecord
    principal = current_principal_ids()
    terms = [case.portfolio_ref == "", case.portfolio_ref.in_(_visible_books(scope))]
    if principal:
        terms.append(case.created_by.in_(principal))
    return or_(*terms)


def _snapshot_clause(scope: BookScope) -> Any:
    m = _models()
    snap = m.AnalysisSnapshotRecord
    principal = current_principal_ids()
    cases = select(m.DecisionCaseRecord.snapshot_id).where(
        m.DecisionCaseRecord.snapshot_id != "", _case_clause(scope)
    )
    terms = [snap.snapshot_id.in_(cases.scalar_subquery())]
    if principal:
        terms.append(snap.created_by.in_(principal))
    return or_(*terms)


ExplicitRule = Callable[[BookScope], Any]


def _explicit_rules() -> dict[str, tuple[str, ExplicitRule]]:
    """table name -> (model class name, scope -> criteria)."""

    m = _models()
    return {
        "trading_books": (
            "TradingBookRecord",
            lambda s: _book_clause(s, m.TradingBookRecord),
        ),
        "credit_lines": ("CreditLineRecord", _visible_entities),
        "trader_mandates": (
            "TraderMandateRecord",
            lambda s: _json_names_any(m.TraderMandateRecord.book_ids, s),
        ),
        "hedge_approvals": (
            "HedgeApprovalRecord",
            lambda s: m.HedgeApprovalRecord.contract_id.in_(_visible_contracts(s)),
        ),
        "contract_daily_deliveries": (
            "ContractDeliveryRecord",
            lambda s: m.ContractDeliveryRecord.contract_id.in_(_visible_contracts(s)),
        ),
        "upstream_contract_revisions": (
            "UpstreamContractRevisionRecord",
            lambda s: m.UpstreamContractRevisionRecord.contract_id.in_(_visible_contracts(s)),
        ),
        "capacity_profiles": (
            "CapacityProfileRecord",
            lambda s: m.CapacityProfileRecord.contract_id.in_(_visible_contracts(s)),
        ),
        "lng_cargo_hedges": (
            "LngCargoHedgeRecord",
            lambda s: m.LngCargoHedgeRecord.cargo_id.in_(_visible_cargoes(s)),
        ),
        "lng_voyage_terms": (
            "LngVoyageTermsRecord",
            lambda s: m.LngVoyageTermsRecord.cargo_id.in_(_visible_cargoes(s)),
        ),
        "decision_cases": ("DecisionCaseRecord", _case_clause),
        "decision_case_records": (
            "DecisionCaseDecisionRecord",
            lambda s: m.DecisionCaseDecisionRecord.case_id.in_(
                select(m.DecisionCaseRecord.case_id).where(_case_clause(s)).scalar_subquery()
            ),
        ),
        "analysis_snapshots": ("AnalysisSnapshotRecord", _snapshot_clause),
    }


def book_column_tables() -> dict[str, Any]:
    """table name -> model class, for every mapped table with a ``book_id`` column."""

    from eurogas_nexus.db.base import Base

    _models()
    found: dict[str, Any] = {}
    for mapper in Base.registry.mappers:
        table = getattr(mapper, "local_table", None)
        if table is None or "book_id" not in table.c:
            continue
        found[table.name] = mapper.class_
    return found


def scoped_tables() -> set[str]:
    """Every table the ORM event narrows."""

    return set(book_column_tables()) | set(_explicit_rules())


def _criteria(scope: BookScope) -> list[Any]:
    m = _models()
    options: list[Any] = []
    explicit = _explicit_rules()
    for table, model in book_column_tables().items():
        if table in explicit:
            continue
        visible = model.book_id.in_(_visible_books(scope))
        if table in NULL_BOOK_SHARED:
            visible = or_(model.book_id.is_(None), visible)
        options.append(with_loader_criteria(model, visible, include_aliases=True))
    for _table, (class_name, rule) in explicit.items():
        options.append(
            with_loader_criteria(getattr(m, class_name), rule(scope), include_aliases=True)
        )
    return options


def _restricted_scope(options: dict[str, Any]) -> BookScope | None:
    if options.get("book_scope") == "system":
        return None
    scope = current_scope()
    if scope is None or scope.all_books:
        return None
    return scope


def _on_execute(state: Any) -> None:
    if not (state.is_select or state.is_update or state.is_delete):
        return
    if state.is_column_load:
        # Refreshing an attribute of a row already loaded under the same scope.
        return
    scope = _restricted_scope(state.execution_options)
    if scope is None:
        return
    state.statement = state.statement.options(*_criteria(scope))


def _on_flush(session: Session, _context: Any, _instances: Any) -> None:
    scope = _restricted_scope({})
    if scope is None:
        return
    tables = book_column_tables()
    for obj in session.new:
        table = getattr(getattr(obj, "__table__", None), "name", None)
        if table in tables and table not in NULL_BOOK_SHARED and not getattr(obj, "book_id", None):
            # A row outside any book is head-office only: a regional caller who wrote one
            # could never read it back, so the write is refused with a clear reason.
            raise BookScopeViolation(table, "(no book)")
    pending = [
        obj
        for obj in (*session.new, *session.dirty)
        if getattr(getattr(obj, "__table__", None), "name", None) in tables
        and getattr(obj, "book_id", None)
    ]
    if not pending:
        return
    tb = _models().TradingBookRecord
    with session.no_autoflush:
        allowed = set(
            session.execute(
                select(tb.book_id).where(_book_clause(scope, tb)),
                execution_options={"book_scope": "system"},
            ).scalars()
        )
        for obj in pending:
            table = obj.__table__.name
            if table == "trading_books":
                # A new book is visible by its own entity/region/book id once written.
                if scope.allows(obj.book_id, getattr(obj, "legal_entity", None),
                                getattr(obj, "region", None)):
                    continue
                raise BookScopeViolation(table, obj.book_id)
            if obj.book_id not in allowed:
                raise BookScopeViolation(table, obj.book_id)


_INSTALLED = False


def install() -> None:
    """Install the scope events on every Session (idempotent)."""

    global _INSTALLED
    if _INSTALLED:
        return
    event.listen(Session, "do_orm_execute", _on_execute)
    event.listen(Session, "before_flush", _on_flush)
    _INSTALLED = True


__all__ = [
    "DELEGATED",
    "NOT_BOOK_DATA",
    "NULL_BOOK_SHARED",
    "BookScopeViolation",
    "book_column_tables",
    "install",
    "scoped_tables",
]

_ = and_  # re-exported helpers kept for rule authors

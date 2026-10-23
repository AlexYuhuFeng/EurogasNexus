"""Strategy ownership ACL, independent of (and additional to) role/data grants."""

from fastapi import HTTPException
from sqlalchemy import and_, exists, or_, select
from sqlalchemy.orm import Session

from eurogas_nexus.db.models import (
    IdentityGroupMemberRecord,
    IdentityGroupRecord,
    IdentityPrincipalRecord,
    StrategyGroupShareRecord,
    StrategyRecord,
)


def visible_strategy_clause(principal_id: str | None):
    active_principal = exists(
        select(IdentityPrincipalRecord.principal_id).where(
            IdentityPrincipalRecord.principal_id == principal_id,
            IdentityPrincipalRecord.status == "ACTIVE",
        )
    )
    shared_group = exists(
        select(StrategyGroupShareRecord.strategy_id)
        .join(
            IdentityGroupRecord, IdentityGroupRecord.group_id == StrategyGroupShareRecord.group_id
        )
        .join(
            IdentityGroupMemberRecord,
            IdentityGroupMemberRecord.group_id == IdentityGroupRecord.group_id,
        )
        .where(
            StrategyGroupShareRecord.strategy_id == StrategyRecord.strategy_id,
            IdentityGroupRecord.status == "ACTIVE",
            IdentityGroupMemberRecord.principal_id == principal_id,
        )
    )
    return and_(
        active_principal,
        StrategyRecord.owner_principal_id.is_not(None),
        or_(
            StrategyRecord.owner_principal_id == principal_id,
            StrategyRecord.visibility == "PUBLIC",
            and_(StrategyRecord.visibility == "GROUPS", shared_group),
        ),
    )


def visible_strategy_ids(session: Session, principal_id: str | None) -> set[str]:
    return set(
        session.scalars(
            select(StrategyRecord.strategy_id).where(visible_strategy_clause(principal_id))
        )
    )


def can_read_strategy(session: Session, strategy_id: str | None, principal_id: str | None) -> bool:
    if not strategy_id or not principal_id:
        return False
    return (
        session.scalar(
            select(StrategyRecord.strategy_id).where(
                StrategyRecord.strategy_id == strategy_id,
                visible_strategy_clause(principal_id),
            )
        )
        is not None
    )


def require_strategy_access(
    session: Session, strategy_id: str, principal_id: str | None, *, write: bool = False
) -> StrategyRecord:
    query = select(StrategyRecord).where(
        StrategyRecord.strategy_id == strategy_id, visible_strategy_clause(principal_id)
    )
    if write:
        query = query.where(StrategyRecord.owner_principal_id == principal_id).with_for_update()
    row = session.scalar(query)
    if row is None:
        raise HTTPException(status_code=404, detail="Strategy not found")
    return row


def require_named_principal(session: Session, principal_id: str | None) -> str:
    principal = session.get(IdentityPrincipalRecord, principal_id) if principal_id else None
    if principal is None or principal.status != "ACTIVE":
        raise HTTPException(
            status_code=403, detail="A named active identity is required to own a strategy"
        )
    return principal.principal_id

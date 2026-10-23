"""Local group membership and owner-selected strategy read sharing."""

from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from eurogas_nexus.db.base import Base


class IdentityGroupRecord(Base):
    __tablename__ = "identity_groups"
    group_id: Mapped[str] = mapped_column(String(80), primary_key=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="ACTIVE", server_default="ACTIVE"
    )


class IdentityGroupMemberRecord(Base):
    __tablename__ = "identity_group_members"
    group_id: Mapped[str] = mapped_column(
        String(80), ForeignKey("identity_groups.group_id", ondelete="CASCADE"), primary_key=True
    )
    principal_id: Mapped[str] = mapped_column(
        String(80),
        ForeignKey("identity_principals.principal_id", ondelete="CASCADE"),
        primary_key=True,
    )


class StrategyGroupShareRecord(Base):
    __tablename__ = "strategy_group_shares"
    strategy_id: Mapped[str] = mapped_column(
        String(128), ForeignKey("strategies.strategy_id", ondelete="CASCADE"), primary_key=True
    )
    group_id: Mapped[str] = mapped_column(
        String(80), ForeignKey("identity_groups.group_id", ondelete="CASCADE"), primary_key=True
    )

"""Local identity groups and membership (neutral identity storage).

Groups are managed by an administrator (``/api/access/groups``) and listed to their
members (``/api/me/groups``). Their only reader before 2026-11-27 was the strategy
laboratory's group sharing, removed with it; the groups and memberships stay as identity
data. No strategy-specific state lives here.
"""

from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from eurogas_nexus.db.base import Base


class IdentityGroupRecord(Base):
    """One local group an administrator can manage."""

    __tablename__ = "identity_groups"
    group_id: Mapped[str] = mapped_column(String(80), primary_key=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="ACTIVE", server_default="ACTIVE"
    )


class IdentityGroupMemberRecord(Base):
    """Membership of one principal in one group."""

    __tablename__ = "identity_group_members"
    group_id: Mapped[str] = mapped_column(
        String(80), ForeignKey("identity_groups.group_id", ondelete="CASCADE"), primary_key=True
    )
    principal_id: Mapped[str] = mapped_column(
        String(80),
        ForeignKey("identity_principals.principal_id", ondelete="CASCADE"),
        primary_key=True,
    )

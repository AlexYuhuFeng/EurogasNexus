"""Which governed writes need two people (P-17 maker-checker), and the setting that says so.

A change to a limit or to reference data that moves money or risk is proposed by one person
and takes effect only when a different authorised person approves it (four eyes, segregation
of duties as in an ETRM or a bank's market-risk controls). Each such write is listed here with
who may approve it. An administrator can switch the requirement off per write in the
organisation settings (``four_eyes``); that switch is itself a governed, audited write.

``approver`` is one of:

* ``risk_function``: REVIEWER held and no front-office role (``security/segregation.py``),
  as for setting the limit itself; for firm marks this is the independent price check;
* ``desk``: anyone who may make the change themselves (portfolio write).

Approved assumption sets are not listed: a version is a draft until a different person in the
risk function approves it (CP-07), always, and no setting turns that off.

需要双人复核（四眼原则）的受治理写入，以及控制它的组织设置 ``four_eyes``。
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

FOUR_EYES_SETTING = "four_eyes"

RISK_FUNCTION = "risk_function"
DESK = "desk"


@dataclass(frozen=True, slots=True)
class FourEyesWrite:
    """One governed write that a second person approves before it takes effect."""

    action: str
    kind: str
    label: str
    label_zh: str
    approver: str
    default_on: bool = True


#: The writes under maker-checker, default on: each moves money or risk.
FOUR_EYES_WRITES: tuple[FourEyesWrite, ...] = (
    FourEyesWrite(
        "risk.credit_line.update", "credit_line", "Credit line", "信用额度", RISK_FUNCTION
    ),
    FourEyesWrite(
        "risk.mandate.update", "trader_mandate", "Trader mandate", "交易员授权", RISK_FUNCTION
    ),
    FourEyesWrite(
        "risk.hedge_approval.update",
        "hedge_approval",
        "Deal hedge band",
        "单笔对冲区间",
        RISK_FUNCTION,
    ),
    FourEyesWrite(
        "market.firm_marks.update", "firm_marks", "Firm marks", "公司估值标记", RISK_FUNCTION
    ),
    FourEyesWrite(
        "lng.terminal_terms.update",
        "lng_terminal_terms",
        "LNG terminal terms",
        "LNG 接收站条款",
        DESK,
    ),
    FourEyesWrite("lng.freight_route", "freight_route", "Freight route", "航运路线", DESK),
)

FOUR_EYES_BY_ACTION: dict[str, FourEyesWrite] = {write.action: write for write in FOUR_EYES_WRITES}
FOUR_EYES_BY_KIND: dict[str, FourEyesWrite] = {write.kind: write for write in FOUR_EYES_WRITES}


class FourEyesSettingError(ValueError):
    """The ``four_eyes`` setting names an unknown write or a value that is not a boolean."""


def validate_four_eyes(values: Any) -> dict[str, bool]:
    """The ``four_eyes`` setting: listed writes only, each ``true`` or ``false``."""

    if not isinstance(values, Mapping) or not values:
        raise FourEyesSettingError(f"{FOUR_EYES_SETTING} must map governed writes to true or false")
    unknown = sorted(str(key) for key in values if key not in FOUR_EYES_BY_ACTION)
    if unknown:
        raise FourEyesSettingError(f"{unknown[0]} is not a write that four eyes can govern")
    if any(not isinstance(value, bool) for value in values.values()):
        raise FourEyesSettingError(f"each {FOUR_EYES_SETTING} value must be true or false")
    return {str(key): bool(value) for key, value in values.items()}


def four_eyes_in_force(stored: Any) -> dict[str, bool]:
    """Each listed write and whether it needs a second person: the default, then the setting.

    A stored value that is not a mapping, or names a write no longer listed, is ignored, so
    a bad row never switches the control off.
    """

    effective = {write.action: write.default_on for write in FOUR_EYES_WRITES}
    if isinstance(stored, Mapping):
        for key, value in stored.items():
            if key in effective and isinstance(value, bool):
                effective[str(key)] = value
    return effective


__all__ = [
    "DESK",
    "FOUR_EYES_BY_ACTION",
    "FOUR_EYES_BY_KIND",
    "FOUR_EYES_SETTING",
    "FOUR_EYES_WRITES",
    "RISK_FUNCTION",
    "FourEyesSettingError",
    "FourEyesWrite",
    "four_eyes_in_force",
    "validate_four_eyes",
]

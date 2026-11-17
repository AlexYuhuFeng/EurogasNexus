"""Data-quality classes of a valuation input and the weakest-input rule.

Commercial product design basis 2, section B.2: every input on a value path carries one
class, and the result's class is the weakest input on that path. A firm's own mark is never
"sourced"; a simulated input is never mixed silently with real ones, because the weakest-
class rule makes any result that touched one "simulated".
"""

from __future__ import annotations

from collections.abc import Iterable
from enum import StrEnum


class InputClass(StrEnum):
    """Where a valuation input comes from, strongest first."""

    #: Licensed (through the customer's entitlement) or public data, named.
    SOURCED = "sourced"
    #: Computed from sourced inputs by a named method (forward FX by interest parity).
    DERIVED = "derived"
    #: The customer's own price mark. Never "sourced", whoever entered it.
    FIRM_MARK = "firm_mark"
    #: A settlement, mid or a provisional publication: real, but not executable or final.
    INDICATIVE = "indicative"
    #: A value from the firm's assumption set or entered by the user.
    ASSUMPTION = "assumption"
    #: Demo data. Valid only on a demo desk, and then always shown as such.
    SIMULATED = "simulated"
    #: Not held. A value path with a missing input cannot be evaluated.
    MISSING = "missing"


#: Strength order (higher is stronger). The overall grade is the minimum.
STRENGTH: dict[InputClass, int] = {
    InputClass.SOURCED: 6,
    InputClass.DERIVED: 5,
    InputClass.FIRM_MARK: 4,
    InputClass.INDICATIVE: 3,
    InputClass.ASSUMPTION: 2,
    InputClass.SIMULATED: 1,
    InputClass.MISSING: 0,
}

#: The words a reader sees for each class.
CLASS_LABEL: dict[InputClass, str] = {
    InputClass.SOURCED: "sourced",
    InputClass.DERIVED: "derived",
    InputClass.FIRM_MARK: "firm's mark",
    InputClass.INDICATIVE: "indicative",
    InputClass.ASSUMPTION: "assumption",
    InputClass.SIMULATED: "simulated",
    InputClass.MISSING: "missing",
}


def weakest(classes: Iterable[InputClass | str]) -> InputClass:
    """Return the weakest class of the inputs on a value path.

    Args:
        classes: The classes of every input the value depends on.

    Returns:
        The weakest class; ``MISSING`` for an empty path (nothing to stand on).
    """

    resolved = [InputClass(value) for value in classes]
    if not resolved:
        return InputClass.MISSING
    return min(resolved, key=STRENGTH.__getitem__)


def is_real(value: InputClass | str) -> bool:
    """Whether an input class describes real data (anything but simulated or missing)."""

    return InputClass(value) not in {InputClass.SIMULATED, InputClass.MISSING}

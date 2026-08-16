"""Actor principal validation tests."""

import pytest

from eurogas_nexus.domain.identity.principal import (
    PrincipalValidationError,
    normalize_principal,
)


def test_normalize_principal_accepts_operator_identifiers() -> None:
    assert normalize_principal("trader-a") == "trader-a"
    assert normalize_principal("  ops-user  ") == "ops-user"
    assert normalize_principal("analyst.alice") == "analyst.alice"
    assert normalize_principal("ops@nexus") == "ops@nexus"
    assert normalize_principal("svc-1_2") == "svc-1_2"


@pytest.mark.parametrize(
    "value",
    [
        None,
        "",
        "   ",
        "-leading",
        "no spaces allowed",
        "tab\tinside",
        "x" * 65,
        "emoji🙂",
    ],
)
def test_normalize_principal_rejects_invalid_values(value) -> None:
    with pytest.raises(PrincipalValidationError):
        normalize_principal(value)

"""TSO access three-state constraint tests."""

from eurogas_nexus.domain.constraints.access import (
    inaccessible_tsos,
    tso_access_status,
)
from eurogas_nexus.domain.ontology.vocabulary import AccessStatus


def test_access_status_confirmed_when_nothing_required() -> None:
    assert tso_access_status([], None) is AccessStatus.CONFIRMED
    assert tso_access_status([], []) is AccessStatus.CONFIRMED


def test_access_status_unknown_when_no_access_list_supplied() -> None:
    # Fail-closed: unknown access must never be interpreted as granted.
    assert tso_access_status(["BBL Company"], None) is AccessStatus.UNKNOWN


def test_access_status_denied_when_empty_list_supplied() -> None:
    assert tso_access_status(["BBL Company"], []) is AccessStatus.DENIED


def test_access_status_confirmed_when_all_required_accessible() -> None:
    assert (
        tso_access_status(["BBL Company"], ["bbl company"]) is AccessStatus.CONFIRMED
    )


def test_access_status_denied_when_any_required_missing() -> None:
    assert (
        tso_access_status(["BBL Company", "IUK"], ["BBL Company"])
        is AccessStatus.DENIED
    )


def test_inaccessible_tsos_unknown_access_fails_closed() -> None:
    # Unknown access reports every required TSO as inaccessible.
    assert inaccessible_tsos(["BBL Company"], None) == ["BBL Company"]


def test_inaccessible_tsos_fails_closed_on_empty_supplied_list() -> None:
    assert inaccessible_tsos(["BBL Company"], []) == ["BBL Company"]


def test_inaccessible_tsos_matches_case_insensitively() -> None:
    assert inaccessible_tsos(["BBL Company"], ["bbl company"]) == []


def test_inaccessible_tsos_reports_missing_tsos() -> None:
    result = inaccessible_tsos(
        ["BBL Company", "IUK"],
        ["BBL Company"],
    )
    assert result == ["IUK"]


def test_inaccessible_tsos_strips_whitespace() -> None:
    assert inaccessible_tsos(["  BBL Company  "], ["BBL Company"]) == []

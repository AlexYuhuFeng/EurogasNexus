"""TSO access fail-closed constraint tests."""

from eurogas_nexus.domain.constraints.access import inaccessible_tsos


def test_inaccessible_tsos_empty_when_no_access_list_supplied() -> None:
    assert inaccessible_tsos(["BBL Company"], None) == []


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

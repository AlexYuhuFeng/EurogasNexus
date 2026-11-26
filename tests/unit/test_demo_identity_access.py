"""Every demo and test identity gets the access its role is documented to have, and no more.

The owner signed in as a demo trader and saw no data (2026-11-17). Access was not the cause
(the reads timed out), but nothing held the demo identities to the documented matrix either.
This test does: the identities the demo start-up creates (``TESTERS``, the ``test_*``
accounts that copy them) are compared with the table in docs/deployment/SELF_HOSTED_DEMO.md
and with what docs/product/ROLES_AND_RESPONSIBILITIES.md says each role and job function may
do, through the server's own permission table.
"""

from __future__ import annotations

import importlib.util
import re
from pathlib import Path

import pytest

from eurogas_nexus.security.authorization import (
    COMMERCIAL_PERMISSIONS,
    ROLE_PERMISSIONS,
    Permission,
    Role,
)

ROOT = Path(__file__).resolve().parents[2]
DOC = (ROOT / "docs/deployment/SELF_HOSTED_DEMO.md").read_text(encoding="utf-8")
EXAMPLE = (ROOT / "deploy/demo/.env.example").read_text(encoding="utf-8")


def _start():
    spec = importlib.util.spec_from_file_location(
        "start_public_demo", ROOT / "scripts/demo/start_public_demo.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


START = _start()


def _permissions(roles) -> set[str]:
    granted: set[str] = set()
    for role in roles:
        granted |= {permission.value for permission in ROLE_PERMISSIONS[Role(role)]}
    return granted


#: What each demo identity may do, from the documents (True: must hold; False: must not).
EXPECTED: dict[str, dict[str, bool]] = {
    "tester": {"market": True, "book_write": True, "review_record": True, "admin": True},
    "demo.trader": {"market": True, "book_write": True, "review_record": False, "admin": False},
    "demo.nl.trader": {"market": True, "book_write": True, "review_record": False, "admin": False},
    "demo.analyst": {"market": True, "book_write": True, "review_record": False, "admin": False},
    "demo.risk": {"market": True, "book_write": False, "review_record": True, "admin": False},
    "demo.manager": {"market": True, "book_write": False, "review_record": True, "admin": False},
    "demo.finance": {"market": True, "book_write": False, "review_record": False, "admin": False},
    "demo.compliance": {"market": True, "book_write": False, "review_record": True,
                        "admin": False},
    "demo.ops": {"market": True, "book_write": False, "review_record": False, "admin": False},
    "demo.originator": {"market": True, "book_write": True, "review_record": False,
                        "admin": False},
    "demo.operations": {"market": True, "book_write": False, "review_record": False,
                        "admin": False},
    # The platform administrator sees no commercial data, by design.
    "demo.admin": {"market": False, "book_write": False, "review_record": False, "admin": True},
}


def _documented_rows() -> dict[str, list[str]]:
    rows = {}
    for match in re.finditer(r"^\| `([a-z.]+)` \| ([A-Z, ]+) \|", DOC, re.MULTILINE):
        rows[match.group(1)] = [role.strip() for role in match.group(2).split(",")]
    return rows


def test_every_tester_is_in_the_documented_table_with_the_same_roles():
    documented = _documented_rows()
    created = {name: list(roles) for name, _d, _r, roles, _f, _o in START.TESTERS}
    assert set(created) == set(documented) == set(EXPECTED)
    for name, roles in created.items():
        assert sorted(roles) == sorted(documented[name]), name


@pytest.mark.parametrize("name", sorted(EXPECTED))
def test_effective_access_matches_the_role_matrix(name):
    _n, _display, primary, roles, functions, _office = START.TESTER_BY_NAME[name]
    assert primary in roles
    granted = _permissions(roles)
    expected = EXPECTED[name]
    assert (Permission.MARKET_READ.value in granted) is expected["market"], name
    assert (Permission.PORTFOLIO_WRITE.value in granted) is expected["book_write"], name
    assert (Permission.REVIEW_RECORD.value in granted) is expected["review_record"], name
    assert (Permission.IDENTITY_MANAGE.value in granted) is expected["admin"], name
    if expected["market"] and name != "demo.ops":
        # Commercial reads the desk pages make: a role that reads the market reads the book.
        assert Permission.PORTFOLIO_READ.value in granted, name
    elif name == "demo.ops":
        # Source operations read no positions by role (security review H1).
        assert Permission.PORTFOLIO_READ.value not in granted, name
    else:
        assert not granted & {permission.value for permission in COMMERCIAL_PERMISSIONS}, name
    assert functions, f"{name} has no job function, so no home screen"


def test_every_demo_identity_reads_every_data_scope_of_the_demo():
    """Data scopes gate licensed and simulated families: every commercial tester reads every
    family the demo carries, and sees only the books its desk is entitled to (H1)."""

    from eurogas_nexus.security.portfolio_scope import scope_from_data_scopes

    assert set(START.TESTER_SCOPES) == set(EXPECTED)
    for name, scopes in START.TESTER_SCOPES.items():
        if not EXPECTED[name]["market"]:
            assert scopes == (), name
            continue
        assert "*" in scopes or set(START.DEMO_SOURCE_FAMILIES) <= set(scopes), name
    uk = scope_from_data_scopes(START.TESTER_SCOPES["demo.trader"])
    nl = scope_from_data_scopes(START.TESTER_SCOPES["demo.nl.trader"])
    assert uk.allows("demo-uk-nbp", "NWG-UK", "europe")
    assert not uk.allows("demo-nl-ttf", "NWG-NL", "europe")
    assert nl.allows("demo-nl-ttf", "NWG-NL", "europe")
    assert not nl.allows("demo-uk-nbp", "NWG-UK", "europe")
    ops = scope_from_data_scopes(START.TESTER_SCOPES["demo.ops"])
    assert not ops.allows("demo-uk-nbp", "NWG-UK", "europe")
    assert scope_from_data_scopes(START.TESTER_SCOPES["demo.risk"]).all_books


def test_test_accounts_copy_a_documented_tester_and_only_test_admin_is_admin():
    line = next(
        row for row in EXAMPLE.splitlines()
        if row.startswith("# EUROGAS_NEXUS_DEMO_TEST_ACCOUNTS=")
    )
    accounts = line.split("=", 1)[1].split(",")
    names = [entry.split(":")[0] for entry in accounts]
    assert names == [
        "test_trader", "test_nl_trader", "test_analyst", "test_risk", "test_manager",
        "test_finance", "test_compliance", "test_ops", "test_admin",
    ]
    from eurogas_nexus.application.local_accounts import parse_demo_accounts

    for spec in parse_demo_accounts(",".join(accounts)):
        assert spec.template in START.TESTER_BY_NAME, spec.username
        roles = START.TESTER_BY_NAME[spec.template][3]
        assert ("ADMIN" in roles) is (spec.username == "test_admin"), spec.username
        assert f"| `{spec.username}` | `{spec.template}` |" in DOC, spec.username

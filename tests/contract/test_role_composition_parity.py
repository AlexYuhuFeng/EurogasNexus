"""The client's role composition registry follows the server's job functions and roles.

Client tests never read backend sources (FF1), so the parity is checked from this side:
``clients/web/src/app/experience/roleComposition.ts`` names every ``FunctionalAssignment``,
and the role -> permission table ``clients/web/tests/roleComposition.test.ts`` proves the
registry against (I11, I12) is the server's ``ROLE_PERMISSIONS``.
"""

from __future__ import annotations

import re
from pathlib import Path

from eurogas_nexus.security.authorization import ROLE_PERMISSIONS
from eurogas_nexus.security.capabilities import FunctionalAssignment

ROOT = Path(__file__).resolve().parents[2]
REGISTRY = ROOT / "clients/web/src/app/experience/roleComposition.ts"
REGISTRY_TEST = ROOT / "clients/web/tests/roleComposition.test.ts"


def test_every_job_function_is_in_the_registry() -> None:
    text = REGISTRY.read_text(encoding="utf-8")
    block = text[text.index("export const JOB_FUNCTION_IDS") : text.index("] as const;")]
    declared = set(re.findall(r'"([A-Z_]+)"', block))
    assert declared == {item.value for item in FunctionalAssignment}
    for item in FunctionalAssignment:
        assert re.search(rf"^\s+{item.value}: \"[a-z_]+\",$", text, re.MULTILINE), item


def test_the_registry_test_proves_against_the_server_role_table() -> None:
    text = REGISTRY_TEST.read_text(encoding="utf-8")
    start = text.index("const ROLE_PERMISSIONS")
    block = text[start : text.index("};", start)]
    table = {
        role: set(re.findall(r'"([a-z_.]+)"', values))
        for role, values in re.findall(r"^\s+([A-Z]+): \[(.*)\],$", block, re.MULTILINE)
    }
    assert table == {
        role.value: {permission.value for permission in permissions}
        for role, permissions in ROLE_PERMISSIONS.items()
    }

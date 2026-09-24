"""Browser acceptance probes must read routes the application actually serves.

The sweep in ``scripts/uat/browser_workflow_smoke.mjs`` reads each surface's own
endpoint from the browser session and compares the rows it returned with what the
surface rendered. A probe that asks for a path no route declares measures
nothing: it records its own 404 as a console error while the surface under test is
never compared with its data. That is what happened to ``contracts``, which asked
for ``/api/contracts/upstream?limit=5`` (run 35888959943); the real read is
``GET /api/route-cost/upstream-contracts``.

The harness itself needs a browser, a migrated database and a seeded identity to
run, so the probe declarations are read from its source and held against the
application's declared GET surface here.
"""

from __future__ import annotations

import re
from pathlib import Path

from apps.api.main import app

ROOT = Path(__file__).resolve().parents[2]
HARNESS = ROOT / "scripts" / "uat" / "browser_workflow_smoke.mjs"
WEB_CLIENT = ROOT / "clients" / "web" / "src" / "api" / "client.ts"

#: The one probe path this repair replaced; it was never a declared route.
RETIRED_CONTRACTS_PROBE = "/api/contracts/upstream"

SIGNALS_BLOCK = re.compile(r"const SURFACE_SIGNALS = \{(?P<body>.*?)\n\};", re.DOTALL)
SIGNAL_ENTRY = re.compile(
    r'^\s{2}(?P<workspace>[a-z_]+): \{.*?apiPath: (?P<path>"[^"]*"|null)',
    re.MULTILINE,
)
WORKSPACES_BLOCK = re.compile(r"const WORKSPACES = \[(?P<body>.*?)\]", re.DOTALL)
WORKSPACE_ID = re.compile(r'"([a-z]+)"')


def _signals_source() -> str:
    match = SIGNALS_BLOCK.search(HARNESS.read_text(encoding="utf-8"))
    assert match, "SURFACE_SIGNALS is still declared in the browser sweep"
    return match.group("body")


def _declared_probes() -> dict[str, str | None]:
    probes: dict[str, str | None] = {}
    for match in SIGNAL_ENTRY.finditer(_signals_source()):
        raw = match.group("path")
        probes[match.group("workspace")] = None if raw == "null" else raw.strip('"')
    return probes


def _declared_workspaces() -> set[str]:
    match = WORKSPACES_BLOCK.search(HARNESS.read_text(encoding="utf-8"))
    assert match, "WORKSPACES is still declared in the browser sweep"
    return set(WORKSPACE_ID.findall(match.group("body")))


def _served_get_paths() -> set[str]:
    operations_by_path = app.openapi()["paths"]
    return {path for path, methods in operations_by_path.items() if "get" in methods}


def test_every_workspace_declares_a_probe_for_the_sweep() -> None:
    probes = _declared_probes()
    assert len(probes) >= 16, "the sweep still declares a signal per workspace"
    assert set(probes) == _declared_workspaces(), (
        "every declared workspace has a signal, and no signal names a workspace the sweep "
        "does not visit"
    )


def test_every_declared_probe_reads_a_served_get_route() -> None:
    served = _served_get_paths()
    for workspace, target in _declared_probes().items():
        if target is None:
            continue
        path = target.split("?", 1)[0]
        assert path in served, f"{workspace} probes a path no GET route serves: {path}"


def test_the_contracts_probe_reads_the_upstream_terms_the_client_reads() -> None:
    probes = _declared_probes()

    assert probes["contracts"] == "/api/route-cost/upstream-contracts"
    assert not any(
        target is not None and target.startswith(RETIRED_CONTRACTS_PROBE)
        for target in probes.values()
    ), "the sweep no longer probes the retired, undeclared contracts path"

    # The probe is the surface's own read, not a privileged one: the client lane that fills the
    # portfolio pool asks for the same path. The client composes it against its own base URL, so
    # the `/api` prefix the probe needs is not part of the literal the client declares.
    client = WEB_CLIENT.read_text(encoding="utf-8")
    client_path = probes["contracts"].removeprefix("/api")
    assert client_path.startswith("/"), "the probe names an absolute public path"
    assert f'"{client_path}"' in client

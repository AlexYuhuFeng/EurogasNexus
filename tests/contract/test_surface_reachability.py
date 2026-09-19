"""Surface reachability: every public route is reached, machine-only, or deliberate.

The D3 census measured client methods -> surfaces, and closed that set to zero. The other direction
was never measured: a declared public route that no client calls. Run over the whole web source
(stream subscriptions live in `stores/api.ts`, not in the transport), **36 of the 178 public paths
are not reached from the web client**, and 10 of those are called by nobody at all.

This gate makes that state declared instead of accidental. Every public path must fall into exactly
one bucket, and each non-obvious entry carries its reason:

- **reached**: the web client calls it (a path literal appears in `clients/web/src`);
- **machine surface**: a read or engine the SDK/CLI/MCP callers use by design and the product does
  not need on a screen... except the four engines `W0-03` D8 records as the *surface gap*, which are
  listed as such rather than excused;
- **deliberate**: probes, a browser redirect target, control-plane administration and the recorded
  unconsumed projection.

The check is textual, and says so: it cannot tell a call from a comment, and it cannot see a URL a
caller builds from parts. It is a drift alarm, not a proof of reachability - what caught the last
three real defects was the browser sweep, not this.
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WEB_SRC = ROOT / "clients" / "web" / "src"


def _client_source() -> str:
    return "\n".join(
        path.read_text(encoding="utf-8", errors="ignore")
        for path in sorted(WEB_SRC.rglob("*.ts*"))
    )


def _machine_source() -> dict[str, str]:
    sdk_dir = ROOT / "packages" / "python-sdk" / "src" / "eurogas_nexus_sdk"
    return {
        "sdk": "\n".join(path.read_text(encoding="utf-8") for path in sorted(sdk_dir.glob("*.py"))),
        "cli": (ROOT / "src" / "eurogas_nexus" / "cli" / "commands.py").read_text(encoding="utf-8"),
        "mcp": (ROOT / "src" / "eurogas_nexus" / "mcp" / "server.py").read_text(encoding="utf-8"),
    }


def _marker(path: str) -> str:
    """The static part of a route path as a client writes it (no ``/api`` base)."""

    parts: list[str] = []
    for segment in path.strip("/").split("/"):
        if segment.startswith("{"):
            break
        parts.append(segment)
    marker = "/" + "/".join(parts)
    return marker[4:] if marker.startswith("/api") else marker


#: Paths the SDK (or CLI/MCP) call by design, and the product does not need on a screen.
MACHINE_SURFACE: dict[str, str] = {
    "/api/analysis/ontology": "ontology read for SDK/agent callers",
    "/api/cost-observations/applicable": "cost-observation bench read (SDK)",
    "/api/cost-observations/values": "cost-observation bench read (SDK)",
    "/api/ingestion-runs": "ingestion history read (SDK/ops tooling)",
    "/api/lng/terminals": "LNG terminal reference read (SDK)",
    "/api/physical/outages": "outage read (SDK)",
    "/api/research/allocation": "research bench (SDK)",
    "/api/research/backtest": "research bench (SDK)",
    "/api/research/feasibility": "research bench (SDK)",
    "/api/research/monitoring": "research bench (SDK)",
    "/api/research/nowcast": "research bench (SDK)",
    "/api/research/shadow-run": "research bench (SDK)",
    "/api/route-cost/calculate": "tariff-driven route costing (SDK)",
    "/api/route-cost/lng-regas/assess": "LNG regas readiness assessment (SDK)",
    "/api/storage/sites": "storage site reference read (SDK)",
    "/api/weather/hdd-cdd": "weather bench (SDK)",
    "/api/weather/observations": "weather bench (SDK)",
    "/api/weather/stations": "weather station reference read (SDK)",
}

#: The surface gap `W0-03` D8 records: engines a desk decision needs, reachable only from the SDK.
#:
#: The nomination-window and storage-dispatch engines, and the run-evidence read, left this list
#: when the desk slice surfaced them on the Decision workspace (`nomination` and `dispatch` tasks).
#: What remains is the engines no surface asks for yet, plus the one route whose operation has a
#: canonical twin.
SURFACE_GAP_D8: dict[str, str] = {
    "/api/optimization/capacity": "capacity product selection engine - no client method",
    "/api/optimization/contracts": "contract pre-selection engine - no client method",
    "/api/optimization/portfolio-network": "portfolio-network engine - no client method",
    "/api/optimization/route": "minimum-cost path engine - no client method",
    # The one operation with two public routes: this is the newer one, which uniquely supports the
    # runtime/DB-first decision context, while the product calls the older route that uniquely
    # carries the Analysis-Snapshot citation and the job tracking (see D8).
    "/api/optimization/resource-pool": (
        "runtime-context pool optimiser; the product uses the older, snapshot-citing route"
    ),
}

#: Engines the desk slice surfaced, so a regression that drops one fails here rather than quietly
#: returning to the gap list.
SURFACED_BY_THE_DESK_SLICE: dict[str, str] = {
    "/api/optimization/nomination-window": "Decision workspace, Nomination task",
    "/api/optimization/storage-dispatch": "Decision workspace, Storage dispatch task",
    "/api/optimization/runs/{run_id}": "read back from either assessment result",
}

#: Paths that are deliberately not a product surface, each with the reason it is not.
DELIBERATE: dict[str, str] = {
    "/api/health/live": "liveness probe, read by operators and CI",
    "/api/health/ready": "readiness probe, read by operators and CI",
    "/api/runtime/metrics": "operational metrics, read by monitoring",
    "/api/runtime/source-operations": "source-operations posture for operators",
    "/api/auth/oidc/callback": "the identity provider's redirect target, not a call",
    "/api/agent/plans/validate": "validated inside the agent run flow, never called on its own",
    "/api/agent/strategy-ir/validate": "validated inside the agent run flow, never on its own",
    "/api/source-certifications": "control-plane administration, outside the business workspaces",
    "/api/source-certifications/{source_id}/certify": "control-plane administration act",
    "/api/projections/scenario-context": (
        "available but deliberately unconsumed (recorded in the execution state)"
    ),
}


def _public_paths() -> list[str]:
    import sys

    src = str(ROOT / "src")
    if src not in sys.path:
        sys.path.insert(0, src)
    from apps.api.main import app  # noqa: PLC0415

    return sorted(app.openapi()["paths"])


def test_every_public_path_is_reached_machine_only_or_deliberate() -> None:
    client = _client_source()
    declared = {**MACHINE_SURFACE, **SURFACE_GAP_D8, **DELIBERATE}
    for path, reason in declared.items():
        assert reason.strip(), path

    unexplained: list[str] = []
    for path in _public_paths():
        if path.startswith(("/api/internal", "/api/dev")):
            continue
        if _marker(path) in client:
            continue
        if path in declared:
            continue
        unexplained.append(path)

    assert unexplained == [], (
        "public paths reachable from no client and not declared: "
        + ", ".join(unexplained)
        + " - add a surface, or declare the path with its reason"
    )


def test_no_declared_exemption_outlives_its_path() -> None:
    paths = set(_public_paths())
    stale = sorted(
        path for path in {**MACHINE_SURFACE, **SURFACE_GAP_D8, **DELIBERATE} if path not in paths
    )
    assert stale == [], f"declared paths that no longer exist: {stale}"


def test_the_recorded_surface_gap_is_the_optimisation_family_and_nothing_else() -> None:
    """D8's remaining gap is stated as a fact about the client, not as a paragraph in a document."""

    client = _client_source()
    for path in SURFACE_GAP_D8:
        assert path.startswith("/api/optimization/"), path
    # Every remaining gap engine is still uncalled, and every surfaced one really is called.
    for path in SURFACE_GAP_D8:
        assert _marker(path) not in client, f"{path} gained a client method - declare it surfaced"
    for path in SURFACED_BY_THE_DESK_SLICE:
        assert _marker(path) in client, f"{path} lost its client method"


def test_the_two_optimisation_families_are_both_declared_and_both_still_reachable() -> None:
    """D8: one operation (pool optimisation) has two public routes, each with a unique capability.

    The pair is pinned so that collapsing it is a visible change: today the older route carries the
    Analysis-Snapshot citation, the job tracking and the product wiring, while the newer one carries
    the runtime/DB-first context and the run-evidence read.
    """

    paths = set(_public_paths())
    assert "/api/optimization/resource-pool" in paths
    assert "/api/route-cost/resource-pool/optimize" in paths

    client = _client_source()
    machine = _machine_source()
    assert "/route-cost/resource-pool/optimize" in client, "the product calls the older route"
    assert "optimization/resource-pool" in machine["sdk"], "the SDK calls the newer one"


def test_the_optimisation_engines_the_product_does_not_ask_for_have_no_client_method() -> None:
    """The gap in D8, measured: the engines no surface asks for are still uncallable, and the two
    the desk needed are not - the second half is what the desk slice delivered."""

    client = _client_source()
    for path in SURFACE_GAP_D8:
        assert _marker(path) not in client, path
    for engine in ("optimization/nomination-window", "optimization/storage-dispatch"):
        assert engine in client, engine


def test_the_census_states_what_it_cannot_see() -> None:
    """A textual reachability check is a drift alarm; the test says so where it is read."""

    source = Path(__file__).read_text(encoding="utf-8")
    assert "cannot tell a call from a comment" in source
    assert "a URL a caller builds from parts" in source
    assert "the browser sweep, not this" in source

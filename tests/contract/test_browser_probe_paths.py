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
application's declared GET surface here - and the record ids the scoped
read-to-render groups compare are held against the DOM rows and the backend
payloads that carry them.
"""

from __future__ import annotations

import re
from pathlib import Path

from apps.api.main import app

ROOT = Path(__file__).resolve().parents[2]
HARNESS = ROOT / "scripts" / "uat" / "browser_workflow_smoke.mjs"
WEB_CLIENT = ROOT / "clients" / "web" / "src" / "api" / "client.ts"
WEB_SRC = ROOT / "clients" / "web" / "src" / "components"

#: The one probe path this repair replaced; it was never a declared route.
RETIRED_CONTRACTS_PROBE = "/api/contracts/upstream"

SIGNALS_BLOCK = re.compile(r"const SURFACE_SIGNALS = \{(?P<body>.*?)\n\};", re.DOTALL)
SIGNAL_ENTRY = re.compile(
    r'^\s{2}(?P<workspace>[a-z_]+): \{.*?apiPath: (?P<path>"[^"]*"|null)',
    re.MULTILINE,
)
ENTRY_BODY = re.compile(r"^\s{2}(?P<workspace>[a-z_]+): \{(?P<body>.*)\},?$", re.MULTILINE)
GROUP_BODY = re.compile(r"\{ label: (?P<body>[^}]*)\}")
GROUP_FIELD = re.compile(r"(\w+): (\"[^\"]*\"|'[^']*'|\d+|null)")
GROUP_SELECTORS = re.compile(r"rowSelectors: \[(?P<body>.*?)\](?=,\s*\w+:|\s*$)")
PORTFOLIO_SLICE_ORDER = re.compile(
    r"PORTFOLIO_SNAPSHOT_SLICE_ORDER: PortfolioSliceKey\[\] = \[(?P<body>.*?)\];",
    re.DOTALL,
)
WORKSPACES_BLOCK = re.compile(r"const WORKSPACES = \[(?P<body>.*?)\]", re.DOTALL)
WORKSPACE_ID = re.compile(r'"([a-z]+)"')
SLICE_KEY = re.compile(r'"([a-z_]+)"')
RECORD_SELECTOR = re.compile(r'\[data-record="(?P<kind>[a-z-]+)"\]')
EMPTY_SELECTOR = re.compile(r'\[data-empty-state="(?P<marker>[a-z-]+)"\]')

#: The projection the portfolio surfaces read, and the client lane that performs the read.
PORTFOLIO_PROJECTION = "/api/projections/portfolio-snapshot"
PORTFOLIO_SNAPSHOT_MODEL = (
    ROOT / "clients" / "web" / "src" / "app" / "model" / "portfolioSnapshotModel.ts"
)
PORTFOLIO_SNAPSHOT_BUILDER = (
    ROOT / "src" / "eurogas_nexus" / "application" / "projections" / "portfolio_snapshot.py"
)
RESOURCE_POOL = ROOT / "src" / "eurogas_nexus" / "application" / "resource_pool.py"
MARKET_POSITIONING_DOMAIN = ROOT / "src" / "eurogas_nexus" / "domain" / "market_positioning.py"

#: The components each scoped probe's rendered rows live in.
WORKSPACE_COMPONENTS: dict[str, tuple[Path, ...]] = {
    "contracts": (WEB_SRC / "PortfolioWorkspace.tsx", WEB_SRC / "ContractWorkbench.tsx"),
    "glossary": (WEB_SRC / "GlossaryWiki.tsx",),
    "orders": (WEB_SRC / "MarketPositioningWorkspace.tsx",),
}

#: The glossary domain payload the probe's rows are compared against.
GLOSSARY_DOMAIN = ROOT / "src" / "eurogas_nexus" / "domain" / "glossary.py"


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


def _group_fields(body: str) -> dict[str, object]:
    fields: dict[str, object] = {}
    for name, raw in GROUP_FIELD.findall(body):
        if raw == "null":
            fields[name] = None
        elif raw.startswith(("'", '"')):
            fields[name] = raw[1:-1]
        else:
            fields[name] = int(raw)
    selectors = GROUP_SELECTORS.search(body)
    if selectors:
        fields["rowSelectors"] = re.findall(r"'([^']*)'", selectors.group("body"))
    return fields


def _declared_groups() -> list[tuple[str, dict[str, object]]]:
    """Every scoped read group, as ``(workspace, fields)``."""

    groups: list[tuple[str, dict[str, object]]] = []
    for match in ENTRY_BODY.finditer(_signals_source()):
        body = match.group("body")
        if "readToRender:" not in body:
            continue
        groups.extend(
            (match.group("workspace"), _group_fields(group.group("body")))
            for group in GROUP_BODY.finditer(body)
        )
    return groups


def _workspace_sources(workspace: str) -> str:
    return "\n".join(path.read_text(encoding="utf-8") for path in WORKSPACE_COMPONENTS[workspace])


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


def test_the_orders_probe_reads_the_projection_the_client_lane_reads() -> None:
    """The orders surface renders projection rows; an aggregate summary is not a row set.

    CI run 35996627042 recorded ``/api/portfolio/live-summary`` six times - exactly once per
    orders scope, and never by the client: the surface renders the ``screen_orders`` and
    ``pnl_snapshots`` slices of the portfolio projection its workspace batch reads. The probe now
    reads that projection, so the rows it compares with the surface are the rows the surface was
    given.
    """

    probes = _declared_probes()

    assert probes["orders"] == PORTFOLIO_PROJECTION
    assert not any(
        target is not None and target.startswith("/api/portfolio/live-summary")
        for target in probes.values()
    ), "no probe compares an aggregate summary with a surface's rows"

    client = WEB_CLIENT.read_text(encoding="utf-8")
    client_path = PORTFOLIO_PROJECTION.removeprefix("/api")
    assert f'"{client_path}"' in client


def test_every_scoped_read_declares_its_own_rows_and_record_id() -> None:
    """A scoped read-to-render check without its own row evidence would measure nothing.

    The sweep collects, per group, only the elements that group's own ``rowSelectors`` match
    *inside the displayed page*, and requires each returned row's exact record id to be among
    them. A declaration that named no selector, no record id field or no rows path would pass a
    surface that rendered nothing; selectors that are not record-kind scoped matched every table
    row on the page, other reads' rows included; and an empty state selected as "any row in this
    table" let a populated table pass an empty check.
    """

    groups = _declared_groups()
    assert {workspace for workspace, _ in groups} == {"contracts", "glossary", "orders"}, (
        "exactly the contracts, glossary and orders surfaces declare the scoped comparison"
    )
    assert len(groups) == 4, "contracts and glossary declare one group each, orders declares two"

    for workspace, group in groups:
        where = f"{workspace}/{group.get('label')}"
        assert group["rowsPath"], f"{where} declares no rows path"
        assert group["recordIdField"], f"{where} declares no record id field"
        selectors = group["rowSelectors"]
        assert selectors, f"{where} declares no rendered-row selector"
        for selector in selectors:
            assert RECORD_SELECTOR.fullmatch(str(selector)), (
                f"{where} scopes its rows to '{selector}', which is not a record-kind selector"
            )
        empty = group.get("emptySelector")
        if empty is not None:
            assert EMPTY_SELECTOR.fullmatch(str(empty)), (
                f"{where} declares '{empty}' as its empty state, which is not a declared marker"
            )
        slice_keys = _portfolio_slice_keys()
        if str(group["rowsPath"]).startswith("data.slices."):
            assert str(group["rowsPath"]).split(".")[2] in slice_keys, (
                f"{where} reads slice '{group['rowsPath']}' the portfolio projection does not "
                "declare"
            )

    markers = [group["emptySelector"] for _, group in groups if group.get("emptySelector")]
    assert markers, "the measured-zero checks name the empty state they expect"
    assert len(markers) == len(set(markers)), "each group declares its own empty-state marker"


def test_the_scoped_groups_compare_record_ids_the_rendered_rows_carry() -> None:
    """Each group compares a payload field the DOM row carries verbatim as ``data-record-id``.

    The comparison is only evidence if the element the group collected is the record the read
    returned, so every record kind a group selects must be declared by a component of that
    workspace, the id must be rendered from the payload field the group names, and a declared
    empty state must exist as the marker the group selects. A surface's measured-zero state is a
    stable marker of its own (`data-empty-state`) rather than the table it happens to sit in, so
    a populated table cannot answer for it.
    """

    for workspace in WORKSPACE_COMPONENTS:
        markers = re.findall(r'data-empty-state="([a-z-]*)"', _workspace_sources(workspace))
        assert markers, f"{workspace} declares no empty-state marker"
        assert len(markers) == len(set(markers)), f"{workspace} reuses an empty-state marker"

    for workspace, group in _declared_groups():
        source = _workspace_sources(workspace)
        for selector in group["rowSelectors"]:
            kind = RECORD_SELECTOR.fullmatch(str(selector)).group("kind")
            assert f'data-record="{kind}"' in source, (
                f"{workspace} declares no rendered row of kind '{kind}'"
            )
        field = group["recordIdField"]
        assert re.search(rf"data-record-id=\{{[A-Za-z_]+\.{field}\}}", source), (
            f"{workspace} renders no row's {field} as its data-record-id"
        )
        empty = group.get("emptySelector")
        if empty is not None:
            marker = EMPTY_SELECTOR.fullmatch(str(empty)).group("marker")
            assert f'data-empty-state="{marker}"' in source, (
                f"{workspace} renders no '{marker}' empty state the group selects"
            )


def test_the_scoped_groups_compare_ids_the_backend_actually_serves() -> None:
    """The ids the DOM carries are the ids the compared payloads carry.

    The contracts group compares upstream contract ids, and one of the rows it accepts is the
    portfolio pool row: ``portfolio_resource_from_contract`` maps ``contract_id`` to
    ``resource_id``, and the projection composes that slice through the same
    ``list_upstream_contracts`` read the route serves, so the pool row carries the term's own id
    rather than a second identifier. The orders groups compare the projection's row slices, whose
    rows are the domain models dumped verbatim, so the ids are the persisted observations' ids.
    """

    resource_pool = RESOURCE_POOL.read_text(encoding="utf-8")
    assert '"resource_id": contract["contract_id"]' in resource_pool, (
        "the pool row's id is the contract's own id"
    )
    assert "list_upstream_contracts(session)" in resource_pool, (
        "the pool is composed from the same contracts read the route serves"
    )

    builder = PORTFOLIO_SNAPSHOT_BUILDER.read_text(encoding="utf-8")
    assert 'order_rows = [order.model_dump(mode="json") for order in entitled_orders]' in builder
    assert (
        'snapshot_rows = [snapshot.model_dump(mode="json") for snapshot in entitled_snapshots]'
        in builder
    ), "the served order and PnL rows are the domain models, ids included"
    domain = MARKET_POSITIONING_DOMAIN.read_text(encoding="utf-8")
    for field in ("order_observation_id", "pnl_snapshot_id"):
        assert re.search(rf"^    {field}: str$", domain, re.MULTILINE), (
            f"the served model declares no {field} for the group to compare"
        )


def test_the_glossary_probe_compares_the_term_ids_the_route_serves() -> None:
    """The term index is compared with the surface's own read, by the term's own id.

    The glossary surface carried a declared exemption from the sweep ("glossary terms return rows
    while the term index renders 'Loading workspace'", measured 2026-09-19). The whole-page
    heuristic could not tell a rendered index from a stale one and could not read the Chinese copy
    at all, so the exemption is replaced by a row comparison: the probe reads the same route the
    client lane reads (``api.glossary``), and every term it returns must be one the index rendered
    under the term's own ``term_id`` - the field the route's payload carries and the card renders.
    """

    probes = _declared_probes()
    assert probes["glossary"] == "/api/glossary?limit=5"

    # The probe is the surface's own read, bounded: the client lane asks the same route, and the
    # surface's own list bound (40 terms) cannot cut off the five the probe compares.
    client_path = probes["glossary"].removeprefix("/api").split("?", 1)[0]
    assert client_path == "/glossary"
    assert f'"{client_path}"' in WEB_CLIENT.read_text(encoding="utf-8")

    domain = GLOSSARY_DOMAIN.read_text(encoding="utf-8")
    assert '"term_id": self.term_id' in domain, (
        "the served term payload carries the id the group compares"
    )

    glossary_groups = [
        group for workspace, group in _declared_groups() if workspace == "glossary"
    ]
    assert len(glossary_groups) == 1, "the glossary surface declares one scoped comparison"
    group = glossary_groups[0]
    assert group["rowsPath"] == "data", "the glossary read serves its rows as the envelope's data"
    assert group["recordIdField"] == "term_id"
    assert group["rowSelectors"] == ['[data-record="glossary-term"]']
    assert group["emptySelector"] == '[data-empty-state="glossary-terms"]'


def _portfolio_slice_keys() -> set[str]:
    match = PORTFOLIO_SLICE_ORDER.search(PORTFOLIO_SNAPSHOT_MODEL.read_text(encoding="utf-8"))
    assert match, "the portfolio snapshot model still declares its slice order"
    return set(SLICE_KEY.findall(match.group("body")))

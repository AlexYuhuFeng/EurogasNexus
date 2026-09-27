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

import json
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
GROUP_FIELD = re.compile(r"(\w+): (\"[^\"]*\"|'[^']*'|\d+|true|false|null)")
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
    "sources": (WEB_SRC / "SourceCenter.tsx",),
}

#: The glossary domain payload the probe's rows are compared against.
GLOSSARY_DOMAIN = ROOT / "src" / "eurogas_nexus" / "domain" / "glossary.py"

#: The static source registry the Source Center probe's rows are compared against, and the route
#: that serves it.
SOURCE_REGISTRY = ROOT / "src" / "eurogas_nexus" / "domain" / "ingestion" / "source_registry.py"
SOURCE_ROUTE = ROOT / "src" / "eurogas_nexus" / "api" / "routes" / "public" / "sources.py"

#: The market hub board's own read, the marker layer it declares its prices with, and the shell and
#: strip elements the sweep reads the displayed context and the projection's as-of from.
MARKET_PROJECTION = "/api/projections/market-context"
MARKET_PROJECTION_BUILDER = (
    ROOT / "src" / "eurogas_nexus" / "application" / "projections" / "market_context.py"
)
MARKET_READS = ROOT / "src" / "eurogas_nexus" / "application" / "projections" / "market_reads.py"
MARKET_REPOSITORY = (
    ROOT / "src" / "eurogas_nexus" / "db" / "repositories" / "market_intelligence.py"
)
MARKET_NORMALIZED_VIEW = (
    ROOT / "src" / "eurogas_nexus" / "domain" / "market_intelligence" / "normalized_view.py"
)
MARKET_TERMINAL = WEB_SRC / "MarketTerminal.tsx"
MARKET_COCKPIT_MODEL = (
    ROOT / "clients" / "web" / "src" / "app" / "model" / "marketCockpitModel.ts"
)
PROJECTION_CONTEXT_MODEL = (
    ROOT / "clients" / "web" / "src" / "app" / "model" / "projectionContext.ts"
)
WORKSPACE_TOP_BAR = WEB_SRC / "WorkspaceTopBar.tsx"
PROJECTION_CONTEXT_STRIP = WEB_SRC / "ProjectionContextStrip.tsx"
EVIDENCE_PRESENTATION = (
    ROOT / "clients" / "web" / "src" / "app" / "model" / "evidencePresentation.ts"
)
READ_TO_RENDER = ROOT / "scripts" / "uat" / "readToRender.mjs"

#: The capacity operating board's own join and read disclosure: the component that renders the
#: board, the model that names its states, and the cockpit that derives them from the store.
CAPACITY_COMPONENT = WEB_SRC / "CapacityWorkspace.tsx"
CAPACITY_BOARD_MODEL = (
    ROOT / "clients" / "web" / "src" / "app" / "model" / "capacityOperatingBoardRead.ts"
)
MARKET_COCKPIT = WEB_SRC / "MarketCockpit.tsx"
I18N = ROOT / "clients" / "web" / "src" / "i18n"


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
        elif raw in {"true", "false"}:
            fields[name] = raw == "true"
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
    assert {workspace for workspace, _ in groups} == {
        "contracts",
        "glossary",
        "orders",
        "sources",
    }, "exactly the contracts, glossary, orders and sources surfaces declare the scoped comparison"
    assert len(groups) == 5, (
        "contracts, glossary and sources declare one group each, orders declares two"
    )

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


def test_the_sources_probe_compares_the_registry_ids_the_catalog_renders() -> None:
    """The source catalog is compared with its own read, by the source's own id.

    The surface carried a declared exemption from the sweep ("sources return rows while the
    administration surface reports Total sources 0", measured 2026-09-19), produced by the
    whole-page heuristic that matched the page's first 400 characters - copy that cannot say which
    row is missing and cannot be read in Chinese at all. The exemption is replaced by a row
    comparison against the registry route the client lane reads (``api.sources``): every source
    ``GET /api/sources`` returns must be one the catalog rendered, under the source's own
    ``source_id``, and - because the catalog renders the whole registry rather than a bound over it
    - a rendered row the read did not return fails as well.

    The surface opens on its priority queue, a *filtered* subset of the same read, so the group
    names the catalog task (``source-tab-catalog``): the sweep activates it before collecting
    evidence, which is what keeps a filtered task from being compared with unfiltered rows.
    """

    probes = _declared_probes()
    assert probes["sources"] == "/api/sources"

    # The probe is the surface's own read: the client lane asks the same route, and the route serves
    # the whole static registry (no page parameter the probe could disagree with).
    client_path = probes["sources"].removeprefix("/api")
    assert client_path == "/sources"
    assert f'"{client_path}"' in WEB_CLIENT.read_text(encoding="utf-8")
    route = SOURCE_ROUTE.read_text(encoding="utf-8")
    assert "registered_sources()" in route, "the route serves the registry the group compares"

    registry = SOURCE_REGISTRY.read_text(encoding="utf-8")
    assert '"source_id": source_id' in registry, (
        "the served registry payload carries the id the group compares"
    )
    assert '"category": category' in registry, (
        "the served registry payload carries the category the interaction filters by"
    )

    source_groups = [group for workspace, group in _declared_groups() if workspace == "sources"]
    assert len(source_groups) == 1, "the source surface declares one scoped comparison"
    group = source_groups[0]
    assert group["rowsPath"] == "data", "the registry read serves its rows as the envelope's data"
    assert group["recordIdField"] == "source_id"
    assert group["rowSelectors"] == ['[data-record="source-row"]']
    assert group["emptySelector"] == '[data-empty-state="source-rows"]'
    assert group.get("taskTab") == "source-tab-catalog", (
        "the group names the task that renders the unfiltered read"
    )
    assert group.get("exactRows") is True, (
        "the catalog renders the whole registry, so a foreign row must fail too"
    )
    assert "rowLimit" not in group, "the registry read is not a bound the group may cut"

    # The task the group names is the surface's own: the view tabs are declared with the
    # `source-tab` id prefix and one of the surface's views is the catalog.
    component = _workspace_sources("sources")
    assert 'idPrefix="source-tab"' in component, "the surface declares the task tab prefix"
    views = re.search(r'SOURCE_VIEWS: SourceViewId\[\] = \[(?P<body>.*?)\]', component)
    assert views, "the surface declares its views"
    assert '"catalog"' in views.group("body"), "the catalog task is one of the surface's views"
    # The filter the interaction exercises is addressed by the category code the registry carries,
    # so the check never matches a localized label.
    assert "data-source-category={category}" in component, (
        "the category filter carries the category code, not only its label"
    )


def _portfolio_slice_keys() -> set[str]:
    match = PORTFOLIO_SLICE_ORDER.search(PORTFOLIO_SNAPSHOT_MODEL.read_text(encoding="utf-8"))
    assert match, "the portfolio snapshot model still declares its slice order"
    return set(SLICE_KEY.findall(match.group("body")))


def _market_signal() -> str:
    """The market workspace's signal entry, as the sweep declares it."""

    match = re.search(r"^\s{2}market: \{(?P<body>.*)\},$", _signals_source(), re.MULTILINE)
    assert match, "the sweep still declares the market workspace's signal"
    return match.group("body")


def _hub_scope_declaration() -> list[str]:
    match = re.search(r"hubScope: \[(?P<body>[^\]]*)\]", _market_signal())
    assert match, "the market signal declares the hub scope the board prices"
    return re.findall(r'"([A-Z]+)"', match.group("body"))


def _model_major_hubs() -> list[str]:
    match = re.search(
        r"MAJOR_MARKET_HUBS = \[(?P<body>[^\]]*)\]",
        MARKET_COCKPIT_MODEL.read_text(encoding="utf-8"),
    )
    assert match, "the market cockpit model still declares its major hubs"
    return re.findall(r'"([A-Z]+)"', match.group("body"))


def test_the_market_probe_reads_the_projection_the_market_lane_reads() -> None:
    """The hub board prices projection rows, not ``/api/market/observations``.

    The market workspace's declared gap ("market observations return rows while every hub card
    renders n/a") came from the visual review while the probe read
    ``/api/market/observations?limit=5`` - an endpoint the market lane never calls: the lane reads
    ``GET /api/projections/market-context`` (``api.marketContext`` in the client) and the board
    prices the ``quotes``/``normalized_quotes`` slices of that payload. The probe now reads that
    projection for the Active Context the shell is displaying, so the rows it compares with the
    cards are the rows the surface was given.
    """

    probes = _declared_probes()
    assert probes["market"] == MARKET_PROJECTION
    assert not any(
        target is not None and target.startswith("/api/market/observations")
        for target in probes.values()
    ), "no probe reads an endpoint the market lane does not call"

    client = WEB_CLIENT.read_text(encoding="utf-8")
    assert f'"{MARKET_PROJECTION.removeprefix("/api")}"' in client

    # The projection serves the price sources the board displays: the L1 quotes and the
    # backend-normalized view (hub/tenor owned by the backend, never re-derived in the sweep).
    builder = MARKET_PROJECTION_BUILDER.read_text(encoding="utf-8")
    for slice_name in ("quotes", "normalized_quotes"):
        assert f'"{slice_name}": projection_slice(' in builder, (
            f"the market projection still serves its {slice_name} slice"
        )
    reads = MARKET_READS.read_text(encoding="utf-8")
    repository = MARKET_REPOSITORY.read_text(encoding="utf-8")
    for field in ("quote_id", "bid_price", "ask_price", "currency", "unit", "source_system"):
        assert f'"{field}": row.{field}' in repository, (
            f"the quote payload still carries the {field} the card shows"
        )
    for field in ("observation_id", "price", "currency", "unit", "source_system"):
        assert f'"{field}": row.{field}' in reads, (
            f"the observation payload still carries the {field} the card shows"
        )
    normalized = MARKET_NORMALIZED_VIEW.read_text(encoding="utf-8")
    for field in ('"hub": observation_hub(observation)', '"tenor": observation_tenor(observation)'):
        assert field in normalized, f"the normalized view still places each row for {field}"


def test_the_market_board_compares_the_pairs_the_sweep_declares() -> None:
    """The scope the board is held to is the product's own hub set, and its markers exist.

    The sweep compares the board's cards with the projection's rows for the *displayed* tenor and
    the hubs the board declares, so the declaration must be the same set the component renders from
    and the comparison must be the pure rule the web suite exercises - never a reading of the
    page's copy.
    """

    declared = sorted(_hub_scope_declaration())
    assert declared == sorted(_model_major_hubs())
    assert declared == ["NBP", "PEG", "PSV", "THE", "TTF", "ZTP"]

    terminal = MARKET_TERMINAL.read_text(encoding="utf-8")
    for marker in (
        'data-market-board="hub-prices"',
        "data-board-tenor={activeTenor}",
        "data-tenor={tenor}",
        'data-record="market-hub-price"',
        "data-record-slice={pricedSlice ?? undefined}",
        "data-price-tenor={row.tenor}",
        "data-price-hub-label",
        "data-price-value",
        "data-price-meta",
        "data-price-source",
    ):
        assert marker in terminal, f"the market board declares {marker}"

    harness = HARNESS.read_text(encoding="utf-8")
    read_to_render = READ_TO_RENDER.read_text(encoding="utf-8")
    for rule in ("collectQuotedBoard", "evaluateQuotedBoard", "marketBoardRows"):
        assert f"export function {rule}(" in read_to_render, f"{rule} is declared"
        assert rule in harness, f"the sweep applies {rule}"
    # The verdict is the pure rule's: the page's copy is never the evidence.
    assert "rendersNothing" in harness
    assert harness.index("} else if (signal.quotedBoard) {") < harness.index("const rendersNothing")


def test_the_market_board_is_issued_for_the_context_the_shell_displays() -> None:
    """The probe is composed from the displayed Active Context, exactly as the client composes it.

    A board filtered by the displayed tenor (and by a focused hub or product) must not be compared
    with an unfiltered payload read for another context. The shell states the context it displays in
    machine-readable form, the sweep composes the query from it with the client's own omission rule,
    and a context it cannot read is a failure rather than a silent unfiltered read.
    """

    topbar = WORKSPACE_TOP_BAR.read_text(encoding="utf-8")
    for attribute in (
        "data-context-gas-day={gasDay}",
        "data-context-product={deliveryProduct}",
        'data-context-hub={hubId ?? ""}',
    ):
        assert attribute in topbar, f"the shell displays {attribute}"
    assert ".topbar-context-disclosure" in _market_signal()

    context_model = PROJECTION_CONTEXT_MODEL.read_text(encoding="utf-8")
    assert (
        'context.deliveryProduct === "all" ? {} : { product: context.deliveryProduct }'
        in context_model
    )
    assert "context.hubId ? { hub: context.hubId } : {}" in context_model

    harness = HARNESS.read_text(encoding="utf-8")
    for attribute in ("data-context-gas-day", "data-context-product", "data-context-hub"):
        assert attribute in harness, f"the probe reads the displayed {attribute}"
    assert "contextProblem" in harness and "if (state.contextProblem)" in harness

    # The as-of the surface states is the payload's own value, declared verbatim beside the
    # formatted instant the strip displays.
    strip = PROJECTION_CONTEXT_STRIP.read_text(encoding="utf-8")
    assert "data-projection-as-of={asOf ?? undefined}" in strip
    presentation = EVIDENCE_PRESENTATION.read_text(encoding="utf-8")
    assert 'toISOString().slice(0, 19).replace("T", " ")' in presentation
    assert "} UTC`;" in presentation
    read_to_render = READ_TO_RENDER.read_text(encoding="utf-8")
    assert "export function utcInstantLabel(" in read_to_render
    assert 'toISOString().slice(0, 19).replace("T", " ")' in read_to_render

    # The unit the card prints is composed by one rule, mirrored by the sweep: a unit that already
    # names its currency is printed as it is, a bare quantity is qualified with the currency.
    assert "export function displayPriceUnit(" in read_to_render
    terminal = MARKET_TERMINAL.read_text(encoding="utf-8")
    assert "const displayPriceUnit = (currency: string, unit: string): string" in terminal
    assert "unitName.toUpperCase().includes(currencyCode.toUpperCase())" in terminal
    assert "unitName.toUpperCase().includes(currencyCode.toUpperCase())" in read_to_render


def test_the_refused_registry_probe_refuses_the_read_the_catalog_compares() -> None:
    """The registry-failure check refuses the surface's own read, and holds it to stated markers.

    The Source Center's recorded defect was that a failed ``GET /api/sources`` left the surface
    rendering "Total sources 0" beside "No active warnings" - a measured zero for a read that never
    answered. The browser check refuses exactly that read through a route interception, requires
    the surface's own declared failure state with no measurement, then removes the interception and
    requires the surface's retry to restore the read. The refusal must be the same route the
    catalog comparison reads, and the markers it selects must be the component's own.
    """

    harness = HARNESS.read_text(encoding="utf-8")
    assert "const SOURCES_READ_ROUTE = /\\/api\\/sources(\\?.*)?$/;" in harness, (
        "the refusal names the registry read alone, not a broader sources path"
    )
    # The refused route is the probe's own path: one read, refused and then compared.
    assert _declared_probes()["sources"] == "/api/sources"
    assert "await page.route(SOURCES_READ_ROUTE, handler);" in harness
    assert harness.count("await page.unroute(SOURCES_READ_ROUTE, handler)") == 2, (
        "the interception is removed in the recovery half and again in the finally"
    )
    assert 'if (request.method() !== "GET") {' in harness, (
        "only the surface's own read is refused; another method on the path reaches the app"
    )
    # The verdicts are the pure rules the web suite exercises, not a reading of the page's copy.
    read_to_render = (ROOT / "scripts" / "uat" / "readToRender.mjs").read_text(encoding="utf-8")
    for rule in ("evaluateRefusedRegistry", "evaluateRegistryRecovery"):
        assert f"export function {rule}(" in read_to_render, f"{rule} is declared"
        assert rule in harness, f"the sweep applies {rule}"

    component = _workspace_sources("sources")
    for marker in (
        "data-source-registry-state={registryRead.state}",
        "data-registry-notice={read.state}",
        'data-source-registry-retry="true"',
    ):
        assert marker in component, f"the surface declares {marker}"
    # The measured-empty marker the refusal must not present stays the group's declared one.
    assert 'data-empty-state="source-rows"' in component


def test_the_capacity_probe_refuses_the_board_read_the_disclosure_names() -> None:
    """The operating board's read disclosure, and the exemption it deliberately keeps.

    The board's rows are a join of two reads (``flows`` and ``capacity``), so its exemption is not
    retired by this change: the scoped joined-row comparison is a later milestone and the whole-page
    declaration stays, still pinned to the probe path it was declared with. What is held here is
    the disclosure path - the refusal names exactly the board's capacity read, the verdicts are the
    pure rules the web suite exercises, and the markers they select are the component's own - plus
    the parity of the copy in both locales.
    """

    harness = HARNESS.read_text(encoding="utf-8")
    # The exemption is kept, and the probe that declared it is unchanged.
    gaps = re.search(r"const KNOWN_FUNCTIONAL_GAPS = \{(?P<body>.*?)\n\};", harness, re.DOTALL)
    assert gaps, "KNOWN_FUNCTIONAL_GAPS is still declared in the browser sweep"
    assert re.search(r"^\s{2}capacity:", gaps.group("body"), re.MULTILINE), (
        "the capacity exemption stays declared until a scoped joined-row replacement exists"
    )
    assert _declared_probes()["capacity"] == "/api/physical/capacity?limit=5"

    # The refused route is one of the two reads the board joins, and it is the client lane's own
    # read: both paths are declared by the client the surface uses.
    client = WEB_CLIENT.read_text(encoding="utf-8")
    for lane in ("/physical/flows", "/physical/capacity"):
        assert f'"{lane}"' in client, f"the board's {lane} read is the client lane's own"
    assert "const CAPACITY_READ_ROUTE = /\\/api\\/physical\\/capacity(\\?.*)?$/;" in harness
    assert "await page.route(CAPACITY_READ_ROUTE, handler);" in harness
    assert harness.count("await page.unroute(CAPACITY_READ_ROUTE, handler)") == 2, (
        "the interception is removed in the recovery half and again in the finally"
    )

    # The verdicts are the pure rules the web suite exercises, not a reading of the page's copy.
    read_to_render = READ_TO_RENDER.read_text(encoding="utf-8")
    for rule in (
        "collectCapacityOperatingBoard",
        "evaluateRefusedCapacityBoard",
        "evaluateCapacityBoardRecovery",
    ):
        assert f"export function {rule}(" in read_to_render, f"{rule} is declared"
        assert rule in harness, f"the sweep applies {rule}"

    # The states the model names, and the two reads they are derived from.
    model = CAPACITY_BOARD_MODEL.read_text(encoding="utf-8")
    assert '"flows", "capacity"' in model, "the board's required reads are declared together"
    for state in ("unread", "pending", "failed", "partial", "empty", "ready"):
        assert f'"{state}"' in model, f"the board's {state} state is declared"
    assert 'from "@/app/model/endpointFailures"' in model, (
        "the failure vocabulary is the shared one, not a second taxonomy"
    )
    assert "measurement" in model, "the measurement rule is declared with the states"

    # The cockpit derives the surface from the store's own facts and offers the store's existing
    # bounded retry: no new fetch machinery, and no calculation moved into the component.
    cockpit = MARKET_COCKPIT.read_text(encoding="utf-8")
    assert "capacityOperatingBoardRead(" in cockpit
    assert "retryFailedWorkspaceEndpoints" in cockpit
    assert "api.endpointErrors.capacity" in cockpit
    assert "api.workspaceLoadsCommitted" in cockpit

    # The markers the check selects are the board component's own, and its measured-empty and
    # filter sentences are separate declared states.
    component = CAPACITY_COMPONENT.read_text(encoding="utf-8")
    for marker in (
        "data-capacity-read-state={boardRead.state}",
        "data-capacity-notice={read.state}",
        'data-capacity-board-retry="true"',
        'data-record="capacity-point"',
        "data-record-id={row.key}",
        "data-empty-state={boardEmptyState.marker}",
        'key: "capacity.board.empty", marker: "capacity-operating-points"',
        'key: "capacity.no_matching_points", marker: "capacity-filter-no-match"',
    ):
        assert marker in component, f"the operating board declares {marker}"

    # Every sentence the board renders for its read states is declared in both locales, and the
    # measured-empty sentence is not the filter sentence.
    locales = {
        name: json.loads((I18N / f"{name}.json").read_text(encoding="utf-8"))
        for name in ("en", "zh")
    }
    for key in (
        "capacity.board.title",
        "capacity.board.unread",
        "capacity.board.pending",
        "capacity.board.failed",
        "capacity.board.partial",
        "capacity.board.empty",
        "capacity.board.retry",
    ):
        assert locales["en"][key].strip(), f"en {key}"
        assert locales["zh"][key].strip(), f"zh {key}"
        assert locales["en"][key] != locales["zh"][key], f"{key} is untranslated"
    assert locales["en"]["capacity.board.empty"] != locales["en"]["capacity.no_matching_points"]
    assert locales["zh"]["capacity.board.empty"] != locales["zh"]["capacity.no_matching_points"]

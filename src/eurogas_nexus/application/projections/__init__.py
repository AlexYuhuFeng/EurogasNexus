"""Application projection read models (Architecture V2 Wave 5).

Constitution rules 34-35: application projection/query services provide coherent
client read models, and frontend code must not reconstruct critical commercial
state from unrelated endpoint calls. This package is that layer for the
business workspaces:

- :func:`build_market_context` - MarketContext (market observations, the
  normalized quote view, quotes, intraday opportunities, derived spreads, the
  monitoring summary/alerts and the data-source freshness/provenance summary on
  one time basis and one as-of instant);
- :func:`build_portfolio_snapshot` - PortfolioSnapshot (summary, screen orders,
  PnL snapshots, contract context, per-slice freshness);
- :func:`build_review_context` - ReviewContext (decisions, resolved review
  evidence and the warnings a reviewer must see);
- :func:`build_scenario_context` - ScenarioContext (entitled route candidates,
  tariff and contract context, plus the explicit list of scenario inputs a read
  model does not provide).

Every projection is a **pure composition** over existing repositories and
application services. None of them owns a table, a calculation or a route
handler: the market and portfolio reads they build on are the same functions the
``/api/market/*`` and ``/api/portfolio/*`` handlers call
(:mod:`eurogas_nexus.application.projections.market_reads`,
:mod:`eurogas_nexus.application.projections.portfolio_reads`).

Each returns the public envelope ``{"data": ..., "meta": ...}`` with honest
meta: ``as_of_utc``, ``time_basis``, ``source_references``, ``warnings``,
``table_lineage``, ``research_only`` and ``human_review_required``.
"""

from eurogas_nexus.application.projections.context import (
    GasDayInputError,
    ProjectionContext,
    resolve_projection_context,
)
from eurogas_nexus.application.projections.envelope import (
    SOURCE_RUNTIME_DB_NOT_CONFIGURED,
    SOURCE_RUNTIME_POSTGRESQL,
    entitlement_block,
    projection_envelope,
    projection_slice,
)
from eurogas_nexus.application.projections.freshness import (
    freshness_block,
    freshness_state,
    source_freshness_expectations,
)
from eurogas_nexus.application.projections.market_context import (
    build_market_context,
)
from eurogas_nexus.application.projections.portfolio_snapshot import (
    build_portfolio_snapshot,
)
from eurogas_nexus.application.projections.review_context import (
    build_review_context,
)
from eurogas_nexus.application.projections.scenario_context import (
    build_scenario_context,
)

__all__ = [
    "GasDayInputError",
    "ProjectionContext",
    "SOURCE_RUNTIME_DB_NOT_CONFIGURED",
    "SOURCE_RUNTIME_POSTGRESQL",
    "build_market_context",
    "build_portfolio_snapshot",
    "build_review_context",
    "build_scenario_context",
    "entitlement_block",
    "freshness_block",
    "freshness_state",
    "projection_envelope",
    "projection_slice",
    "resolve_projection_context",
    "source_freshness_expectations",
]

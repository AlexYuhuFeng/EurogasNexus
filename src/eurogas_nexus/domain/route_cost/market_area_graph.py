"""The graph route pricing walks: market areas joined through named interconnection points.

A route from one hub to another is priced only along proven adjacency (the reference bundle's
``market_area_link`` and ``interconnector`` edges, derived from ENTSOG by the rule in
``reference_data/network_adjacency.py``):

- a **direct crossing** joins two market areas at one interconnection point: the exit of the
  first market area's TSO and the entry of the second's apply there;
- a **pipeline crossing** joins two market areas through a two-point pipeline (IUK, BBL): exit
  from the first market area at the pipeline's near end, the pipeline's own charges, entry to
  the second market area at its far end.

A multi-hop route chains crossings (TTF -> THE -> PEG). Every leg names its point, operator and
direction. A leg whose tariff the register does not hold is priced as missing (the route says
so); it is never priced at zero. Two market areas with no crossing are not priced as direct.
"""

from __future__ import annotations

from collections import deque
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

#: Pipeline charges as the tariff register holds them, by pipeline operator and direction of
#: flow (near end -> far end): (tso, source point name, direction, country, market area).
#: A pipeline direction not listed has its charges priced as missing.
PIPELINE_CHARGES: dict[tuple[str, str, str], tuple[tuple[str, str, str, str, str], ...]] = {
    # IUK (Interconnector): Bacton (ITP-00005) <-> Zeebrugge IZT (ITP-00061).
    ("UK-TSO-0003", "ITP-00005", "ITP-00061"): (
        ("Interconnector UK", "IUK Bacton Entry", "ENTRY", "GB", "IUK"),
        ("Interconnector UK", "IUK Zeebrugge Exit", "EXIT", "BE", "IUK"),
    ),
    ("UK-TSO-0003", "ITP-00061", "ITP-00005"): (
        ("Interconnector UK", "IUK Zeebrugge Entry", "ENTRY", "BE", "IUK"),
        ("Interconnector UK", "IUK Bacton Exit", "EXIT", "GB", "IUK"),
    ),
    # BBL: Balgzand (ITP-00063) <-> Bacton (BBL) (ITP-00207); one capacity charge per direction.
    ("UK-TSO-0004", "ITP-00063", "ITP-00207"): (
        ("BBL Company", "BBL Forward Flow NL to GB", "EXIT", "NL", "BBL"),
    ),
    ("UK-TSO-0004", "ITP-00207", "ITP-00063"): (
        ("BBL Company", "BBL Reverse Flow GB to NL", "ENTRY", "GB", "BBL"),
    ),
}

#: Market-area TSO charges at an interconnection point as the register holds them:
#: (operator key, point key, direction) -> (tso, source point name, country, market area).
#: None are held yet (the register holds National Gas beach-terminal entries, not its IP
#: tariffs), so a crossing's market-area legs are priced as missing until one is loaded.
POINT_CHARGES: dict[tuple[str, str, str], tuple[str, str, str, str]] = {}


@dataclass(frozen=True)
class Crossing:
    """One way from market area ``from_hub`` to ``to_hub``."""

    from_hub: str
    to_hub: str
    #: The interconnection point(s) in flow order: one for a direct crossing, the near and far
    #: ends for a pipeline crossing.
    points: tuple[str, ...]
    pipeline_operator: str | None = None

    @property
    def via(self) -> str:
        return "/".join(self.points)


@dataclass(frozen=True)
class TariffLegSpec:
    """A leg the route must price: who charges what, where, in which direction."""

    point_key: str
    point_name: str
    country: str
    tso: str
    direction: str
    market_area: str | None
    role: str  # market_area_exit | pipeline | market_area_entry


@dataclass
class MarketAreaGraph:
    """Hubs (ENTSOG VTP point keys) joined by crossings."""

    hub_codes: dict[str, str] = field(default_factory=dict)  # code -> hub point key
    hub_names: dict[str, str] = field(default_factory=dict)  # hub point key -> code
    points: dict[str, dict[str, Any]] = field(default_factory=dict)  # point key -> facts
    #: point key -> {hub point key: operator keys on that hub's side}
    point_hubs: dict[str, dict[str, tuple[str, ...]]] = field(default_factory=dict)
    #: point key -> pipeline operators the point is an end of
    point_pipes: dict[str, set[str]] = field(default_factory=dict)
    #: pipeline operator -> its two end point keys
    pipelines: dict[str, tuple[str, str]] = field(default_factory=dict)
    operator_names: dict[str, str] = field(default_factory=dict)
    #: representative point per sorted pair of hubs (what the map draws by default)
    representative: set[str] = field(default_factory=set)

    @classmethod
    def from_bundle(cls, bundle: Mapping[str, Any]) -> MarketAreaGraph:
        """Build the graph from the reference bundle's nodes and adjacency edges."""

        from eurogas_nexus.ingestion.public_sources import _market_hub_code

        graph = cls()
        by_id = {node["id"]: node for node in bundle.get("nodes") or []}
        for node in by_id.values():
            graph.points[str(node["point_key"])] = {
                "name": node.get("name"),
                "country": node.get("country"),
                "node_id": node["id"],
                "type": node.get("type"),
            }
            if node.get("type") == "hub":
                code = _market_hub_code(node["name"], node["point_key"])
                graph.hub_codes[code] = node["point_key"]
                graph.hub_names[node["point_key"]] = code
        graph.operator_names = {
            key: str(value.get("name") or key)
            for key, value in (bundle.get("operators") or {}).items()
        }
        for edge in bundle.get("edges") or []:
            if edge.get("type") == "market_area_link":
                point, hub = edge["point_key"], edge["hub_point_key"]
                graph.point_hubs.setdefault(point, {})[hub] = tuple(edge.get("operators") or ())
                for joined in edge.get("joins") or []:
                    if str(joined).startswith("pipeline:"):
                        graph.point_pipes.setdefault(point, set()).add(str(joined).split(":", 1)[1])
                if edge.get("representative"):
                    graph.representative.add(point)
            elif edge.get("type") == "interconnector":
                ends = tuple(edge.get("point_keys") or ())
                if len(ends) == 2:
                    graph.pipelines[str(edge["operator_key"])] = (ends[0], ends[1])
        return graph

    # -- resolution ------------------------------------------------------------------

    def hub_for(self, name: str | None) -> str | None:
        """The hub a route endpoint names, by market code (TTF) or VTP point key."""

        text = (name or "").strip().upper()
        if not text:
            return None
        if text in self.hub_codes:
            return self.hub_codes[text]
        if text in self.hub_names:
            return text
        return None

    # -- adjacency -------------------------------------------------------------------

    def crossings(self, from_hub: str, to_hub: str) -> list[Crossing]:
        """Every proven way from one market area into a neighbouring one, sorted."""

        found: list[Crossing] = []
        for point, hubs in self.point_hubs.items():
            if from_hub in hubs and to_hub in hubs:
                found.append(Crossing(from_hub, to_hub, (point,)))
        for operator, (a, b) in self.pipelines.items():
            for near, far in ((a, b), (b, a)):
                if from_hub in self.point_hubs.get(near, {}) and to_hub in self.point_hubs.get(
                    far, {}
                ):
                    if operator in self.point_pipes.get(
                        near, set()
                    ) and operator in self.point_pipes.get(far, set()):
                        found.append(Crossing(from_hub, to_hub, (near, far), operator))
        return sorted(
            found,
            key=lambda crossing: (crossing.points[0] not in self.representative, crossing.via),
        )

    def neighbours(self, hub: str) -> set[str]:
        out: set[str] = set()
        for hubs in self.point_hubs.values():
            if hub in hubs:
                out |= set(hubs) - {hub}
        for a, b in self.pipelines.values():
            if hub in self.point_hubs.get(a, {}):
                out |= set(self.point_hubs.get(b, {}))
            if hub in self.point_hubs.get(b, {}):
                out |= set(self.point_hubs.get(a, {}))
        out.discard(hub)
        return out

    def hub_paths(self, start: str, target: str, *, max_hops: int = 3) -> list[list[str]]:
        """Shortest sequences of market areas from ``start`` to ``target`` (by hop count)."""

        if start == target:
            return [[start]]
        paths: list[list[str]] = []
        queue: deque[list[str]] = deque([[start]])
        best: int | None = None
        while queue:
            path = queue.popleft()
            if best is not None and len(path) > best:
                break
            if len(path) - 1 >= max_hops:
                continue
            for nxt in sorted(self.neighbours(path[-1])):
                if nxt in path:
                    continue
                if nxt == target:
                    paths.append([*path, nxt])
                    best = len(path) + 1
                else:
                    queue.append([*path, nxt])
        return paths

    def route(
        self,
        start: str,
        target: str,
        *,
        via_points: Sequence[str] = (),
        max_hops: int = 3,
    ) -> list[Crossing] | None:
        """The crossings of the route, or None when no proven route exists.

        Without ``via_points`` the shortest route through each pair's representative point is
        taken (the point the map draws). With them, the route must pass exactly through the
        named points, in order; a named point that does not join consecutive market areas of a
        route makes the route unproven (None).
        """

        via = [point for point in via_points if point]
        candidates = (
            self.all_hub_paths(start, target, max_hops=max_hops)
            if via
            else self.hub_paths(start, target, max_hops=max_hops)
        )
        for hubs in candidates:
            chosen: list[Crossing] = []
            remaining = list(via)
            for a, b in zip(hubs, hubs[1:], strict=False):
                options = self.crossings(a, b)
                if remaining:
                    named = [crossing for crossing in options if remaining[0] in crossing.points]
                    if named:
                        options = named
                        remaining.pop(0)
                if not options:
                    break
                chosen.append(options[0])
            else:
                if not remaining:
                    return chosen
        return None

    def all_hub_paths(self, start: str, target: str, *, max_hops: int = 3) -> list[list[str]]:
        """Every simple sequence of market areas up to ``max_hops``, shortest first."""

        paths: list[list[str]] = []
        stack: list[list[str]] = [[start]]
        while stack:
            path = stack.pop()
            if path[-1] == target and len(path) > 1:
                paths.append(path)
                continue
            if len(path) - 1 >= max_hops:
                continue
            for nxt in sorted(self.neighbours(path[-1]), reverse=True):
                if nxt not in path:
                    stack.append([*path, nxt])
        return sorted(paths, key=lambda item: (len(item), item))

    # -- legs ------------------------------------------------------------------------

    def legs(self, crossing: Crossing) -> list[TariffLegSpec]:
        """Exit, pipeline and entry legs of one crossing, in flow order."""

        near, far = crossing.points[0], crossing.points[-1]
        legs = [self._market_area_leg(near, crossing.from_hub, "EXIT")]
        if crossing.pipeline_operator:
            charges = PIPELINE_CHARGES.get((crossing.pipeline_operator, near, far))
            if charges:
                for tso, point_name, direction, country, area in charges:
                    legs.append(
                        TariffLegSpec(near, point_name, country, tso, direction, area, "pipeline")
                    )
            else:
                name = self.operator_names.get(
                    crossing.pipeline_operator, crossing.pipeline_operator
                )
                for point, direction in ((near, "ENTRY"), (far, "EXIT")):
                    facts = self.points.get(point, {})
                    legs.append(
                        TariffLegSpec(
                            point,
                            str(facts.get("name") or point),
                            str(facts.get("country") or ""),
                            name,
                            direction,
                            name,
                            "pipeline",
                        )
                    )
        legs.append(self._market_area_leg(far, crossing.to_hub, "ENTRY"))
        return legs

    def _market_area_leg(self, point: str, hub: str, direction: str) -> TariffLegSpec:
        operators = self.point_hubs.get(point, {}).get(hub, ())
        for operator in operators:
            held = POINT_CHARGES.get((operator, point, direction))
            if held:
                tso, point_name, country, area = held
                return TariffLegSpec(
                    point, point_name, country, tso, direction, area, _role(direction)
                )
        facts = self.points.get(point, {})
        tso = " / ".join(self.operator_names.get(op, op) for op in operators) or "unknown TSO"
        return TariffLegSpec(
            point,
            str(facts.get("name") or point),
            str(facts.get("country") or ""),
            tso,
            direction,
            self.hub_names.get(hub),
            _role(direction),
        )

    def path_node_ids(self, crossings: Iterable[Crossing]) -> list[str]:
        """Node ids hub -> point(s) -> hub ..., the line the map draws for the route."""

        ids: list[str] = []
        for crossing in crossings:
            for key in (crossing.from_hub, *crossing.points, crossing.to_hub):
                node_id = self.points.get(key, {}).get("node_id")
                if node_id and (not ids or ids[-1] != node_id):
                    ids.append(node_id)
        return ids


def _role(direction: str) -> str:
    return "market_area_exit" if direction == "EXIT" else "market_area_entry"

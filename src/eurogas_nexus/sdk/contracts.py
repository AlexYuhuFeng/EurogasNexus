"""SDK client for /api/contracts."""

from pydantic import BaseModel, Field

from eurogas_nexus.sdk import _http


class CapacityContract(BaseModel):
    """A contracted transport capacity on one route.

    Attributes:
        contract_id: Unique identifier of the contract.
        route_name: Display name of the contracted route.
        from_node_id: Identifier of the entry (source) node.
        to_node_id: Identifier of the exit (destination) node.
        capacity_boe_d: Contracted capacity in barrels of oil equivalent per day.
        unit: Capacity unit (default ``boe/d``).
        start_utc: Contract start (ISO-8601 UTC); empty when not set.
        end_utc: Contract end (ISO-8601 UTC); empty when not set.
        status: Contract status (default ``active``).
    """

    contract_id: str
    route_name: str
    from_node_id: str
    to_node_id: str
    capacity_boe_d: float
    unit: str = "boe/d"
    # 合同可能是开放式（未定起止），空串表达"未设置"而非纪元时间。
    start_utc: str = ""
    end_utc: str = ""
    status: str = "active"


class RouteEligibility(BaseModel):
    """Eligibility of one route for capacity transport.

    Attributes:
        route_id: Identifier of the route.
        from_node_id: Identifier of the entry (source) node.
        to_node_id: Identifier of the exit (destination) node.
        eligibility: Eligibility verdict returned by the backend.
        confidence: Confidence of the verdict, used to rank low-confidence rows.
        constraints: Constraint labels applying to the route.
    """

    route_id: str
    from_node_id: str
    to_node_id: str
    eligibility: str
    confidence: float
    # constraints 用 default_factory 按实例新建列表，避免可变默认值共享。
    constraints: list[str] = Field(default_factory=list)


def _get(url: str) -> dict:
    """GET a JSON envelope and return the parsed payload."""

    r = _http.get(url, timeout=10)
    r.raise_for_status()
    return r.json()


def fetch_capacity_contracts(base_url: str) -> list[CapacityContract]:
    """Return all capacity contracts.

    Args:
        base_url: Base URL of the backend server.

    Returns:
        All capacity contracts currently exposed by the backend.
    """
    return [CapacityContract(**c) for c in _get(f"{base_url}/api/contracts/capacity")["data"]]

def fetch_route_eligibility(base_url: str) -> list[RouteEligibility]:
    """Return route eligibility verdicts.

    Args:
        base_url: Base URL of the backend server.

    Returns:
        All route eligibility rows currently exposed by the backend.
    """
    # eligibility 与 confidence 成对返回：展示层可把低置信度条目标黄
    # 供人工复核，而不是把资格判断当成事实直接采信。
    return [RouteEligibility(**r) for r in _get(f"{base_url}/api/contracts/routes")["data"]]

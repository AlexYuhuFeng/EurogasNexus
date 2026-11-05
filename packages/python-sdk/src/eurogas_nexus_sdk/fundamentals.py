"""Regional balance scenario client; the backend owns numerical calculations."""

from typing import Any

from eurogas_nexus_sdk import _http
from eurogas_nexus_sdk._transport import ResponseMeta, SdkResult, api_url


def calculate_nwe_balance_scenario(
    base_url: str, inputs: dict[str, Any], *, timeout_seconds: float = 30.0
) -> SdkResult[dict[str, Any]]:
    """Submit explicit scenario inputs, or replay the result's ``inputs`` object."""
    response = _http.post(
        api_url(base_url, "market/nwe-balance"), json=inputs, timeout=timeout_seconds
    )
    response.raise_for_status()
    payload = response.json()
    return SdkResult(data=payload["data"], meta=ResponseMeta.model_validate(payload["meta"]))

"""SDK client for provider credential metadata (read-only).

Credential writes are operator-only routes and intentionally have no SDK
client; this module only lists provider posture (configured/missing/status).
"""

from __future__ import annotations

from pydantic import BaseModel

from eurogas_nexus_sdk import _http
from eurogas_nexus_sdk._transport import ResponseMeta, SdkResult


class CredentialProviderDTO(BaseModel):
    """Read-only posture of one credential provider.

    Attributes:
        provider_id: Stable identifier of the provider.
        display_name: Human-readable provider name.
        credential_required: Whether the provider needs a credential at all.
        default_model: Default model the provider would use; None when unknown.
        configured: Whether a credential is configured for this provider.
        status: Overall posture label; None when the provider is not configured.
        label: Short status label for UI display; None when not configured.
        redacted_preview: Redacted preview of the stored credential; None when
            no credential is configured (never a plaintext secret).
        last_tested_at_utc: UTC timestamp of the last connectivity test; None
            when the credential was never tested.
        last_test_status: Result of the last test; None when never tested.
    """

    provider_id: str
    display_name: str
    credential_required: bool
    default_model: str | None = None
    configured: bool = False
    # 未配置/未测试的 provider 相关字段保持 None：把"未配置"误显示为
    # "失败"会引导用户做无意义的排查，None 表达的是状态缺失而非错误。
    status: str | None = None
    label: str | None = None
    redacted_preview: str | None = None
    last_tested_at_utc: str | None = None
    last_test_status: str | None = None


def fetch_credential_providers(
    base_url: str,
) -> SdkResult[list[CredentialProviderDTO]]:
    """List provider credential posture."""

    # rstrip('/') 归一化 base_url：调用方可能传 host/ 或 host，避免拼出双斜杠。
    response = _http.get(
        f"{base_url.rstrip('/')}/api/credentials/providers", timeout=10
    )
    response.raise_for_status()
    payload = response.json()
    return SdkResult(
        data=[CredentialProviderDTO.model_validate(row) for row in payload["data"]],
        meta=ResponseMeta.model_validate(payload["meta"]),
    )

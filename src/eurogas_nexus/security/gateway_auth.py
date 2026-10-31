"""Identity asserted by an authenticating gateway, for networks with their own SSO.

Many trading houses run a dedicated network whose single sign-on is not OIDC: SAML through
a service provider (Shibboleth, mod_auth_mellon, a Keycloak broker), Kerberos/SPNEGO
(integrated Windows authentication) through Apache or IIS, or a vendor agent (Broadcom
SiteMinder, Oracle Access Manager, PingAccess). They all end the same way: a reverse
proxy authenticates the person and forwards the request with the user and groups in
headers.

This mode accepts those headers only when the request also carries the gateway's shared
secret (compared in constant time) and, when configured, comes from a trusted proxy
address. Groups map to roles and data scopes with the same maps as OIDC
(``EUROGAS_NEXUS_OIDC_GROUPS_ROLE_MAP`` and ``..._SCOPE_MAP``), so a firm keeps one
role model whichever protocol its SSO speaks. Off unless
``EUROGAS_NEXUS_GATEWAY_AUTH_ENABLED`` is true.
"""

from __future__ import annotations

import hmac
import ipaddress
import os
from collections.abc import Mapping
from dataclasses import dataclass

from eurogas_nexus.security.identity import AuthenticatedPrincipal

ENABLED_ENV = "EUROGAS_NEXUS_GATEWAY_AUTH_ENABLED"
SECRET_ENV = "EUROGAS_NEXUS_GATEWAY_SECRET"
TRUSTED_PROXIES_ENV = "EUROGAS_NEXUS_GATEWAY_TRUSTED_PROXIES"
USER_HEADER_ENV = "EUROGAS_NEXUS_GATEWAY_USER_HEADER"
GROUPS_HEADER_ENV = "EUROGAS_NEXUS_GATEWAY_GROUPS_HEADER"
EMAIL_HEADER_ENV = "EUROGAS_NEXUS_GATEWAY_EMAIL_HEADER"
OFFICE_HEADER_ENV = "EUROGAS_NEXUS_GATEWAY_OFFICE_HEADER"
SECRET_HEADER = "X-Eurogas-Gateway-Secret"
MIN_SECRET_LENGTH = 32
_ROLE_ORDER = ("VIEWER", "REVIEWER", "ANALYST", "OPERATOR", "ADMIN")


class GatewayAuthError(Exception):
    """The gateway assertion is not trusted; carries a stable code."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class GatewayConfig:
    enabled: bool
    secret: str
    trusted_proxies: tuple[ipaddress.IPv4Network | ipaddress.IPv6Network, ...]
    user_header: str
    groups_header: str
    email_header: str
    office_header: str = "X-Remote-Office"

    @classmethod
    def from_env(cls, environ: Mapping[str, str] | None = None) -> GatewayConfig:
        env = os.environ if environ is None else environ
        proxies = tuple(
            ipaddress.ip_network(item.strip(), strict=False)
            for item in str(env.get(TRUSTED_PROXIES_ENV, "")).split(",")
            if item.strip()
        )
        return cls(
            enabled=str(env.get(ENABLED_ENV, "")).strip().lower() in {"1", "true", "yes", "on"},
            secret=str(env.get(SECRET_ENV, "")).strip(),
            trusted_proxies=proxies,
            user_header=str(env.get(USER_HEADER_ENV) or "X-Remote-User"),
            groups_header=str(env.get(GROUPS_HEADER_ENV) or "X-Remote-Groups"),
            email_header=str(env.get(EMAIL_HEADER_ENV) or "X-Remote-Email"),
            office_header=str(env.get(OFFICE_HEADER_ENV) or "X-Remote-Office"),
        )

    def problems(self) -> list[str]:
        """Configuration errors that make the mode unsafe (checked at start-up)."""

        if not self.enabled:
            return []
        problems = []
        if len(self.secret) < MIN_SECRET_LENGTH:
            problems.append(f"{SECRET_ENV} must be at least {MIN_SECRET_LENGTH} characters")
        return problems


def gateway_principal(
    headers: Mapping[str, str],
    peer: str | None,
    *,
    config: GatewayConfig,
    groups_role_map: Mapping[str, str],
    groups_scope_map: Mapping[str, list[str]],
) -> AuthenticatedPrincipal | None:
    """The principal the gateway asserts, ``None`` when the request carries no assertion.

    Raises:
        GatewayAuthError: the assertion is present but the secret or the peer is not trusted,
            or the mode is misconfigured.
    """

    lowered = {key.lower(): value for key, value in headers.items()}
    user = (lowered.get(config.user_header.lower()) or "").strip()
    if not config.enabled or not user:
        return None
    if config.problems():
        raise GatewayAuthError("gateway_misconfigured", "; ".join(config.problems()))
    presented = lowered.get(SECRET_HEADER.lower(), "")
    if not hmac.compare_digest(presented.encode(), config.secret.encode()):
        raise GatewayAuthError("gateway_secret_invalid", "The gateway assertion is not trusted.")
    if config.trusted_proxies:
        try:
            address = ipaddress.ip_address(peer or "")
        except ValueError as exc:
            raise GatewayAuthError("gateway_peer_untrusted", "Unknown gateway address.") from exc
        if not any(address in network for network in config.trusted_proxies):
            raise GatewayAuthError("gateway_peer_untrusted", "The gateway address is not trusted.")
    groups = [
        item.strip()
        for item in (lowered.get(config.groups_header.lower()) or "").replace(";", ",").split(",")
        if item.strip()
    ]
    roles = {groups_role_map[g] for g in groups if g in groups_role_map}
    role = max(roles, key=_ROLE_ORDER.index) if roles else "VIEWER"
    scopes = sorted({s for g in groups for s in groups_scope_map.get(g, [])})
    name = user.split("\\")[-1].split("@")[0]
    return AuthenticatedPrincipal(
        principal_id=f"sso:{user.lower()}"[:128],
        name=name,
        principal_type="USER",
        role=role,
        status="ACTIVE",
        data_scopes=tuple(scopes),
        roles=(role,),
        email=(lowered.get(config.email_header.lower()) or None),
        identity_source="GATEWAY",
        auth_method="gateway_header",
        office=(lowered.get(config.office_header.lower()) or "").strip().upper()[:16] or None,
    )

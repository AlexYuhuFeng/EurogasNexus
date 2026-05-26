"""Shared exception types for import-safe layers."""


class EurogasNexusError(Exception):
    """Base error for domain-neutral Eurogas Nexus failures."""


class ConfigurationError(EurogasNexusError):
    """Raised when configuration is invalid or incomplete."""


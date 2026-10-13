"""GIE AGSI/ALSI connector: real fetch-only transport (no mock fallback).

The previous shell inherited ``MockConnector`` and returned an empty payload, so
an absent credential was indistinguishable from an absent dataset. This connector
now calls the real GIE transport in :mod:`eurogas_nexus.ingestion.gie_transport`
and fails closed: a missing credential, a provider refusal, an empty response or
a malformed product identity raises instead of returning a synthetic empty
payload. It never substitutes simulated data.

The connector is fetch-only. The operator-facing ingestion path
(``scripts/ops/ingest_public_sources.py``) reuses the same transport and applies
the entitlement/certification gates and database persistence; this class exists
for the connector contract and for direct programmatic fetches.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime

import httpx

from eurogas_nexus.ingestion.connectors.base import ConnectorMetadata
from eurogas_nexus.ingestion.contracts import IngestionPayload
from eurogas_nexus.ingestion.gie_transport import (
    GIE_HARD_MAX_PAGES,
    GIE_MAX_PAGE_SIZE,
    GieCredentialMissingError,
    GieEmptyResponseError,
    GieProduct,
    fetch_gie_product,
    resolve_gie_api_key,
)

GIE_METADATA = ConnectorMetadata(
    source_system="GIE",
    datasets=("agsi-storage", "alsi-lng"),
    entitlement_required=True,
    polling_supported=True,
    request_mode_supported=True,
    freshness_expectation_minutes=60,
    export_restricted=True,
    research_only=True,
)

#: Registered dataset name -> GIE product constructor.
_DATASET_PRODUCTS = {
    "agsi-storage": GieProduct.agsi,
    "alsi-lng": GieProduct.alsi,
}


class GieConnector:
    """Real, bounded, fetch-only connector for GIE AGSI and ALSI.

    ``page_size`` and ``max_pages`` are independent: ``page_size=30,
    max_pages=2`` fetches two 30-record pages, it does not collapse into one
    60-record page. ``max_pages`` is clamped to the transport's absolute
    :data:`GIE_HARD_MAX_PAGES` ceiling.

    The returned aggregate payload carries the **last** page's post-response
    receipt instant (the conservative, latest retrieval time for the whole
    payload), and ``source_reference_id`` states the page count, the provider's
    advertised ``last_page`` and whether the fetch was complete, so a bounded
    partial can never be read as full history.

    Args:
        environ: Environment mapping for credential resolution; defaults to
            ``os.environ`` inside the transport.
        client: Optional pre-built ``httpx.Client`` (tests inject a
            ``MockTransport`` client). A client created here is closed after use.
        page_size: Entries per page, 1..300.
        max_pages: Bounded page count for one ``fetch`` call (clamped to the
            hard ceiling).
    """

    def __init__(
        self,
        *,
        environ: Mapping[str, str] | None = None,
        client: httpx.Client | None = None,
        page_size: int = 30,
        max_pages: int = 1,
    ) -> None:
        self._metadata = GIE_METADATA
        self._environ = environ
        self._client = client
        self._page_size = max(1, min(GIE_MAX_PAGE_SIZE, int(page_size)))
        self._max_pages = min(max(1, int(max_pages)), GIE_HARD_MAX_PAGES)

    @property
    def metadata(self) -> ConnectorMetadata:
        """Capabilities/requirements metadata of the GIE connector."""

        return self._metadata

    def fetch(self, dataset: str) -> IngestionPayload:
        """Fetch one GIE dataset from the live provider.

        Raises:
            ValueError: The dataset is not a registered GIE dataset.
            GieCredentialMissingError: No credential is configured.
            GieTransportError: The provider refused, failed or returned no data.
        """

        product_factory = _DATASET_PRODUCTS.get(dataset)
        if product_factory is None:
            raise ValueError(
                f"GIE connector does not serve dataset {dataset!r}; "
                f"expected one of: {', '.join(sorted(_DATASET_PRODUCTS))}."
            )
        product = product_factory()

        key = resolve_gie_api_key(self._environ)
        if key is None:
            raise GieCredentialMissingError(
                (
                    f"GIE {product.product} connector has no credential; set "
                    "GIE_API_KEY or GIE_API_KEY_FILE. An empty payload is not an "
                    "acceptable substitute."
                ),
                product=product.product,
            )

        client = self._client or httpx.Client(
            timeout=30.0,
            follow_redirects=False,
            headers={"User-Agent": "EurogasNexus/0.5 gie-connector"},
        )
        try:
            result = fetch_gie_product(
                client,
                product=product,
                api_key=key.value,
                page_size=self._page_size,
                max_pages=self._max_pages,
            )
        finally:
            if self._client is None:
                client.close()

        if not result.records:
            raise GieEmptyResponseError(
                f"GIE {product.product} returned no records for dataset {dataset!r}.",
                product=product.product,
            )

        # Conservative aggregate retrieval time: the latest post-response receipt
        # of the fetched pages, never the first page's receipt.
        retrieval_ts = max(page.received_at_utc for page in result.pages)
        return IngestionPayload(
            source_name=f"gie-{product.product.lower()}",
            source_reference=f"gie-{product.product.lower()}-api",
            source_system="GIE",
            dataset=dataset,
            raw_data=[dict(record) for record in result.records],
            retrieval_ts_utc=_iso(retrieval_ts),
            source_reference_id=result.source_reference,
        )


def _iso(value: datetime) -> str:
    return value.isoformat()

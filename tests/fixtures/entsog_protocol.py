"""Development-only small ENTSOG envelopes for transaction tests."""

import json
from datetime import UTC, datetime

import httpx

from eurogas_nexus.ingestion.entsog_transport import EntsogFetchResult, EntsogPage

RECEIPT = datetime(2026, 10, 13, 2, 0, tzinfo=UTC)


def observation(identifier="one", indicator="Physical Flow", value=10500000):
    return {
        "id": identifier,
        "indicator": indicator,
        "pointKey": "ITP-TEST",
        "pointLabel": "Test interconnection",
        "operatorKey": "TEST-TSO",
        "directionKey": "entry",
        "unit": "kWh/d",
        "value": value,
        "periodFrom": "2026-10-10T06:00:00+02:00",
        "periodTo": "2026-10-11T06:00:00+02:00",
        "lastUpdateDateTime": "2026-10-11T10:00:00+02:00",
    }


def connectionpoint(identifier="ITP-TEST"):
    return {
        "id": identifier,
        "pointKey": identifier,
        "pointLabel": "Test interconnection",
        "pointType": "Cross-Border Transmission",
        "countryKey": "BE",
        "tpMapX": 4.3,
        "tpMapY": 51.2,
        "hasData": True,
    }


def operatorpoint(identifier="opd-one", point="ITP-TEST"):
    return {
        "id": identifier,
        "pointKey": point,
        "pointLabel": "Test interconnection",
        "operatorKey": "BE-TSO-TEST",
        "operatorLabel": "Test TSO",
        "directionKey": "entry",
        "countryKey": "BE",
        "tsoEicCode": "21X-TEST",
        "hasData": True,
    }


def query_result(dataset, rows, *, complete=True, receipt=RECEIPT, offset=0, indicator=None):
    limit = len(rows) + 1 if complete else max(1, len(rows))
    params = {"limit": str(limit), "offset": str(offset), "sort": "id"}
    if indicator is not None:
        params["indicator"] = indicator
    url = str(httpx.URL(f"https://transparency.entsog.eu/api/v1/{dataset}", params=params))
    payload = {
        "meta": {
            "limit": limit,
            "offset": offset,
            "count": len(rows),
            "total": len(rows),
            "sort": "id",
        },
        dataset: rows,
    }
    # Deliberate whitespace proves that the raw archive does not hash reserialized JSON.
    raw = (json.dumps(payload, indent=2) + "\n").encode()
    page = EntsogPage(dataset, offset, limit, len(rows), len(rows), url, receipt, raw)
    return EntsogFetchResult(
        dataset,
        (page,),
        complete,
        "provider_offset_exhausted" if complete else "operator_record_budget",
        100,
        10,
    )

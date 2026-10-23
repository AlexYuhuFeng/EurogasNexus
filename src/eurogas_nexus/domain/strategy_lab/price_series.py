"""Stable evidence names shared by market discovery and historical evaluation."""

def canonical_price_name(source_system: str, tenor: str) -> str:
    normalized_source = source_system.upper().replace("_SIM", "")
    normalized_tenor = tenor.replace("-", "_").replace(" ", "_").upper()
    if "ICE_OCM" in normalized_source:
        return "ICE_OCM"
    if "ICIS" in normalized_source or "HEREN" in normalized_source:
        return "ICIS_HEREN_DAY_AHEAD"
    if "SAP" in normalized_source:
        return "SAP"
    if "EEX" in normalized_source:
        return (
            "EEX_DAY_AHEAD"
            if "DAY_AHEAD" in normalized_tenor or "DAYAHEAD" in normalized_tenor
            else f"EEX_{normalized_tenor}"
        )
    return f"{normalized_source}_{normalized_tenor}"


def evidence_tenor_from_product(product: str) -> str:
    lowered = product.lower()
    if "within-day" in lowered or "withinday" in lowered:
        return "within-day"
    if "day-ahead" in lowered or "day ahead" in lowered:
        return "day-ahead"
    if "weekend" in lowered:
        return "weekend"
    if "month" in lowered:
        return "month-ahead"
    return lowered

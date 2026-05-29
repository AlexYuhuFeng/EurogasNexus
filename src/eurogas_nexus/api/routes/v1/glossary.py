"""Read-only /api/v1/glossary routes — English and Mandarin gas terms."""

from fastapi import APIRouter, Query, Request

router = APIRouter(tags=["glossary"])


def _env(data: object) -> dict:
    return {"data": data, "meta": {"research_only": True, "human_review_required": True,
            "source_references": ["synthetic-fixture"]}}


_TERMS = {
    "TTF": {"en": "Title Transfer Facility — the primary Dutch/European gas trading hub.",
            "zh": "产权转让设施——荷兰/欧洲主要天然气交易中心。"},
    "NBP": {"en": "National Balancing Point — the UK gas trading hub.",
            "zh": "国家平衡点——英国天然气交易中心。"},
    "PEG": {"en": "Point d'Echange de Gaz — the French gas trading hub.",
            "zh": "天然气交易所点——法国天然气交易中心。"},
    "NCG": {"en": "NetConnect Germany — a German gas market area and trading hub.",
            "zh": "德国网络连接——德国天然气市场区和交易中心。"},
    "HDD": {"en": "Heating Degree Days — a measure of heating demand based on temperature.",
            "zh": "采暖度日数——基于温度的采暖需求衡量指标。"},
    "CDD": {"en": "Cooling Degree Days — a measure of cooling demand based on temperature.",
            "zh": "制冷度日数——基于温度的制冷需求衡量指标。"},
    "LNG": {"en": "Liquefied Natural Gas — natural gas cooled to liquid for transport.",
            "zh": "液化天然气——冷却至液态以便运输的天然气。"},
    "MCM": {"en": "Million Cubic Meters — a unit of gas volume.",
            "zh": "百万立方米——天然气体积单位。"},
    "boe": {"en": "Barrel of Oil Equivalent — a unit of energy.",
            "zh": "桶油当量——能量单位。"},
    "send-out": {"en": "Gas injected into the grid from an LNG terminal after regasification.",
                 "zh": "再气化后从液化天然气终端注入管网的天然气。"},
    "regas": {"en": "Regasification — the process of converting LNG back to gaseous state.",
              "zh": "再气化——将液化天然气转换回气态的过程。"},
    "netback": {"en": "Netback — market price minus transport cost, indicating upstream value.",
                "zh": "净回值——市场价格减去运输成本，指示上游价值。"},
    "spread": {"en": "Price spread — the difference between two market prices.",
               "zh": "价差——两个市场价格之间的差异。"},
    "ENTSOG": {"en": "European Network of Transmission System Operators for Gas.",
               "zh": "欧洲天然气输送系统运营商网络。"},
    "GIE": {"en": "Gas Infrastructure Europe — European gas infrastructure operators association.",
            "zh": "欧洲天然气基础设施——欧洲天然气基础设施运营商协会。"},
}


@router.get("/api/v1/glossary")
def list_terms(request: Request, lang: str = Query("en", pattern="^(en|zh)$")) -> dict:
    terms = [
        {"term": term, "definition": defs[lang]}
        for term, defs in sorted(_TERMS.items())
    ]
    return _env(terms)


@router.get("/api/v1/glossary/{term}")
def get_term(term: str, request: Request, lang: str = Query("en", pattern="^(en|zh)$")) -> dict:
    upper = term.upper()
    if upper not in _TERMS:
        from fastapi import HTTPException
        raise HTTPException(404, f"Term '{term}' not found.")
    return _env({"term": upper, "definition": _TERMS[upper][lang]})

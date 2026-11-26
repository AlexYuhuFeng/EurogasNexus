"""A small deterministic reader for the common way a desk states a spread study.

It covers ``<hub A> vs|–|minus <hub B> [tenor] [net of tariff]`` and ``spread between <hub A>
and <hub B> …`` in English and Chinese, and works with no model configured. Anything it cannot
place is left to the caller's questions; it never guesses a hub.

- ``between A and B`` / ``from A to B`` / ``A to B`` / ``从A到B`` / ``A和B之间``: gas moves
  A → B, so the spread is ``B − A`` (sell B, buy A) and a tariff is charged A → B;
- ``A vs B`` / ``A - B`` / ``A minus B`` / ``A over B`` / ``A对B`` / ``A减B``: the spread is
  ``A − B``, gas moves B → A;
- a tenor (``jan27``, ``M+1``, ``front month``, ``Q1-27``, ``cal-28``, ``DA``, ``次月``,
  ``27年1月``) makes it a history of that tenor; ``forward``, ``curve``, ``by tenor``, ``term
  structure``, ``远期``, ``曲线`` (or no tenor) make it the forward curve by delivery month;
- ``net of (transport|transmission|route) (tariff|cost)``, ``after tariffs``, ``扣除…费``,
  ``净`` add the route tariff in the spread's direction;
- ``in p/th`` / ``in EUR/MWh`` / ``in USD/MMBtu`` set the display unit; ``spot fx`` the FX;
- ``z-score`` / ``zscore`` / ``均值回归`` add a z-score rule (a history).

Pasted code is read as text, never run: only these words are looked for in it.

确定性解析器：覆盖常见的“A 对 B [期限] [扣除运输费]”表述（中英文），无模型时也可用；
无法识别的部分交给调用方提问，从不猜测枢纽；粘贴的代码只作文字读取，绝不执行。
"""

from __future__ import annotations

import re
from typing import Any

#: Hub words a desk writes, beyond the code itself (lower case) → hub code.
HUB_WORDS: dict[str, str] = {
    "ttf": "TTF", "dutch": "TTF", "netherlands": "TTF", "荷兰": "TTF",
    "nbp": "NBP", "uk": "NBP", "british": "NBP", "britain": "NBP", "英国": "NBP",
    "german": "THE", "germany": "THE", "德国": "THE",
    "peg": "PEG", "french": "PEG", "france": "PEG", "法国": "PEG",
    "ztp": "ZTP", "zeebrugge": "ZTP", "belgian": "ZTP", "belgium": "ZTP", "比利时": "ZTP",
    "psv": "PSV", "italian": "PSV", "italy": "PSV", "意大利": "PSV",
    "cegh": "CEGH", "austrian": "CEGH", "austria": "CEGH", "奥地利": "CEGH",
    "pvb": "PVB", "spanish": "PVB", "spain": "PVB", "西班牙": "PVB",
    "etf": "ETF", "danish": "ETF", "denmark": "ETF", "丹麦": "ETF",
    "gtf": "ETF",  # the OTC name of the Danish hub
    "hh": "HH", "henry hub": "HH", "亨利港": "HH", "亨利中心": "HH",
    "jkm": "JKM",
}
_TOKEN = re.compile(r"henry hub|[A-Za-z]+", re.IGNORECASE)
_MONTHS = ("jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec")

_BETWEEN = re.compile(
    r"\bbetween\b|\bfrom\b.*\bto\b|(?<=\w)\s+to\s+(?=\w)|从.+到|之间|到", re.IGNORECASE
)
_VERSUS = re.compile(r"\bvs\.?\b|\bversus\b|\bminus\b|\bover\b|\bagainst\b|对|减|[–—]|\s-\s",
                     re.IGNORECASE)
_NET = re.compile(
    r"net of|after (?:the )?(?:transport|transmission|route|tariff)|less (?:the )?(?:transport|"
    r"tariff|route)|(?:transport|transmission|route|pipeline) (?:tariff|cost|fee)s?|tariff|"
    r"扣除|运输费|管输费|输气费|运费|费率|净",
    re.IGNORECASE,
)
_CURVE = re.compile(r"forward|curve|by tenor|by delivery|term structure|strip|远期|曲线|期限结构",
                    re.IGNORECASE)
_HISTORY = re.compile(r"history|historical|over time|daily|z-?score|历史|均值回归|threshold|阈值",
                      re.IGNORECASE)
_ZSCORE = re.compile(r"z-?score|mean[- ]revers|均值回归", re.IGNORECASE)
_SPOT_FX = re.compile(r"spot fx|at spot|即期汇率", re.IGNORECASE)
_UNITS = (
    (re.compile(r"p\s*/\s*th(?:erm)?|pence|便士", re.IGNORECASE), "GBp/th"),
    (re.compile(r"usd\s*/\s*mmbtu|\$\s*/\s*mmbtu|美元", re.IGNORECASE), "USD/MMBtu"),
    (re.compile(r"gbp\s*/\s*mwh|£\s*/\s*mwh|英镑", re.IGNORECASE), "GBP/MWh"),
    (re.compile(r"eur\s*/\s*mwh|€\s*/\s*mwh|欧元", re.IGNORECASE), "EUR/MWh"),
)


def find_hubs(text: str, held: set[str] | None = None) -> list[tuple[int, str]]:
    """Hub codes named in ``text`` with their positions, in order, each once.

    ``THE`` counts only written in capitals (it is an English word). A code-like word that is
    not a known hub (``XYZ``) is returned as ``?XYZ`` so the caller can ask about it.
    """

    hits: list[tuple[int, str]] = []
    for match in _TOKEN.finditer(text):
        word = match.group(0)
        lower = word.lower()
        if word == "THE":
            hits.append((match.start(), "THE"))
        elif lower in HUB_WORDS:
            hits.append((match.start(), HUB_WORDS[lower]))
        elif held and word.upper() in held and word.isupper():
            hits.append((match.start(), word.upper()))
        elif word.isupper() and 3 <= len(word) <= 5 and word not in _NOT_HUBS:
            hits.append((match.start(), f"?{word}"))
    for zh, hub in HUB_WORDS.items():
        if re.match(r"[\u4e00-\u9fff]", zh):
            hits.extend((found.start(), hub) for found in re.finditer(re.escape(zh), text))
    out: list[tuple[int, str]] = []
    seen: set[str] = set()
    for position, code in sorted(hits):
        if code not in seen:
            seen.add(code)
            out.append((position, code))
    return out


_NOT_HUBS = frozenset({
    "EUR", "GBP", "USD", "MWH", "UK", "DA", "WD", "WE", "BOM", "CAL", "GY", "IUK", "BBL", "TSO",
    "LNG", "SPOT", "THEN", "AND", "FOR", "NET", "DEF", "RETURN", "IF", "ELSE", "SELL", "BUY",
    "MMBTU", "SQL", "API", "JSON",
})


def find_tenor(text: str) -> str | None:
    """A product code the text names (``M+1``, ``Jan-27``, ``Q1-27``, ``Cal-28``, ``DA``)."""

    lower = text.lower()
    if re.search(r"\bday[- ]ahead\b|\bda\b|日前", lower):
        return "DA"
    if re.search(r"\bwithin[- ]day\b|\bwd\b|日内", lower):
        return "WD"
    rolling = re.search(r"\b(m|q|s|cal|gy)\s*\+\s*(\d{1,2})\b", lower)
    if rolling:
        family = "Cal" if rolling.group(1) == "cal" else rolling.group(1).upper()
        return f"{family}+{int(rolling.group(2))}"
    if re.search(r"front[- ]month|month[- ]ahead|prompt month|\bm1\b|次月|近月|下月", lower):
        return "M+1"
    month = re.search(r"\b(" + "|".join(_MONTHS) + r")[a-z]*[\s'-]?(\d{2}|20\d{2})\b", lower)
    if month:
        return f"{month.group(1).title()}-{month.group(2)[-2:]}"
    zh_month = re.search(r"(\d{2}|20\d{2})年(\d{1,2})月", text)
    if zh_month and 1 <= int(zh_month.group(2)) <= 12:
        return f"{_MONTHS[int(zh_month.group(2)) - 1].title()}-{zh_month.group(1)[-2:]}"
    quarter = re.search(r"\bq([1-4])[\s-]?(\d{2}|20\d{2})\b", lower)
    if quarter:
        return f"Q{quarter.group(1)}-{quarter.group(2)[-2:]}"
    season = re.search(r"\b(sum|summer|win|winter)[\s-]?(\d{2}|20\d{2})\b", lower)
    if season:
        return f"{'Sum' if season.group(1).startswith('s') else 'Win'}-{season.group(2)[-2:]}"
    year = re.search(r"\b(cal|gy)[\s-]?(\d{2}|20\d{2})\b", lower)
    if year:
        return f"{'Cal' if year.group(1) == 'cal' else 'GY'}-{year.group(2)[-2:]}"
    return None


_TENOR_PATTERNS: tuple[tuple[re.Pattern[str], Any], ...] = (
    (re.compile(r"\bday[- ]ahead\b|\bda\b|日前", re.IGNORECASE), lambda m: "DA"),
    (re.compile(r"\bwithin[- ]day\b|\bwd\b|日内", re.IGNORECASE), lambda m: "WD"),
    (re.compile(r"\b(m|q|s|cal|gy)\s*\+\s*(\d{1,2})\b", re.IGNORECASE),
     lambda m: f"{'Cal' if m.group(1).lower() == 'cal' else m.group(1).upper()}+"
               f"{int(m.group(2))}"),
    (re.compile(r"front[- ]month|month[- ]ahead|prompt month|\bm1\b|次月|近月|下月",
                re.IGNORECASE), lambda m: "M+1"),
    (re.compile(r"\b(sum|summer|win|winter)[\s-]?(\d{2}|20\d{2})\b", re.IGNORECASE),
     lambda m: f"{'Sum' if m.group(1).lower().startswith('s') else 'Win'}-{m.group(2)[-2:]}"),
    (re.compile(r"(\d{2}|20\d{2})年?(冬季|夏季)"),
     lambda m: f"{'Win' if m.group(2) == '冬季' else 'Sum'}-{m.group(1)[-2:]}"),
    (re.compile(r"\bq([1-4])[\s-]?(\d{2}|20\d{2})\b", re.IGNORECASE),
     lambda m: f"Q{m.group(1)}-{m.group(2)[-2:]}"),
    (re.compile(r"\b(cal|gy)[\s-]?(\d{2}|20\d{2})\b", re.IGNORECASE),
     lambda m: f"{'Cal' if m.group(1).lower() == 'cal' else 'GY'}-{m.group(2)[-2:]}"),
    (re.compile(r"\b(" + "|".join(_MONTHS) + r")[a-z]*[\s'-]?(\d{2}|20\d{2})\b",
                re.IGNORECASE),
     lambda m: f"{m.group(1).title()}-{m.group(2)[-2:]}"),
)


def find_tenors(text: str) -> list[str]:
    """Every product code the text names, in the order written, each once."""

    hits: list[tuple[int, str]] = []
    taken: list[tuple[int, int]] = []
    for pattern, build in _TENOR_PATTERNS:
        for match in pattern.finditer(text):
            span = match.span()
            if any(start < span[1] and span[0] < end for start, end in taken):
                continue
            taken.append(span)
            hits.append((span[0], build(match)))
    out: list[str] = []
    for _, code in sorted(hits):
        if code not in out:
            out.append(code)
    return out


_NUMBER = r"(\d+(?:\.\d+)?)"
_LOOKBACK = re.compile(
    r"(?:lookback|look[- ]back|over|window|rolling|回看|窗口)\D{0,12}?(\d{1,3})\s*"
    r"(?:-?\s*days?|d\b|天|日|个交易日)|(\d{1,3})\s*(?:-?\s*days?|天|日)\s*"
    r"(?:lookback|look[- ]back|window|回看|窗口)",
    re.IGNORECASE,
)
_ENTRY = re.compile(
    r"(?:enter|entry|open)\D{0,14}?" + _NUMBER + r"|z\s*(?:值)?\s*" + _NUMBER
    + r"\s*(?:入场|开仓)",
    re.IGNORECASE,
)
_EXIT = re.compile(
    r"(?:exit|close|flat)\D{0,14}?" + _NUMBER + r"|" + _NUMBER + r"\s*(?:出场|平仓)",
    re.IGNORECASE,
)
_THRESHOLD = re.compile(r"threshold|阈值|storage cost|储气成本|储存成本", re.IGNORECASE)
_HIGH = re.compile(
    r"(?:storage cost|储气成本|储存成本|sell above|above|高于|卖出于)\D{0,6}?" + _NUMBER,
    re.IGNORECASE,
)
_LOW = re.compile(r"(?:buy below|below|低于|买入于)\D{0,6}?(-?\d+(?:\.\d+)?)",
                  re.IGNORECASE)


def find_rule(text: str) -> dict[str, Any] | None:
    """A rule the text states: z-score with its numbers, or a threshold with its levels."""

    threshold = bool(_THRESHOLD.search(text))
    zscore = bool(_ZSCORE.search(text))
    if not threshold and not zscore:
        return None
    rule: dict[str, Any] = {"kind": "threshold" if threshold and not zscore else "zscore"}
    lookback = _LOOKBACK.search(text)
    if lookback:
        rule["lookback"] = int(lookback.group(1) or lookback.group(2))
    else:
        rule["lookback"] = 20
    if rule["kind"] == "zscore":
        entry, leave = _ENTRY.search(text), _EXIT.search(text)
        if entry:
            rule["entry_z"] = float(entry.group(1) or entry.group(2))
        if leave:
            rule["exit_z"] = float(leave.group(1) or leave.group(2))
    else:
        high, low = _HIGH.search(text), _LOW.search(text)
        rule["high"] = float(high.group(1)) if high else None
        rule["low"] = float(low.group(1)) if low else None
    return rule


def parse_description(text: str, *, held_hubs: set[str] | None = None) -> dict[str, Any] | None:
    """A spec dict (``strategy_spec.spec_from_dict`` shape) for a common statement, or None.

    None when fewer than two hubs are named: the caller asks which instruments are meant.
    """

    clean = " ".join((text or "").split())[:2000]
    hubs = find_hubs(clean, held_hubs)
    unknown = [code[1:] for _, code in hubs if code.startswith("?")]
    tenors = find_tenors(clean)
    if len(hubs) == 1 and len(tenors) >= 2:
        # One hub, two products: a time spread (Win-27 − Sum-27, DA − M+1, M+1 − M+2).
        hub = hubs[0][1].lstrip("?")
        between = bool(_BETWEEN.search(clean)) and not _VERSUS.search(clean)
        later, earlier = (tenors[1], tenors[0]) if between else (tenors[0], tenors[1])
        return {
            "version": 1,
            "kind": "history",
            "legs": [{"hub": hub, "tenor": later, "weight": 1},
                     {"hub": hub, "tenor": earlier, "weight": -1}],
            "unit": next((code for pattern, code in _UNITS if re.search(r"\bin\s+|以|换算", clean)
                          and pattern.search(clean)), None),
            "fx": "spot" if _SPOT_FX.search(clean) else "forward",
            "cost": None,
            "rule": find_rule(clean),
            "_first_named": hub,
            "_unknown_hubs": [code[1:] for _, code in hubs if code.startswith("?")],
        }
    if len(hubs) < 2:
        return None
    first, second = (code for _, code in hubs[:2])
    between = bool(_BETWEEN.search(clean)) and not _VERSUS.search(clean)
    # "between A and B": gas moves A → B, the spread is B − A.
    sell, buy = (second, first) if between else (first, second)
    tenor = find_tenor(clean)
    wants_curve = bool(_CURVE.search(clean))
    wants_history = bool(_HISTORY.search(clean))
    kind = "history" if (tenor and not wants_curve) or wants_history else "curve"
    if kind == "history" and not tenor:
        tenor = "M+1"
    unit = next((code for pattern, code in _UNITS if re.search(r"\bin\s+|以|换算", clean)
                 and pattern.search(clean)), None)
    spec: dict[str, Any] = {
        "version": 1,
        "kind": kind,
        "legs": [
            {"hub": sell.lstrip("?"), "tenor": tenor if kind == "history" else None,
             "weight": 1},
            {"hub": buy.lstrip("?"), "tenor": tenor if kind == "history" else None,
             "weight": -1},
        ],
        "unit": unit,
        "fx": "spot" if _SPOT_FX.search(clean) else "forward",
        "cost": {"kind": "route_tariff", "from_hub": buy.lstrip("?"), "to_hub": sell.lstrip("?")}
        if _NET.search(clean)
        else None,
        "rule": find_rule(clean),
        "_first_named": first.lstrip("?"),
        "_unknown_hubs": unknown,
    }
    return spec

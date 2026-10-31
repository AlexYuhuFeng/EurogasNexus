"""Read a signed gas contract or confirmation (PDF) into a draft for human review.

Bilateral supply arrives as a PDF: an EFET General Agreement with an individual contract,
a confirmation, or a bespoke supply agreement, sometimes scanned. Re-keying it is slow and
error-prone, so intake reads the document and proposes the contract terms the workbench
holds, each with the page and the words it came from. Nothing is saved: the draft opens in
the contract workbench, a person checks every term against the document and saves it
through the governed contract write, which records who did and keeps both revisions.

Text comes from the PDF's own text layer (pypdf). A scanned page has none; if the server
has the Tesseract OCR engine installed (``tesseract`` on the path, Apache-2.0, installed by
the customer), the page's JPEG scan is read by OCR and the terms say so. Otherwise intake
reports that the document is a scan and asks for a text PDF or an OCR'd copy.

Terms recognised (case-insensitive, EFET wording and common variants): contract reference,
seller and buyer (the counterparty is the side that is not the firm, when the firm's own
names are set in ``EUROGAS_NEXUS_OWN_LEGAL_NAMES``), delivery point and hub, delivery
period (as a gas-year label), daily contract quantity in MWh/d, kWh/h, MW, th/d or GJ/d
(converted to MWh/d), contract price in EUR/MWh, GBP/MWh, p/th or USD/MMBtu or an index
formula, delivery and nomination tolerances, payment day, governing law and the EFET
master agreement. A term not found is left out, never guessed.
"""

from __future__ import annotations

import io
import os
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from datetime import date

OWN_NAMES_ENV = "EUROGAS_NEXUS_OWN_LEGAL_NAMES"
MAX_PDF_BYTES = 20 * 1024 * 1024
MAX_PAGES = 200
_OCR_TIMEOUT_SECONDS = 60
_THERM_MWH = 0.029307107
_MMBTU_MWH = 0.29307107
_HUBS = {
    "TTF": ("TTF", "Title Transfer Facility"),
    "NBP": ("NBP", "National Balancing Point"),
    "THE": ("THE", "Trading Hub Europe"),
    "PEG": ("PEG", "Point d'Echange de Gaz", "Point d’Echange de Gaz", "TRF"),
    "ZTP": ("ZTP", "Zeebrugge Trading Point", "ZEE"),
    "PSV": ("PSV", "Punto di Scambio Virtuale"),
    "PVB": ("PVB", "Punto Virtual de Balance"),
    "CEGH": ("CEGH", "VTP Austria", "Central European Gas Hub"),
    "ETF": ("ETF", "Exchange Transfer Facility"),
}


class IntakeError(ValueError):
    """The upload is not a PDF this intake can read."""


@dataclass
class Term:
    value: object
    page: int
    evidence: str
    unit: str = ""
    note: str = ""

    def as_dict(self, name: str) -> dict[str, object]:
        return {
            "field": name,
            "value": self.value,
            "unit": self.unit,
            "page": self.page,
            "evidence": self.evidence,
            "note": self.note,
        }


@dataclass
class IntakeResult:
    file_name: str
    pages: int
    text_pages: int
    ocr_pages: int
    terms: dict[str, Term] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)

    def record(self) -> dict[str, object]:
        """The draft record the contract workbench reads (its import overlay keys)."""

        record: dict[str, object] = {
            "document_name": self.file_name,
            "document_status": "PDF_EXTRACTED_REVIEW_REQUIRED",
            "source_reference": f"pdf:{self.file_name}",
        }
        for name, term in self.terms.items():
            if name.startswith("_"):
                continue
            record[name] = term.value
        return record

    def as_dict(self) -> dict[str, object]:
        return {
            "file_name": self.file_name,
            "pages": self.pages,
            "text_pages": self.text_pages,
            "ocr_pages": self.ocr_pages,
            "record": self.record(),
            "terms": [term.as_dict(name) for name, term in self.terms.items()],
            "warnings": self.warnings,
        }


# --------------------------------------------------------------------------------- reading


def _ocr_page(page) -> str:
    """OCR the JPEG scans on a page with a locally installed Tesseract, if there is one."""

    binary = shutil.which("tesseract")
    if not binary:
        return ""
    texts = []
    try:
        images = list(page.images)
    except Exception:  # noqa: BLE001 - malformed image dictionaries: no OCR for this page
        return ""
    for image in images[:4]:
        data = getattr(image, "data", b"") or b""
        if not data.startswith(b"\xff\xd8"):  # only JPEG scans go straight to Tesseract
            continue
        with tempfile.TemporaryDirectory() as folder:
            path = os.path.join(folder, "page.jpg")
            with open(path, "wb") as handle:
                handle.write(data)
            try:
                completed = subprocess.run(  # noqa: S603 - fixed binary, temp file argument
                    [binary, path, "stdout", "--psm", "4"],
                    capture_output=True,
                    timeout=_OCR_TIMEOUT_SECONDS,
                    check=False,
                )
            except (OSError, subprocess.TimeoutExpired):
                continue
            texts.append(completed.stdout.decode("utf-8", "replace"))
    return "\n".join(texts)


def read_pdf(content: bytes) -> tuple[list[str], int, int]:
    """Text per page, the number of pages with a text layer and the number read by OCR."""

    if not content.startswith(b"%PDF"):
        raise IntakeError("The file is not a PDF.")
    if len(content) > MAX_PDF_BYTES:
        raise IntakeError(f"The PDF is larger than {MAX_PDF_BYTES // (1024 * 1024)} MB.")
    from pypdf import PdfReader
    from pypdf.errors import PdfReadError

    try:
        reader = PdfReader(io.BytesIO(content))
        if reader.is_encrypted:
            try:
                reader.decrypt("")
            except Exception as exc:  # noqa: BLE001
                raise IntakeError("The PDF is password-protected.") from exc
        pages = list(reader.pages)[:MAX_PAGES]
    except PdfReadError as exc:
        raise IntakeError("The PDF could not be read.") from exc
    texts, text_pages, ocr_pages = [], 0, 0
    for page in pages:
        try:
            text = page.extract_text() or ""
        except Exception:  # noqa: BLE001 - one bad page must not lose the document
            text = ""
        if len(text.strip()) >= 40:
            text_pages += 1
        else:
            scanned = _ocr_page(page)
            if scanned.strip():
                ocr_pages += 1
                text = scanned
        texts.append(text)
    return texts, text_pages, ocr_pages


# ------------------------------------------------------------------------------ extraction


def _clean(text: str) -> str:
    return re.sub(r"[ \t ]+", " ", text)


def _number(raw: str) -> float | None:
    text = raw.strip().replace(" ", "").replace(" ", "")
    if re.fullmatch(r"\d{1,3}(\.\d{3})+(,\d+)?", text):  # 1.234.567,89
        text = text.replace(".", "").replace(",", ".")
    elif re.fullmatch(r"\d{1,3}(,\d{3})+(\.\d+)?", text):  # 1,234,567.89
        text = text.replace(",", "")
    elif re.fullmatch(r"\d+,\d+", text):  # 12,5
        text = text.replace(",", ".")
    try:
        return float(text)
    except ValueError:
        return None


def _snippet(text: str, start: int, end: int) -> str:
    return _clean(text[max(0, start - 30) : min(len(text), end + 50)]).strip()[:200]


_LABEL_END = r"\s*(?:[:\-–]|\bis\b|\bshall be\b)?\s*"


def _first(pages: list[str], pattern: str, flags=re.IGNORECASE | re.MULTILINE):
    regex = re.compile(pattern, flags)
    for number, text in enumerate(pages, start=1):
        match = regex.search(text)
        if match:
            return number, text, match
    return None


_QUANTITY_UNITS = {
    "mwh/d": 1.0,
    "mwh per day": 1.0,
    "mwh/day": 1.0,
    "gwh/d": 1000.0,
    "gwh per day": 1000.0,
    "kwh/h": 0.024,
    "mw": 24.0,
    "th/d": _THERM_MWH,
    "therms/d": _THERM_MWH,
    "therms per day": _THERM_MWH,
    "gj/d": 1 / 3.6,
    "gj per day": 1 / 3.6,
}
_QTY_UNIT = (
    r"(MWh\s*/\s*d(?:ay)?|MWh per day|GWh\s*/\s*d|GWh per day|kWh\s*/\s*h|MW\b|"
    r"th(?:erms)?\s*/\s*d|therms per day|GJ\s*/\s*d|GJ per day)"
)
_NUM = r"(\d[\d.,  ]*\d|\d)"


def _quantity(pages: list[str]) -> Term | None:
    found = _first(
        pages,
        r"(?:daily contract quantity|contract quantity|\bDCQ\b|daily quantity|"
        r"contract capacity|quantity)[^\n\d]{0,60}?" + _NUM + r"\s*" + _QTY_UNIT,
    )
    if not found:
        return None
    page, text, match = found
    value = _number(match.group(1))
    unit = re.sub(r"\s+", "", match.group(2).lower()).replace("perday", "/d").replace("/day", "/d")
    unit = {"therms/d": "th/d", "mwhperday": "mwh/d", "gwhperday": "gwh/d"}.get(unit, unit)
    factor = next((f for k, f in _QUANTITY_UNITS.items() if re.sub(r"\s+", "", k) == unit), None)
    if value is None or factor is None:
        return None
    note = "" if factor == 1.0 else f"converted from {match.group(1).strip()} {match.group(2)}"
    return Term(round(value * factor, 3), page, _snippet(text, *match.span()), "MWh/d", note)


_PRICE = (
    r"(?:contract price|price)[^\n\d€£$]{0,60}?"
    r"(EUR|€|GBP|£|USD|\$)?\s*" + _NUM + r"\s*"
    r"(EUR|€|GBP|£|USD|\$|p|pence)?\s*(?:/|per)\s*(MWh|therm|th|MMBtu)"
)


def _price(pages: list[str]) -> tuple[Term | None, Term | None]:
    """A fixed price converted to per MWh, or an index formula when the price floats."""

    index = _first(
        pages,
        r"(?:contract price|price)[^\n]{0,40}?((?:TTF|NBP|THE|PEG|ZTP|PSV|PVB|CEGH)[^\n]{0,80}"
        r"(?:index|month[- ]ahead|day[- ]ahead|heren|argus|icis|EEX|settlement)[^\n]{0,80})",
    )
    found = _first(pages, _PRICE)
    fixed = None
    if found:
        page, text, match = found
        before, raw, after, per = match.group(1), match.group(2), match.group(3), match.group(4)
        value = _number(raw)
        currency_mark = (before or after or "").lower()
        per = per.lower()
        if value is not None:
            if currency_mark in {"p", "pence"} and per in {"therm", "th"}:
                currency, per_mwh = "GBP", value / 100 / _THERM_MWH
            else:
                currency = {"€": "EUR", "£": "GBP", "$": "USD"}.get(
                    currency_mark, currency_mark.upper() or "EUR"
                )
                per_mwh = {"mwh": value, "therm": value / _THERM_MWH, "th": value / _THERM_MWH}.get(
                    per, value / _MMBTU_MWH
                )
            fixed = Term(
                round(per_mwh, 4),
                page,
                _snippet(text, *match.span()),
                f"{currency}/MWh",
                ""
                if per == "mwh" and currency_mark not in {"p", "pence"}
                else f"converted from {raw} {after or before or ''}/{per}".strip(),
            )
    index_term = None
    if index:
        page, text, match = index
        index_term = Term(_clean(match.group(1)).strip()[:160], page, _snippet(text, *match.span()))
    return fixed, index_term


_MONTHS = {
    m: i
    for i, m in enumerate(
        ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1
    )
}


def _date(raw: str) -> date | None:
    raw = raw.strip().rstrip(".,")
    for pattern in (r"(\d{4})-(\d{2})-(\d{2})", r"(\d{1,2})[./](\d{1,2})[./](\d{4})"):
        match = re.fullmatch(pattern, raw)
        if match:
            a, b, c = (int(x) for x in match.groups())
            try:
                return date(a, b, c) if a > 31 else date(c, b, a)
            except ValueError:
                return None
    match = re.fullmatch(r"(\d{1,2})(?:st|nd|rd|th)?\s+([A-Za-z]{3})[A-Za-z]*\s+(\d{4})", raw)
    if match:
        month = _MONTHS.get(match.group(2).lower())
        if month:
            try:
                return date(int(match.group(3)), month, int(match.group(1)))
            except ValueError:
                return None
    return None


_DATE = (
    r"(\d{4}-\d{2}-\d{2}|\d{1,2}[./]\d{1,2}[./]\d{4}"
    r"|\d{1,2}(?:st|nd|rd|th)?\s+[A-Za-z]{3,9}\s+\d{4})"
)


def _period(pages: list[str]) -> Term | None:
    found = _first(
        pages,
        r"(?:delivery period|contract period|term)[^\n]{0,60}?(?:from\s+)?"
        + _DATE
        + r"[^\n]{0,40}?(?:to|until|through|–|-)\s*"
        + _DATE,
    )
    if not found:
        return None
    page, text, match = found
    start, end = _date(match.group(1)), _date(match.group(2))
    if start is None or end is None or end < start:
        return None
    first_year = start.year if start.month >= 10 else start.year - 1
    last_year = end.year if end.month >= 10 else end.year - 1
    label = f"{first_year}" if last_year <= first_year else f"{first_year}-{last_year}"
    note = f"delivery {start.isoformat()} to {end.isoformat()}; gas years from October"
    return Term(label, page, _snippet(text, *match.span()), "gas year", note)


def _party(pages: list[str], role: str) -> Term | None:
    found = _first(
        pages,
        rf"(?:^|\n)\s*(?:the\s+)?{role}\s*(?:[:\-–]|\(the \"?{role}\"?\))\s*"
        r"([A-Z][^\n,;()]{2,100})",
    )
    if not found:
        found = _first(
            pages, rf"([A-Z][A-Za-z0-9&.\- ]{{2,80}}?)\s*\((?:the\s+)?[\"“]?{role}[\"”]?\)"
        )
    if not found:
        return None
    page, text, match = found
    name = _clean(match.group(1)).strip(" .")
    return Term(name, page, _snippet(text, *match.span()))


def _pct(pages: list[str], labels: str) -> Term | None:
    found = _first(pages, rf"(?:{labels})[^\n%]{{0,80}}?(\d+(?:[.,]\d+)?)\s*(?:%|per ?cent)")
    if not found:
        found = _first(pages, rf"(\d+(?:[.,]\d+)?)\s*(?:%|per ?cent)[^\n]{{0,40}}(?:{labels})")
    if not found:
        return None
    page, text, match = found
    value = _number(match.group(1))
    return None if value is None else Term(value, page, _snippet(text, *match.span()), "%")


def _text_term(pages: list[str], pattern: str, group: int = 1) -> Term | None:
    found = _first(pages, pattern)
    if not found:
        return None
    page, text, match = found
    return Term(_clean(match.group(group)).strip(" .")[:160], page, _snippet(text, *match.span()))


def _own_names(environ=None) -> set[str]:
    env = os.environ if environ is None else environ
    raw = env.get(OWN_NAMES_ENV, "")
    return {item.strip().casefold() for item in raw.split(",") if item.strip()}


def extract_terms(pages: list[str], *, own_names: set[str] | None = None) -> dict[str, Term]:
    own = _own_names() if own_names is None else own_names
    terms: dict[str, Term] = {}

    def put(name: str, term: Term | None) -> None:
        if term is not None and term.value not in (None, ""):
            terms[name] = term

    put(
        "contract_id",
        _text_term(
            pages,
            r"(?:contract|confirmation|agreement|deal|trade)\s*(?:reference|ref\.?|no\.?|number|id)"
            + _LABEL_END
            + r"([A-Z0-9][A-Z0-9/_.\-]{2,60})",
        ),
    )
    seller, buyer = _party(pages, "Seller"), _party(pages, "Buyer")
    put("_seller", seller)
    put("_buyer", buyer)
    if seller and buyer:
        seller_own = any(name in str(seller.value).casefold() for name in own)
        buyer_own = any(name in str(buyer.value).casefold() for name in own)
        if buyer_own and not seller_own:
            put("counterparty", seller)
        elif seller_own and not buyer_own:
            put("counterparty", buyer)
        else:
            put(
                "counterparty",
                Term(
                    seller.value,
                    seller.page,
                    seller.evidence,
                    note="the seller; set the firm's own names to pick the other party",
                ),
            )
    elif seller or buyer:
        put("counterparty", seller or buyer)
    point = _text_term(pages, r"delivery point" + _LABEL_END + r"([^\n]{3,120})")
    if point is not None:
        upper = str(point.value).upper()
        hub = next(
            (code for code, names in _HUBS.items() if any(n.upper() in upper for n in names)), None
        )
        put(
            "delivery_point_name",
            Term(
                hub or point.value,
                point.page,
                point.evidence,
                note="" if hub else "no hub recognised; check the point",
            ),
        )
        put("title_transfer_point", point)
    put("gas_year", _period(pages))
    put("delivery_quantity_mwh_per_day", _quantity(pages))
    fixed, index = _price(pages)
    if fixed is not None:
        if fixed.unit == "GBP/MWh":
            put("contract_price_gbp_mwh", fixed)
        else:
            put("_contract_price", fixed)
    put("index_basis", index)
    put("delivery_tolerance_pct", _pct(pages, "delivery tolerance|swing|flexibility"))
    put("nomination_tolerance_pct", _pct(pages, "nomination tolerance|renomination"))
    put(
        "_payment_day",
        _text_term(
            pages,
            r"(?:payment|invoice)[^\n]{0,80}?"
            r"(\d{1,2}(?:st|nd|rd|th)?\s+(?:business |banking )?day)",
        ),
    )
    put(
        "governing_law",
        _text_term(
            pages,
            r"governed by (?:and construed in accordance with )?(?:the )?"
            r"(laws? of [A-Z][A-Za-z ]{2,40}|[A-Z][a-z]+ law)",
        ),
    )
    put(
        "contract_type",
        _text_term(
            pages,
            r"(EFET General Agreement[^\n]{0,60}|individual contract[^\n]{0,40}|"
            r"confirmation[^\n]{0,20}EFET[^\n]{0,40})",
        ),
    )
    return terms


def intake_pdf(
    content: bytes, *, file_name: str, own_names: set[str] | None = None
) -> IntakeResult:
    texts, text_pages, ocr_pages = read_pdf(content)
    result = IntakeResult(
        file_name=re.sub(r"[^\w.\- ]+", "_", file_name)[:128] or "contract.pdf",
        pages=len(texts),
        text_pages=text_pages,
        ocr_pages=ocr_pages,
    )
    if not any(text.strip() for text in texts):
        result.warnings.append(
            "The PDF has no text layer (a scan) and no OCR engine is installed on the server; "
            "upload a text PDF or an OCR'd copy, or ask IT to install Tesseract."
        )
        return result
    if ocr_pages:
        result.warnings.append(
            f"{ocr_pages} page(s) were read by OCR; check figures on those pages character "
            "by character."
        )
    result.terms = extract_terms(texts, own_names=own_names)
    price = result.terms.get("_contract_price")
    if price is not None:
        result.warnings.append(
            f"The fixed price is {price.value} {price.unit}; the workbench price field is "
            "GBP/MWh, so enter it there only after converting, or record it in the notes."
        )
    missing = [
        label
        for key, label in (
            ("counterparty", "counterparty"),
            ("delivery_point_name", "delivery point"),
            ("gas_year", "delivery period"),
            ("delivery_quantity_mwh_per_day", "daily quantity"),
        )
        if key not in result.terms
    ]
    if missing:
        result.warnings.append(f"Not found in the document: {', '.join(missing)}.")
    result.warnings.append(
        "Every term is a proposal: check it against the page shown before saving."
    )
    return result

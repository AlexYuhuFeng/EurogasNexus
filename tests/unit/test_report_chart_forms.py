"""Report exhibits gain the in-app chart standard's two forms (design basis 2, F.3 #12).

``band``: lines over a grey history range and its mean, the range labelled with the years it
is drawn from; a day where the range is not held is a gap. ``term_structure``: price by
delivery month with a marker per month (never bars), prior curves in grey, months labelled
"Jan-27". The catalogue's existing types are untouched by these additions.
"""

from __future__ import annotations

import re
from datetime import date, timedelta

from eurogas_nexus.application.reports.charts import chart_table, render_chart


def _days(first: date, count: int) -> list[str]:
    return [(first + timedelta(days=i)).isoformat() for i in range(count)]


def _band_spec() -> dict:
    days = _days(date(2026, 10, 1), 10)
    low = [[d, 60.0 + i] for i, d in enumerate(days)]
    low[4][1] = None  # one day not held by every year: the range has a gap there
    return {
        "type": "band",
        "unit": "%",
        "title": "EU storage fill",
        "series": [
            {"name": "2026/27", "points": [[d, 70.0 + i * 0.5] for i, d in enumerate(days)]},
            {"name": "2025/26", "context": True,
             "points": [[d, 75.0 + i * 0.4] for i, d in enumerate(days)]},
        ],
        "band": {
            "label": "5-yr range 2021/22–2025/26",
            "mean_label": "5-yr mean",
            "low": low,
            "high": [[d, 80.0 + i] for i, d in enumerate(days)],
            "mean": [[d, 70.0 + i] for i, d in enumerate(days)],
        },
    }


def test_band_draws_the_range_in_grey_split_at_a_missing_day() -> None:
    svg = render_chart(_band_spec(), "fig1")
    polygons = re.findall(r'<polygon [^>]*class="r-band"', svg)
    assert len(polygons) == 2, "a day the range does not hold breaks it in two"
    assert 'class="r-band-mean"' in svg and 'stroke-dasharray="4 3"' in svg
    # A long label is shortened by its name, never its years (reports `_fit_label`).
    assert "2021/22–2025/26" in svg
    assert "5-yr mean" in svg
    # The subject is drawn after (over) the context and the band.
    assert svg.index('class="r-band"') < svg.index('class="r-stroke-1"')


def test_band_table_carries_the_range_beside_the_series() -> None:
    header, rows = chart_table(_band_spec())
    assert header == [
        "Day",
        "2026/27 (%)",
        "2025/26 (%)",
        "5-yr range 2021/22–2025/26 low (%)",
        "5-yr range 2021/22–2025/26 high (%)",
        "5-yr range 2021/22–2025/26 mean (%)",
    ]
    assert rows[0][3:] == ["60.00", "80.00", "70.00"]
    assert rows[4][3] == "n/a", "the missing day is a gap, not zero"


def test_term_structure_marks_each_delivery_month_and_labels_months() -> None:
    months = ["2026-12", "2027-01", "2027-02", "2027-03"]
    spec = {
        "type": "term_structure",
        "unit": "EUR/MWh",
        "title": "TTF curve",
        "series": [
            {"name": "TTF", "points": [[m, 31.0 - i] for i, m in enumerate(months)]},
            {"name": "Close 13 Nov", "context": True,
             "points": [[m, 30.5 - i] for i, m in enumerate(months)]},
        ],
    }
    svg = render_chart(spec, "fig2")
    assert svg.count('fill="#ffffff" stroke=') == len(months), "one marker per month, subject only"
    assert "<rect" not in svg.split('<g class="r-hover">')[0], "never bars"
    assert "Mar-27" in svg and "Dec-26" in svg

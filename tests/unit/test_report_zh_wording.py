"""A Chinese report reads Chinese throughout: the masthead and a refused conversion's reason."""

from eurogas_nexus.application.reports import joins, render
from eurogas_nexus.application.reports.lang import writing


def test_refused_conversion_reason_is_chinese():
    reason = joins._unconvertible_zh(ValueError("not convertible: no EURGBP rate held"))
    assert reason == "未持有截至该日的 EURGBP 汇率"
    forward = joins._unconvertible_zh(ValueError("not convertible forward: x"))
    assert "not convertible" not in forward
    assert joins._unconvertible_zh(ValueError("anything else")) == "缺少所需的汇率或换算系数"


def test_publication_line_follows_the_report_language():
    with writing("zh-CN"):
        assert render._publication() == "Eurogas Nexus · 天然气市场"
    with writing("en"):
        assert render._publication() == "Eurogas Nexus · Gas Markets"

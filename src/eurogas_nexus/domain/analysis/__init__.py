"""LLM-ready analysis and report contracts built from backend data snapshots.

Package facade: re-exports the public API of the former ``domain/analysis.py``
monolith so existing importers keep working unchanged. Submodules:

- ``contracts`` — Pydantic data contracts.
- ``builders`` — deterministic report/answer builders.
- ``glossary_context`` — glossary term context assembly.
- ``glossary_profile`` — term -> context profile resolution.
- ``glossary_entities`` — entity matching, metrics, quality, sections.

本包是分析/报告链路的领域层：只做纯函数组装，不发起外部调用、
不访问数据库；LLM 调用与否由 API 层决定并经 provider 门禁控制。
"""

from __future__ import annotations

from eurogas_nexus.domain.analysis.builders import (
    build_analysis_result,
    build_portfolio_report,
    business_logic_ontology,
)
from eurogas_nexus.domain.analysis.contracts import (
    AnalysisRequest,
    AnalysisResult,
    AnalysisSnapshot,
    AnalysisTask,
    GlossaryContext,
    PortfolioReportRequest,
    ReportSection,
)
from eurogas_nexus.domain.analysis.glossary_context import build_glossary_context

__all__ = [
    "AnalysisRequest",
    "AnalysisResult",
    "AnalysisSnapshot",
    "AnalysisTask",
    "GlossaryContext",
    "PortfolioReportRequest",
    "ReportSection",
    "build_analysis_result",
    "build_glossary_context",
    "build_portfolio_report",
    "business_logic_ontology",
]

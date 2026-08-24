"""Report/answer builders: deterministic cited output from snapshots.

本模块是分析链路的"构建层"：从快照与（可选）LLM 文本组装可引用的
确定性输出。外部 provider 只在调用方显式开启时参与，缺省路径纯确定性
（不发起任何外部调用）。
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from eurogas_nexus.domain.analysis._common import _unique
from eurogas_nexus.domain.analysis.contracts import (
    AnalysisRequest,
    AnalysisResult,
    AnalysisSnapshot,
    AnalysisTask,
    PortfolioReportRequest,
    ReportSection,
)


def business_logic_ontology() -> dict:
    """Return the business ontology used by analysis and reports.

    返回业务本体摘要：由类型化 ``domain.ontology`` 契约派生，保证分析
    上下文与领域引擎使用同一套概念、关系与护栏。

    Returns:
        Dict with ``entities`` (concept ids), ``relationships`` (subject
        predicate object strings) and ``guardrails`` (list).
    """

    from eurogas_nexus.domain.ontology import CONCEPTS, GUARDRAILS, RELATIONS

    return {
        "entities": [concept.concept_id for concept in CONCEPTS],
        "relationships": [
            f"{relation.subject} {relation.predicate} {relation.object}"
            for relation in RELATIONS
        ],
        "guardrails": list(GUARDRAILS),
    }


def build_analysis_result(
    request: AnalysisRequest,
    snapshot: AnalysisSnapshot,
    *,
    provider_text: str | None = None,
    provider_status: str = "not_invoked",
) -> AnalysisResult:
    """Build deterministic cited output, optionally enriched by provider text.

    组装分析结果：引用、缺失输入、预警、默认章节与确定性双语答案。

    Args:
        request: The analysis request.
        snapshot: Backend-data snapshot to cite and summarize.
        provider_text: Optional provider synthesis text (enrichment only).
        provider_status: ``not_invoked`` / ``success`` / error tag.

    Returns:
        An AnalysisResult with deterministic answer text, sections,
        citations, missing inputs and warnings.

    Raises:
        No exceptions; missing inputs are reported in the result.
    """

    citations = _snapshot_citations(snapshot)
    missing_inputs = _missing_inputs_for_task(request, snapshot)
    warnings = [*snapshot.warnings]
    if not request.invoke_provider:
        # 未开启 provider 时必须显式告警：答案仅为确定性摘要。
        warnings.append("LLM_PROVIDER_NOT_INVOKED")
    if provider_status not in {"not_invoked", "success"}:
        warnings.append(provider_status)

    sections = _default_sections(request, snapshot, provider_text)
    answer_en = provider_text or _deterministic_answer_en(request, snapshot)
    answer_zh = _deterministic_answer_zh(request, snapshot)
    return AnalysisResult(
        analysis_id=f"analysis-{uuid4().hex[:12]}",
        task=request.task,
        provider_id=request.provider_id,
        provider_status=provider_status,
        answer_en=answer_en,
        answer_zh_cn=answer_zh,
        citations=citations,
        sections=sections,
        missing_inputs=missing_inputs,
        warnings=_unique(warnings),
        snapshot_id=snapshot.snapshot_id,
        created_at_utc=datetime.now(UTC),
    )


def build_portfolio_report(
    request: PortfolioReportRequest,
    snapshot: AnalysisSnapshot,
    *,
    provider_text: str | None = None,
    provider_status: str = "not_invoked",
) -> AnalysisResult:
    """Build a portfolio decision-support report.

    组合投资组合报告：把 PortfolioReportRequest 投影为 AnalysisRequest
    后复用通用构建器（行为与直接查询一致，只是任务类型不同）。

    Args:
        request: The portfolio report request.
        snapshot: Backend-data snapshot.
        provider_text: Optional provider synthesis text.
        provider_status: Provider status tag.

    Returns:
        An AnalysisResult for the PORTFOLIO_REPORT task.

    Raises:
        No exceptions; missing inputs are reported in the result.
    """

    analysis_request = AnalysisRequest(
        question=request.title,
        task=AnalysisTask.PORTFOLIO_REPORT,
        provider_id=request.provider_id,
        model=request.model,
        invoke_provider=request.invoke_provider,
        selected_contracts=request.selected_contracts,
        selected_assets=request.selected_resources,
        duration_start_utc=request.duration_start_utc,
        duration_end_utc=request.duration_end_utc,
        language=request.language,
    )
    return build_analysis_result(
        analysis_request,
        snapshot,
        provider_text=provider_text,
        provider_status=provider_status,
    )


def _default_sections(
    request: AnalysisRequest,
    snapshot: AnalysisSnapshot,
    provider_text: str | None,
) -> list[ReportSection]:
    """Assemble the default report sections (portfolio/market/strategy[/llm]).

    默认章节：组合与资源、市场与物理上下文、策略与 PnL；有 provider
    文本时追加 LLM 综合章节。每章都带快照引用。
    """

    sections = [
        ReportSection(
            section_id="portfolio",
            title="Portfolio and resources",
            content=(
                f"{len(snapshot.portfolio_context)} portfolio records and "
                f"{len(snapshot.route_candidates)} route candidates were available."
            ),
            citations=_snapshot_citations(snapshot),
        ),
        ReportSection(
            section_id="market",
            title="Market and physical context",
            content=(
                f"{len(snapshot.market_observations)} market observations, "
                f"{len(snapshot.fx_rates)} FX rates, and "
                f"{len(snapshot.flow_observations)} flow observations were available."
            ),
            citations=_snapshot_citations(snapshot),
        ),
        ReportSection(
            section_id="strategy",
            title="Strategy and PnL context",
            content=(
                f"{len(snapshot.strategy_runs)} strategy run records were available. "
                "Historical PnL requires persisted strategy or portfolio PnL records."
            ),
            citations=_snapshot_citations(snapshot),
            warnings=["HISTORICAL_PNL_REQUIRES_PERSISTED_PNL_SERIES"],
        ),
    ]
    if provider_text:
        sections.append(
            ReportSection(
                section_id="llm",
                title=f"{request.provider_id} synthesis",
                content=provider_text,
                citations=_snapshot_citations(snapshot),
            )
        )
    return sections


def _deterministic_answer_en(request: AnalysisRequest, snapshot: AnalysisSnapshot) -> str:
    """Deterministic English answer summarizing the evaluated context."""

    return (
        f"{request.task} was evaluated against snapshot {snapshot.snapshot_id}. "
        f"Available context: {len(snapshot.market_observations)} market observations, "
        f"{len(snapshot.fx_rates)} FX rates, {len(snapshot.flow_observations)} flow records, "
        f"{len(snapshot.route_candidates)} routes, and "
        f"{len(snapshot.strategy_runs)} strategy runs. "
        "Use the cited source snapshots and warnings before making any commercial decision."
    )


def _deterministic_answer_zh(request: AnalysisRequest, snapshot: AnalysisSnapshot) -> str:
    """Deterministic Chinese answer summarizing the evaluated context."""

    return (
        f"{request.task} 已基于快照 {snapshot.snapshot_id} 进行评估。"
        f"可用上下文包括 {len(snapshot.market_observations)} 条市场观测、"
        f"{len(snapshot.fx_rates)} 条汇率、{len(snapshot.flow_observations)} 条物理流量、"
        f"{len(snapshot.route_candidates)} 条路线和 {len(snapshot.strategy_runs)} 条策略运行。"
        "在作出任何商业决策前，必须查看引用来源、缺失输入和预警。"
    )


def _missing_inputs_for_task(
    request: AnalysisRequest,
    snapshot: AnalysisSnapshot,
) -> list[str]:
    """List missing snapshot inputs required by the request's task.

    按任务类型判定缺失输入：PnL/组合报告需要策略与组合上下文，
    TSO 状态报告需要流量观测，市场异动需要市场观测；缺什么报什么。
    """

    missing: list[str] = []
    if request.task in {AnalysisTask.PNL_TRACKING, AnalysisTask.PORTFOLIO_REPORT}:
        if not snapshot.strategy_runs:
            missing.append("STRATEGY_OR_PORTFOLIO_PNL_SERIES_MISSING")
        if not snapshot.portfolio_context:
            missing.append("PORTFOLIO_CONTEXT_MISSING")
    if request.task == AnalysisTask.TSO_STATUS_REPORT and not snapshot.flow_observations:
        missing.append("TSO_FLOW_OBSERVATIONS_MISSING")
    if request.task == AnalysisTask.MARKET_MOVEMENT and not snapshot.market_observations:
        missing.append("MARKET_OBSERVATIONS_MISSING")
    return missing


def _snapshot_citations(snapshot: AnalysisSnapshot) -> list[str]:
    """Collect deduplicated source references from every snapshot collection.

    从快照各集合中提取 source_reference/source_system 作为引用清单
    （含快照来源本身），去重保序。
    """

    citations = [snapshot.source]
    for collection in (
        snapshot.market_observations,
        snapshot.live_market_marks,
        snapshot.fx_rates,
        snapshot.flow_observations,
        snapshot.capacity_context,
        snapshot.route_candidates,
        snapshot.strategy_runs,
        snapshot.portfolio_context,
    ):
        for row in collection:
            ref = row.get("source_reference") or row.get("source_system")
            if ref:
                citations.append(str(ref))
    return _unique(citations)

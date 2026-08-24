"""Freshness evaluation against source expectations (audit item 3).

Rows are written with their observed freshness at write time, but "is this
source still live?" is a read-side question: compare the newest observed row
against the source's declared ``freshness_expectation_minutes``. Sources with
no declared expectation evaluate as UNKNOWN (annotated, not silently live).

本模块是新鲜度判定的唯一实现：读侧（Source Center）、写侧（ingestion）
与任何未来消费者都使用同一个三态结果，避免各端自行解释"过期"。
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum


class FreshnessStatus(StrEnum):
    """Three-state freshness classification for a data source.

    三态语义：live=期望窗口内；stale=超过期望窗口；unknown=无法判定
    （无观测或无期望声明）。unknown 必须被展示为"未判定"，不得当作 live。
    """

    LIVE = "live"
    STALE = "stale"
    UNKNOWN = "unknown"


def evaluate_freshness(
    expectation_minutes: int,
    last_observed_at_utc: datetime | None,
    now_utc: datetime | None = None,
) -> FreshnessStatus:
    """Evaluate whether the newest observation satisfies the expectation.

    评估最新观测是否满足来源的新鲜度期望（审计项 3 的判定核心）。

    Args:
        expectation_minutes: Positive expectation window in minutes;
            non-positive values mean no expectation is declared and the
            result is UNKNOWN (fail-closed, never silently live).
        last_observed_at_utc: Newest observation time, or None when the
            source has no observations yet.
        now_utc: Evaluation clock; defaults to ``datetime.now(UTC)``.
            Injectable for deterministic tests.

    Returns:
        ``LIVE`` when the newest observation is at most
        ``expectation_minutes`` old, ``STALE`` when older, ``UNKNOWN`` when
        no observation or no positive expectation exists.

    Raises:
        No exceptions are raised; all malformed inputs degrade to UNKNOWN.
    """

    if last_observed_at_utc is None:
        # 无观测：无从判定，明确标记 unknown 而非假定活跃。
        return FreshnessStatus.UNKNOWN
    if expectation_minutes <= 0:
        # 未声明期望：任何行龄判定都没有基准，同样标记 unknown。
        return FreshnessStatus.UNKNOWN

    observed = _as_utc(last_observed_at_utc)
    now = _as_utc(now_utc or datetime.now(UTC))
    if observed > now:
        # 时钟偏差容忍：未来时间戳按 live 处理（数据源时钟超前）。
        return FreshnessStatus.LIVE
    age_minutes = (now - observed).total_seconds() / 60.0
    if age_minutes <= expectation_minutes:
        return FreshnessStatus.LIVE
    return FreshnessStatus.STALE


def _as_utc(value: datetime) -> datetime:
    """Normalize a timestamp to an aware UTC datetime.

    naive 时间戳按 UTC 解释（与全仓 ISO 契约一致），避免时区混算。
    """

    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)

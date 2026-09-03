"""Semantic Kernel v1 — small, stable value objects for the executable ontology.

These types are the canonical carriers for the semantics the audit called out:

- ``Measure``/``Money``/``PriceBasis``/``FxConversionRef`` — quantities keep
  their unit/currency and reference conditions; unknown conversions fail closed.
- ``GasDayRef``/``GasYearRef``/``TimeInterval``/``EffectivePeriod`` — time is
  interval-based and versioned (DST-aware gas days via the gas_day calendar).
- ``CanonicalId``/``ExternalIdentifier`` — stable internal ids vs versioned
  external identifier schemes (EIC, ENTSOG pointKey, hub codes, ...).
- ``JurisdictionRef``/``RegulatoryInstrumentRef`` — explicit jurisdiction with
  versioned, superseding regulatory instruments.
- ``SourceRef``/``LineageRef`` — provenance for raw -> canonical mapping.
- ``OntologyVersion``/``MappingVersion`` — every interpretation is versioned.

PostgreSQL + Pydantic remain the storage and validation substrate; no RDF/OWL.

本模块是全仓语义的"可执行本体"：值对象一律 frozen 不可变，跨层传递时
不会发生"数字与单位脱钩"的静默混算；任何版本化规则（法规、日历、
映射）都通过显式版本引用，禁止覆盖历史。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

from eurogas_nexus.domain.market.gas_day import (
    GAS_DAY_CALENDARS,
    gas_day_interval_utc,
)

_EUROPE_ZONE = ZoneInfo("Europe/Berlin")

# ---------------------------------------------------------------------------
# Identity
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CanonicalId:
    """Stable internal identifier: ``concept:value``.

    Attributes:
        concept: Ontology concept name (e.g. ``hub``, ``point``).
        value: Concept-specific stable value (e.g. ``THE``).
    """

    concept: str
    value: str

    def __str__(self) -> str:
        # 单一序列化形式：concept:value，作为主键/外键引用的统一载体。
        return f"{self.concept}:{self.value}"


@dataclass(frozen=True)
class ExternalIdentifier:
    """A versioned identifier from an external scheme (EIC, pointKey, ...).

    ``valid_from``/``valid_to`` let renaming/migration be represented instead
    of overwriting history (e.g. THE replacing NCG/GASPOOL).

    Attributes:
        identifier: The raw external identifier value.
        scheme: Identifier scheme, e.g. ``EIC``, ``ENTSOG_POINT_KEY``,
            ``HUB_CODE``, ``LEI``.
        valid_from: First day the identifier is active (inclusive).
        valid_to: Last day the identifier is active (inclusive); None = open.
    """

    identifier: str
    scheme: str
    valid_from: date | None = None
    valid_to: date | None = None

    def active_on(self, day: date) -> bool:
        """Whether this identifier is active on the given calendar day.

        Args:
            day: The day to test.

        Returns:
            True when the day falls inside the validity window; open-ended
            windows treat the missing bound as unbounded.
        """

        if self.valid_from is not None and day < self.valid_from:
            return False
        if self.valid_to is not None and day > self.valid_to:
            return False
        return True


# ---------------------------------------------------------------------------
# Quantity semantics
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Measure:
    """A quantity with its canonical unit and optional reference conditions.

    Attributes:
        value: Numeric magnitude in the canonical unit.
        unit: Canonical unit, e.g. ``MWh``, ``mcm``, ``therm``.
        reference_conditions: Physical reference conditions, e.g.
            ``25C/101.325kPa``; None when not applicable.
    """

    value: float
    unit: str
    reference_conditions: str | None = None


@dataclass(frozen=True)
class Money:
    """A monetary amount in an explicit ISO 4217 currency.

    Attributes:
        amount: Monetary magnitude.
        currency: ISO 4217 code (e.g. ``EUR``, ``GBP``, ``USD``).
    """

    amount: float
    currency: str


def money_triple_valid(
    amount: float | None,
    currency: str | None,
    unit: str | None,
) -> bool:
    """Whether a (amount, currency, unit) triple is a valid money expression.

    判定定价三元组是否自洽：计价组件必须三要素齐全，未计价组件必须全空，
    杜绝"裸数字混加"这类静默错误。

    Args:
        amount: Monetary amount, or None for an unpriced component.
        currency: ISO 4217 code, or None.
        unit: Billing unit (e.g. ``MWh``), or None.

    Returns:
        True when the triple is self-consistent: an unpriced component
        (amount None) must carry neither currency nor unit; a priced
        component must carry both non-blank currency and unit. Anything
        else is a silent-mixing hazard and must fail closed rather than be
        summed as a bare number.
    """

    if amount is None:
        return not (currency or unit)
    return bool((currency or "").strip() and (unit or "").strip())


@dataclass(frozen=True)
class PriceBasis:
    """A price with explicit money, unit, venue, and assessment time.

    Attributes:
        money: The price's monetary amount and currency.
        unit: Price unit (e.g. ``MWh``).
        venue: Trading venue / index name, or None when not applicable.
        assessment_time_utc: When the price was assessed, or None.
    """

    money: Money
    unit: str
    venue: str | None = None
    assessment_time_utc: datetime | None = None


@dataclass(frozen=True)
class FxConversionRef:
    """Provenance of a cross-currency conversion (as-of FX observation).

    记录汇率换算的来源凭据：任何跨币种金额都必须能回溯到一次具体观测，
    不允许在无依据的情况下直接换算。

    Attributes:
        from_currency: Source ISO 4217 currency.
        to_currency: Target ISO 4217 currency.
        rate: Applied conversion rate (from -> to).
        observation_id: Reference to the FX observation record, or None.
        value_date: Value date of the FX observation, or None.
    """

    from_currency: str
    to_currency: str
    rate: float
    observation_id: str | None = None
    value_date: date | None = None


# ---------------------------------------------------------------------------
# Time semantics
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TimeInterval:
    """A half-open UTC interval [start, end).

    Attributes:
        start_utc: Interval start (inclusive), aware UTC.
        end_utc: Interval end (exclusive), aware UTC.
    """

    start_utc: datetime
    end_utc: datetime

    def contains(self, instant: datetime) -> bool:
        """Whether the interval contains the instant (half-open).

        Args:
            instant: Timestamp to test; naive values are assumed UTC.

        Returns:
            True when ``start_utc <= instant < end_utc``.
        """

        if instant.tzinfo is None:
            instant = instant.replace(tzinfo=UTC)
        return self.start_utc <= instant < self.end_utc


@dataclass(frozen=True)
class GasDayRef:
    """One gas day under an explicit, versioned calendar.

    Attributes:
        label: Stable label = calendar date of the local start (ISO).
        calendar_version: Gas-day calendar version id (e.g. ``EU-CAM-2025``).
        start_utc: Gas-day start, aware UTC.
        end_utc: Gas-day end (next day's local 05:00), aware UTC.
    """

    label: str
    calendar_version: str
    start_utc: datetime
    end_utc: datetime

    @classmethod
    def containing(
        cls,
        instant: datetime,
        calendar: str = "EU-CAM-2025",
    ) -> GasDayRef:
        """Build the gas-day reference containing ``instant``.

        Args:
            instant: Timestamp to locate; naive values are assumed UTC.
            calendar: Calendar version id; defaults to ``EU-CAM-2025``.

        Returns:
            A frozen GasDayRef with label, calendar version and UTC bounds.

        Raises:
            ValueError: When ``calendar`` is not registered.
        """

        start, end = gas_day_interval_utc(instant, calendar=calendar)
        zone = _calendar_zone_name(calendar)
        local_date = start.astimezone(zone).date().isoformat()
        return cls(
            label=local_date,
            calendar_version=calendar,
            start_utc=start,
            end_utc=end,
        )


@dataclass(frozen=True)
class GasYearRef:
    """A gas year (Oct 1 .. Sep 30) with explicit UTC bounds.

    Attributes:
        year: Gas-year label = the calendar year in which it starts.
        start_utc: Gas-year start (Oct 1, 05:00 UTC), aware.
        end_utc: Gas-year end (next Oct 1, 05:00 UTC), aware.
    """

    year: int
    start_utc: datetime
    end_utc: datetime

    @classmethod
    def containing(cls, instant: datetime) -> GasYearRef:
        """Build the gas-year reference containing ``instant``.

        Args:
            instant: Timestamp to locate; naive values are assumed UTC.

        Returns:
            A frozen GasYearRef with the European gas-year bounds.
        """

        if instant.tzinfo is None:
            instant = instant.replace(tzinfo=UTC)
        year = instant.astimezone(_EUROPE_ZONE).year
        start = datetime(year, 10, 1, 5, 0, tzinfo=UTC)
        if instant < start:
            # 10 月 1 日 05:00 UTC 之前的时刻仍属于上一个气体年。
            start = datetime(year - 1, 10, 1, 5, 0, tzinfo=UTC)
            year -= 1
        end = datetime(year + 1, 10, 1, 5, 0, tzinfo=UTC)
        return cls(year=year, start_utc=start, end_utc=end)


@dataclass(frozen=True)
class EffectivePeriod:
    """Effective-dated validity window (open-ended allowed).

    Attributes:
        valid_from: Window start (inclusive); None = unbounded past.
        valid_to: Window end (inclusive); None = open-ended.
    """

    valid_from: datetime | None = None
    valid_to: datetime | None = None

    def contains(self, instant: datetime) -> bool:
        """Whether the instant falls inside the effective window.

        Args:
            instant: Timestamp to test (aware or naive UTC).

        Returns:
            True when both bounds (when present) admit the instant.
        """

        if self.valid_from is not None and instant < self.valid_from:
            return False
        if self.valid_to is not None and instant > self.valid_to:
            return False
        return True


# ---------------------------------------------------------------------------
# Jurisdiction & regulation
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RegulatoryInstrumentRef:
    """A versioned regulatory instrument.

    Attributes:
        instrument_id: Stable id (e.g. ``REG-2024-1789``).
        title_en: English title of the instrument.
        effective_from: First day the instrument is effective.
        supersedes: Instrument id this one replaces, or None.
    """

    instrument_id: str
    title_en: str
    effective_from: date
    supersedes: str | None = None


@dataclass(frozen=True)
class JurisdictionRef:
    """Explicit jurisdiction (EU, GB, DE, NL, ...) with applicable instruments.

    Attributes:
        jurisdiction_id: Jurisdiction code.
        instruments: Applicable regulatory instruments, most recent first.
    """

    jurisdiction_id: str
    instruments: tuple[RegulatoryInstrumentRef, ...] = ()


_REG_715_2009 = RegulatoryInstrumentRef(
    instrument_id="REG-2009-715",
    title_en=(
        "Regulation (EC) No 715/2009 on conditions for access to natural gas "
        "transmission networks"
    ),
    effective_from=date(2009, 9, 3),
)
_REG_2024_1789 = RegulatoryInstrumentRef(
    instrument_id="REG-2024-1789",
    title_en="Regulation (EU) 2024/1789 (recast of the gas market rules)",
    effective_from=date(2024, 8, 4),
    supersedes="REG-2009-715",
)
_REG_2017_459 = RegulatoryInstrumentRef(
    instrument_id="REG-2017-459",
    title_en="Regulation (EU) 2017/459 (CAM Network Code)",
    effective_from=date(2017, 4, 6),
)
_REG_2015_703 = RegulatoryInstrumentRef(
    instrument_id="REG-2015-703",
    title_en="Regulation (EU) 2015/703 (interoperability Network Code)",
    effective_from=date(2015, 5, 1),
)
_REG_2011_1227 = RegulatoryInstrumentRef(
    instrument_id="REG-2011-1227",
    title_en="Regulation (EU) No 1227/2011 (REMIT)",
    effective_from=date(2011, 12, 28),
)
_REG_2024_1106 = RegulatoryInstrumentRef(
    instrument_id="REG-2024-1106",
    title_en="Regulation (EU) 2024/1106 (REMIT amendment)",
    effective_from=date(2024, 7, 15),
    supersedes="REG-2011-1227",
)

EU_JURISDICTION = JurisdictionRef(
    jurisdiction_id="EU",
    instruments=(
        _REG_2024_1789,
        _REG_2017_459,
        _REG_2015_703,
        _REG_2024_1106,
    ),
)

# 历史法规保留在登记表中用于"有效期内引用"，但不再出现在当前管辖区清单。
KNOWN_REGULATORY_INSTRUMENTS: tuple[RegulatoryInstrumentRef, ...] = (
    _REG_715_2009,
    _REG_2024_1789,
    _REG_2017_459,
    _REG_2015_703,
    _REG_2011_1227,
    _REG_2024_1106,
)

KNOWN_JURISDICTIONS: tuple[JurisdictionRef, ...] = (EU_JURISDICTION,)

# 法规被替代关系表：2009/715 由 2024/1789 重订，2011/1227（REMIT）
# 由 2024/1106 修订；查询"当日适用版本"时沿此链解析。
_INSTRUMENT_SUPERSEDED_BY = {
    "REG-2009-715": "REG-2024-1789",
    "REG-2011-1227": "REG-2024-1106",
}


def applicable_instrument(
    instrument_id: str,
    on: date,
) -> RegulatoryInstrumentRef | None:
    """Resolve the instrument version effective on ``on``.

    解析指定日期生效的法规版本：先沿替代链前进到现行版本，再校验其
    生效日期；未来生效的版本不返回（返回 None 表示当日无适用版本）。

    Args:
        instrument_id: Instrument id, possibly superseded.
        on: The date of interest.

    Returns:
        The effective instrument, or None when no version is effective yet
        or the id is unknown.
    """

    current = instrument_id
    visited: set[str] = set()
    while current in _INSTRUMENT_SUPERSEDED_BY and current not in visited:
        # 防御环保护：替代链理论上无环，但解析器必须避免死循环。
        visited.add(current)
        current = _INSTRUMENT_SUPERSEDED_BY[current]
    for instrument in KNOWN_REGULATORY_INSTRUMENTS:
        if instrument.instrument_id == current and instrument.effective_from <= on:
            return instrument
    return None


# ---------------------------------------------------------------------------
# Provenance
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SourceRef:
    """Reference to one source record (system + reference + observation time).

    Attributes:
        source_system: Source system id (e.g. ``entsog``, ``gie``).
        source_reference: Record id within the source system.
        observed_at_utc: When the record was observed, or None.
        dataset: Dataset name within the source, or None.
    """

    source_system: str
    source_reference: str
    observed_at_utc: datetime | None = None
    dataset: str | None = None


@dataclass(frozen=True)
class LineageRef:
    """Raw -> canonical mapping provenance for one transformed value.

    Attributes:
        raw_reference: Reference of the raw source record.
        mapping_version: Version of the mapping applied.
        transformed_at_utc: When the transformation happened.
    """

    raw_reference: str
    mapping_version: str
    transformed_at_utc: datetime


# ---------------------------------------------------------------------------
# Versions
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class OntologyVersion:
    """Semantic version of the executable ontology.

    Attributes:
        major: Breaking semantics changes.
        minor: Additive semantics.
        patch: Corrections with no semantic change.
    """

    major: int
    minor: int
    patch: int

    def label(self) -> str:
        """Return the ``vX.Y.Z`` display label."""

        return f"v{self.major}.{self.minor}.{self.patch}"


@dataclass(frozen=True)
class MappingVersion:
    """Version of the raw -> canonical mapping for one source family.

    Attributes:
        source_system: Source system the mapping applies to.
        version: Mapping version string.
        released_at_utc: When the mapping version was released.
    """

    source_system: str
    version: str
    released_at_utc: datetime


def current_ontology_version() -> OntologyVersion:
    """Version of the executable ontology shipped with this codebase.

    Returns:
        The current semantic version; bump it whenever the ontology's
        semantics change in a way consumers must observe.
    """

    return OntologyVersion(0, 5, 0)


def gas_day_calendar_versions() -> tuple[str, ...]:
    """Return the supported versioned gas-day calendar ids.

    Returns:
        Sorted tuple of registered calendar version ids.
    """

    return tuple(sorted(GAS_DAY_CALENDARS))


def _calendar_zone_name(calendar: str) -> ZoneInfo:
    """Resolve a calendar id to its IANA timezone (internal helper)."""

    return ZoneInfo(GAS_DAY_CALENDARS[calendar].timezone_name)

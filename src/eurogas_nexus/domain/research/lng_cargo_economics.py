"""LNG cargo economics composition — research-only decision support.

Two public compositions share one private monetary/cash implementation:

1. The preserved strict path, ``compute_lng_cargo_economics``, requires an
   ``LngRegasScenario``, delegates to the existing regas readiness assessor and
   fails closed on its blocking missing inputs.
2. The economics-only path, ``compute_lng_economics_only``, requires no physical
   scenario, never calls the readiness assessor and never fabricates terminal,
   slot, storage, TSO or nomination evidence. Its result explicitly declares
   ``physical_readiness='NOT_ASSESSED'`` and ``readiness_assessed=False``.

Both paths compose explicitly supplied LNG cargo energy quantities, unit prices,
a declared purchase basis and itemized downstream costs into the delivered-unit
sale basis, the per-purchased-MWh unit netback and the total cargo margin — then,
by reusing the bounded ``lng_cash_valuation`` primitive with explicit dated
discount factors, into undiscounted cash and net present value. It is decision
support only, not accounting, custody or settlement, and it must not be read as
complete LNG business economics.

唯一职责（research boundary / 研究边界）:
- 只做"显式能量数量 × 显式单价 − 显式下游成本 → 单位 netback / 船货毛利 /
  损失披露"的组合运算，并把同一组显式金额/日期/贴现因子交给既有
  ``domain/research/lng_cash_valuation.py`` 本原计算 NPV；
- 不推断船量/能量换算（m³/MMBtu 一律不转换、不默认），不把损失自动货币化，
  不合并或重复计算成本，不默认任何价格、日期、来源、汇率或购买基准；
- legacy 路径的就绪度沿用 ``domain/route_cost/lng_regas.py`` 的既有评估器：
  其 ``missing_inputs`` 非空即 fail-closed 拒绝给出估值结果；其 ``warnings``
  只原样传播，不当作"全部阻断"的借口，也不在全局修改就绪度规则；
- economics-only 路径只接受显式有序能量阶段；该路径不调用就绪度评估器，
  因此也绝不以缺失场景、槽位、权利或任意物理证据来伪装"已就绪"。

Declared formulas (all within one explicit local decimal context, quantum
0.0001, ROUND_HALF_EVEN):

- ``purchase_outlay_eur`` = purchased_energy_mwh × purchase_unit_price
- ``sale_proceeds_eur`` = delivered_energy_mwh × sale_unit_price
- ``total_downstream_costs_eur`` = sum of individually rounded cost EUR totals
  (nonnegative), matching the cash primitive's per-leg rounding
- ``unit_netback_eur_per_purchased_mwh`` =
      (sale_proceeds − total_downstream_costs) ÷ purchased_energy_mwh
- ``sale_basis_eur_per_delivered_mwh`` = sale_proceeds ÷ delivered_energy_mwh
  (a separate denominator; the two denominators are never mixed)
- ``cargo_margin_eur`` = sale_proceeds − total_downstream_costs − purchase_outlay
- reconciliation: ``cargo_margin_eur`` must equal
      (unit_netback − purchase_unit_price) × purchased_energy_mwh
  within the declared rounding tolerance, otherwise the valuation is refused
- legacy ``energy_loss_mwh`` = purchased_energy_mwh − delivered_energy_mwh —
  this is the total reduction only, disclosed and never monetized as an
  additional expense. The economics-only path instead reports exact
  ``total_consumed_energy_mwh``, ``physical_loss_energy_mwh`` and
  ``total_reduction_energy_mwh`` separately from explicit stages.

Boundaries and refusals:
- EUR-only initial scope; no FX conversion is performed and none is claimed.
- Prices are signed finite EUR/MWh (negative prices are economically possible);
  zero is allowed and any resulting zero leg is omitted with disclosure because
  the cash primitive refuses zero amounts.
- Each itemized cost produces exactly one cash leg; the caller cannot supply
  legs, duplicate cost ids are refused, and downstream categories already
  declared as included in the purchase price are refused instead of netted.
- Missing prices, costs, dates, sources, purchase basis, cost-scope statement
  or energy-basis declaration are refused; nothing is defaulted.
- No trade execution, nomination or settlement authority is added.

Compact sources and docs:
- NPV/cash primitive: ``domain/research/lng_cash_valuation.py``;
- explicit energy stages: ``domain/research/lng_energy_balance.py``;
- capability note: ``docs/architecture/LNG_ECONOMICS_ONLY_CAPABILITY.md``;
- regas readiness assessor (legacy path only): ``domain/route_cost/lng_regas.py``;
- peer research services: ``domain/research/netback.py`` and
  ``domain/research/route_cost.py``;
- ownership row: ``docs/architecture/MODULE_OWNERSHIP_MATRIX.md``;
- programme scope record: ``docs/engineering/ARCHITECTURE_V2_EXECUTION_STATE.md``.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import ROUND_HALF_EVEN, Context, Decimal, DecimalException, localcontext
from typing import Literal, Protocol, cast

# Canonical definitions (one authority) are re-exported for import compatibility.
from eurogas_nexus.domain.ontology.vocabulary import LngDownstreamChargeBasis
from eurogas_nexus.domain.research.lng_cash_valuation import (
    LNG_CASH_VALUATION_MODEL_VERSION,
    MAX_ABS_CASH_AMOUNT,
    MONEY_QUANTUM,
    WORKING_PRECISION,
    LngCargoCashValuationInput,
    LngCargoCashValuationResult,
    LngCashDiscountFactorInput,
    LngCashLegCategory,
    LngCashLegInput,
    LngCashValuationError,
    compute_lng_cargo_cash_valuation,
)
from eurogas_nexus.domain.research.lng_energy_balance import (
    LNG_ENERGY_BALANCE_MODEL_VERSION,
    SUPPORTED_ENERGY_UNIT,
    LngEnergyBalanceError,
    LngEnergyBalanceInput,
    LngEnergyBalanceResult,
    LngEnergyStage,
    compute_lng_energy_balance,
)
from eurogas_nexus.domain.route_cost.lng_regas import (
    LngRegasReadinessResult,
    LngRegasScenario,
    assess_lng_regas_readiness,
)

LNG_CARGO_ECONOMICS_MODEL_VERSION = "lng-cargo-economics/v1"
LNG_ECONOMICS_ONLY_MODEL_VERSION = "lng-economics-only/v1"

# The economics-only path never assesses physical readiness. The constant is
# echoed explicitly so a consumer cannot mistake an absent readiness result for
# a successful assessment.
PHYSICAL_READINESS_NOT_ASSESSED = "NOT_ASSESSED"

# Initial scope is EUR-only and explicit; nothing converts currency anywhere in
# this module, so no multi-currency claim is made.
EUR_REPORTING_CURRENCY = "EUR"

# Explicitly accepted purchase bases; any other value (including other Incoterms)
# is refused rather than inferred.
PURCHASE_BASES: tuple[str, ...] = ("FOB", "DES")

# Deterministic magnitude guards. These are input-sanity limits, not market
# conventions, and they keep the composed EUR amounts inside the bound the cash
# primitive already enforces.
MAX_ENERGY_MWH = Decimal("1e12")
MAX_ABS_UNIT_PRICE_EUR_PER_MWH = Decimal("1e9")

_ASSUMPTIONS: tuple[str, ...] = (
    "purchase_outlay = purchased_energy_mwh x purchase_unit_price; sale_proceeds ="
    " delivered_energy_mwh x sale_unit_price.",
    "unit_netback_eur_per_purchased_mwh = (sale_proceeds - total_downstream_costs) /"
    " purchased_energy_mwh, i.e. per purchased MWh.",
    "sale_basis_eur_per_delivered_mwh = sale_proceeds / delivered_energy_mwh, i.e. per"
    " delivered MWh; the purchased and delivered denominators are never mixed.",
    "cargo_margin_eur = sale_proceeds - total_downstream_costs - purchase_outlay, and it"
    " is reconciled as (unit_netback - purchase_unit_price) x purchased_energy_mwh"
    " within the declared rounding tolerance.",
    "energy_loss_mwh = purchased_energy_mwh - delivered_energy_mwh is disclosed only and"
    " is never monetized as an additional expense.",
    "All quantities are explicit MWh on the one declared energy_basis_reference; no"
    " m3/MMBtu conversion is performed or inferred.",
    "purchase_basis (FOB/DES) and the cost items already included in the purchase price"
    " are declared by the caller; downstream categories overlapping them are refused,"
    " not netted.",
    "Downstream costs are explicit itemized EUR totals with mandatory source references;"
    " each item produces exactly one cash leg and duplicate cost ids are refused.",
    "Discount factors are explicit per payment date and NPV is produced only by the"
    " existing lng-cargo-cash-valuation primitive; zero-value legs are omitted with"
    " disclosure because that primitive refuses zero amounts.",
    "Initial scope is EUR-only; no FX conversion is performed or claimed.",
    "Readiness is assessed only by the existing lng_regas readiness method: its"
    " missing_inputs block the valued result fail-closed, its warnings are propagated"
    " without being treated as blockers.",
    "The existing readiness scenario carries no resource reference; resource_id is"
    " carried through to the composed cash valuation rather than matched against it.",
    "Research-only decision support: no trade execution, nomination or settlement"
    " semantics are added.",
)

_BASELINE_WARNINGS: tuple[str, ...] = (
    "RESEARCH_ONLY_DECISION_SUPPORT_NOT_ACCOUNTING_CUSTODY_OR_SETTLEMENT",
    "NO_TRADE_EXECUTION_NOMINATION_OR_SETTLEMENT",
    "EUR_ONLY_NO_FX_CONVERSION_PERFORMED",
)

_ECONOMICS_ONLY_BASELINE_WARNINGS: tuple[str, ...] = (
    *_BASELINE_WARNINGS,
    "PHYSICAL_READINESS_NOT_ASSESSED",
    "PROFITABLE_ECONOMICS_IS_NOT_DELIVERY_FEASIBILITY_TERMINAL_SLOT_STORAGE_RIGHTS_OR_"
    "NOMINATION_AUTHORITY",
    "IN_KIND_ENERGY_CONSUMPTION_AND_PHYSICAL_LOSS_ARE_NOT_MONETIZED",
)

_ECONOMICS_ONLY_ASSUMPTIONS: tuple[str, ...] = (
    "purchase_outlay = purchased_energy_mwh x purchase_unit_price; sale_proceeds ="
    " delivered_energy_mwh x sale_unit_price.",
    "unit_netback_eur_per_purchased_mwh = (sale_proceeds - total_downstream_costs) /"
    " purchased_energy_mwh, i.e. per purchased MWh.",
    "sale_basis_eur_per_delivered_mwh = sale_proceeds / delivered_energy_mwh, i.e. per"
    " delivered MWh; the purchased and delivered denominators are never mixed.",
    "cargo_margin_eur = sale_proceeds - total_downstream_costs - purchase_outlay, and it"
    " is reconciled as (unit_netback - purchase_unit_price) x purchased_energy_mwh"
    " within the declared rounding tolerance.",
    "The energy chain is explicit and exact: every stage satisfies input = output +"
    " consumed + physical loss, adjacent stages match exactly, and the first input/final"
    " output equal purchased/delivered energy. Total consumed, physical loss and total"
    " reduction are reported separately and never monetized automatically.",
    "In-kind consumed energy and physical loss are not downstream cash costs. Cash costs"
    " require an explicit invoiced-cash charge basis and provenance; in-kind or unknown"
    " charges supplied as cash expenses are refused.",
    "No regas readiness assessor is called and no terminal access, regas slot, storage"
    " capacity, TSO access, nomination authority or delivery feasibility is assessed;"
    " physical_readiness is NOT_ASSESSED.",
    "All quantities are explicit MWh on the one declared energy_basis_reference; no"
    " m3/MMBtu conversion is performed or inferred.",
    "Initial scope is EUR-only; no FX conversion is performed or claimed.",
    "Discount factors are explicit per payment date and NPV is produced only by the"
    " existing lng-cargo-cash-valuation primitive; zero-value legs are omitted with"
    " disclosure because that primitive refuses zero amounts.",
    "Research-only decision support: no trade execution, nomination or settlement"
    " semantics are added.",
)

_CASH_LEG_CATEGORIES_NOT_COSTS = frozenset(
    {LngCashLegCategory.CARGO_PURCHASE, LngCashLegCategory.CARGO_SALE}
)


class LngCargoEconomicsError(ValueError):
    """Deterministic refusal of invalid LNG cargo economics input.

    Attributes:
        violations: Ordered ``(code, detail)`` pairs of every detected
            violation; ``code`` is the stable machine-readable code.
        codes: The stable validation codes in input order.
    """

    def __init__(self, violations: list[tuple[str, str]]) -> None:
        """Build the refusal from ordered ``(code, detail)`` violations."""

        self.violations = tuple(violations)
        self.codes = tuple(code for code, _ in violations)
        super().__init__("; ".join(f"{code} ({detail})" for code, detail in violations))


class LngEconomicsOnlyError(LngCargoEconomicsError):
    """Deterministic refusal of invalid economics-only input.

    The stable-code contract is identical to :class:`LngCargoEconomicsError`,
    including propagated cash-primitive and energy-balance codes.
    """


@dataclass(frozen=True)
class LngCargoDownstreamCostInput:
    """One itemized downstream cost total of one LNG cargo.

    Attributes:
        cost_id: Unique item id within the composition; duplicates are refused
            because each item produces exactly one signed cash leg.
        category: Cost category, reusing the existing cash-leg taxonomy so the
            vocabulary cannot silently drift; the purchase and sale leg
            categories are refused here because those legs are constructed by
            this composition.
        amount_eur: Nonnegative EUR total of the item; zero is allowed and the
            resulting zero leg is omitted with disclosure.
        payment_date: Cash date of the item; never before the valuation date.
        source_reference: Mandatory provenance of the amount.
    """

    cost_id: str
    category: LngCashLegCategory
    amount_eur: Decimal
    payment_date: date
    source_reference: str


@dataclass(frozen=True)
class LngEconomicsOnlyCostInput:
    """One explicitly invoiced downstream cash cost of an economics-only run.

    This is deliberately a distinct type from the legacy downstream cost input:
    the economics-only path requires the caller to declare the charge basis and
    refuses in-kind or unknown charges as monetary expenses.

    Attributes:
        cost_id: Unique item id within the composition.
        category: Cost category from the shared cash-leg taxonomy.
        amount_eur: Nonnegative EUR total of the item; zero is allowed and the
            resulting zero leg is omitted with disclosure.
        payment_date: Cash date of the item; never before the valuation date.
        source_reference: Mandatory provenance of the invoiced cash amount.
        charge_basis: Must be exactly ``INVOICED_CASH``; ``IN_KIND`` and
            ``UNKNOWN`` are refused as duplicate/unsupported cash expenses.
    """

    cost_id: str
    category: LngCashLegCategory
    amount_eur: Decimal
    payment_date: date
    source_reference: str
    charge_basis: LngDownstreamChargeBasis


@dataclass(frozen=True)
class LngCargoEconomicsInput:
    """Typed, versioned input of one LNG cargo economics composition.

    Attributes:
        contract_id: Mandatory contract reference; must match the readiness
            scenario.
        cargo_id: Mandatory cargo reference; must match the readiness scenario.
        terminal_id: Mandatory terminal reference; must match the readiness
            scenario.
        resource_id: Mandatory supply-resource reference, carried through to
            the composed cash valuation (the readiness scenario has no
            resource field to match against).
        readiness_scenario: Existing ``LngRegasScenario``; assessed only by the
            existing readiness method, whose blocking missing inputs refuse the
            valuation fail-closed.
        valuation_date: Valuation date; every payment date is at or after it.
        energy_basis_reference: Mandatory declared energy-basis reference for
            both quantities; no implicit conversion is ever performed.
        purchased_energy_mwh: Explicit purchased energy in MWh (positive).
        delivered_energy_mwh: Explicit delivered energy in MWh (positive and at
            most ``purchased_energy_mwh``); the difference is the legacy disclosed
            total reduction, not a physical-loss decomposition.
        purchase_unit_price_eur_per_mwh: Signed finite EUR/MWh price on
            purchased energy; negative and zero prices are allowed.
        sale_unit_price_eur_per_mwh: Signed finite EUR/MWh price on delivered
            energy; negative and zero prices are allowed.
        purchase_price_source_reference: Mandatory provenance of the purchase
            price.
        sale_price_source_reference: Mandatory provenance of the sale price.
        purchase_basis: Explicit purchase basis, exactly ``FOB`` or ``DES``.
        purchase_included_cost_items: Items the caller declares as already
            included in the purchase price; downstream costs with these
            categories are refused as double counting.
        cost_scope_statement: Mandatory free-text statement of the cost scope.
        purchase_payment_date: Cash date of the purchase outlay.
        sale_payment_date: Cash date of the sale proceeds.
        downstream_costs: Explicit itemized downstream costs.
        discount_factors: Explicit per-payment-date discount factors; every
            declared payment date must be covered.
        model_version: Model version; any other value is refused.
    """

    contract_id: str
    cargo_id: str
    terminal_id: str
    resource_id: str
    readiness_scenario: LngRegasScenario
    valuation_date: date
    energy_basis_reference: str
    purchased_energy_mwh: Decimal
    delivered_energy_mwh: Decimal
    purchase_unit_price_eur_per_mwh: Decimal
    sale_unit_price_eur_per_mwh: Decimal
    purchase_price_source_reference: str
    sale_price_source_reference: str
    purchase_basis: Literal["FOB", "DES"]
    purchase_included_cost_items: tuple[LngCashLegCategory, ...]
    cost_scope_statement: str
    purchase_payment_date: date
    sale_payment_date: date
    downstream_costs: tuple[LngCargoDownstreamCostInput, ...]
    discount_factors: tuple[LngCashDiscountFactorInput, ...]
    model_version: str = LNG_CARGO_ECONOMICS_MODEL_VERSION


@dataclass(frozen=True)
class LngCargoEconomicsResult:
    """Typed, versioned research result of one LNG cargo economics composition.

    Deterministic by construction: no wall-clock field is included, so equal
    inputs always produce equal results. The discounted figures are echoes of
    the embedded ``cash_valuation`` result and never replace it.

    Attributes:
        model_version: Version of the producing composition model.
        contract_id / cargo_id / terminal_id / resource_id: Echoed references.
        valuation_date: Echoed valuation date.
        reporting_currency: Always ``EUR`` in the initial explicit scope.
        energy_basis_reference: Echoed declared energy-basis reference.
        purchase_basis: Echoed explicit purchase basis.
        purchase_included_cost_items: Echoed declared included cost items.
        cost_scope_statement: Echoed declared cost scope.
        purchased_energy_mwh / delivered_energy_mwh: Echoed energies.
        energy_loss_mwh: Legacy disclosed purchased-minus-delivered total
            reduction, never monetized and not a physical-loss decomposition.
        purchase_unit_price_eur_per_mwh / sale_unit_price_eur_per_mwh: Echoed
            signed unit prices.
        unit_netback_eur_per_purchased_mwh: Netback per purchased MWh.
        sale_basis_eur_per_delivered_mwh: Sale proceeds per delivered MWh.
        purchase_outlay_eur: Purchased energy × purchase unit price.
        sale_proceeds_eur: Delivered energy × sale unit price.
        total_downstream_costs_eur: Sum of itemized cost totals.
        cargo_margin_eur: Proceeds − costs − outlay.
        margin_reconciliation_gap_eur: Margin minus the declared reconciliation
            expression, within the declared tolerance.
        margin_reconciliation_tolerance_eur: Declared rounding tolerance.
        net_present_value_eur / total_undiscounted_cash_eur: Echoes of the
            embedded cash valuation for reporting convenience.
        cash_valuation: The full bounded cash-primitive result.
        readiness: The existing readiness assessment result.
        assumptions: Explicit model formulas and boundaries.
        warnings: Always-on research warnings, readiness warnings, loss and
            omission disclosures, and negative-result warnings.
        source_references: Sorted unique provenance supplied by the caller.
        lineage: Calculation lineage tokens including the reused primitive.
        research_only: Always True.
        human_review_required: Always True.
    """

    model_version: str
    contract_id: str
    cargo_id: str
    terminal_id: str
    resource_id: str
    valuation_date: date
    reporting_currency: str
    energy_basis_reference: str
    purchase_basis: str
    purchase_included_cost_items: tuple[LngCashLegCategory, ...]
    cost_scope_statement: str
    purchased_energy_mwh: Decimal
    delivered_energy_mwh: Decimal
    energy_loss_mwh: Decimal
    purchase_unit_price_eur_per_mwh: Decimal
    sale_unit_price_eur_per_mwh: Decimal
    unit_netback_eur_per_purchased_mwh: Decimal
    sale_basis_eur_per_delivered_mwh: Decimal
    purchase_outlay_eur: Decimal
    sale_proceeds_eur: Decimal
    total_downstream_costs_eur: Decimal
    cargo_margin_eur: Decimal
    margin_reconciliation_gap_eur: Decimal
    margin_reconciliation_tolerance_eur: Decimal
    net_present_value_eur: Decimal
    total_undiscounted_cash_eur: Decimal
    cash_valuation: LngCargoCashValuationResult
    readiness: LngRegasReadinessResult
    assumptions: tuple[str, ...]
    warnings: tuple[str, ...]
    source_references: tuple[str, ...]
    lineage: tuple[str, ...]
    research_only: bool = True
    human_review_required: bool = True


@dataclass(frozen=True)
class LngEconomicsOnlyInput:
    """Typed economics-only input with no physical-readiness scenario.

    The type deliberately has no ``readiness_scenario`` field: this path composes
    only explicitly supplied economics and an explicit bounded energy chain. It
    does not fabricate terminal access, slots, storage rights, TSO access or any
    other physical evidence.

    Attributes:
        contract_id / cargo_id / terminal_id / resource_id: Mandatory references.
        valuation_date: Valuation date; every payment date is at or after it.
        reporting_currency: Explicit reporting currency; only ``EUR`` is supported.
        energy_basis_reference: Mandatory declared energy-basis reference.
        energy_unit: Explicit energy unit; only ``MWh`` is supported.
        purchased_energy_mwh: Explicit purchased energy (positive).
        delivered_energy_mwh: Explicit delivered energy (positive, first/final
            stage chain ends must match exactly).
        purchase_unit_price_eur_per_mwh: Signed finite EUR/MWh price on purchased
            energy; negative and zero prices are allowed.
        sale_unit_price_eur_per_mwh: Signed finite EUR/MWh price on delivered
            energy; negative and zero prices are allowed.
        purchase_price_source_reference: Mandatory provenance of the purchase
            price.
        sale_price_source_reference: Mandatory provenance of the sale price.
        purchase_basis: Explicit purchase basis, exactly ``FOB`` or ``DES``.
        purchase_included_cost_items: Items declared as already included in the
            purchase price; downstream costs with these categories are refused
            as double counting.
        cost_scope_statement: Mandatory free-text statement of the cost scope.
        purchase_payment_date: Cash date of the purchase outlay.
        sale_payment_date: Cash date of the sale proceeds.
        downstream_costs: Explicitly invoiced downstream cash costs.
        energy_stages: Ordered explicit energy stages; no stage is inferred.
        discount_factors: Explicit per-payment-date discount factors; every
            declared payment date must be covered.
        model_version: Model version; any other value is refused.
    """

    contract_id: str
    cargo_id: str
    terminal_id: str
    resource_id: str
    valuation_date: date
    reporting_currency: str
    energy_basis_reference: str
    energy_unit: str
    purchased_energy_mwh: Decimal
    delivered_energy_mwh: Decimal
    purchase_unit_price_eur_per_mwh: Decimal
    sale_unit_price_eur_per_mwh: Decimal
    purchase_price_source_reference: str
    sale_price_source_reference: str
    purchase_basis: Literal["FOB", "DES"]
    purchase_included_cost_items: tuple[LngCashLegCategory, ...]
    cost_scope_statement: str
    purchase_payment_date: date
    sale_payment_date: date
    downstream_costs: tuple[LngEconomicsOnlyCostInput, ...]
    energy_stages: tuple[LngEnergyStage, ...]
    discount_factors: tuple[LngCashDiscountFactorInput, ...]
    model_version: str = LNG_ECONOMICS_ONLY_MODEL_VERSION


@dataclass(frozen=True)
class LngEconomicsOnlyResult:
    """Typed economics-only result with explicit NOT_ASSESSED physical status.

    It has no ``readiness`` field carrying a physical assessment. Instead,
    ``physical_readiness`` is exactly ``NOT_ASSESSED`` and
    ``readiness_assessed`` is exactly False, so an absent assessment cannot be
    mistaken for a successful legacy readiness result.

    Deterministic by construction: no wall-clock field is included.

    Attributes:
        model_version: Actual producing implementation version, never a caller
            supplied version.
        contract_id / cargo_id / terminal_id / resource_id: Echoed references.
        valuation_date: Echoed valuation date.
        reporting_currency: Echoed EUR reporting currency.
        energy_basis_reference / energy_unit: Echoed explicit energy declaration.
        purchased_energy_mwh / delivered_energy_mwh: Exact chain endpoints.
        total_consumed_energy_mwh / physical_loss_energy_mwh: Exact explicit
            totals, reported separately.
        total_reduction_energy_mwh: Exact purchased-minus-delivered total; never
            labelled as physical loss alone.
        purchase_basis: Echoed explicit purchase basis.
        purchase_included_cost_items: Echoed declared included cost items.
        cost_scope_statement: Echoed declared cost scope.
        purchase_unit_price_eur_per_mwh / sale_unit_price_eur_per_mwh: Echoed
            signed unit prices.
        unit_netback_eur_per_purchased_mwh: Netback per purchased MWh.
        sale_basis_eur_per_delivered_mwh: Sale proceeds per delivered MWh.
        purchase_outlay_eur: Purchased energy × purchase unit price.
        sale_proceeds_eur: Delivered energy × sale unit price.
        total_downstream_costs_eur: Sum of itemized invoiced cash costs.
        cargo_margin_eur: Proceeds − costs − outlay.
        margin_reconciliation_gap_eur / margin_reconciliation_tolerance_eur:
            Declared rounding reconciliation.
        net_present_value_eur / total_undiscounted_cash_eur: Echoes of the
            embedded shared cash valuation.
        cash_valuation: The full bounded cash-primitive result.
        energy_balance: The full explicit energy-balance result.
        physical_readiness: Always ``NOT_ASSESSED``.
        readiness_assessed: Always False.
        assumptions: Explicit model formulas and boundaries.
        warnings: Research, no-physical-readiness, no-monetization, loss,
            omission and negative-result warnings.
        source_references: Sorted unique cash and energy-stage provenance.
        lineage: Calculation lineage tokens including the energy balance and the
            reused cash primitive.
        research_only: Always True.
        human_review_required: Always True.
    """

    model_version: str
    contract_id: str
    cargo_id: str
    terminal_id: str
    resource_id: str
    valuation_date: date
    reporting_currency: str
    energy_basis_reference: str
    energy_unit: str
    purchased_energy_mwh: Decimal
    delivered_energy_mwh: Decimal
    total_consumed_energy_mwh: Decimal
    physical_loss_energy_mwh: Decimal
    total_reduction_energy_mwh: Decimal
    purchase_basis: str
    purchase_included_cost_items: tuple[LngCashLegCategory, ...]
    cost_scope_statement: str
    purchase_unit_price_eur_per_mwh: Decimal
    sale_unit_price_eur_per_mwh: Decimal
    unit_netback_eur_per_purchased_mwh: Decimal
    sale_basis_eur_per_delivered_mwh: Decimal
    purchase_outlay_eur: Decimal
    sale_proceeds_eur: Decimal
    total_downstream_costs_eur: Decimal
    cargo_margin_eur: Decimal
    margin_reconciliation_gap_eur: Decimal
    margin_reconciliation_tolerance_eur: Decimal
    net_present_value_eur: Decimal
    total_undiscounted_cash_eur: Decimal
    cash_valuation: LngCargoCashValuationResult
    energy_balance: LngEnergyBalanceResult
    physical_readiness: Literal["NOT_ASSESSED"]
    readiness_assessed: bool
    assumptions: tuple[str, ...]
    warnings: tuple[str, ...]
    source_references: tuple[str, ...]
    lineage: tuple[str, ...]
    research_only: bool = True
    human_review_required: bool = True


class _EconomicInputLike(Protocol):
    """Structural economic fields shared by both public input dataclasses."""

    model_version: str
    contract_id: str
    cargo_id: str
    terminal_id: str
    resource_id: str
    valuation_date: date
    energy_basis_reference: str
    purchased_energy_mwh: Decimal
    delivered_energy_mwh: Decimal
    purchase_unit_price_eur_per_mwh: Decimal
    sale_unit_price_eur_per_mwh: Decimal
    purchase_price_source_reference: str
    sale_price_source_reference: str
    purchase_basis: str
    purchase_included_cost_items: tuple[LngCashLegCategory, ...]
    cost_scope_statement: str
    purchase_payment_date: date
    sale_payment_date: date
    downstream_costs: tuple[object, ...]
    discount_factors: tuple[object, ...]


class _CostInputLike(Protocol):
    """Structural downstream-cost fields shared by both cost input types."""

    cost_id: str
    category: LngCashLegCategory
    amount_eur: Decimal
    payment_date: date
    source_reference: str


@dataclass(frozen=True)
class _CargoEconomicCompositionResult:
    """Private monetary/cash composition shared by both public LNG paths."""

    energy_reduction_mwh: Decimal
    unit_netback_eur_per_purchased_mwh: Decimal
    sale_basis_eur_per_delivered_mwh: Decimal
    purchase_outlay_eur: Decimal
    sale_proceeds_eur: Decimal
    total_downstream_costs_eur: Decimal
    cargo_margin_eur: Decimal
    margin_reconciliation_gap_eur: Decimal
    margin_reconciliation_tolerance_eur: Decimal
    cash_valuation: LngCargoCashValuationResult
    warnings: tuple[str, ...]


def compute_lng_cargo_economics(input_: LngCargoEconomicsInput) -> LngCargoEconomicsResult:
    """Compose one LNG cargo's netback, margin and discounted cash value.

    把显式购买/交付能量、显式单价、显式购买基准与逐项下游成本组合为
    单位 netback、船货毛利与损失披露，并复用既有 lng_cash_valuation 本原
    计算显式贴现的 NPV；就绪度沿用既有 regas 评估器，缺失输入 fail-closed。

    Args:
        input_: Validated typed input with references, readiness scenario,
            declared bases, energies, prices, itemized costs and explicit
            discount factors.

    Returns:
        A deterministic result with sale basis, unit netback, cargo margin,
        reconciliation, disclosed loss, the embedded cash valuation and the
        embedded readiness assessment.

    Raises:
        LngCargoEconomicsError: When any input violates the deterministic
            validation rules (stable codes in ``codes``), when the existing
            readiness method reports blocking missing inputs, or when every
            composed cash leg would be exactly zero.
    """

    if not isinstance(input_, LngCargoEconomicsInput):
        raise LngCargoEconomicsError(
            [
                (
                    "INPUT_TYPE_INVALID",
                    "input must be a LngCargoEconomicsInput instance",
                )
            ]
        )
    # 显式物化容器：生成器等一次性可迭代对象绝不能导致"第二次迭代为空"的静默错误结果。
    (
        container_violations,
        downstream_costs,
        discount_factors,
        included_items,
    ) = _materialize_common_containers(input_, LngCargoDownstreamCostInput.__name__)
    violations = container_violations + _collect_violations(
        input_, downstream_costs, discount_factors, included_items
    )
    if violations:
        raise LngCargoEconomicsError(violations)

    # 就绪度：唯一实现在 lng_regas 中；本组合只消费其结果，不修改全局规则。
    readiness = assess_lng_regas_readiness(input_.readiness_scenario)
    if readiness.missing_inputs:
        raise LngCargoEconomicsError(
            [
                (
                    "READINESS_BLOCKED",
                    "the existing regas readiness method reported blocking missing"
                    f" inputs: {', '.join(readiness.missing_inputs)}; the valued result"
                    " is refused fail-closed",
                )
            ]
        )

    warnings: list[str] = list(_BASELINE_WARNINGS)
    warnings.extend(f"READINESS_WARNING:{item}" for item in readiness.warnings)

    composition = _compose_cargo_economics(
        input_,
        cast(tuple[_CostInputLike, ...], downstream_costs),
        cast(tuple[LngCashDiscountFactorInput, ...], discount_factors),
        base_warnings=tuple(warnings),
        reduction_warning="ENERGY_LOSS_DISCLOSED_NOT_ADDITIONALLY_MONETIZED",
    )

    return LngCargoEconomicsResult(
        model_version=input_.model_version,
        contract_id=input_.contract_id,
        cargo_id=input_.cargo_id,
        terminal_id=input_.terminal_id,
        resource_id=input_.resource_id,
        valuation_date=input_.valuation_date,
        reporting_currency=EUR_REPORTING_CURRENCY,
        energy_basis_reference=input_.energy_basis_reference,
        purchase_basis=input_.purchase_basis,
        purchase_included_cost_items=included_items,
        cost_scope_statement=input_.cost_scope_statement,
        purchased_energy_mwh=input_.purchased_energy_mwh,
        delivered_energy_mwh=input_.delivered_energy_mwh,
        energy_loss_mwh=composition.energy_reduction_mwh,
        purchase_unit_price_eur_per_mwh=input_.purchase_unit_price_eur_per_mwh,
        sale_unit_price_eur_per_mwh=input_.sale_unit_price_eur_per_mwh,
        unit_netback_eur_per_purchased_mwh=(
            composition.unit_netback_eur_per_purchased_mwh
        ),
        sale_basis_eur_per_delivered_mwh=(
            composition.sale_basis_eur_per_delivered_mwh
        ),
        purchase_outlay_eur=composition.purchase_outlay_eur,
        sale_proceeds_eur=composition.sale_proceeds_eur,
        total_downstream_costs_eur=composition.total_downstream_costs_eur,
        cargo_margin_eur=composition.cargo_margin_eur,
        margin_reconciliation_gap_eur=composition.margin_reconciliation_gap_eur,
        margin_reconciliation_tolerance_eur=(
            composition.margin_reconciliation_tolerance_eur
        ),
        net_present_value_eur=(
            composition.cash_valuation.net_present_value_reporting_ccy
        ),
        total_undiscounted_cash_eur=(
            composition.cash_valuation.total_undiscounted_cash_reporting_ccy
        ),
        cash_valuation=composition.cash_valuation,
        readiness=readiness,
        assumptions=_ASSUMPTIONS,
        warnings=composition.warnings,
        source_references=composition.cash_valuation.source_references,
        lineage=(
            "lng-cargo-economics",
            LNG_CARGO_ECONOMICS_MODEL_VERSION,
            LNG_CASH_VALUATION_MODEL_VERSION,
        ),
        research_only=True,
        human_review_required=True,
    )


def compute_lng_economics_only(input_: LngEconomicsOnlyInput) -> LngEconomicsOnlyResult:
    """Compose economics from explicit cash and energy stages without readiness.

    This path never calls the regas readiness assessor and never fabricates a
    terminal, slot, storage right, TSO access or nomination. Its result states
    ``physical_readiness='NOT_ASSESSED'`` and ``readiness_assessed=False``.

    Args:
        input_: Explicit economics plus an explicit ordered energy-stage chain.

    Returns:
        Deterministic margins, netback, NPV and separately reported consumed,
        physical-loss and total-reduction energy.

    Raises:
        LngEconomicsOnlyError: When economics, cash or energy-stage validation
            refuses the input. Cash-primitive and energy-balance codes are
            propagated unchanged.
    """

    if not isinstance(input_, LngEconomicsOnlyInput):
        raise LngEconomicsOnlyError(
            [
                (
                    "INPUT_TYPE_INVALID",
                    "input must be a LngEconomicsOnlyInput instance",
                )
            ]
        )

    (
        container_violations,
        downstream_costs,
        discount_factors,
        included_items,
    ) = _materialize_common_containers(input_, LngEconomicsOnlyCostInput.__name__)
    violations = container_violations + _collect_economics_only_violations(
        input_, downstream_costs, discount_factors, included_items
    )
    if violations:
        raise LngEconomicsOnlyError(violations)

    try:
        energy_balance = compute_lng_energy_balance(
            LngEnergyBalanceInput(
                purchased_energy_mwh=input_.purchased_energy_mwh,
                delivered_energy_mwh=input_.delivered_energy_mwh,
                energy_basis_reference=input_.energy_basis_reference,
                energy_unit=input_.energy_unit,
                stages=input_.energy_stages,
            )
        )
    except LngEnergyBalanceError as exc:
        raise LngEconomicsOnlyError(list(exc.violations)) from exc

    try:
        composition = _compose_cargo_economics(
            input_,
            cast(tuple[_CostInputLike, ...], downstream_costs),
            cast(tuple[LngCashDiscountFactorInput, ...], discount_factors),
            base_warnings=_ECONOMICS_ONLY_BASELINE_WARNINGS,
            reduction_warning=(
                "TOTAL_REDUCTION_DISCLOSED_AS_CONSUMED_PLUS_PHYSICAL_LOSS_NOT"
                "_ADDITIONALLY_MONETIZED"
            ),
        )
    except LngCargoEconomicsError as exc:
        raise LngEconomicsOnlyError(list(exc.violations)) from exc

    source_references = tuple(
        sorted(
            set(composition.cash_valuation.source_references)
            | set(energy_balance.source_references)
        )
    )
    return LngEconomicsOnlyResult(
        model_version=LNG_ECONOMICS_ONLY_MODEL_VERSION,
        contract_id=input_.contract_id,
        cargo_id=input_.cargo_id,
        terminal_id=input_.terminal_id,
        resource_id=input_.resource_id,
        valuation_date=input_.valuation_date,
        reporting_currency=EUR_REPORTING_CURRENCY,
        energy_basis_reference=energy_balance.energy_basis_reference,
        energy_unit=energy_balance.energy_unit,
        purchased_energy_mwh=energy_balance.purchased_energy_mwh,
        delivered_energy_mwh=energy_balance.delivered_energy_mwh,
        total_consumed_energy_mwh=energy_balance.total_consumed_energy_mwh,
        physical_loss_energy_mwh=energy_balance.physical_loss_energy_mwh,
        total_reduction_energy_mwh=energy_balance.total_reduction_energy_mwh,
        purchase_basis=input_.purchase_basis,
        purchase_included_cost_items=included_items,
        cost_scope_statement=input_.cost_scope_statement,
        purchase_unit_price_eur_per_mwh=input_.purchase_unit_price_eur_per_mwh,
        sale_unit_price_eur_per_mwh=input_.sale_unit_price_eur_per_mwh,
        unit_netback_eur_per_purchased_mwh=(
            composition.unit_netback_eur_per_purchased_mwh
        ),
        sale_basis_eur_per_delivered_mwh=(
            composition.sale_basis_eur_per_delivered_mwh
        ),
        purchase_outlay_eur=composition.purchase_outlay_eur,
        sale_proceeds_eur=composition.sale_proceeds_eur,
        total_downstream_costs_eur=composition.total_downstream_costs_eur,
        cargo_margin_eur=composition.cargo_margin_eur,
        margin_reconciliation_gap_eur=composition.margin_reconciliation_gap_eur,
        margin_reconciliation_tolerance_eur=(
            composition.margin_reconciliation_tolerance_eur
        ),
        net_present_value_eur=(
            composition.cash_valuation.net_present_value_reporting_ccy
        ),
        total_undiscounted_cash_eur=(
            composition.cash_valuation.total_undiscounted_cash_reporting_ccy
        ),
        cash_valuation=composition.cash_valuation,
        energy_balance=energy_balance,
        physical_readiness=PHYSICAL_READINESS_NOT_ASSESSED,
        readiness_assessed=False,
        assumptions=_ECONOMICS_ONLY_ASSUMPTIONS,
        warnings=composition.warnings,
        source_references=source_references,
        lineage=(
            "lng-economics-only",
            LNG_ECONOMICS_ONLY_MODEL_VERSION,
            "lng-energy-balance",
            LNG_ENERGY_BALANCE_MODEL_VERSION,
            LNG_CASH_VALUATION_MODEL_VERSION,
        ),
        research_only=True,
        human_review_required=True,
    )


def _materialize_common_containers(
    input_: _EconomicInputLike,
    downstream_cost_type_name: str,
) -> tuple[
    list[tuple[str, str]],
    tuple[object, ...],
    tuple[object, ...],
    tuple[object, ...],
]:
    """Materialize both public inputs' common iterables once and deterministically."""

    container_violations: list[tuple[str, str]] = []
    if isinstance(input_.downstream_costs, (tuple, list)):
        downstream_costs: tuple[object, ...] = tuple(input_.downstream_costs)
    else:
        container_violations.append(
            (
                "DOWNSTREAM_COSTS_INVALID",
                "downstream_costs must be a tuple or list of"
                f" {downstream_cost_type_name}",
            )
        )
        downstream_costs = ()
    if isinstance(input_.discount_factors, (tuple, list)):
        discount_factors: tuple[object, ...] = tuple(input_.discount_factors)
    else:
        container_violations.append(
            (
                "DISCOUNT_FACTORS_INVALID",
                "discount_factors must be a tuple or list of LngCashDiscountFactorInput",
            )
        )
        discount_factors = ()
    if isinstance(input_.purchase_included_cost_items, (tuple, list)):
        included_items: tuple[object, ...] = tuple(input_.purchase_included_cost_items)
    else:
        container_violations.append(
            (
                "PURCHASE_INCLUDED_COST_ITEMS_INVALID",
                "purchase_included_cost_items must be a tuple or list of"
                " LngCashLegCategory",
            )
        )
        included_items = ()
    return (
        container_violations,
        downstream_costs,
        discount_factors,
        included_items,
    )


def _compose_cargo_economics(
    input_: _EconomicInputLike,
    downstream_costs: tuple[_CostInputLike, ...],
    discount_factors: tuple[LngCashDiscountFactorInput, ...],
    *,
    base_warnings: tuple[str, ...],
    reduction_warning: str,
) -> _CargoEconomicCompositionResult:
    """Compose monetary economics and cash value identically for both paths.

    All formulas, rounding, reconciliation, magnitude bounds, zero-leg
    disclosure, cash-leg ordering and delegation to the shared cash primitive
    live here exactly once. The caller validates its own physical-readiness
    concerns separately; this helper consumes only structural economic fields
    and the already materialized costs/discount factors.
    """

    warnings: list[str] = list(base_warnings)
    with localcontext(_economics_decimal_context()):
        try:
            purchase_outlay = _quantize_money(
                input_.purchased_energy_mwh * input_.purchase_unit_price_eur_per_mwh
            )
            sale_proceeds = _quantize_money(
                input_.delivered_energy_mwh * input_.sale_unit_price_eur_per_mwh
            )
            total_costs = _quantize_money(
                sum(
                    (_quantize_money(cost.amount_eur) for cost in downstream_costs),
                    Decimal(0),
                )
            )
            energy_reduction = _quantize_money(
                input_.purchased_energy_mwh - input_.delivered_energy_mwh
            )
            unit_netback = _quantize_money(
                (sale_proceeds - total_costs) / input_.purchased_energy_mwh
            )
            sale_basis = _quantize_money(sale_proceeds / input_.delivered_energy_mwh)
            cargo_margin = _quantize_money(sale_proceeds - total_costs - purchase_outlay)
            reconciled_margin = _quantize_money(
                (unit_netback - input_.purchase_unit_price_eur_per_mwh)
                * input_.purchased_energy_mwh
            )
            reconciliation_gap = _quantize_money(cargo_margin - reconciled_margin)
            reconciliation_tolerance = _quantize_money(
                MONEY_QUANTUM * (input_.purchased_energy_mwh / 2 + 2)
            )
        except DecimalException as exc:
            raise LngCargoEconomicsError(
                [
                    (
                        "NUMERIC_EVALUATION_OVERFLOW",
                        f"deterministic decimal evaluation failed: {exc}",
                    )
                ]
            ) from exc

        for amount, code in (
            (purchase_outlay, "PURCHASE_OUTLAY_OVERFLOW"),
            (sale_proceeds, "SALE_PROCEEDS_OVERFLOW"),
            (total_costs, "DOWNSTREAM_COSTS_OVERFLOW"),
        ):
            if amount.copy_abs() > MAX_ABS_CASH_AMOUNT:
                raise LngCargoEconomicsError(
                    [
                        (
                            code,
                            f"composed amount {amount} exceeds the supported magnitude"
                            f" {MAX_ABS_CASH_AMOUNT}",
                        )
                    ]
                )
        if reconciliation_gap.copy_abs() > reconciliation_tolerance:
            raise LngCargoEconomicsError(
                [
                    (
                        "MARGIN_RECONCILIATION_FAILED",
                        f"cargo margin {cargo_margin} does not reconcile with"
                        f" (unit_netback - purchase_unit_price) x purchased_energy"
                        f" = {reconciled_margin} within the declared tolerance"
                        f" {reconciliation_tolerance}",
                    )
                ]
            )

        if energy_reduction > 0:
            warnings.append(reduction_warning)

        # 每条声明现金流恰好生成一条现金腿；零金额腿被省略并逐条披露
        # （既有本原拒绝零金额腿，不做静默改写）。
        legs: list[LngCashLegInput] = []
        if purchase_outlay != 0:
            legs.append(
                LngCashLegInput(
                    leg_id="cargo-purchase",
                    category=LngCashLegCategory.CARGO_PURCHASE,
                    payment_date=input_.purchase_payment_date,
                    signed_amount=-purchase_outlay,
                    currency=EUR_REPORTING_CURRENCY,
                    source_reference=input_.purchase_price_source_reference,
                )
            )
        else:
            warnings.append("OMITTED_ZERO_CASH_LEG:cargo-purchase")
        if sale_proceeds != 0:
            legs.append(
                LngCashLegInput(
                    leg_id="cargo-sale",
                    category=LngCashLegCategory.CARGO_SALE,
                    payment_date=input_.sale_payment_date,
                    signed_amount=sale_proceeds,
                    currency=EUR_REPORTING_CURRENCY,
                    source_reference=input_.sale_price_source_reference,
                )
            )
        else:
            warnings.append("OMITTED_ZERO_CASH_LEG:cargo-sale")
        for cost in downstream_costs:
            leg_id = f"downstream-cost:{cost.cost_id}"
            if cost.amount_eur != 0:
                legs.append(
                    LngCashLegInput(
                        leg_id=leg_id,
                        category=cost.category,
                        payment_date=cost.payment_date,
                        signed_amount=-cost.amount_eur,
                        currency=EUR_REPORTING_CURRENCY,
                        source_reference=cost.source_reference,
                    )
                )
            else:
                warnings.append(f"OMITTED_ZERO_CASH_LEG:{leg_id}")
        if not legs:
            raise LngCargoEconomicsError(
                [
                    (
                        "NO_NONZERO_CASH_LEGS",
                        "every composed cash leg is exactly zero; the cash primitive"
                        " refuses zero legs, so there is nothing to value",
                    )
                ]
            )

        try:
            cash_valuation = compute_lng_cargo_cash_valuation(
                LngCargoCashValuationInput(
                    contract_id=input_.contract_id,
                    cargo_id=input_.cargo_id,
                    terminal_id=input_.terminal_id,
                    resource_id=input_.resource_id,
                    valuation_date=input_.valuation_date,
                    reporting_currency=EUR_REPORTING_CURRENCY,
                    legs=tuple(legs),
                    discount_factors=discount_factors,
                )
            )
        except LngCashValuationError as exc:
            raise LngCargoEconomicsError(
                [
                    (f"CASH_PRIMITIVE_REFUSED:{code}", detail)
                    for code, detail in exc.violations
                ]
            ) from exc

    if cargo_margin < 0:
        warnings.append("NEGATIVE_CARGO_MARGIN")
    if unit_netback < 0:
        warnings.append("NEGATIVE_UNIT_NETBACK")
    if cash_valuation.net_present_value_reporting_ccy < 0:
        warnings.append("NEGATIVE_NET_PRESENT_VALUE")

    return _CargoEconomicCompositionResult(
        energy_reduction_mwh=energy_reduction,
        unit_netback_eur_per_purchased_mwh=unit_netback,
        sale_basis_eur_per_delivered_mwh=sale_basis,
        purchase_outlay_eur=purchase_outlay,
        sale_proceeds_eur=sale_proceeds,
        total_downstream_costs_eur=total_costs,
        cargo_margin_eur=cargo_margin,
        margin_reconciliation_gap_eur=reconciliation_gap,
        margin_reconciliation_tolerance_eur=reconciliation_tolerance,
        cash_valuation=cash_valuation,
        warnings=tuple(warnings),
    )


def _collect_violations(
    input_: LngCargoEconomicsInput,
    downstream_costs: tuple[object, ...],
    discount_factors: tuple[object, ...],
    included_items: tuple[object, ...],
) -> list[tuple[str, str]]:
    """Collect legacy economics violations plus the existing readiness match."""

    violations, purchased_ok = _collect_common_violations(
        input_,
        downstream_costs,
        discount_factors,
        included_items,
        expected_model_version=LNG_CARGO_ECONOMICS_MODEL_VERSION,
        cost_type=LngCargoDownstreamCostInput,
    )
    # 就绪度匹配保持为 legacy 路径独有的最后一项校验。
    _validate_readiness(input_, purchased_ok, violations)
    return violations


def _collect_economics_only_violations(
    input_: LngEconomicsOnlyInput,
    downstream_costs: tuple[object, ...],
    discount_factors: tuple[object, ...],
    included_items: tuple[object, ...],
) -> list[tuple[str, str]]:
    """Collect economics-only violations without invoking any readiness assessor."""

    violations, _ = _collect_common_violations(
        input_,
        downstream_costs,
        discount_factors,
        included_items,
        expected_model_version=LNG_ECONOMICS_ONLY_MODEL_VERSION,
        cost_type=LngEconomicsOnlyCostInput,
    )
    if input_.reporting_currency != EUR_REPORTING_CURRENCY:
        violations.append(
            (
                "REPORTING_CURRENCY_UNSUPPORTED",
                f"reporting_currency={input_.reporting_currency!r} must be exactly"
                f" {EUR_REPORTING_CURRENCY!r}; this path performs no FX conversion",
            )
        )
    if input_.energy_unit != SUPPORTED_ENERGY_UNIT:
        violations.append(
            (
                "ENERGY_UNIT_UNSUPPORTED",
                f"energy_unit={input_.energy_unit!r} must be exactly"
                f" {SUPPORTED_ENERGY_UNIT!r}; no volume or heat-unit conversion is"
                " performed",
            )
        )
    for position, cost in enumerate(downstream_costs):
        if not isinstance(cost, LngEconomicsOnlyCostInput):
            continue
        label = f"downstream_costs[{position}] ({cost.cost_id})"
        if not isinstance(cost.charge_basis, LngDownstreamChargeBasis):
            violations.append(
                (
                    "CHARGE_BASIS_INVALID",
                    f"{label}.charge_basis must be a LngDownstreamChargeBasis member",
                )
            )
        elif cost.charge_basis is LngDownstreamChargeBasis.IN_KIND:
            violations.append(
                (
                    "IN_KIND_COST_NOT_A_CASH_CHARGE",
                    f"{label}.charge_basis=in_kind; consumed or lost energy must be"
                    " declared in the explicit energy stages, not monetized again as a"
                    " downstream cash cost",
                )
            )
        elif cost.charge_basis is not LngDownstreamChargeBasis.INVOICED_CASH:
            violations.append(
                (
                    "CHARGE_BASIS_NOT_INVOICED_CASH",
                    f"{label}.charge_basis={cost.charge_basis.value!r} is not an"
                    " explicitly invoiced cash charge",
                )
            )
    return violations


def _collect_common_violations(
    input_: _EconomicInputLike,
    downstream_costs: tuple[object, ...],
    discount_factors: tuple[object, ...],
    included_items: tuple[object, ...],
    *,
    expected_model_version: str,
    cost_type: type,
) -> tuple[list[tuple[str, str]], bool]:
    """Collect all common economics violations in fixed validation order.

    校验顺序固定（身份 → 日期/能量 → 单价 → 购买基准与成本范围 → 逐项成本 →
    付款日期 → 贴现覆盖），使拒绝结果可复现；任何 violations 非空即整体拒绝，
    绝不在缺失输入上继续估值。物理就绪度由调用方单独追加。
    """

    violations: list[tuple[str, str]] = []
    if input_.model_version != expected_model_version:
        violations.append(
            (
                "MODEL_VERSION_UNSUPPORTED",
                f"model_version={input_.model_version!r}; "
                f"supported={expected_model_version!r}",
            )
        )
    for field_name in ("contract_id", "cargo_id", "terminal_id", "resource_id"):
        value = getattr(input_, field_name)
        if not isinstance(value, str) or not value.strip():
            violations.append(
                ("REFERENCE_MISSING", f"{field_name} must be a non-empty reference")
            )

    date_ok = _is_plain_date(input_.valuation_date)
    if not date_ok:
        violations.append(
            (
                "VALUATION_DATE_INVALID",
                "valuation_date must be a calendar date (a datetime is not a valuation"
                " date)",
            )
        )
    if (
        not isinstance(input_.energy_basis_reference, str)
        or not input_.energy_basis_reference.strip()
    ):
        violations.append(
            (
                "ENERGY_BASIS_REFERENCE_MISSING",
                "energy_basis_reference is mandatory: both quantities must be declared on"
                " one explicit energy basis and no m3/MMBtu conversion is performed",
            )
        )

    purchased_ok = _validate_energy(
        input_.purchased_energy_mwh, "purchased_energy_mwh", "PURCHASED_ENERGY", violations
    )
    delivered_ok = _validate_energy(
        input_.delivered_energy_mwh, "delivered_energy_mwh", "DELIVERED_ENERGY", violations
    )
    if (
        purchased_ok
        and delivered_ok
        and input_.delivered_energy_mwh > input_.purchased_energy_mwh
    ):
        violations.append(
            (
                "DELIVERED_ENERGY_EXCEEDS_PURCHASED",
                f"delivered_energy_mwh={input_.delivered_energy_mwh} exceeds"
                f" purchased_energy_mwh={input_.purchased_energy_mwh}",
            )
        )

    _validate_unit_price(
        input_.purchase_unit_price_eur_per_mwh,
        "purchase_unit_price_eur_per_mwh",
        "PURCHASE_UNIT_PRICE",
        violations,
    )
    _validate_unit_price(
        input_.sale_unit_price_eur_per_mwh,
        "sale_unit_price_eur_per_mwh",
        "SALE_UNIT_PRICE",
        violations,
    )
    for field_name in (
        "purchase_price_source_reference",
        "sale_price_source_reference",
    ):
        value = getattr(input_, field_name)
        if not isinstance(value, str) or not value.strip():
            violations.append(
                (f"{field_name.upper()}_MISSING", f"{field_name} is mandatory")
            )
    if (
        not isinstance(input_.purchase_basis, str)
        or input_.purchase_basis not in PURCHASE_BASES
    ):
        violations.append(
            (
                "PURCHASE_BASIS_INVALID",
                f"purchase_basis={input_.purchase_basis!r} must be exactly one of"
                f" {PURCHASE_BASES}; no purchase basis is inferred",
            )
        )
    if (
        not isinstance(input_.cost_scope_statement, str)
        or not input_.cost_scope_statement.strip()
    ):
        violations.append(
            (
                "COST_SCOPE_STATEMENT_MISSING",
                "cost_scope_statement is mandatory: the caller must state the cost scope"
                " instead of leaving it implied",
            )
        )

    included_set = _validate_included_items(included_items, violations)
    valuation_date = input_.valuation_date if date_ok else None
    cost_coverage = _validate_downstream_costs(
        downstream_costs,
        included_set,
        valuation_date,
        violations,
        cost_type=cost_type,
    )
    purchase_date = _validate_payment_date(
        input_.purchase_payment_date,
        "purchase_payment_date",
        "PURCHASE_PAYMENT_DATE",
        valuation_date,
        violations,
    )
    sale_date = _validate_payment_date(
        input_.sale_payment_date,
        "sale_payment_date",
        "SALE_PAYMENT_DATE",
        valuation_date,
        violations,
    )
    _validate_discount_coverage(
        [("purchase_payment_date", purchase_date), ("sale_payment_date", sale_date)]
        + cost_coverage,
        discount_factors,
        violations,
    )
    return violations, purchased_ok


def _validate_energy(
    value: object,
    label: str,
    prefix: str,
    violations: list[tuple[str, str]],
) -> bool:
    """Validate one explicit positive bounded MWh quantity."""

    if not isinstance(value, Decimal):
        violations.append(
            (
                f"{prefix}_NOT_DECIMAL",
                f"{label} must be an explicit Decimal, got {type(value).__name__}",
            )
        )
        return False
    if not value.is_finite():
        violations.append((f"{prefix}_NOT_FINITE", f"{label} must be finite"))
        return False
    if value <= 0:
        violations.append(
            (
                f"{prefix}_NOT_POSITIVE",
                f"{label} must be positive; zero or negative energy is not a cargo",
            )
        )
        return False
    if value > MAX_ENERGY_MWH:
        violations.append(
            (
                f"{prefix}_OVERFLOW",
                f"{label}={value} exceeds the supported magnitude {MAX_ENERGY_MWH}",
            )
        )
        return False
    return True


def _validate_unit_price(
    value: object,
    label: str,
    prefix: str,
    violations: list[tuple[str, str]],
) -> None:
    """Validate one signed finite bounded EUR/MWh unit price.

    Negative prices are economically possible and zero is allowed (the resulting
    zero leg is omitted with disclosure); only non-numeric, non-finite or
    oversized values are refused.
    """

    if not isinstance(value, Decimal):
        violations.append(
            (
                f"{prefix}_NOT_DECIMAL",
                f"{label} must be an explicit Decimal, got {type(value).__name__}",
            )
        )
        return
    if not value.is_finite():
        violations.append((f"{prefix}_NOT_FINITE", f"{label} must be finite"))
        return
    if value.copy_abs() > MAX_ABS_UNIT_PRICE_EUR_PER_MWH:
        violations.append(
            (
                f"{prefix}_OVERFLOW",
                f"{label}={value} exceeds the supported magnitude"
                f" {MAX_ABS_UNIT_PRICE_EUR_PER_MWH}",
            )
        )


def _validate_included_items(
    included_items: tuple[object, ...],
    violations: list[tuple[str, str]],
) -> set[LngCashLegCategory]:
    """Validate the declared purchase-included cost items and return the set."""

    seen: set[LngCashLegCategory] = set()
    for position, item in enumerate(included_items):
        label = f"purchase_included_cost_items[{position}]"
        if not isinstance(item, LngCashLegCategory):
            violations.append(
                (
                    "PURCHASE_INCLUDED_COST_ITEM_INVALID",
                    f"{label} must be a LngCashLegCategory member",
                )
            )
            continue
        if item in _CASH_LEG_CATEGORIES_NOT_COSTS:
            violations.append(
                (
                    "PURCHASE_INCLUDED_COST_ITEM_INVALID",
                    f"{label}={item.value!r} names a composed cash leg, not a cost item"
                    " that a purchase price can include",
                )
            )
            continue
        if item in seen:
            violations.append(
                (
                    "PURCHASE_INCLUDED_COST_ITEM_DUPLICATE",
                    f"{label}={item.value!r} is supplied more than once",
                )
            )
        seen.add(item)
    return seen


def _validate_downstream_costs(
    downstream_costs: tuple[object, ...],
    included_set: set[LngCashLegCategory],
    valuation_date: date | None,
    violations: list[tuple[str, str]],
    *,
    cost_type: type,
) -> list[tuple[str, date | None]]:
    """Validate itemized downstream costs and return their coverage dates."""

    seen_cost_ids: set[str] = set()
    coverage: list[tuple[str, date | None]] = []
    for position, cost in enumerate(downstream_costs):
        label = f"downstream_costs[{position}]"
        if not isinstance(cost, cost_type):
            violations.append(
                (
                    "DOWNSTREAM_COST_ITEM_INVALID",
                    f"{label} must be a {cost_type.__name__} instance",
                )
            )
            continue
        if not isinstance(cost.cost_id, str) or not cost.cost_id.strip():
            violations.append(
                ("COST_ID_MISSING", f"{label}.cost_id must be a non-empty unique id")
            )
        else:
            label = f"{label} ({cost.cost_id})"
            if cost.cost_id in seen_cost_ids:
                violations.append(
                    (
                        "DUPLICATE_COST_ID",
                        f"{label}.cost_id is supplied more than once; one cost is counted"
                        " exactly once",
                    )
                )
            seen_cost_ids.add(cost.cost_id)
        if not isinstance(cost.category, LngCashLegCategory):
            violations.append(
                (
                    "COST_CATEGORY_INVALID",
                    f"{label}.category must be a LngCashLegCategory member",
                )
            )
        elif cost.category in _CASH_LEG_CATEGORIES_NOT_COSTS:
            violations.append(
                (
                    "COST_CATEGORY_INVALID",
                    f"{label}.category={cost.category.value!r} cannot be a downstream cost;"
                    " the purchase and sale legs are constructed by this composition and"
                    " cannot be supplied by the caller",
                )
            )
        elif cost.category in included_set:
            violations.append(
                (
                    "DOWNSTREAM_COST_DOUBLES_INCLUDED_PURCHASE_COST",
                    f"{label}.category={cost.category.value!r} is declared as already"
                    " included in the purchase price; itemizing it again would double"
                    " count it",
                )
            )
        _validate_cost_amount(cost.amount_eur, label, violations)
        if not isinstance(cost.source_reference, str) or not cost.source_reference.strip():
            violations.append(
                ("COST_SOURCE_REFERENCE_MISSING", f"{label}.source_reference is mandatory")
            )
        valid_date: date | None = None
        if not _is_plain_date(cost.payment_date):
            violations.append(
                ("COST_PAYMENT_DATE_INVALID", f"{label}.payment_date must be a calendar date")
            )
        elif valuation_date is not None and cost.payment_date < valuation_date:
            violations.append(
                (
                    "COST_PAYMENT_DATE_BEFORE_VALUATION",
                    f"{label}.payment_date={cost.payment_date.isoformat()} is before"
                    f" valuation_date={valuation_date.isoformat()}; past cash dates are out"
                    " of scope",
                )
            )
        else:
            valid_date = cost.payment_date
        coverage.append((label, valid_date))
    return coverage


def _validate_cost_amount(
    value: object,
    label: str,
    violations: list[tuple[str, str]],
) -> None:
    """Validate one nonnegative bounded EUR cost total."""

    if not isinstance(value, Decimal):
        violations.append(
            (
                "COST_AMOUNT_NOT_DECIMAL",
                f"{label}.amount_eur must be an explicit Decimal, got"
                f" {type(value).__name__}",
            )
        )
        return
    if not value.is_finite():
        violations.append(("COST_AMOUNT_NOT_FINITE", f"{label}.amount_eur must be finite"))
        return
    if value < 0:
        violations.append(
            (
                "COST_AMOUNT_NEGATIVE",
                f"{label}.amount_eur must be nonnegative; signed relief belongs in the"
                " declared prices, not in a cost item",
            )
        )
        return
    if value.copy_abs() > MAX_ABS_CASH_AMOUNT:
        violations.append(
            (
                "COST_AMOUNT_OVERFLOW",
                f"{label}.amount_eur={value} exceeds the supported magnitude"
                f" {MAX_ABS_CASH_AMOUNT}",
            )
        )


def _validate_payment_date(
    value: object,
    label: str,
    prefix: str,
    valuation_date: date | None,
    violations: list[tuple[str, str]],
) -> date | None:
    """Validate one mandatory plain payment date at or after the valuation date."""

    if not _is_plain_date(value):
        violations.append((f"{prefix}_INVALID", f"{label} must be a calendar date"))
        return None
    if valuation_date is not None and value < valuation_date:
        violations.append(
            (
                f"{prefix}_BEFORE_VALUATION",
                f"{label}={value.isoformat()} is before"
                f" valuation_date={valuation_date.isoformat()}; past cash dates are out"
                " of scope",
            )
        )
        return None
    return value


def _validate_discount_coverage(
    needed_dates: list[tuple[str, date | None]],
    discount_factors: tuple[LngCashDiscountFactorInput, ...],
    violations: list[tuple[str, str]],
) -> None:
    """Require one explicit discount factor per declared payment date."""

    supplied: set[date] = set()
    for position, item in enumerate(discount_factors):
        if not isinstance(item, LngCashDiscountFactorInput):
            violations.append(
                (
                    "DISCOUNT_FACTOR_ITEM_INVALID",
                    f"discount_factors[{position}] must be a LngCashDiscountFactorInput"
                    " instance",
                )
            )
            continue
        if _is_plain_date(item.payment_date):
            supplied.add(item.payment_date)
    reported: set[date] = set()
    for label, payment_date in needed_dates:
        if payment_date is None or payment_date in supplied or payment_date in reported:
            continue
        reported.add(payment_date)
        violations.append(
            (
                "DISCOUNT_FACTOR_MISSING_FOR_PAYMENT_DATE",
                f"no explicitly supplied discount factor for {label}"
                f" ({payment_date.isoformat()})",
            )
        )


def _validate_readiness(
    input_: LngCargoEconomicsInput,
    purchased_ok: bool,
    violations: list[tuple[str, str]],
) -> None:
    """Match the composition references/quantity against the readiness scenario."""

    scenario = input_.readiness_scenario
    if not isinstance(scenario, LngRegasScenario):
        violations.append(
            (
                "READINESS_INPUT_TYPE_INVALID",
                "readiness_scenario must be a LngRegasScenario assessed by the existing"
                " regas readiness method",
            )
        )
        return
    for field_name in ("contract_id", "cargo_id", "terminal_id"):
        expected = getattr(input_, field_name)
        actual = getattr(scenario, field_name)
        if isinstance(expected, str) and expected.strip() and actual != expected:
            violations.append(
                (
                    "READINESS_REFERENCE_MISMATCH",
                    f"readiness_scenario.{field_name}={actual!r} does not match the"
                    f" composition reference {expected!r}",
                )
            )
    if purchased_ok:
        declared_energy = Decimal(str(scenario.cargo_size_mwh))
        if declared_energy != input_.purchased_energy_mwh:
            violations.append(
                (
                    "READINESS_ENERGY_QUANTITY_MISMATCH",
                    f"readiness_scenario.cargo_size_mwh={scenario.cargo_size_mwh!r} does"
                    f" not match purchased_energy_mwh={input_.purchased_energy_mwh}",
                )
            )


def _is_plain_date(value: object) -> bool:
    """Whether ``value`` is a calendar date and not a ``datetime`` or None."""

    if isinstance(value, datetime):
        return False
    return isinstance(value, date)


def _economics_decimal_context() -> Context:
    """Build a fresh explicit decimal context for deterministic arithmetic."""

    return Context(
        prec=WORKING_PRECISION, rounding=ROUND_HALF_EVEN, Emax=999_999, Emin=-999_999
    )


def _quantize_money(value: Decimal) -> Decimal:
    """Quantize a EUR (or MWh, at the same declared rounding) amount."""

    return value.quantize(MONEY_QUANTUM, rounding=ROUND_HALF_EVEN)

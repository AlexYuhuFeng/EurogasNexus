"""Explicit LNG cargo energy-stage accounting — research-only decision support.

One deterministic job: compose an explicitly supplied, ordered chain of LNG
cargo energy stages into the purchased energy, delivered energy, total consumed
energy, physical loss energy and total energy reduction.

The chain is never inferred. Every stage explicitly states four exact ``Decimal``
energy quantities on one declared energy unit and basis:

- ``input_energy_mwh`` (positive);
- ``output_energy_mwh`` (positive);
- ``consumed_energy_mwh`` (nonnegative, energy consumed in kind);
- ``physical_loss_energy_mwh`` (nonnegative, energy lost physically).

Per-stage conservation is exact and unquantized:

    input = output + consumed + physical_loss

Stages must be adjacent (previous output equals next input), stage ids unique,
the first input equal to the declared purchased energy and the final output
equal to the declared delivered energy. Total reduction is reported separately
as ``purchased - delivered`` and must equal the sum of consumed plus physical
loss. Neither consumed energy nor physical loss is monetized here.

Compatibility note: ``lng_cargo_economics.energy_loss_mwh`` on the legacy path is
the total reduction (purchased minus delivered). This module does not rename or
reinterpret that legacy field; it reports consumed energy, physical loss energy
and total reduction as three distinct values.

Boundaries and refusals:
- explicit MWh only; no m3/MMBtu conversion, no inferred stage, fuel percentage
  or unspecified loss is ever added;
- exact ``Decimal`` amounts only; int, float and bool are refused rather than
  coerced;
- bounded stage count, magnitude, coefficient width and decimal exponent are
  checked before any conservation arithmetic;
- omitted stages or omitted consumed/loss values are missing input, never zero;
- no terminal, slot, storage, TSO or physical-readiness assessment is performed;
- research-only decision support; no trade execution, nomination or settlement.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from decimal import ROUND_HALF_EVEN, Context, Decimal, DecimalException, localcontext

# Canonical definition (one authority) is re-exported for import compatibility.
from eurogas_nexus.domain.ontology.vocabulary import LngEnergyStageKind

LNG_ENERGY_BALANCE_MODEL_VERSION = "lng-energy-balance/v1"

# One explicit energy unit only. No volume or heat-unit conversion is performed.
SUPPORTED_ENERGY_UNIT = "MWh"

# Deterministic input-sanity limits, checked before conservation arithmetic.
MAX_ENERGY_STAGE_COUNT = 32
MAX_STAGE_ENERGY_MWH = Decimal("1e12")
MIN_NONZERO_STAGE_ENERGY_MWH = Decimal("1e-12")
MAX_STAGE_ENERGY_COEFFICIENT_DIGITS = 34
MIN_STAGE_ENERGY_EXPONENT = -64
MAX_STAGE_ENERGY_EXPONENT = 64

# Editing precision for exact additions of bounded stage amounts. The limits
# above keep the largest three-term sum well inside this precision.
ENERGY_ARITHMETIC_PRECISION = 80

_BASELINE_WARNINGS: tuple[str, ...] = (
    "RESEARCH_ONLY_DECISION_SUPPORT_NOT_ACCOUNTING_CUSTODY_OR_SETTLEMENT",
    "EXPLICIT_ENERGY_STAGES_ONLY_NO_VOLUME_OR_FX_CONVERSION",
    "CONSUMED_ENERGY_AND_PHYSICAL_LOSS_DISCLOSED_SEPARATELY_NOT_MONETIZED",
)


class LngEnergyBalanceError(ValueError):
    """Deterministic refusal of invalid LNG cargo energy-stage input.

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


@dataclass(frozen=True)
class LngEnergyStage:
    """One explicit energy stage in an ordered LNG cargo energy chain.

    Attributes:
        stage_id: Unique id of the stage within the chain.
        kind: Declared stage kind from :class:`LngEnergyStageKind`.
        input_energy_mwh: Positive exact stage input energy.
        output_energy_mwh: Positive exact stage output energy.
        consumed_energy_mwh: Nonnegative energy consumed in kind by the stage.
        physical_loss_energy_mwh: Nonnegative physical energy loss of the stage.
        source_references: Non-empty provenance references for the stage.
    """

    stage_id: str
    kind: LngEnergyStageKind
    input_energy_mwh: Decimal
    output_energy_mwh: Decimal
    consumed_energy_mwh: Decimal
    physical_loss_energy_mwh: Decimal
    source_references: tuple[str, ...]


@dataclass(frozen=True)
class LngEnergyBalanceInput:
    """Typed, versioned input of one explicit LNG cargo energy balance.

    Attributes:
        purchased_energy_mwh: Declared purchased energy; must equal the first
            stage input exactly.
        delivered_energy_mwh: Declared delivered energy; must equal the final
            stage output exactly.
        energy_basis_reference: Mandatory declared energy-basis reference.
        energy_unit: Explicit energy unit; only ``MWh`` is supported.
        stages: Ordered explicit energy stages; at least one is required.
        model_version: Model version; any other value is refused.
    """

    purchased_energy_mwh: Decimal
    delivered_energy_mwh: Decimal
    energy_basis_reference: str
    energy_unit: str
    stages: tuple[LngEnergyStage, ...]
    model_version: str = LNG_ENERGY_BALANCE_MODEL_VERSION


@dataclass(frozen=True)
class LngEnergyBalanceResult:
    """Typed, versioned result of one explicit LNG cargo energy balance.

    Attributes:
        model_version: Version of the producing implementation (never a caller
            supplied version).
        purchased_energy_mwh: Echoed declared purchased energy.
        delivered_energy_mwh: Echoed declared delivered energy.
        energy_basis_reference: Echoed declared energy-basis reference.
        energy_unit: Echoed explicit energy unit.
        total_consumed_energy_mwh: Exact sum of explicitly declared consumed
            energy; never added to the cash costs.
        physical_loss_energy_mwh: Exact sum of explicitly declared physical
            losses; never added to the cash costs.
        total_reduction_energy_mwh: Exact purchased-minus-delivered reduction,
            reported separately from physical loss.
        stage_count: Number of explicit stages in the chain.
        stages: Normalized explicit stage chain.
        warnings: Always-on research and no-monetization warnings.
        source_references: Sorted unique stage provenance supplied by the
            caller.
        research_only: Always True.
        human_review_required: Always True.
    """

    model_version: str
    purchased_energy_mwh: Decimal
    delivered_energy_mwh: Decimal
    energy_basis_reference: str
    energy_unit: str
    total_consumed_energy_mwh: Decimal
    physical_loss_energy_mwh: Decimal
    total_reduction_energy_mwh: Decimal
    stage_count: int
    stages: tuple[LngEnergyStage, ...]
    warnings: tuple[str, ...]
    source_references: tuple[str, ...]
    research_only: bool = True
    human_review_required: bool = True


_STAGE_ENERGY_FIELDS: tuple[tuple[str, str, bool], ...] = (
    ("input_energy_mwh", "STAGE_INPUT_ENERGY", True),
    ("output_energy_mwh", "STAGE_OUTPUT_ENERGY", True),
    ("consumed_energy_mwh", "STAGE_CONSUMED_ENERGY", False),
    ("physical_loss_energy_mwh", "STAGE_PHYSICAL_LOSS_ENERGY", False),
)


def compute_lng_energy_balance(input_: LngEnergyBalanceInput) -> LngEnergyBalanceResult:
    """Validate and compose one explicit LNG cargo energy-stage chain.

    Args:
        input_: Typed input with purchased/delivered energy, one explicit energy
            basis and unit, and an ordered chain of explicit stages.

    Returns:
        Deterministic exact energy totals and the normalized stage chain.

    Raises:
        LngEnergyBalanceError: When any declared field, stage, conservation
            identity or chain adjacency violates the deterministic rules.
    """

    if not isinstance(input_, LngEnergyBalanceInput):
        raise LngEnergyBalanceError(
            [
                (
                    "INPUT_TYPE_INVALID",
                    "input must be a LngEnergyBalanceInput instance",
                )
            ]
        )

    violations: list[tuple[str, str]] = []
    if input_.model_version != LNG_ENERGY_BALANCE_MODEL_VERSION:
        violations.append(
            (
                "MODEL_VERSION_UNSUPPORTED",
                f"model_version={input_.model_version!r}; "
                f"supported={LNG_ENERGY_BALANCE_MODEL_VERSION!r}",
            )
        )
    if (
        not isinstance(input_.energy_basis_reference, str)
        or not input_.energy_basis_reference.strip()
    ):
        violations.append(
            (
                "ENERGY_BASIS_REFERENCE_MISSING",
                "energy_basis_reference is mandatory: all stages must be on one"
                " explicit energy basis and no conversion is performed",
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

    _validate_energy_amount(
        input_.purchased_energy_mwh,
        "purchased_energy_mwh",
        "PURCHASED_ENERGY",
        positive=True,
        violations=violations,
    )
    _validate_energy_amount(
        input_.delivered_energy_mwh,
        "delivered_energy_mwh",
        "DELIVERED_ENERGY",
        positive=True,
        violations=violations,
    )

    if isinstance(input_.stages, (tuple, list)):
        stages = tuple(input_.stages)
        if not stages:
            violations.append(
                (
                    "STAGE_COUNT_INVALID",
                    "at least one explicit energy stage is required; zero stages must"
                    " not be interpreted as zero consumption or zero loss",
                )
            )
        elif len(stages) > MAX_ENERGY_STAGE_COUNT:
            violations.append(
                (
                    "STAGE_COUNT_EXCEEDED",
                    f"{len(stages)} stages exceeds the supported limit"
                    f" {MAX_ENERGY_STAGE_COUNT}",
                )
            )
    else:
        violations.append(
            (
                "STAGES_INVALID",
                "stages must be a tuple or list of LngEnergyStage",
            )
        )
        stages = ()

    normalized_stages: list[LngEnergyStage] = []
    seen_stage_ids: set[str] = set()
    for position, stage in enumerate(stages):
        label = f"stages[{position}]"
        if not isinstance(stage, LngEnergyStage):
            violations.append(
                (
                    "STAGE_ITEM_INVALID",
                    f"{label} must be a LngEnergyStage instance",
                )
            )
            continue

        stage_ok = True
        if not isinstance(stage.stage_id, str) or not stage.stage_id.strip():
            violations.append(
                ("STAGE_ID_MISSING", f"{label}.stage_id must be a non-empty unique id")
            )
            stage_ok = False
        else:
            label = f"{label} ({stage.stage_id})"
            if stage.stage_id in seen_stage_ids:
                violations.append(
                    (
                        "STAGE_ID_DUPLICATE",
                        f"{label}.stage_id is supplied more than once; each stage is"
                        " counted exactly once",
                    )
                )
                stage_ok = False
            seen_stage_ids.add(stage.stage_id)

        if not isinstance(stage.kind, LngEnergyStageKind):
            violations.append(
                (
                    "STAGE_KIND_INVALID",
                    f"{label}.kind must be a LngEnergyStageKind member",
                )
            )
            stage_ok = False

        for field_name, prefix, positive in _STAGE_ENERGY_FIELDS:
            if not _validate_energy_amount(
                getattr(stage, field_name),
                f"{label}.{field_name}",
                prefix,
                positive=positive,
                violations=violations,
            ):
                stage_ok = False

        if not isinstance(stage.source_references, (tuple, list)):
            violations.append(
                (
                    "STAGE_SOURCE_REFERENCES_INVALID",
                    f"{label}.source_references must be a tuple or list of"
                    " non-empty references",
                )
            )
            source_references: tuple[str, ...] = ()
            stage_ok = False
        else:
            source_references = tuple(stage.source_references)
            if not source_references:
                violations.append(
                    (
                        "STAGE_SOURCE_REFERENCE_MISSING",
                        f"{label}.source_references must contain at least one"
                        " provenance reference",
                    )
                )
                stage_ok = False
            for source_position, source_reference in enumerate(source_references):
                if (
                    not isinstance(source_reference, str)
                    or not source_reference.strip()
                ):
                    violations.append(
                        (
                            "STAGE_SOURCE_REFERENCE_INVALID",
                            f"{label}.source_references[{source_position}] must be a"
                            " non-empty string",
                        )
                    )
                    stage_ok = False

        if stage_ok:
            normalized_stages.append(
                replace(stage, source_references=source_references)
            )

    if violations:
        raise LngEnergyBalanceError(violations)

    # Chain and conservation arithmetic starts only after every stage field and
    # bound has been validated. No result is quantized: an inconsistency must be
    # visible as a refusal, never rounded away.
    with localcontext(_energy_decimal_context()):
        try:
            for position, stage in enumerate(normalized_stages):
                conserved = (
                    stage.output_energy_mwh
                    + stage.consumed_energy_mwh
                    + stage.physical_loss_energy_mwh
                )
                if stage.input_energy_mwh != conserved:
                    violations.append(
                        (
                            "STAGE_CONSERVATION_FAILED",
                            f"stages[{position}] ({stage.stage_id}): input"
                            f" {stage.input_energy_mwh} != output + consumed + physical"
                            f" loss = {conserved}",
                        )
                    )
            for position in range(1, len(normalized_stages)):
                previous = normalized_stages[position - 1]
                current = normalized_stages[position]
                if previous.output_energy_mwh != current.input_energy_mwh:
                    violations.append(
                        (
                            "STAGE_CHAIN_DISCONTINUOUS",
                            f"stages[{position - 1}] ({previous.stage_id}) output"
                            f" {previous.output_energy_mwh} != stages[{position}]"
                            f" ({current.stage_id}) input {current.input_energy_mwh}",
                        )
                    )
            if normalized_stages[0].input_energy_mwh != input_.purchased_energy_mwh:
                violations.append(
                    (
                        "STAGE_CHAIN_START_MISMATCH",
                        f"first stage ({normalized_stages[0].stage_id}) input"
                        f" {normalized_stages[0].input_energy_mwh} != declared"
                        f" purchased_energy_mwh {input_.purchased_energy_mwh}",
                    )
                )
            if normalized_stages[-1].output_energy_mwh != input_.delivered_energy_mwh:
                violations.append(
                    (
                        "STAGE_CHAIN_END_MISMATCH",
                        f"final stage ({normalized_stages[-1].stage_id}) output"
                        f" {normalized_stages[-1].output_energy_mwh} != declared"
                        f" delivered_energy_mwh {input_.delivered_energy_mwh}",
                    )
                )
            total_consumed = sum(
                (stage.consumed_energy_mwh for stage in normalized_stages), Decimal(0)
            )
            physical_loss = sum(
                (stage.physical_loss_energy_mwh for stage in normalized_stages),
                Decimal(0),
            )
            total_reduction = (
                input_.purchased_energy_mwh - input_.delivered_energy_mwh
            )
            reduced_in_stages = total_consumed + physical_loss
            if total_reduction != reduced_in_stages:
                violations.append(
                    (
                        "TOTAL_REDUCTION_RECONCILIATION_FAILED",
                        f"total reduction {total_reduction} != total consumed"
                        f" {total_consumed} + physical loss {physical_loss}",
                    )
                )
        except DecimalException as exc:
            raise LngEnergyBalanceError(
                [
                    (
                        "NUMERIC_EVALUATION_FAILED",
                        f"deterministic decimal evaluation failed: {exc}",
                    )
                ]
            ) from exc

    if violations:
        raise LngEnergyBalanceError(violations)

    source_references = tuple(
        sorted(
            {
                source_reference
                for stage in normalized_stages
                for source_reference in stage.source_references
            }
        )
    )
    return LngEnergyBalanceResult(
        model_version=LNG_ENERGY_BALANCE_MODEL_VERSION,
        purchased_energy_mwh=input_.purchased_energy_mwh,
        delivered_energy_mwh=input_.delivered_energy_mwh,
        energy_basis_reference=input_.energy_basis_reference,
        energy_unit=input_.energy_unit,
        total_consumed_energy_mwh=total_consumed,
        physical_loss_energy_mwh=physical_loss,
        total_reduction_energy_mwh=total_reduction,
        stage_count=len(normalized_stages),
        stages=tuple(normalized_stages),
        warnings=_BASELINE_WARNINGS,
        source_references=source_references,
        research_only=True,
        human_review_required=True,
    )


def _validate_energy_amount(
    value: object,
    label: str,
    prefix: str,
    *,
    positive: bool,
    violations: list[tuple[str, str]],
) -> bool:
    """Validate one exact, finite, bounded stage energy amount before arithmetic."""

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
    if positive:
        if value <= 0:
            violations.append(
                (
                    f"{prefix}_NOT_POSITIVE",
                    f"{label} must be positive; zero is only valid for consumed"
                    " energy or physical loss",
                )
            )
            return False
    elif value < 0:
        violations.append((f"{prefix}_NEGATIVE", f"{label} must be nonnegative"))
        return False

    if value.copy_abs() > MAX_STAGE_ENERGY_MWH:
        violations.append(
            (
                f"{prefix}_OVERFLOW",
                f"{label}={value} exceeds the supported magnitude"
                f" {MAX_STAGE_ENERGY_MWH}",
            )
        )
        return False
    if value != 0 and value.copy_abs() < MIN_NONZERO_STAGE_ENERGY_MWH:
        violations.append(
            (
                f"{prefix}_BELOW_MINIMUM",
                f"{label}={value} is below the supported non-zero magnitude"
                f" {MIN_NONZERO_STAGE_ENERGY_MWH}",
            )
        )
        return False

    value_tuple = value.as_tuple()
    if len(value_tuple.digits) > MAX_STAGE_ENERGY_COEFFICIENT_DIGITS:
        violations.append(
            (
                f"{prefix}_COEFFICIENT_LIMIT",
                f"{label}={value} has {len(value_tuple.digits)} coefficient digits;"
                f" the supported limit is {MAX_STAGE_ENERGY_COEFFICIENT_DIGITS}",
            )
        )
        return False
    if not (
        MIN_STAGE_ENERGY_EXPONENT
        <= value_tuple.exponent
        <= MAX_STAGE_ENERGY_EXPONENT
    ):
        violations.append(
            (
                f"{prefix}_EXPONENT_LIMIT",
                f"{label}={value} has exponent {value_tuple.exponent}; the supported"
                f" range is [{MIN_STAGE_ENERGY_EXPONENT},"
                f" {MAX_STAGE_ENERGY_EXPONENT}]",
            )
        )
        return False
    return True


def _energy_decimal_context() -> Context:
    """Build a fresh explicit decimal context for exact energy arithmetic."""

    return Context(
        prec=ENERGY_ARITHMETIC_PRECISION,
        rounding=ROUND_HALF_EVEN,
        Emax=999_999,
        Emin=-999_999,
    )

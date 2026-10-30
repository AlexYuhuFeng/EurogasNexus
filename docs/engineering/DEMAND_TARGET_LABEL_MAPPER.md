# Demand target label mapper

Status: bounded RFC-0008 stage 2 mapper-only implementation. Runtime, operator,
API, prediction, schema and source-activation wiring remain out of scope.

Related records:

- [RFC-0008: Retrospective demand-label availability](RFC-0008-RETROSPECTIVE-DEMAND-LABEL-AVAILABILITY.md)
- [Execution state](ARCHITECTURE_V2_EXECUTION_STATE.md)
- Mapper: [`demand_target_inputs.py`](../../src/eurogas_nexus/application/research/demand_target_inputs.py)
- Tests: [`test_demand_target_label_mapper.py`](../../tests/unit/test_demand_target_label_mapper.py)

## Purpose

The National Gas target mapper now accepts an explicit
`target_label_basis` alongside the existing receipt and revision-order
selection. This lets a research caller construct a separate label clock from
already-persisted provider applicability evidence without rewriting actual
receipt, publication identity, native units or quality.

This is mapper mechanics only. It does not prove first publication, public
availability, genuine out-of-sample eligibility, provider-history accuracy or
production suitability.

## Public selection

`build_demand_target_rows` accepts:

```python
target_label_basis: DemandTargetLabelBasis = DemandTargetLabelBasis.ACTUAL_RECEIPT
```

The two admitted values are:

| Value | Meaning |
| --- | --- |
| `ACTUAL_RECEIPT` | Default. The effective label clock is the immutable actual receipt, `DemandTargetRow.available_at`. `label_at` is absent (`None`). |
| `RETROSPECTIVE_PROVIDER_APPLICABILITY_RESEARCH` | Explicit research-only basis. `label_at` is the validated consensus provider applicability instant. This is not first-publication truth and is never production or genuine-OOS evidence. |

The basis is independent of revision ranking. Passing
`DERIVED_REST_APPLICABILITY_ORDER_V1` alone does **not** select the research
label basis and does not populate `label_at`.

## Validation before record reads

The complete selection is validated before the mapper iterates over records.
The nondefault basis is refused with `DemandTargetInputValidationError` when:

- `source_format` is not exactly `REST`;
- `revision_order_policy` is not explicitly
  `DERIVED_REST_APPLICABILITY_ORDER_V1` (receipt ranking is refused);
- the basis value is unknown or malformed.

CSV source rows are never used to infer a clock. Provider revision numbers,
receipt order and lexical order are never fallback label clocks.

## Evidence reuse

The research basis reuses the existing `DERIVED_REST_APPLICABILITY_ORDER_V1`
evidence path. It does not add another clock-derivation method. A row is
admitted only when all existing strict checks pass:

- fixed REST API origin, series/hash identity and approved provider item;
- complete persisted REST provenance;
- raw offset-bearing, normalized UTC and naive wall-clock copies for
  `applicableAt`, `generatedTimeStamp` and `createdDate`;
- each normalized clock agrees with its raw clock and wall-clock copy;
- all three source clocks resolve to exactly one UTC instant;
- the provider timestamp upper bound equals that consensus instant;
- the consensus instant is not later than actual receipt or actual
  availability.

Missing, naive, malformed, disagreeing, inconsistent or future source clocks
produce the existing typed diagnostic and no admitted row. No maximum-clock,
receipt-time, wall-clock or provider-number fallback is introduced.

## Row and provenance mapping

Under `RETROSPECTIVE_PROVIDER_APPLICABILITY_RESEARCH`:

- `DemandTargetRow.available_at` remains the immutable actual receipt.
- `DemandTargetRow.label_at` is copied from the already-reviewed
  `source_order_at_utc` consensus instant.
- `revision_id`, gas day, native `MSCM` value/unit, source revision IDs and
  derived integer revision rank are preserved.
- `DemandTargetRow.revision` is still the derived order (now the source-
  applicability order), never a provider revision number.
- `DemandTargetRow.source_ref` appends the label basis so a downstream hop
  cannot silently lose it.
- `DemandTargetProvenance` records the separate `label_basis`, `label_at`,
  versioned `label_method_version` and deterministic `label_policy_hash`, in
  addition to the existing source-order and actual-receipt evidence.

Default rows keep the exact pre-change values, IDs, order and source
references. The existing REST revision-order opt-in without a label-basis
opt-in also keeps its exact pre-change row and reference shape.

Source references, for one publication `pub`:

| Selection | `source_ref` |
| --- | --- |
| Default CSV | `NATIONAL_GAS:CSV:pub` |
| Default REST | `NATIONAL_GAS:REST:pub` |
| REST source-order opt-in, default label basis | `NATIONAL_GAS:REST:pub:DERIVED_REST_APPLICABILITY_ORDER_V1` |
| REST source-order opt-in, research label basis | `NATIONAL_GAS:REST:pub:DERIVED_REST_APPLICABILITY_ORDER_V1:RETROSPECTIVE_PROVIDER_APPLICABILITY_RESEARCH` |

## Cutoff and revision retention

Actual receipt admission is unchanged: every admitted revision must satisfy
`available_at <= available_at_utc` (the explicit analysis cutoff). Therefore a
label clock earlier than the analysis cutoff does not admit a row whose actual
receipt is later than that cutoff.

Every admitted revision remains in `rows`, ordered by the selected policy. The
mapper never narrows the result to a global latest revision. Downstream fold
selection can use the per-row `label_at` and derived rank, while actual-receipt
eligibility remains available separately. Equal consensus source instants for
distinct publications remain a typed ambiguity refusal.

Quality mapping is unchanged: D+1 provisional requires explicit permission,
source quality `A` remains `AMENDED` and is refused, D+6/unknown provisionality
is refused, and blanks remain missing rather than zero. Label timing cannot
promote quality.

## Non-goals and preserved boundaries

This change does not add or modify:

- runtime, operator, CLI, API, prediction or consumer wiring;
- SQL, repository reads, schema, migrations or persistence;
- source activation, network access or scheduling;
- dependencies, CI registration or deployment artifacts;
- wall-clock reads, wall-clock trust or a new clock-derivation method;
- a CSV or provider-revision-number label clock;
- historical-publication, genuine-OOS, accuracy or production claims.

Runtime and consumer opt-in require separate review, including a trusted server
clock for any analysis-as-of cap and preservation of actual-receipt SQL
admission.

## Test coverage

The new focused mapper module covers:

- unchanged CSV and REST defaults, including explicit REST revision order
  without a label-basis opt-in;
- CSV, receipt-ranking and unknown-basis refusal before record iteration;
- consensus-clock mapping with receipt and identity preservation;
- missing, naive, inconsistent, disagreeing and future source clocks;
- label earlier than analysis but actual receipt later than analysis;
- all revisions retained with rank monotonic in the label clock;
- equal source instants for competing publications;
- provisional permission and amended/D+6 quality refusals.

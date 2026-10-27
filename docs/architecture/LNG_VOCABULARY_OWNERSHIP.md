# LNG Vocabulary Ownership

Status: reviewed architecture decision, implemented 2026-10-27.

This note records why the LNG vocabularies have two owners and where each enum
must live. It is the doc decision referenced by
[tests/contract/test_domain_enum_ontology_gate.py](../../tests/contract/test_domain_enum_ontology_gate.py)
and [tests/contract/test_lng_vocabulary_ownership.py](../../tests/contract/test_lng_vocabulary_ownership.py).

## Decision

An independent full contract run found new LNG string enums outside the
executable ontology. The review rejected a blanket allowlist entry: the enums
are not one kind of vocabulary, so a single exemption would hide both semantic
drift and ordinary reference-contract control codes. Ownership is therefore
split by meaning.

### Canonical ontology semantics

These four are gas/energy semantics and have one canonical definition in
[src/eurogas_nexus/domain/ontology/vocabulary.py](../../src/eurogas_nexus/domain/ontology/vocabulary.py):

| Enum | Preserved public import path | Semantic reason |
| --- | --- | --- |
| `LngEnergyStageKind` | `domain/research/lng_energy_balance.py` | Names the physical/commercial stage of a cargo energy chain. |
| `LngDownstreamChargeBasis` | `domain/research/lng_cargo_economics.py` | Declares whether a charge is invoiced cash, in-kind or unknown; it governs whether energy may be monetized. |
| `QuantityBasis` | `domain/route_cost/lng_terminal_reference.py` | Names liquid, actual-gas, normal-gas, energy, duration, tank and money measurement bases. |
| `FactParameter` | `domain/route_cost/lng_terminal_reference.py` | Names terminal facts whose meaning depends on a compatible measurement basis. |

The member names and exact value strings are unchanged. The definitions exist
once; the original modules import and re-export the same class objects, so
`from ...lng_energy_balance import LngEnergyStageKind` and the equivalent
imports from the other two modules keep returning the canonical class. There is
no shadow class and no duplicated enum body.

### Reference-contract control codes

These four stay owned by
[src/eurogas_nexus/domain/route_cost/lng_terminal_reference.py](../../src/eurogas_nexus/domain/route_cost/lng_terminal_reference.py):

| Enum | Why it is not ontology semantics |
| --- | --- |
| `FactReviewStatus` | Candidate/reviewed review lifecycle of one reference fact. |
| `LngFactLookupStatus` | Explicit lookup/selection outcomes, including ambiguity and unknown applicability. |
| `LngReferenceErrorCode` | Stable refusal codes of the local reference contract. |
| `SourceChangeStatus` | Byte-comparison result for a captured source; never an automatic replacement. |

Each is recorded individually in the ontology gate. The gate's allowlist must
not gain `LngEnergyStageKind`, `LngDownstreamChargeBasis`, `QuantityBasis` or
`FactParameter`: those belong in the canonical ontology and would fail the
review intent if exempted locally.

## Compatibility

- Existing import paths, module-level `__all__` entries, API/SDK serialization
  and callers remain compatible because the original modules still expose the
  same names and class objects.
- Model version strings, dataclass field order, formulas, warning strings,
  refusal codes and result values are unchanged.
- The only metadata change is that a moved enum's `__module__` now names the
  canonical vocabulary module. That is the intended ownership record, not an
  API value change.
- No public source is activated, no database or grant is touched and no new
  capability, service or page is introduced.

## Preserved measurement boundary

The review specifically protects these semantics:

- physical loss, in-kind consumed energy and total reduction remain separate;
  legacy `energy_loss_mwh` is still purchased minus delivered total reduction,
  never physical loss alone;
- consumed energy and physical loss are still not monetized;
- `IN_KIND` and `UNKNOWN` downstream charge bases are still not cash expenses;
  only `INVOICED_CASH` can become a cash leg;
- liquid LNG m3/h, actual-gas m3/h, normal-gas Nm3/h, MWh/h and GWh/day remain
  distinct bases with no conversion between them;
- terminal parameter-to-basis compatibility and unit matching are unchanged.

## Guards

- The ontology gate scans for unreviewed domain `StrEnum` definitions and
  records only those four LNG control codes; the semantic enums are absent from
  that allowlist because they live in the canonical vocabulary.
- The ownership test checks class identity, member names/values, exact string
  values, control-code ownership and (by AST inspection) that the origin
  modules do not redefine the semantic enums.
- The same test adds focused regressions for the new energy balance, the
  terminal-reference manifest/lookup/source comparison contract and the
  economics-only path, including separate consumed/physical-loss totals and the
  in-kind refusal.

## Change rule

A future semantic enum goes to `domain/ontology/vocabulary.py` and is
re-exported by its original module. A future reference-contract control code
stays with its contract and needs a precise, explained gate entry plus an update
to this decision. Blanket allowlisting, duplicated enum bodies and broadening
the moved set without review are not accepted.

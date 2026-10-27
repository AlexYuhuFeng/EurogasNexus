# LNG Terminal Reference Contract

Status: **bounded offline contract implemented; committed reference data empty**.
Implementation: `src/eurogas_nexus/domain/route_cost/lng_terminal_reference.py`.
Offline comparison CLI: `scripts/ops/compare_lng_terminal_reference.py`.
Tests: `tests/unit/test_lng_terminal_reference.py`.
Committed manifest: `data/reference/lng_terminal_reference_manifest.json`.

This is static informational reference governance. It is not terminal access, a
booking, a slot, a capacity right, a tariff entitlement, technical availability,
nomination, trade execution, settlement or a new service. Backend numerical and
entitlement authority remains unchanged. A reviewed reference fact is evidence for a
human workflow; it is not a readiness grant and does not become an automatic model
input.

## 1. Versioned manifest

The committed manifest is intentionally empty:

```json
{
  "schema_version": "eurogas.lng-terminal-reference/1",
  "model_version": "lng-terminal-reference-model/1",
  "notes": "Empty informational reference manifest. ...",
  "sources": [],
  "facts": []
}
```

The two version fields are required `Literal` values in the frozen Pydantic model.
`notes` is required and non-blank. Unknown fields are forbidden at every level.
Sources and facts are tuples in memory, so the loaded manifest and its records cannot
be edited in place through normal attribute or sequence assignment.

The current research document,
`docs/data/LNG_TERMINAL_RESEARCH_CANDIDATES_20261027.md`, remains the authoritative
source evidence for a later, separately reviewed promotion. This bounded task does
not restore an earlier cloud manifest, transcribe candidates into the committed file,
or claim that any operator page is currently applicable. The empty committed manifest
is deliberate.

## 2. Source record

Each source carries:

| Field | Requirement |
| --- | --- |
| `source_id` | Stable identifier, unique within the manifest. |
| `official_url` | HTTPS URL with no userinfo credentials, query string or fragment. The validator enforces this syntax; it does not establish that a page is official. |
| `operator` | Non-blank organisation name. |
| `document_title` | Non-blank document/page title. |
| `publication_version` | Non-blank publication version string; `UNDATED_PAGE` is allowed when no better version exists. |
| `captured_sha256` | Exactly 64 lowercase hexadecimal characters describing the captured bytes. |
| `retrieved_at_utc` | Explicit, timezone-aware UTC retrieval instant. It is not a publication or effective date. |
| `published_date` | Optional calendar date; `None` means unknown, not the retrieval date. |
| `applicability_notes` | Explicit non-blank scope note. |

URL validation rejects credentials, all query strings, fragments, non-HTTPS schemes
and missing hosts. That is a credential/secret-query control, not provenance proof.
A hash, URL or page title does not prove authenticity, authority, entitlement or
continuing applicability.

## 3. Fact record

Each fact carries:

| Field | Requirement |
| --- | --- |
| `fact_id` | Stable identifier, unique within the manifest. |
| `terminal_id` | Stable terminal identifier. |
| `parameter` | One supported terminal-fact parameter. |
| `value` | Exact non-negative decimal **string**. Floats, integers, booleans, `NaN`, infinities, exponent notation, leading zeros, signs and oversized coefficients are refused. Trailing zeros are preserved. |
| `original_value_text` | Original published text/value rendering, non-blank. No separator interpretation is performed. |
| `original_unit` | Original unit text, non-blank and checked against the declared basis. |
| `quantity_basis` | One explicit measurement basis. |
| `quotation` | Short source excerpt, at most 25 words per source **in total across the manifest**. |
| `source_id` | Must resolve to a source in the same manifest. |
| `applicability_notes` | Explicit non-blank scope note. |
| `effective_from` / `effective_to` | Optional calendar dates. Unknown is `None`; it is never filled from retrieval time. |
| `review_status` | `CANDIDATE` or `REVIEWED`. |
| `reviewed_by` / `reviewed_at` | Required for `REVIEWED`; forbidden for `CANDIDATE`. `reviewed_at` is aware UTC and cannot precede the source retrieval. |

Date validation refuses `effective_from > effective_to` and refuses an
`effective_to` without an `effective_from`. A known `effective_from` with
`effective_to = None` is treated as open-ended; an unknown `effective_from` stays
unknown. Duplicate source IDs, duplicate fact IDs, dangling source references,
oversized decimal coefficients and over-limit quotations are refused.

The decimal limit is 18 integer digits and 18 fractional digits. The contract stores
the submitted string; it does not convert it to `float` or `Decimal` for business use.
No arithmetic, energy/volume conversion, FX conversion, hours/day conversion or
capacity-to-rights conversion is performed.

## 4. Distinct bases and compatible parameters

`QuantityBasis` deliberately separates:

- liquid LNG `m3/h`;
- actual gas `m3/h`;
- normal gas `Nm3/h`;
- energy `MWh/h`;
- energy `GWh/d`;
- duration `hours`;
- percent of tank capacity per day;
- percent of cargo energy;
- money per energy.

Each parameter accepts only a narrow set of bases:

| Parameter family | Allowed bases |
| --- | --- |
| `VESSEL_UNLOADING_MAX_RATE`, `VESSEL_UNLOADING_RATE`, `UNLOADING_RATE` | liquid LNG `m3/h` only |
| `SENDOUT_CAPACITY`, `MINIMUM_SENDOUT_RATE` | actual gas `m3/h`, normal gas `Nm3/h`, `MWh/h`, `GWh/d` |
| `REGASIFICATION_CAPACITY` | `MWh/h`, `GWh/d` |
| `TANK_EVAPORATION_RATE`, `EVAPORATION_RATE` | percent of tank capacity per day only |
| `CARGO_ENERGY_LOSS_RATE`, `RETAINED_FUEL_RATE` | percent of cargo energy only |
| `VESSEL_DISCHARGE_DURATION` | hours only |
| `TERMINAL_FEE` | money per energy, with an explicit currency unit such as `EUR/MWh` |

The unit must also agree with the basis. In particular:

- Gate-style tank-capacity evaporation cannot be represented as cargo-energy loss or
  a retained-fuel rate without a separate reviewed fact using the cargo-energy basis.
- Vessel-unloading liquid volume cannot be represented as sendout energy or normal-gas
  sendout.
- A fee cannot lose its currency. No fee, FX or unit conversion is supplied.
- Grain's distinct `645 GWh/d` and `654 GWh/d` claims remain separate facts if they are
  ever promoted; they are never averaged or silently overwritten.

## 5. Reviewed lookup

`lookup_reviewed_lng_terminal_fact()` requires `terminal_id`, `parameter`,
`quantity_basis` and `scenario_date`. Candidate facts are excluded unconditionally.
The result is always explicit:

| Status | Meaning |
| --- | --- |
| `REVIEWED_FACT_FOUND` | Exactly one reviewed fact has a known interval covering the scenario date. |
| `NO_REVIEWED_FACT` | No reviewed fact matches the exact terminal, parameter and basis. |
| `NO_APPLICABLE_REVIEWED_FACT` | Reviewed matches exist, but none has a known interval covering the date. |
| `APPLICABILITY_UNKNOWN` | At least one reviewed match has an unknown effective start; no fact is selected. |
| `AMBIGUOUS_REVIEWED_FACTS` | More than one reviewed match is applicable on the date; no fact is selected. |

Unknown applicability is never replaced by the retrieval timestamp. When ambiguity
exists, `selected_fact` is `None`; the caller receives the matching reviewed facts and
their IDs rather than an average, a latest-wins pick or an automatic replacement.

`inspect_candidate_lng_terminal_facts()` is a separate informational path. It returns
only `CANDIDATE` facts and never marks them reviewed, makes them scenario-eligible or
grants readiness. A warning discloses when candidates were excluded from a reviewed
lookup.

## 6. Offline source-change comparison

The comparison function and CLI operate on local bytes only. There is no network,
database, source-enable, grant, settings or manifest-write path. Required arguments:

```text
--manifest PATH
--source-id ID
--candidate-file PATH
--retrieved-at ISO_8601_UTC
```

Example:

```powershell
.venv/Scripts/python.exe scripts/ops/compare_lng_terminal_reference.py `
  --manifest data/reference/lng_terminal_reference_manifest.json `
  --source-id synthetic-source-id `
  --candidate-file .local-runtime/candidate.bin `
  --retrieved-at 2026-10-27T12:00:00Z
```

The current committed manifest has no sources, so this example requires a synthetic
test manifest or a later reviewed source addition.

Input policy:

- the candidate file is bounded to **10 MiB** and checked before and after reading;
- an empty candidate payload is refused; zero bytes cannot prove source absence;
- a naive or non-UTC `--retrieved-at` is refused;
- an unknown `source_id` is refused;
- malformed/oversized/non-UTF-8 manifests, byte-order marks and invalid JSON are
  refused;
- the command prints JSON only and never prints a traceback or overwrites a file.

Exit codes:

| Code | Meaning |
| --- | --- |
| `0` | Candidate bytes match the preserved hash; status `UNCHANGED`. |
| `2` | Bytes changed; status `REVIEW_REQUIRED`, a change candidate for human review. |
| `1` | Error/refusal, including malformed input, unknown source, empty/oversized payload or invalid time. |

A changed hash returns `before_sha256`, `after_sha256`, source identity, candidate
retrieval time, every affected fact ID and warnings. `auto_replace` is always `false`
and `semantic_change_established` is always `false`. A byte change can be navigation,
markup, analytics or other non-semantic drift; it only signals that review is needed.
The manifest is not mutated and no fact becomes reviewed.

Unchanged bytes do not prove authority, authenticity or current applicability either.
Source hashes alone prove byte identity relative to the preserved capture, nothing
more.

## 7. Tests and evidence boundary

`tests/unit/test_lng_terminal_reference.py` uses clearly synthetic source and fact
fixtures only. It covers version roundtrip, immutability, exact-decimal refusal and
trailing-zero preservation, provenance/reviewer/date validation, duplicate and
dangling references, unit/basis separation, candidate exclusion, unknown
applicability, reviewed ambiguity, unchanged/changed hashes, non-mutation, CLI codes,
bounded reads, malformed inputs and naive-time refusal. These fixtures are not in the
committed manifest and are not operator evidence.

Passing synthetic tests does not establish commercial readiness, source authenticity,
entitlement, operator approval or terminal availability.

## 8. Remaining integration and evidence gaps

- **Data population:** the committed manifest is empty. Candidate facts still need
  exact structural promotion, per-fact source-section evidence, effective dates where
  officially established, reviewer attribution and a separate approval step.
- **Grain ambiguity:** the distinct `645 GWh/d` and `654 GWh/d` claims remain unresolved;
  the contract preserves both rather than selecting one.
- **Gate denominators:** tank-capacity evaporation is not a cargo-energy loss,
  retained-fuel rate, invoice deduction or irrecoverable energy loss. Those remain
  separate missing facts.
- **Rights and technical limits:** terminal access, booking, slot/storage availability,
  sendout rights, fuel retention and network entry capacity remain independent
  missing inputs. This contract grants none of them.
- **Source ingestion:** no automatic operator-page capture, scheduling, archival,
  extraction or promotion is implemented. The CLI is offline inspection only and the
  manifest loader reads explicit local files.
- **UI/API integration:** no API route, UI surface or scenario adoption was added.
  Treating reviewed informational facts as model inputs requires a separate bounded
  integration and entitlement review.
- **Coverage:** the four researched facilities are not complete European terminal
  coverage, and the current candidate document is not itself a versioned manifest.
- **Authenticity:** HTTPS and SHA-256 checks do not authenticate an operator, establish
  redistribution rights or prove that a preserved page remains current.

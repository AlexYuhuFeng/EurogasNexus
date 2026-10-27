# LNG Terminal Reference Contract

Status: **bounded offline contract implemented; five captured sources and seven CANDIDATE facts committed; reviewed fact set empty**.
Implementation: `src/eurogas_nexus/domain/route_cost/lng_terminal_reference.py`.
Offline comparison CLI: `scripts/ops/compare_lng_terminal_reference.py`.
Tests: `tests/unit/test_lng_terminal_reference.py`.
Committed manifest: `data/reference/lng_terminal_reference_manifest.json`.

This is static informational reference governance. It is not terminal access, a
booking, a slot, a capacity right, a tariff entitlement, technical availability,
nomination, trade execution, settlement or a new service. Backend numerical and
entitlement authority remains unchanged. A reviewed reference fact is evidence for a
human workflow; it is not a readiness grant and does not become an automatic model
input. The committed records are CANDIDATE facts, so they are not scenario-eligible
at all yet.

## 1. Versioned manifest

The committed manifest contains five captured official-publication source records and
seven CANDIDATE fact records. It contains no REVIEWED fact, no reviewer attribution
and no effective interval:

```json
{
  "schema_version": "eurogas.lng-terminal-reference/1",
  "model_version": "lng-terminal-reference-model/1",
  "sources": ["... five captured source records ..."],
  "facts": ["... seven CANDIDATE records ..."]
}
```

The two version fields are required `Literal` values in the frozen Pydantic model.
`notes` is required and non-blank. Unknown fields are forbidden at every level.
Sources and facts are tuples in memory, so the loaded manifest and its records cannot
be edited in place through normal attribute or sequence assignment.

`terminal_id` values (`gate-terminal`, `dunkerque-lng`, `grain-lng`,
`south-hook-lng`) are stable identifiers in this internal reference namespace. They
are not GIE, provider, operator-system or market-participant identifiers, and no
mapping to an operational ID is proven or asserted. `source_id` values identify
captured publications inside this manifest.

The research note,
`docs/data/LNG_TERMINAL_RESEARCH_CANDIDATES_20261027.md`, remains the prose evidence
summary. The structured manifest records the same five captured publications and
seven claims with exact provenance. Neither document establishes current
applicability, authenticity, redistribution rights or commercial availability.

## 2. Source record

Each source carries:

| Field | Requirement |
| --- | --- |
| `source_id` | Stable identifier, unique within the manifest. |
| `official_url` | HTTPS URL with no userinfo credentials, query string or fragment. The validator enforces this syntax; it does not establish that a page is official. |
| `operator` | Non-blank organisation name. |
| `document_title` | Non-blank document/page title. |
| `publication_version` | Non-blank publication version string; `UNDATED_PAGE` is used where no better version exists. |
| `captured_sha256` | Exactly 64 lowercase hexadecimal characters describing the captured bytes. |
| `retrieved_at_utc` | Explicit, timezone-aware UTC retrieval instant. It is not a publication or effective date. |
| `published_date` | Optional calendar date; `None` means unknown, not the retrieval date. |
| `applicability_notes` | Explicit non-blank scope note. |

The five committed sources use these recorded URLs, hashes and retrieval instants:

| Source ID | Official URL | Captured SHA-256 | Retrieved (UTC) |
| --- | --- | --- | --- |
| `gate-operational` | `https://www.gateterminal.com/en/commercial/operational-data/` | `222f6d89f422fd8f33fbd4959461fa4b49959be744d2850b55dfb36fd860f205` | `2026-10-27T14:13:49.470061+00:00` |
| `gate-faq` | `https://www.gateterminal.com/en/gate-terminal/faq/` | `e7bcff83d859b7f9025450d11ea6e6f48c58f33abea78abcc5ecc657f681752f` | `2026-10-27T14:14:45.979968+00:00` |
| `dunkerque-infrastructure` | `https://www.fluxys.com/en/about-us/dunkerque-lng/infrastructure` | `aca9b21f8bb8cb705481e2016e910f2ceea411000fa3bf61adb16832e64a82ad` | `2026-10-27T14:13:49.505751+00:00` |
| `grain-operational` | `https://www.grainlng.com/operational-information` | `9243ff6f925f5ae2e5a3dcda66d309ec6a6cd7fc3c83efe5c43614e4b64dfc5e` | `2026-10-27T14:13:49.931386+00:00` |
| `southhook-operations` | `https://www.southhooklng.com/operations/what-we-do/` | `792b29e57c4f306c177ce7f4796171e9f4341085b2107249a8fe18c669bfa22c` | `2026-10-27T14:13:49.640660+00:00` |

All five are undated pages in the reference record: `published_date` is `None` and
`publication_version` is `UNDATED_PAGE`. No publication date, official revision or
effective date is invented from page metadata, retrieval time or a content hash.

URL validation rejects credentials, all query strings, fragments, non-HTTPS schemes
and missing hosts. That is a credential/secret-query control, not provenance proof.
A hash, URL or page title does not prove authenticity, authority, entitlement,
redistribution rights or continuing applicability. The hashes identify the preserved
captured bytes only.

## 3. Fact record

Each fact carries:

| Field | Requirement |
| --- | --- |
| `fact_id` | Stable identifier, unique within the manifest. |
| `terminal_id` | Stable terminal identifier in the internal reference namespace. |
| `parameter` | One supported terminal-fact parameter. |
| `value` | Exact non-negative decimal coefficient **string**, without grouping separators. Floats, integers, booleans, `NaN`, infinities, exponent notation, leading zeros, signs and oversized coefficients are refused. Trailing zeros are preserved. |
| `original_value_text` | Original published text/value rendering, non-blank. This preserves literal notation such as Gate's `12.500` and `139.000` or Dunkerque's `14,000`. |
| `original_unit` | Original unit text, non-blank and checked against the declared basis. |
| `quantity_basis` | One explicit measurement basis. It is never inferred from the unit alone. |
| `quotation` | Short source excerpt, at most 25 words per source **in total across the manifest**. |
| `source_id` | Must resolve to a source in the same manifest. |
| `applicability_notes` | Explicit non-blank scope note, including the source section where relevant. |
| `effective_from` / `effective_to` | Optional calendar dates. Unknown is `None`; it is never filled from retrieval time. |
| `review_status` | `CANDIDATE` or `REVIEWED`. |
| `reviewed_by` / `reviewed_at` | Required for `REVIEWED`; forbidden for `CANDIDATE`. `reviewed_at` is aware UTC and cannot precede the source retrieval. |

The committed facts are all `CANDIDATE`, with no `reviewed_by`, no `reviewed_at` and
no effective dates. The `value` / `original_value_text` split preserves both the
decimal quantity and the publication's literal numeric notation. For example, the
Gate record stores `value = "12500"` and `original_value_text = "12.500 m3/h of LNG"`;
the Gate minimum-sendout record stores `"139000"` and `"139.000 m3(n)/h"`. The
Dunkerque record stores `"14000"` and `"14,000 m³ per hour"`. No arithmetic, unit
conversion, separator rewriting in `original_value_text` or business use as
`Decimal`/`float` is performed.

Date validation refuses `effective_from > effective_to` and refuses an
`effective_to` without an `effective_from`. A known `effective_from` with
`effective_to = None` is treated as open-ended; an unknown `effective_from` stays
unknown. Duplicate source IDs, duplicate fact IDs, dangling source references,
oversized decimal coefficients and over-limit quotations are refused.

The decimal limit is 18 integer digits and 18 fractional digits. No arithmetic,
energy/volume conversion, FX conversion, hours/day conversion or capacity-to-rights
conversion is performed.

## 4. Committed candidate claims

| Fact ID | Terminal | Parameter and basis | Value | Original text | Source section |
| --- | --- | --- | --- | --- | --- |
| `gate-vessel-unloading-max` | `gate-terminal` | `VESSEL_UNLOADING_MAX_RATE`, liquid LNG `m3/h` | `12500` | `12.500 m3/h of LNG` | Operational data, bullet list |
| `gate-minimum-sendout` | `gate-terminal` | `MINIMUM_SENDOUT_RATE`, normal gas `Nm3/h` | `139000` | `139.000 m3(n)/h` | Operational data, bullet list |
| `gate-tank-evaporation` | `gate-terminal` | `TANK_EVAPORATION_RATE`, tank capacity percent/day | `0.07` | `approximately 0.07% of the tank capacity per day` | FAQ, "How is LNG stored?" |
| `dunkerque-vessel-unloading-max` | `dunkerque-lng` | `VESSEL_UNLOADING_MAX_RATE`, liquid LNG `m3/h` | `14000` | `14,000 m³ per hour` | Infrastructure, facilities and installations |
| `grain-regasification-equipment-645` | `grain-lng` | `REGASIFICATION_CAPACITY`, `GWh/d` | `645` | `645 GWh/d` | Terminal characteristics, physical characteristics, re-gasification equipment |
| `grain-primary-capacity-654` | `grain-lng` | `REGASIFICATION_CAPACITY`, `GWh/d` | `654` | `circa 654 GWh/d` | Terminal characteristics, capacities, primary market |
| `southhook-vessel-discharge-duration` | `south-hook-lng` | `VESSEL_DISCHARGE_DURATION`, hours | `24` | `up to 24 hours` | What We Do, jetty section |

These are informational claims, not economic inputs:

- Gate's maximum vessel unloading is a liquid-LNG volumetric rate. It is not sendout,
  gas volume, energy throughput, a guaranteed average rate or a booked right.
- Gate's minimum sendout is a normal-gas volumetric rate. The same publication says
  additional services may allow lower flow rates; no maximum sendout, MWh/h value or
  current availability is inferred.
- Gate's `0.07%` uses tank capacity as its denominator. It is not
  `CARGO_ENERGY_PERCENT`, a retained-fuel percentage, an invoice deduction, a
  physical-loss quantity or irrevocable cargo-energy loss. No fuel-retention or
  gas-in-kind fact is supplied.
- Dunkerque's `14,000 m³ per hour` is jetty unloading in an LNG vessel context. The
  separate `8,800 m³ per hour` reloading limit and sendout are not substituted for
  it. The literal unit `m³ per hour` is accepted as a normalized variant of the
  explicitly declared `LIQUID_LNG_M3_PER_HOUR` basis; the basis is declared, not
  inferred from the unit alone.
- Grain's `645 GWh/d` equipment specification and `circa 654 GWh/d` primary-market
  capacity are two distinct claims with different section scopes. They are never
  averaged, overwritten or silently selected. The later primary-market wording does
  not by itself establish precedence.
- South Hook's "up to 24 hours" is a descriptive discharge duration. It is not a
  contractual guaranteed turnaround, slot duration, constant unloading rate or
  universal vessel operation. Mooring and other operations are not inferred.

No fuel retention, monetary terminal fee, availability, booked right, conversion
factor, current sendout or maximum sendout is manufactured from these facts.

## 5. Distinct bases and compatible parameters

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
- Grain's distinct `645 GWh/d` and `654 GWh/d` claims remain separate; they are never
  averaged or silently overwritten.

## 6. Reviewed lookup

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

Because the committed reviewed-fact set is empty, every lookup for one of the seven
committed candidate facts returns `NO_REVIEWED_FACT` for any scenario date, even when
the terminal, parameter and basis match exactly. The warning
`CANDIDATE_FACTS_EXCLUDED_FROM_REVIEWED_SELECTION` discloses the exclusion.
`inspect_candidate_lng_terminal_facts()` is a separate informational path. It returns
only `CANDIDATE` facts and never marks them reviewed, makes them scenario-eligible or
grants readiness.

## 7. Offline source-change comparison

The comparison function and CLI operate on local bytes only. There is no network,
database, source-enable, grant, settings or manifest-write path. Required arguments:

```text
--manifest PATH
--source-id ID
--candidate-file PATH
--retrieved-at ISO_8601_UTC
```

Example against a committed source:

```powershell
.venv/Scripts/python.exe scripts/ops/compare_lng_terminal_reference.py `
  --manifest data/reference/lng_terminal_reference_manifest.json `
  --source-id gate-operational `
  --candidate-file .local-runtime/candidate.bin `
  --retrieved-at 2026-10-27T12:00:00Z
```

The candidate file is caller-supplied local evidence. The command does not fetch,
recapture or replace an operator page.

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
retrieval time, every affected fact ID and warnings. For example, a change in
`gate-operational` lists `gate-minimum-sendout` and `gate-vessel-unloading-max`; a
change in `grain-operational` lists `grain-primary-capacity-654` and
`grain-regasification-equipment-645`. `auto_replace` is always `false` and
`semantic_change_established` is always `false`. A byte change can be navigation,
markup, analytics or other non-semantic drift; it only signals that review is needed.
The manifest is not mutated and no fact becomes reviewed.

Unchanged bytes do not prove authority, authenticity or current applicability either.
Source hashes alone prove byte identity relative to the preserved capture, nothing
more.

## 8. Tests and evidence boundary

`tests/unit/test_lng_terminal_reference.py` keeps its clearly synthetic fixtures for
validation edge cases. Those synthetic facts are never in the committed manifest and
are not operator evidence.

Separate tests load the actual committed manifest and assert:

- five sources and seven facts, with the exact recorded URLs, SHA-256 values and UTC
  retrieval instants;
- exact fact values, original value texts, units, bases, quotations and source
  references;
- every fact is `CANDIDATE`, with no reviewer metadata and no effective interval;
- Gate tank-capacity evaporation remains on the tank-percent basis and is not cargo
  energy;
- Grain's `645` and `654` claims remain distinct;
- candidate-only inspection works while every reviewed lookup for a committed
  candidate returns `NO_REVIEWED_FACT`;
- an offline byte change reports the correct affected fact IDs, cannot auto-replace
  and leaves the manifest byte-identical.

Passing these tests does not establish commercial readiness, source authenticity,
entitlement, operator approval, effective dates or terminal availability.

## 9. Remaining integration and evidence gaps

- **Effective dates:** all five pages are treated as undated. No effective start or
  end is established, so no candidate can become scenario-eligible by date.
- **Fees and fuel:** terminal fees, fuel retention, invoiced gas-in-kind, physical
  loss and BOG handling remain separate missing facts. No zero, generic industry
  percentage, currency or tariff is supplied.
- **Rights and technical limits:** terminal access, booking, berthing slots, storage
  and sendout availability, network entry capacity and current technical limits
  remain independent missing inputs. The candidates grant none of them.
- **Operational identifiers:** the internal terminal IDs have no proven mapping to
  GIE, operator-system, provider or market-participant IDs.
- **Grain ambiguity:** `645 GWh/d` and `654 GWh/d` remain distinct, unresolved claims.
  Dated operator contracts or a formal clarification are required to establish scope
  and precedence.
- **Source ingestion:** no automatic operator-page capture, scheduling, archival,
  extraction or promotion is implemented. The CLI is offline inspection only and the
  manifest loader reads explicit local files.
- **API/UI integration:** no API route, UI surface, scenario adoption or economics
  input was added. Treating any reviewed informational fact as a model input requires
  a separate bounded integration and entitlement review.
- **Coverage:** the five captures cover four facilities and are not complete European
  terminal coverage.
- **Authenticity and rights:** HTTPS and SHA-256 checks do not authenticate an
  operator, establish redistribution rights or prove that a preserved page remains
  current.

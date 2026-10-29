# RFC-0005: ENTSOG native rates without assumed calorific conversion

Status: Accepted architecture for staged implementation,2026-10-29.
Owner/reviewer: root architect and integrator under the Autonomous Execution Policy;
DeepSeek performs bounded implementation. This acceptance is not delivery evidence.

## Problem and reviewed facts

`ingestion/public_sources.py` divides provider kWh/day by10550000 and otherwise
labels arbitrary native units as mcm/day. The flow/capacity ORM volume columns are
non-null; append-or-verify persistence refuses changed values at an existing key.
The physical API, SDK and shared Capacity Workspace assume numeric mcm/day. Agent
DB reads bypass the physical API. Legacy `original_value` is a binary Float, not
an exact provider token. `EntsogPage.raw_body` already preserves exact raw JSON;
its normal payload parser currently loses numeric lexemes. These facts require
coordinated storage/read/ingestion/client changes, not a replacement CV constant.

## Decision

1. Use the existing flow/capacity tables. Add nullable `normalizer_version` and
   `native_rate_json`; permit null volume only on a supported native record with
   a native payload. Legacy rows retain values, identities and timestamps.
   JSON stores original value/unit strings, exact canonical rate strings,
   dimension/basis/version. Application validation MUST recompute and compare
   the representation through `parse_entsog_native_rate`, never trust arbitrary
   persisted JSON or convert a legacy Float into apparent exact source text.
2. Native ingestion reparses archived raw JSON with numeric callbacks that
   preserve original number tokens as strings, without changing protocol paging
   validation or the existing default payload. Exact raw-page lineage and actual
   receipt remain authoritative. Zero is a value; NA/missing stays unavailable.
   Unsupported units and non-string numeric inputs are typed refusals.
3. New normalized representations have a versioned identity namespace and retain
   the original provider record id. This distinguishes normalization semantics,
   not a provider revision. Existing rows MUST NOT be overwritten/backfilled.
   Within the new namespace, changed semantic content still refuses atomically;
   this RFC does not invent provider revision history or authorize overwrites.
   Repeated captures preserve first receipt. Legacy and native copies MUST NOT
   be summed or offered as two independent observations of the same event.
4. Existing `/api/physical/flows` and `/api/physical/capacity` default contracts
   remain volume-only with non-null numeric volume. Add optional query parameter
   `quantity_basis=native` for a distinct typed native representation on those
   paths; `quantity_basis=volume` is the default. Native responses expose exact
   rate strings with explicit quantity kind/unit/basis and provenance references.
   This parameter is additive; no new page or new endpoint is required. Legacy
   ENTSOG rows with unverified normalization MUST be excluded from business
   quantity reads, with a visible warning, while remaining archived in storage.
   Native energy rows have no volume, and cannot enter a volume-only response.
5. Agent/analysis DB bridges MUST apply the same quantity admission. SDK supplies
   separate typed native methods; existing SDK methods retain volume DTOs.
   Shared Web/desktop capacity consumption must compare matching energy rates
   or matching volume rates, never mix dimensions or invent a CV. Missing or
   incompatible comparison remains explicit; exact backend strings are retained,
   and approximate display ratios never become authoritative economic evidence.
6. Canonical conversions stay within dimension: MWh to kWh and m3 to mcm are
   exact powers of ten. Hourly-to-daily rate scaling24 is not integration over
   a23/25-hour gas day. No energy/volume conversion is implemented in this phase;
   a future evidenced CV needs an explicit time/location/method contract.
7. Authentication, commercial and row entitlement remain unchanged. Native mode
   grants no wider access. No execution, nomination, settlement, new datastore,
   credential or source activation is introduced.

## Staged compatibility and rollback

A. Add the schema/ORM contract and strict native payload projection; preserve all
legacy columns. A downgrade refuses any native payload/version or null-volume
row rather than destroying evidence. Verify SQLite and real PostgreSQL0043 to0044.
B. Update default/opt-in physical reads and agent admission before enabling native
normalization. API evolution declaration and negative entitlement tests accompany
this stage. Default legacy numeric DTOs remain unchanged.
C. Connect raw-lexeme parsing, native normalization and immutable persistence;
remove the fixed CV. Verify genuine provider capture, raw hashes, replay/conflict,
explicit receipts, dimension separation and no double counting.
D. Adopt native SDK/shared client capacity comparisons and source evidence views.
Update unit semantics in data products/glossary where needed. Test mixed units,
missing sides, paired periods/products and consumer result changes.
E. Same-commit hosted tests plus PostgreSQL/provider and installed SDK/native
checks establish delivery evidence. Earlier parser-only checks do not close this
migration. Keep unrelated LNG/other provider volume contracts unchanged.

## Alternatives and non-goals

Reject a replacement CV, zero placeholders, dropping real energy data as the final
solution, a second datastore, in-place legacy rewrites, and making all existing
volume fields nullable without a client migration. A separate native endpoint
would duplicate the same resource/auth boundary; an explicit opt-in representation
preserves existing paths while giving the SDK an unambiguous result type.
Historical exact-value recovery and provider revision history remain separate
work; legacy Floats cannot prove original tokens. Production source activation
and all-source/customer acceptance are not implied by this decision.

## Required evidence

- Additive upgrade preserves legacy rows; downgrade refuses native evidence.
- Exact payload consistency, unsafe legacy rejection, no CV or unknown-unit fallthrough.
- Existing numeric clients remain valid; opt-in native SDK/Web reads preserve dimensions.
- Real archived numeric tokens survive normalization and append/query/replay.
- Multi-row conflict is atomic; first receipt survives recapture.
- Unauthorized reads remain denied and row filters apply to both representations.
- Matching native flow/capacity changes the displayed comparison; incompatible
  dimensions or periods do not generate utilization or apparent physical headroom.

Implementation records are in the execution checkpoint; this RFC does not assert
that any stage is already complete. Root reviews each bounded task and runs tests.

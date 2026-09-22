# Trading-house commercial acceptance audit

Date: 2026-09-22. Baseline: `e911fae` (matched origin/main at audit start).
Disposition: **NOT APPROVED FOR CUSTOMER PRODUCTION**. This is an engineering
audit and target amendment, not legal advice, certification or vendor parity.

## Scope and evidence

Reviewed V2 entrypoint/checkpoint, product experience, identity, data platform,
operations/NFR targets, release workflow, deployment packagers, promotion gate,
MCP identity construction, and current repository visibility. This is not a
completed penetration test, full source audit or whole-product UAT. The repository
is public. Recent successful release runs inspected were for older SHAs, not
evidence that the current product has passed customer acceptance.

The in-app browser reached the current localhost sign-in screen. The previous
test credentials were rejected. Authentication was not bypassed and accounts
were not provisioned. Therefore authenticated layouts, interaction efficiency,
screen-reader behavior, decision workflows and native installation remain
**unverified in this audit**. Previous screenshots are not substituted for new
evidence. The user has been asked for current test access.

## Findings, ordered by release risk

| ID | Priority | Evidence / finding | Disposition |
| --- | --- | --- | --- |
| CA-01 | P1 | `validate_stable_release.evaluate_gates` matched only the requested channel or `all`; stable skipped gates G1/G11 marked `rc`. | Fixed channel inheritance; regression proves missing RC evidence blocks stable. |
| CA-02 | P1 | `load_evidence` accepts a status/detail without checking tested SHA, artifact digest, issuer, age or environment. Older or unrelated PASS files are not distinguished. | Open: require versioned evidence envelopes, SHA/digest binding, provenance and explicit authorised external approval. Never fabricate PASS records. |
| CA-03 | P1 | `release.yml` web job builds but does not run the frontend suite. Browser acceptance exists in `ci.yml`, but release publication is not tied to that result for the same SHA. | Added frontend tests and locale-key gate before packaging. Same-SHA browser/critical workflow evidence still required. |
| CA-04 | P1 | Python, Bash and PowerShell deployment packagers recursively copy local runtime/doc trees; an incidental secret or private file can enter a customer ZIP. | Fixed by DeepSeek's bounded implementation, independently reviewed: canonical explicit allowlist, thin wrappers, fail-closed validation and actual archive tests. Ten payload files verified. |
| CA-05 | P1 | Checkpoint explicitly lists organisation/portfolio scopes as unsupported and D2/D6/D7 as decided-not-built; MCP still constructs authority from environment values. | No shared multi-organisation/desk-isolation claim. Build/test persisted service identity, elevation dual control and scope isolation, or disable affected features in customer profile. |
| CA-06 | P1 | Container acceptance inspects manifest platforms, not running service health or install/upgrade/rollback. Assembly downloads `release-*`, while image metadata is named `image-metadata`; evidence path assembly also needs end-to-end proof. | Fixed explicit metadata download and mandatory digest validation. Still open: immutable-image boot + PostgreSQL migration + authenticated smoke; prove final evidence assembly in CI. |
| CA-07 | P1 | Checkpoint says "Nothing else is outstanding" despite named implementation and release gaps; readiness report is dated September 7. | Correct checkpoint; this audit is the current commercial disposition, not historical test totals. |
| CA-08 | P2 | Public source tracks local autonomous supervisor configuration, worker prompts and orchestration scripts, including pre-existing local edits. | Remove `.automation` from tracked delivery; retain local files unchanged. Exclude Docker context and source archives. Historical Git objects/releases are not erased. |
| CA-09 | Acceptance blocker | Current approved-user access unavailable to reviewer. No current authenticated visual/interaction evidence supports an LSEG/Kpler-level quality claim. | Obtain test access; run the workflow matrix below. No cosmetic redesign based on stale screenshots. |
| CA-10 | P1 | Both Windows installer scripts fall back to a desktop `tauri.conf.json` path containing a literal tab; this config is also absent from the operator ZIP. Without `EUROGAS_NEXUS_VERSION`, even preflight cannot resolve the version. | Open: deliver explicit immutable release identity in the bundle and test extracted-bundle preflight without a source checkout. Do not claim the ZIP is installation-approved. |

## Revised product objective

Deliver a licensed, reproducible, permission-bounded European gas decision
workstation for trading-house analysts, traders and independent reviewers.
Gas remains the supported asset class; power is a future separately validated
domain. Preserve the modular monolith, PostgreSQL, FastAPI, React and thin Tauri
host. Do not add order entry, execution, nomination submission or settlement.
Compete on verified workflow quality, not the number of pages or visual imitation.

V2's context/evidence/action/decision sequence is appropriate. Its missing
commercial acceptance layer is an explicit evidence contract:

| Audience | Required acceptance exercise | Proof, not a feature claim |
| --- | --- | --- |
| Trader | Investigate hub/tenor move; compare physical route-adjusted alternatives; retain portfolio, gas day and valuation context into review. | Recorded task replay; no silent product/currency/unit mixing; explicit quote type and market/ingestion/as-of times. |
| Trader | Toggle numeric/map view and revisit after login; inspect IP, VTP, LNG, storage and pipeline evidence. | Preference retained per identity; no compulsory map; visible legend and verified/indicative classification; VTP never represented as exact physical facility. |
| Risk/reviewer | Challenge a proposed allocation and reproduce its evidence later. | Immutable input/model versions; constraints and infeasibility visible; stale/restricted inputs block inappropriate recommendations; independent decision actor and audit chain. |
| Quant | Compare strategy versions against reproducible baselines. | Point-in-time joins and revision policy, walk-forward evaluation, leakage controls, transaction/transport costs and capacity constraints; uncertainty, drawdown and out-of-sample results, not PnL alone. |
| Data scientist | Freeze a lawful training/evaluation dataset. | Source rights for view/derive/export/LLM/training, lineage, DST/gas-day test vectors, deduplication, publication lag, leakage-safe splits and dataset/model cards. Simulation excluded from live/calibration claims. |
| Operator | Install, upgrade, recover and diagnose the exact customer artifact. | Signed installer, immutable image, SBOM/notices, checksums/provenance, migration compatibility, tested rollback/restore and bounded diagnostics without secrets/licensed values. |

## HMI and UI acceptance contract

The Professional UI Constitution remains the visual authority; V2 remains the
interaction authority. Do not create another parallel design system.

1. Capture sign-in -> numeric market -> evidence Inspector -> portfolio/scenario
   -> alternatives -> review; and dataset -> backtest -> comparison -> shadow.
2. At 1440x900 and 1920x1080, in EN and Mandarin, verify one context owner, stable
   table columns/units, predictable primary actions, no hidden critical warnings,
   no overlaps, keyboard access and visible focus. Narrow layouts must preserve
   semantic reading order, not simply shrink a desktop grid.
3. Measure task completion, context re-entry, errors, action count and time with
   representative traders. Set performance targets against an agreed user/data
   workload; do not invent production SLOs from a laptop test.
4. Test loss of connection, expired session, partial entitlement, stale data,
   long sessions, concurrent changes and interrupted calculations. Preserve
   drafts appropriately; never leak the previous user's answers or selections.
5. Automated accessibility scans are necessary, not sufficient. Add keyboard,
   zoom, screen-reader and colour-independent state checks; aim for WCAG 2.2 AA
   as the product acceptance target, without claiming certification from axe.

## EU applicability and customer assurance

There is no single blanket "European commercial software release standard".
The manufacturer, deployment model, customer entity and intended use determine
legal applicability. Maintain an owner-reviewed applicability register.

- CRA: assess this distributed desktop/server product, vulnerability handling,
  support lifetime and technical documentation. Commission guidance states
  reporting obligations apply from 11 September 2026 and main obligations from
  11 December 2027. Do not equate a green build with conformity assessment.
  [Commission CRA guidance](https://digital-strategy.ec.europa.eu/en/library/commission-publishes-new-guidance-support-timely-cyber-resilience-act-implementation).
- GDPR: user identities/audit/support data require purpose, minimisation,
  retention, access, processor/subprocessor and international-transfer review.
  [Commission obligations](https://commission.europa.eu/law/law-topic/data-protection/information-business-and-organisations/obligations_en).
- DORA: assess customer status and contractual ICT-service obligations; not every
  gas trading house is a DORA financial entity.
  [EIOPA supplier-contract guidance](https://www.eiopa.europa.eu/qa-regulation/questions-and-answers-database/3501-dora-286_en).
- NIS2: assess relevant energy entities, size/national implementation and supply
  chain obligations. It is not a software product certificate.
  [Commission NIS2 overview](https://digital-strategy.ec.europa.eu/en/policies/nis2-directive).
- AI Act: classify intended use, provider/deployer roles and external models;
  do not label all trading analytics high-risk or exempt without assessment.
  [Commission classification guidance](https://digital-strategy.ec.europa.eu/en/faqs/navigating-ai-act).
- Provider rights, customer contracts, support/EOL, security incident contacts
  and applicable market-conduct obligations need accountable owner/legal review.
  This tool does not replace a customer's regulatory reporting or ETRM controls.

Benchmark references inform workflow breadth only: [LSEG trader workspace](https://www.lseg.com/en/data-analytics/products/workspace/sales-traders)
and [Kpler gas/power intelligence](https://www.kpler.com/solutions/fundamental-intelligence/gas-power).
No internal vendor architecture or equivalence was inspected or claimed.

## Delivery boundary and release sequence

Keep maintainers' source, tests and architecture history available for engineering;
they are not automatically customer installation payload. Remove local automation
from public HEAD but preserve it on this machine. Do not rewrite public Git history
or delete published releases without a separate reviewed migration. If an actual
secret is identified, revocation precedes history cleanup.

Customer handover must include only intended binaries/operator payload, versioned
configuration templates, installation/upgrade/DR runbooks, compatibility/support
policy, release notes/known issues, licences/notices and integrity/provenance.
No account credentials, raw market data, prompts, internal traces or test fixtures.

Sequence: delivery-boundary fixes -> same-SHA release evidence -> service identity
and dual control -> authenticated trader/HMI UAT -> numerical/research acceptance
-> real IdP/provider/security/restore acceptance -> signed production candidate.
Release must remain blocked while mandatory evidence is absent. No production
tag, deployment or external approval is created by this audit.

## Verification of this bounded change

- Release suite plus readiness/Linux packaging contracts: 71 passed, three
  symlink tests skipped because Windows did not permit symlink creation;
  two existing dependency deprecation warnings. Junction refusal is tested.
- Frontend suite: 551 passed; production build passed. An existing dynamic-import
  chunking warning remains. Locale coverage: 2,810 keys in each locale, no missing keys.
- Focused Python lint and whitespace checks passed. Built and inspected the
  actual deployment ZIP: exactly ten allowlisted files, no recursive directory payload.
- The worker additionally reported a full suite run: 1,906 passed, 20 skipped,
  one sandbox-permission failure in a Markdown-link test that writes outside its
  workspace. Independent rerun of that entire three-test module passed. This
  does not establish a database-backed full acceptance run.
- No current database migration/restore, native installation,
  authenticated HMI acceptance or new GitHub release execution was performed.
  Local test success is not customer production approval.

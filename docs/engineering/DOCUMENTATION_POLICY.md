# Documentation policy

Eurogas Nexus is sold to and run by teams in the UK, Canada, Singapore and China. The
documentation has to be readable by each of them and has to stay true to the code.

## Language

1. **One language per document.** English is the canonical language. A Chinese
   version is a companion file with the same name and a `-CN` suffix
   (`DEPLOYMENT_ROLES-EN.md` / `DEPLOYMENT_ROLES-CN.md`, or `FOO.md` / `FOO-CN.md`).
   Do not interleave the two languages paragraph by paragraph.
2. **Maintain one factual baseline.** Write and review the English source first, then edit
   the Chinese companion for native use. If they disagree, verify the installed/released
   behaviour and correct both before client distribution. A change to a client guide updates
   its companion in the same commit. Record deferred internal-reference work in the backlog.
3. **Every `-CN` file has an English source.** A Chinese-only specification is not
   allowed; `tests/contract/test_documentation_language.py` enforces this.
4. **Exceptions.**
   - *Dated records* (acceptance audits, review minutes, incident reports) stay in the
     language they were written in; an English abstract is added at the top. Evidence is
     not rewritten after the fact.
   - *Terminology tables and the ontology* may show the English term with its Chinese
     equivalent, because the pair is the content.
   - *Code comments and docstrings* follow `CODING_STANDARDS.md`.
5. **Plain, specific English.** Desk vocabulary (gas day, WD/DA/BOM, MA, Cal, p/th,
   EUR/MWh) is used as traders use it; see `docs/product/UX_REFERENCE.md`.

### Translation backlog

Canonical files still written mainly in Chinese. The guard test fails if a file is added
here or if a new one appears; remove an entry when its English version lands.

| File | Plan |
|---|---|
| `docs/engineering/CODING_STANDARDS.md` | Split into `CODING_STANDARDS.md` (English) and `CODING_STANDARDS-CN.md`. |
| `docs/ontology/europe-natural-gas.md` | Translate; keep the term table bilingual. |

## Where documents live

| Folder | Holds | Audience |
|---|---|---|
| `docs/user/` | How to do a task in the product | traders, analysts, risk |
| `docs/product/` | What the product does and why; roles; UX rules | product, buyers |
| `docs/architecture/` | How it is built; ADRs; API contract policy | engineers, architects |
| `docs/operations/`, `docs/deployment/` | How to run, deploy, ingest, recover | operators |
| `docs/research/` | Datasets, features, targets, ML readiness | quants, data scientists |
| `docs/legal/` | Licence and data-source terms | legal, procurement |
| `docs/release/` | Release readiness and dated acceptance records | release owners, auditors |
| `docs/engineering/` | Working method, CI, plans and their execution state | contributors |

Execution plans and wave records in `docs/engineering/` are working history. When a plan is
finished, its outcome goes into the owning document (architecture, product or operations)
and the plan is marked *Closed* at the top rather than kept as a second source of truth.

## Client delivery standard

The client entry point is [the role-guide hub](../guides/README.md). Keep engineering
execution records and release evidence in their owning directories, with specialist links
from the client layer.

A client procedure states the task and outcome, prerequisites, numbered actions, expected
result, recovery/escalation route and related detail. Use current interface labels.
Describe release-specific availability and the evidence for supported platforms; do not
infer an installed-client support guarantee from a package version or a successful build.

Write direct instructions. Explain a material calculation assumption or access requirement
at the step where it matters. Keep product scope in the guide hub rather than repeating
general warnings at the end of every task. Avoid retrospective bug narratives, implementation
debates, unsupported completeness claims and invented service commitments in client guides.

## Chinese editorial standard

Use natural Chinese task titles and short action sentences. Choose established domain
terms consistently; preserve units, provider names, API identifiers and calendar versions.
Use the Chinese UI label where the product is localised. Restructure long English sentences
and tables when that makes a Chinese procedure easier to follow.

Review both editions for the same permissions, prerequisites, units, steps, outcomes and
exception handling. Compare style with current native Chinese product help, such as
Apple China's task guides. The Chinese edition must be usable without consulting English.

## Review and publication

For client-facing changes:

1. Check the relevant release/source behaviour and record the reviewed baseline.
2. Complete English, then edit Chinese against the same facts.
3. Validate local links and companion files, and run the documentation language checks.
4. Verify code/CLI examples against the supplied SDK or command interface.
5. Record screenshot capture build/date when updating illustrated procedures.
6. Confirm client-specific support, platform, data-coverage and recovery fields in the handover.
7. Publish the documents with the release they describe and retain the release's prior edition.

Changes to configuration examples use the repository's generator and its check mode.
Do not hand-edit generated examples. Treat an unresolved factual or language mismatch
as a documentation defect to resolve before the affected delivery.

See [the delivery review](DOCUMENTATION_DELIVERY_REVIEW.md) for the current assessment,
public reference sources and the customer-documentation structure.

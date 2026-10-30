# Documentation policy

Eurogas Nexus is sold to and run by teams in the UK, Canada, Singapore and China. The
documentation has to be readable by each of them and has to stay true to the code.

## Language

1. **One language per document.** English is the canonical language. A Chinese
   version is a companion file with the same name and a `-CN` suffix
   (`DEPLOYMENT_ROLES-EN.md` / `DEPLOYMENT_ROLES-CN.md`, or `FOO.md` / `FOO-CN.md`).
   Do not interleave the two languages paragraph by paragraph.
2. **The English file wins.** When they disagree, the English file is correct and the
   companion is out of date. A change to the English file names the companion in the same
   commit, or records it in the backlog below.
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

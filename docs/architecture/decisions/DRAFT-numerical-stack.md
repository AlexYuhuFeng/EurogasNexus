# DRAFT ADR: A numerical library stack for models and solvers

**Status:** DRAFT, awaiting owner review (2026-11-26). Proposed in
[ARCHITECTURE_V3_PLAN.md](../ARCHITECTURE_V3_PLAN.md) section 3.4. On acceptance it is appended to
[ARCHITECTURE_DECISION_RECORD.md](../ARCHITECTURE_DECISION_RECORD.md). It adds runtime
dependencies, not a service. It leaves Decision 36 (the enumerative LNG disruption engine)
unchanged.

**Context.** The runtime has no NumPy or SciPy (`requirements.lock`; `pyarrow` only). Solvers are
hand-written in pure Python: successive shortest paths with Bellman-Ford
(`optimization/network_flow.py`), a dynamic programme for storage (`optimization/storage.py`,
O(N^2 T) with a default inventory step of 1 MWh, which makes a 1 TWh facility impossible), a
min-cost circulation (`optimization/circulation.py`, verified correct). Black-76 implied
volatility is computed in pure Python (`domain/market/options.py`). A model validator cannot
compare a hand-written solver with a standard one; value-at-risk by tenor with correlation,
expected shortfall, stress and Monte Carlo for storage and swing are impractical without
vectorised arithmetic (quant review section 5; technology review section 4a). The quant review
notes that AGENTS.md rule 5 requires a decision for this.

**Decision.**

1. Add **NumPy** (BSD-3-Clause) and **SciPy** (BSD-3-Clause) to the runtime, and **HiGHS** through
   `highspy` (MIT) for linear and mixed-integer programmes. Add **Numba** (BSD-2-Clause) only when
   a measured loop needs compiling (storage or swing Monte Carlo). Each passes the existing
   fail-closed licence audit before it is locked.
2. **Where they are used**: the risk engine (return matrices, correlation, VaR, expected shortfall,
   stress); storage and network optimisation (HiGHS); option and optionality valuation; the
   weather and balance models. Domain code stays free of web, database and network imports
   (unchanged rule); NumPy is allowed in `domain/`.
3. **The hand-written solvers become test oracles**: each HiGHS-based result is checked against
   them on small cases in CI, and the golden cases the quant review verified are kept.
4. **Decision 36 stands**: the LNG disruption engine stays enumerative, because each option must
   be explained line by line and its option space is small.
5. **Determinism**: random-number generators are seeded and the seed is stored in the run
   manifest; results of record are rounded and stored as decimals (see the money draft).
6. **Research reads**: Polars or DuckDB (both MIT) over Arrow for the research extra, where
   `pyarrow` already sits; not in the request path.
7. **Compiled extensions** (Rust through PyO3) only at a measured trigger: a full-book
   revaluation above about 60 seconds after NumPy and Numba.

**Alternatives.** (a) Keep pure Python: one to two orders of magnitude slower, more correctness
risk, unvalidatable against a standard. (b) A commercial solver (Gurobi, CPLEX): licence cost and
redistribution terms without a measured need; HiGHS is competitive at this size. (c) OR-Tools:
Apache-2.0 and capable, but heavier; HiGHS covers the linear and mixed-integer needs. (d) A
separate calculation service in another language: a new service and a second toolchain for no
measured gain.

**Consequences.** About 60 to 80 MB more in the backend image; wheels exist for all supported
platforms. Numerical results of the storage and network optimisers may change in the last digits
against the oracles; tolerances are stated per test. The numerical CI gate gains the oracle
comparisons.

**Migration.** (1) Add the dependencies and the licence records. (2) Storage optimisation on
HiGHS with a bounded grid and the DP as oracle. (3) Network optimisation on HiGHS, separating
"infeasible" from "unprofitable". (4) The risk engine on NumPy (plan phase 4). (5) Optionality
(phase 6).

**Tests that make it observable.** Oracle comparisons per solver; a storage case of 1 TWh solves
within a stated time; reproducibility of a seeded Monte Carlo from its manifest.

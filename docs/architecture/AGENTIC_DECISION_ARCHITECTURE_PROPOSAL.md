# Agentic decision architecture proposal

**Status:** Proposed. The implemented experiment is an offline synthetic route calculation and evidence-gated workflow.

## Dispatch and ownership

1. Call a pure function when typed inputs and a formula fully specify the answer. Use a domain service when the formula needs governed evidence, effective-date resolution, conversions or portfolio context.
2. Dispatch known multistep tasks through an explicit workflow. Apply an event trigger when domain facts change within a watched dependency and horizon.
3. Run the mathematical optimiser for a choice among coupled alternatives. It owns constraints, feasibility, tolerances, objective and candidate comparison.
4. Use a single LLM call for extraction or prose when the information is already scoped and the desired output is defined.
5. Trial a governed planner only when the next investigative step plausibly depends on earlier findings. Limit follow-ups and expose deterministic capabilities through the current registry. Use multiple roles only after measuring value beyond an independent deterministic challenger.

Fast path resolves the event, affected keys and first check. Optimisation path runs authorised scenario solves against versioned inputs, returning feasible incumbents with termination status and explicit gaps where supported. Agentic path operates asynchronously over selected results and may propose follow-ups or scenarios. Optional analysis can arrive after the first alert or decision pack. A deadline latches the last reproducible result and marks outstanding investigation.

## Portfolio and LNG boundary

Freeze an authorised portfolio snapshot and manifest at an as-of cutoff. Include book/mandate, contracts and amendments, confirmed cargo and terminal windows, rights, storage inventories, Send-out and pipeline profiles, credit/hedges and available prices. Cite snapshot and component versions. Resolve gas-day and unit conversions at the domain boundary. Partition projections by tenant, book or authorised cross-book scope. Keep the existing transactional model and `LiveSnapshotReader` pattern. Follow the separate LNG team's canonical types and delivery dates.

Evaluate affected cargoes together when they share a resource. The optimiser models capacity by resource and time interval, subtracts authoritative commitments, and returns analytical alternatives. Assumptions and hypothetical allocations live in the scenario. Concurrent analyses may share a snapshot, but cannot change live resource balances. Before approval or export, compare dependency versions against current state and request re-evaluation after a material change. Any future committed reservation would require versioned atomic allocation by the authorised system and separate product approval. Decision Cases hold reviewed packages and status references.

## Evidence and execution policy

| Evidence state | Required behavior |
| --- | --- |
| VERIFIED | Authorised source and version matched to proposition, scope, effective period and unit. Contractual rules need a reviewer and approved version. |
| CONDITIONAL | Preconditions are explicit and the result remains contingent. |
| INDICATIVE | Research estimates, synthetic cases and non-executable quotes. Carry the class into downstream outputs. |
| UNKNOWN | Withhold dependent claims and surface the missing input. |
| CONFLICTED | Preserve conflicting evidence and require reconciliation or authorised resolution. |

Keep physical feasibility, commercial feasibility and execution confirmation as separate axes. Use explicit conditional, awaiting confirmation, not assessed and infeasible outcomes. Physical capacity says little about ownership and access. Executable quotes, commercial rights and current credit and liquidity are separately necessary for a commercial assessment. The prototype reports synthetic scenario feasibility and commercial status `NOT_ASSESSED`.

Provider input is untrusted text or data. Resolve observations and extracted terms to typed candidate facts. Tool argument schemas, action allowlists and data scopes come from Nexus. Bind roles and row visibility to authenticated human or persisted service identities, check again at each invocation and before external model processing, and reject model-supplied authority or citation IDs. Where terms restrict external AI consumption, use an approved local path or deterministic fallback. Check references against the exact source version, units, value and effective period. Preserve discrepancy and reviewer outcome. Record versions of capability, input, model and prompt, resolved evidence IDs, decisions, timings and cost; avoid logging raw commercial documents and quote payloads.

Start any future model trial with one bounded read-only plan proposal, a token cap, a deadline and a server-side allowlist. Run validated steps through the current runtime and keep skipped, denied, timed-out and incomplete states. Separate network timeout from task deadline and implement cancellation. Disallow arbitrary SQL, writes and human-approval delegation. Restrict MCP to its current supported deployment profiles until delegated identity, legacy tool migration and security acceptance are proven.

## Event and performance architecture

Current scheduled debounce and SSE serve different purposes. Five minutes is an eligibility window between full scheduled runs. Source acquisition delay, scheduler wait and calculation duration still need measurement. Carry event time, source publication, receipt, projection and user-visible timestamps. Record revisions. Start with existing pending keys and a PostgreSQL transactional outbox only when failure recovery and re-evaluation requirements justify one. Use idempotent jobs keyed by event revision and snapshot, materiality filters, coalescing by dependency and version, deadline-aware priority and supersession. Recheck before persisting derived output. A late update can trigger replay under the relevant as-of cutoff.

Invalidate caches by snapshot and entitlement version. Prioritise urgent expiry/ETA cases separately from full re-optimisation. Bound scenario parallelism to preserve database and solver capacity, measure cold and warm solves, and test cancellation and retry before concurrency changes. Human reviews persist independently of jobs. Instrument receipt-to-detection, detection-to-first feasible scenario, time to quantitative recommendation, completion, CPU/solver time, model tokens/cost and human actions. Set desk SLOs after representative measurements segmented by workload and operating hours.

## Migration

Keep the experiment disconnected from runtime entry points. Promote evidence checks only after adopting canonical source IDs and valuation fields, proving row-level access and shadowing existing decisions. Maintain a deterministic fallback and scoped opt-in. Start event processing in shadow against current debounce, compare completeness, latency and allocator results, then move a narrow class after acceptance. An agent trial stays optional and removable without schema changes. Queue, worker and solver changes require their own ADRs and measurements.

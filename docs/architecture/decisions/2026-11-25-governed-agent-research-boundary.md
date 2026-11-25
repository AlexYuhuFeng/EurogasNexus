# ADR — Governed agent experiments around deterministic decisions

**Status:** Proposed for independent review.

**Context.** Existing tools already compute route costs, feasibility, cargo economics, portfolio allocation and risk. The Research Orchestrator validates plans and uses the Capability Runtime. Research capability labels and cited inputs do not establish underlying commercial authority.

**Decision.** Retain deterministic calculations, portfolio constraints and event-response workflows. Research may add explicit evidence gates to their composition. Test dynamic planning only for novel investigations on a frozen, authorised snapshot. Keep the initial offline prototype out of the API, MCP and worker surfaces and use synthetic indicative outputs. Keep portfolio authority inside existing state and solver boundaries. Maintain the execution and confirmation controls.

**Alternatives.** An agent on every tick adds a dependency and a second risk interpretation for tasks already covered by rules. Independent cargo agents cannot resolve shared inventory and rights without a common allocator. A new workflow engine could provide stronger replay primitives, but the current pilot requires neither external durability nor throughput beyond existing infrastructure.

**Consequences.** Provenance and refusal can be reviewed separately from any model. Dynamic exploration will have to beat a fixed workflow in blind review and pass identity, evidence and latency gates. Integrating the prototype itself would require real evidence adapters and maturity work. Reverting the offline experiment has no persisted state impact.

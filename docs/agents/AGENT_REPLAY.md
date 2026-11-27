# Agent Replay (CR-15)

## What is persisted

AgentRun stores objective, principal, agent profile, model provider/id,
status/stage, artifacts, evidence dependencies, warnings/blockers, cost
metadata, and runtime version. ToolInvocation stores capability id +
capability version, safe input summary + input hash, output reference/hash,
evidence refs, warnings, error code, duration, and entitlement state.

## What is never persisted

Hidden chain-of-thought. Replay payloads explicitly return
`hidden_chain_of_thought: null`.

## API

The governed agent research endpoints (runs, replay, plans, strategy IR) and the System >
Agent Research UI were removed with the strategy laboratory on 2026-11-27. The AgentRun and
ToolInvocation persistence, the capability runtime and its `/api/capabilities` surface remain;
a historical agent run is evidence and is not re-issued.

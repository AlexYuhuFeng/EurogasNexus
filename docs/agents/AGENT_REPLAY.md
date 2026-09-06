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

- `GET /api/agent/runs`
- `GET /api/agent/runs/{id}`
- `GET /api/agent/runs/{id}/replay`

UI: System > Agent Research > Agent Runs with an observable step timeline.

# Security and Entitlement (CR-15)

## What holds

- `CapabilityRuntime` checks the permission and then the family entitlement before every
  handler it runs, and it re-authorises a principal rebuilt from the invocation context
  rather than trusting the caller's claim (`application/agents/runtime.py`).
- Capability `entitlement_policy` lists source families; principal `data_scopes` are
  evaluated fail-closed, where `*` is an explicit grant and never a default.
- External LLM payloads reuse the existing licensed-data and sensitive-field filtering
  rules, and a direct provider invocation is additionally re-authorised against the
  calling identity's own analysis capability
  (`api/dependencies/ai_authority.py`; Architecture V2 finding C8).
- Provider text, documents and comments are untrusted data, never instructions.
- `HUMAN_ONLY` review recording and `HUMAN_CONFIRMATION` freeze/shadow operations cannot
  be bypassed by an agent call.
- MCP tool names and descriptions contain no SQL or execution vocabulary.

## What does *not* hold yet, stated plainly

Architecture V2 finding C8 recorded that an earlier version of this page overstated the
MCP path. The corrections:

- **MCP does not inherit the calling user.** The MCP transport carries no user identity, so
  registry capability tools run as an environment-configured pseudo-principal
  (`EUROGAS_NEXUS_AGENT_PRINCIPAL`, default `service:mcp`) with the role and scopes the
  deployment grants. What changed in the C8 fix is the *default*: it is now **no commercial
  grant** rather than `*`, so an unconfigured MCP server cannot read licensed families -
  only the public baselines any active principal may read. Carrying the caller's identity
  across the transport is still open work.
- **The legacy read/sandbox MCP tools bypass `CapabilityRuntime`.** They call the SDK
  directly and therefore inherit only the API token and principal the SDK sends, not the
  permission and entitlement checks above. Retiring or re-homing them is open work.
- **API-side agent invocation passes the real principal**, so the checks above do apply
  there; a deployment with no identity attached substitutes a synthetic `ANALYST`, which
  is a broad default rather than a denial and is tracked with finding C5.

Until the first two items are closed, treat MCP as deployment-trusted infrastructure
rather than as a per-user surface, and grant it data scopes deliberately.

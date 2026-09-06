# Security and Entitlement (CR-15)

- The agent inherits the normal authenticated principal; there is no AI-admin.
- `CapabilityRuntime` checks permission before every handler, including MCP.
- Capability `entitlement_policy` lists source families; principal
  `data_scopes` are evaluated fail-closed (`*` is an explicit grant).
- External LLM payloads reuse the existing licensed-data and sensitive-field
  filtering rules.
- Provider text/documents/comments are untrusted data, never instructions.
- `HUMAN_ONLY` review recording and `HUMAN_CONFIRMATION` freeze/shadow
  operations cannot be bypassed by an agent call.
- MCP tool names/descriptions contain no SQL or execution vocabulary.

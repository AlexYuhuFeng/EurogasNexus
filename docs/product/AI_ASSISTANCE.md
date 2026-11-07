# AI assistance: what it does today, and how a trader should meet it

Status: design proposal, 2026-11-07. Related: `docs/product/ADAPTIVE_CLIENT.md`,
`docs/architecture/CENTRAL_DATA_PLATFORM.md`.

## The principle

**Detection is deterministic; the model explains, summarises and drafts.** A rule decides that
an outage moves supply, that a credit line is breached or that a feed failed. The model never
decides that something happened. It says why it matters, in the user's language, citing the
evidence it was given, and a person acts. Nothing the model writes executes a trade, a
nomination or a settlement (AGENTS.md rule 8). Every answer carries its evidence references,
and only data the user is entitled to reaches the model.

## What exists today

| Capability | Where | What it does |
|---|---|---|
| Copilot actions (Ask, Explain, Compare, Challenge, Draft) | Market overview and Review; command palette | Answers over the user's current context and cited evidence; refuses without evidence |
| Alert analysis | Alert centre | A bilingual explanation of each monitoring alert, generated once per new or escalated alert under a named service identity |
| Monitoring | Worker, every few minutes | Deterministic alerts for intraday spread candidates, strategy drift, failed data feeds and (new) outages that move supply |
| Agent research | Research → Agent Research | Research runs over registered capabilities, with a human review gate |
| MCP server | `src/eurogas_nexus/mcp/server.py` | 21 read and sandbox tools, so the firm's own AI assistants can query the product |
| Contract intake | Portfolio → Resources → Import | OCR of a contract PDF into a draft for review (OCR, not an LLM) |

The provider is any OpenAI-compatible endpoint (DeepSeek today). It is off unless the operator
enables it. A firm can point it at a model it hosts itself.

## How a trader should meet it

Not a chat bubble floating over the board: traders do not stop to chat. AI should appear in
three places, each at the moment it is useful.

1. **Ask, in the search box.** The search box (Ctrl K) already finds pages and objects. A
   question typed there ("why is NBP up today?", "what is my exposure to Norwegian outages?")
   goes to the Copilot with the current page as context, and the answer opens in the side panel
   with its sources. One entry point, already where the user's hands are.
2. **Explain, where the number is.** Next to an alert, an outage, a credit breach, a price move
   or a P&L figure, a small "Why?" gives two or three sentences with the evidence, without leaving
   the page. This is the most valuable form: an explanation attached to the thing that needs it.
3. **Proactive, in the ticker and the inbox.** When monitoring raises a critical item, the
   ticker headline is the rule's fact ("Haldor field 563 GWh/d out now"). The alert centre holds
   the model's one-paragraph context: what the asset feeds, what it means for the hub, and what
   the desk holds there. A morning brief and an end-of-day summary are drafted from the same
   evidence for a person to edit and send.

## What it should do next, in order of value to a desk

| # | Capability | Why a trader cares | Feasible now? |
|---|---|---|---|
| 1 | Outage, breach and price-move alerts, explained | "Warn me in time": the explanation turns a REMIT line into "this is 8 % of NBP supply and we are long" | Outages done; credit and mandate breaches need the credit calculation as a service a worker can call (see the engineering review) |
| 2 | "Why?" on alerts, outages, breaches and P&L | Answers the first question a trader asks, in place | Yes, through the existing Explain action with the object as evidence |
| 3 | Morning brief and end-of-day report drafts | Saves the half hour every desk spends writing them | Yes: the report exports exist; the model drafts the narrative |
| 4 | Contract and confirmation reading | Turn a PDF into terms and flag deviations from the template | OCR exists; extraction into the draft is a short step |
| 5 | Ask in the search box | One place to ask anything, with sources | Yes: route palette questions to the Copilot |
| 6 | Strategy and data assistance | Draft a spread spec, explain a backtest result, suggest features | Agent research exists; wire it into the Research pages |

## Guardrails that stay

- Evidence or nothing: an answer without cited sources is withheld, as it is today.
- Entitlements apply before the model sees data: licensed rows go only to users holding the
  scope.
- No execution: the model drafts and explains, and a person decides.
- Off by default, with the provider set by the firm (including a self-hosted model).
- Every call is audited under the user's or the service's identity.

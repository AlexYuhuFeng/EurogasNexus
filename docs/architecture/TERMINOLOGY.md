# Product Terminology Standard

Chinese companion: [TERMINOLOGY-CN.md](TERMINOLOGY-CN.md)

## Canonical Product Positioning

Eurogas Nexus is a European natural gas market intelligence, optimization, and decision-support platform.

The product supports market analysis, infrastructure visibility, route economics, contract and resource evaluation, optimization, and trader-reviewed decisions. It is not an execution venue, order router, nomination system, settlement platform, or ETRM replacement.

## Required Terms

Use the following terms consistently in code, API descriptions, user interfaces, release notes, and documentation:

| Avoid | Use instead |
|---|---|
| research only / research-only | decision support / human review required |
| research-oriented platform | decision-support platform |
| research tool | decision-support tool |
| research workspace | analysis workspace or optimization workspace |
| research assistant | market analyst or decision assistant |
| automatic trading recommendation | trader-reviewed decision-support output |

## Code and API Rules

- Do not add a `research_only` field to new request bodies, domain models, stored records, or business-data payloads.
- Use `human_review_required` when an output must be reviewed by a trader or operator.
- Use `decision_support_only` where a stored record or future API contract explicitly needs that governance classification.
- The shared API response envelope temporarily retains `meta.research_only` for compatibility with the existing Web `ApiMeta` contract and repository guardrails. It must not be copied into endpoint data objects.
- Replacing the compatibility envelope field requires a dedicated migration that updates backend envelopes, Web client types and consumers, repository guardrails, contract tests, and compatibility documentation together.
- Do not imply that optimization results execute trades, submit nominations, book capacity, or create official approvals.
- Existing technical route paths are not renamed solely for terminology consistency when doing so would break compatibility. Deprecation and migration require a separate API change.

## Optimization Naming

Preferred capability names include:

- Route Optimization
- Resource Pool Optimization
- Capacity Optimization
- Contract Optimization
- Storage Dispatch
- Scenario Analysis
- Risk Optimization

`Route Cost` may remain in technical compatibility paths and module names, but new user-facing descriptions should use Route Optimization or Route Economics where appropriate.

## Human Review Boundary

All optimization, scenario, analysis, route, portfolio, and report outputs require human review. This requirement must be expressed through result metadata and product documentation, not through new research-only business fields.

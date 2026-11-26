# Professional review, 2026-11-26

Seven independent reviews of Eurogas Nexus 1.0.0-beta, each written from the point of view of
the people who would use, control, operate or buy it at a European gas trading house. They are
kept here as written, as evidence. The response to them is
[ARCHITECTURE_V3_PLAN.md](../../architecture/ARCHITECTURE_V3_PLAN.md), whose appendix A maps
every blocker and major finding to a workstream and phase.

The reviewers read the integrated tree at about commit `3a1f81a` (the technology review saw it
move to `870da77`). Where the tree has changed since, or a claim did not hold when checked in
code, the plan says so in its section 2 and appendix D. The demo account password and the demo
address given to the reviewers are not reproduced here.

| Report | Point of view | Headline |
| --- | --- | --- |
| [front_office.md](front_office.md) | Prompt/curve trader, LNG trader, originator, fundamentals analyst, power trader | A useful second screen (book impact of outages, the physical gas day, auditable LNG netbacks); blocked by no licensed live prices, no settlement history and linear-only valuation |
| [middle_back_office.md](middle_back_office.md) | Market risk, credit, scheduling, product control, compliance, head of desk | Risk and scheduling would use parts of it; finance and compliance cannot: no versioned trades, no end-of-day close, roles too coarse for segregation of duties |
| [technology.md](technology.md) | Trading-systems developer, SRE, data engineer, information security, enterprise architect | Disciplined engineering; blocked by a one-process runtime, a daily dump as the only backup and licensed connectors that are only manifests |
| [multinational.md](multinational.md) | Localisation lead, contracts and legal manager, COO of a seven-desk group | Careful within English and Chinese, but languages are written into code and schema; no legal-entity or jurisdiction model |
| [security.md](security.md) | CISO office: AppSec, architecture, IT risk, pen-test planning, market-abuse controls | Good hygiene; authorisation and data segregation are the weak layer (findings H1 to H7, M1 to M10) |
| [operations_governance.md](operations_governance.md) | IT service management, change, DBA, monitoring, market-data and vendor management, data governance, procurement, BCP | A better governance core than most desk tools; not supportable in production: continuity, backups, alerting, environments |
| [quant_models.md](quant_models.md) | Quant, model validator, structurer, product controller | Careful arithmetic building blocks; the risk layer is indicators, three concrete VaR errors, nothing values optionality, nothing is reproducible |

Work already under way when the plan was written: the fixes to the risk and valuation formulas
from the quant review, and the remediation of security findings H1 to H7 and the mediums.

# Identity, Access, Experience and Control Plane

## 1. Effective access

`Identity + Capability Grants + Scope + Data Entitlements + Constraints -> Effective Access`

Then:

`Effective Access + Functional Assignments + Selected Work Mode + Preferences -> Experience Composition`

The second equation never creates permissions.

## 2. Functional assignments

Users may simultaneously hold:
- Trader / Commercial Analyst
- HQ Business Analyst
- Reviewer / Management
- Quant / Research
- Data Operator
- Platform Administrator

Do not model these as mutually exclusive personas.

## 3. Capability model

Examples:
- market.read
- portfolio.read
- portfolio.assumption.write
- scenario.run
- decision.create
- decision.review
- strategy.design
- strategy.freeze
- backtest.run
- dataset.build
- dataset.export
- provider.connection.view
- provider.ingestion.operate
- provider.credential.manage
- provider.certification.manage
- access.manage
- audit.read

Existing roles can remain compatibility bundles/floors.

## 4. Scope

Capabilities are constrained by:
- organisation;
- portfolio;
- market/hub;
- resource/contract set;
- commercial entity;
- region where relevant.

## 5. Data entitlement

Entitlement can distinguish:
- provider/data product;
- raw vs derived;
- view vs export;
- redistribution;
- external-LLM usage;
- effective dates/expiry.

Provider Connection != Data Entitlement.

## 6. Conflict resolution

Recommended order:
1. hard product/security prohibition;
2. explicit deny/licence restriction;
3. organisation/portfolio scope;
4. data entitlement;
5. capability grant;
6. experience composition.

## 7. Platform admin is not commercial super-user

Platform Admin can manage:
- SSO;
- users/groups;
- runtime;
- provider secret metadata;
- system settings;

without automatically seeing:
- contract prices;
- strategy parameters;
- commercial PnL;
- restricted datasets.

Commercial access is separately granted.

## 8. Control Plane

Administration should be a distinct product surface.

Control Plane owns:
- Users / Groups
- Roles / Capabilities
- Scopes
- Data Entitlements
- Provider Connections
- Credentials
- Source Certification
- Pipelines
- Runtime
- Audit
- LLM Providers
- System Config
- Feature Lifecycle

Normal business users should not navigate through these controls.

## 9. ExperienceProfile

Backend may return a safe composition contract:

```json
{
  "functional_assignments": ["TRADER", "RESEARCHER"],
  "available_work_modes": ["TRADING_ANALYSIS", "RESEARCH"],
  "default_work_mode": "TRADING_ANALYSIS",
  "effective_capabilities": ["market.read", "portfolio.read", "backtest.run"],
  "scope_refs": ["ORG:CUML", "PORTFOLIO:UK_GAS"],
  "data_entitlement_refs": ["NBP_CORE", "TTF_CORE"]
}
```

Every API call is still re-authorised server-side.

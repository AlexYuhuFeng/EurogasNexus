# Roles, job functions and responsibilities

Eurogas Nexus separates three things that trading-house access models often blur:

| Layer | Question | Set by | Grants access? |
|---|---|---|---|
| **Role** (VIEWER, REVIEWER, ANALYST, OPERATOR, ADMIN) | What may this person do? | Administrator; never self-granted (a second admin must make the change) | Yes: permissions |
| **Data scopes** (EEX, ICE_OCM, Trayport, WMR, …) | Which licensed data may they see? | Administrator, in line with the vendor licence | Yes: row entitlement |
| **Job functions** (below) and **office** | What does this person do, and where? | Administrator, audited | No: home screen and emphasis only |

A job function an administrator declares but the role cannot support is shown as
*unsatisfied*, never granted. Work modes and job functions never change what the
backend authorises.

## Job functions (front, middle and back office)

| Job function | Typical role(s) | Home screen | First things they read |
|---|---|---|---|
| Trader | ANALYST | Market → Curves (ladder or hub board) | Prices, spreads, spread candidates, capacity on their routes, position by delivery period |
| Business analyst | ANALYST | Market → Curves | Fundamentals, storage vs target, scenarios |
| Quant researcher | ANALYST | Strategy Lab → Design | Spread and benchmark research, backtests |
| Risk manager (middle office) | ANALYST + REVIEWER | Portfolio → Exposure | Net position by delivery period (physical + financial), limits, open decisions; challenges and reviews decisions |
| Finance & settlement (back office) | ANALYST | Portfolio → Exposure | Cash timing, payment lags, financing (SONIA/€STR/SOFR + spread), FX fixes |
| Legal & compliance | REVIEWER | Decision Center → Review | Decision records and evidence, contract terms, data-licence entitlements |
| Management | ANALYST or REVIEWER | Portfolio → Overview | Portfolio footprint, P&L, exposure summary, decisions needing attention |
| Decision reviewer | REVIEWER | Decision Center → Review | Cases awaiting a decision |
| Data operator | OPERATOR | Administration → Sources | Source health, ingestion, certification |
| Platform administrator | ADMIN | Administration → Access | Users, roles, keys, audit |

People hold several functions (a senior trader may also be a reviewer); the first
declared function picks the home screen. A URL or a saved personal preference always
wins over the persona home.

## Segregation of duties

- **Four-eyes on decisions.** The person who opened a decision case cannot record
  its decision (`409 four_eyes_required`). A second person, typically risk or a
  reviewer, decides.
- **No self-granting.** An administrator cannot change their own roles or data
  scopes. A second administrator must.
- **Platform administration is not commercial access.** ADMIN without a commercial
  role sees no market or portfolio data.
- **No execution.** Nothing in the product places orders, nominates or settles.
  Decisions are recorded evidence, not execution approval.

## Offices

Office codes (UK, CA, SG, CN, NL, DE, CH) set a person's local time zone for display. They
are the hook for regional scoping (see `docs/architecture/GLOBAL_DEPLOYMENT.md`): a
region scope is not enforced yet, and the experience profile reports `REGION` and
`PORTFOLIO` as unsupported scope kinds rather than pretending otherwise.

## How to delegate

1. A platform administrator creates the user (or SSO provisions them) and assigns
   **roles** and **data scopes** according to the person's mandate and the vendor
   licences.
2. The same or a second administrator sets **job functions** and **office** under
   Administration → Access → Job profile.
3. Personal preferences (theme, language, density, default market view) belong to
   the user (Preferences menu). Organisation-wide settings (data sources, map tiles,
   retention) belong to administrators (Administration).

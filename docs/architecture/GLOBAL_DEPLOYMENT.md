# Global deployment: UK, Canada, Singapore and China

**Decision (2026-10-30).** Run **one primary installation for the UK, Canada and
Singapore offices**, hosted in a UK region, and **a separate installation inside
mainland China** for the China office. The two do not share a database. Data moves from
the primary to China only as approved, one-way, signed exports. This is a hub with one
sovereign spoke, not a federation of peers.

This builds on [GLOBAL_DATA_DEPLOYMENT_ASSESSMENT.md](GLOBAL_DATA_DEPLOYMENT_ASSESSMENT.md)
(what the code does and does not isolate) and
[REGIONAL_EXCHANGE_PROTOCOL_V1.md](REGIONAL_EXCHANGE_PROTOCOL_V1.md) (the envelope for
cross-installation transfers). Legal conclusions belong to the customer's counsel; this
document states the engineering choice and the constraints it is built to respect.

## Why not one installation for everyone

| Concern | UK / Canada / Singapore | Mainland China |
|---|---|---|
| Personal data of staff (identities, audit trail) | UK GDPR; transfers to Canada (adequacy) and Singapore (standard clauses) are routine | PIPL: personal information of China staff stays in China unless a transfer mechanism (security assessment, standard contract or certification) is in place |
| Commercial data (positions, contracts, P&L) | The same trading book is read in all three offices | May fall under the Data Security Law's "important data" rules; the customer's classification decides |
| Licensed market data (EEX, ICE, Trayport, Argus, ICIS) | Display licences are per user and site; existing entitlements apply | Many vendor licences name sites or countries; China use usually needs its own licence |
| Network | London to Toronto about 80 ms, to Singapore about 170 ms; fine for a research and decision tool | Cross-border links to EU hosting are slow and unreliable; in-China hosting also needs an ICP filing |

A London trader, a Calgary analyst and a Singapore LNG desk read the **same book**.
Splitting it into per-office installations would divide positions and P&L, duplicate
ingestion and licences, and create reconciliation work with no regulatory benefit. China
is different on every row of the table, so it gets its own installation.

## Topology

```
                    ┌────────────────────────── Primary (UK region) ───────────────────────────┐
 UK / CA / SG  ───► │ HTTPS gateway → API → PostgreSQL (primary)   workers: ENTSOG, GIE, ECB,   │
 desktop & web      │                      ↘ backups (UK, encrypted)  BoE, licensed imports      │
                    │ Corporate IdP (OIDC) per legal entity                                      │
                    └───────────────┬──────────────────────────────────────────────────────────┘
                                    │ one-way, signed exports (exchange envelope v1):
                                    │ public fundamentals, approved derived datasets
                                    ▼
                    ┌────────────────────────── China (in-country region) ─────────────────────┐
 China office  ───► │ HTTPS gateway → API → PostgreSQL     own IdP, own audit, own backups      │
                    │ licensed data only under a China licence; external LLM off unless approved │
                    └──────────────────────────────────────────────────────────────────────────┘
```

## Data classes and where they may live

| Class | Examples | Primary | China | Moves to China? |
|---|---|---|---|---|
| Public fundamentals | ENTSOG flows and capacity, AGSI, ALSI, ECB and BoE rates, weather | yes | yes | Yes: China may ingest directly or receive exports |
| Licensed market data | EEX settlements, Trayport and ICE quotes | yes, per entitlement | only under its own licence | No, unless the licence covers China |
| Commercial book | contracts, positions, P&L, decision cases | yes | China entity's own book | Only approved derived aggregates, by export |
| Research artefacts | datasets, features, strategy versions | yes | yes | By export with owner approval (protocol v1) |
| Personal data | identities, sessions, audit events, preferences | per legal entity | stays in China | No |
| Credentials | provider keys, API keys | per installation | per installation | Never |

## How data moves

- **Within an installation:** HTTPS (TLS 1.2 or later) from clients to the gateway. The
  API is the only database client. Streaming uses server-sent events over the same
  origin.
- **Between installations:** no live replication and no cross-database query. Transfers
  are files described by the
  [exchange envelope](schemas/exchange-envelope-v1.schema.json). Each names its
  purpose, classification, owner approval, entitlement reference and SHA-256 digest; it
  expires within seven days. Transfers go one way (primary → China) and are logged at
  both ends.
- **Time:** stored in UTC with the EU-CAM gas-day calendar. Each user sees their office
  time zone (profile `office`); gas days stay gas days.

## Identity and access across offices

- One OIDC identity provider per legal entity. Job functions and office come from the
  profile ([ROLES_AND_RESPONSIBILITIES.md](../product/ROLES_AND_RESPONSIBILITIES.md)).
- Positions roll up by **book → business → region → legal entity → firm** in one reporting
  currency (Portfolio → Exposure; Decision 26), so head office reads the global book and each
  region or desk its part.
- **Office does not limit data today.** Data scopes do (source families). Region and
  portfolio scope kinds are reported as unsupported. Before a desk's book is hidden from
  another office inside the primary, a `PORTFOLIO` scope must be implemented. Until then,
  separate books need separate installations.

## When to add capacity, not before

AGENTS.md rule 5 applies: no new datastore or service without a measured need.

| Signal | Action |
|---|---|
| Singapore or Canada p95 API latency above 1.5 s for interactive reads over a month | Add a PostgreSQL read replica and API instance in that region; writes stay on the primary |
| Recovery time objective under 4 hours | Warm standby in a second UK or EU region with streaming replication |
| China office goes live | Build the China installation; certify each export class with the customer's DPO and counsel |
| A desk's book must be hidden from another office | Implement `PORTFOLIO` scopes first; do not use office as an access control |

## Operating checklist per installation

1. Hosting region, backup location and key custody recorded in the installation's run
   book.
2. External LLM calls off unless approved for that installation
   (`EUROGAS_NEXUS_LLM_EXTERNAL_PROVIDER_ENABLED`).
3. Egress allowlist limited to the provider endpoints that installation is licensed for.
4. Restore drill (`scripts/ops/backup_restore_drill.py`) run into the same region.
5. Audit retention set (`scripts/ops/prune_audit_events.py`) to the entity's policy.

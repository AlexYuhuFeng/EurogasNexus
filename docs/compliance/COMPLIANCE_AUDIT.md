# Compliance audit (2026-10-31, release 0.6.0)

An engineering review of how Eurogas Nexus supports a trading house's compliance
obligations: security, data protection and residency, market regulation, reporting, data
sourcing and licensing, and legal exposure. It records what the product does, the evidence
for it, and the gaps. **It is not legal advice**: each customer's counsel and compliance
function confirm the conclusions for their entities and jurisdictions before go-live.

## Summary

| Area | Status | Open items |
|---|---|---|
| Product boundary (no orders, nominations, settlement) | Met | — |
| Security controls | Largely met | Windows code signing pending; encryption at rest is a deployment duty |
| Data protection (GDPR / UK GDPR / PIPL / PDPA / PIPEDA) | Largely met | Erasure is a documented admin procedure, not self-service |
| Data residency and cross-border transfer | Met by design | China installation and export approvals are customer-run |
| Market regulation (REMIT, MAR, MiFID II record-keeping) | Supported | Information barriers between desks need portfolio scopes |
| Reporting | Internal reports and exports met | Regulatory transaction reporting stays with the ETRM/RRM |
| Data sourcing, scraping and licensing | Met | Per-platform reuse terms for REMIT exports to be confirmed |
| Open-source licences | Met | — |
| Legal claims and trademarks | Met | Customer contract sets liability and warranty terms |

## 1. Product boundary

The product is decision support. It never places orders, nominates capacity, settles or
reports transactions (AGENTS.md rules 8-9; `docs/compliance/RESEARCH_ONLY_COMPLIANCE.md`).
Decided cases leave only as signed hand-offs that a receiving system must book under its
own controls (`GET /api/decision-cases/{id}/handoff`, "Not an order" in every document).
Every analytic output carries `research_only` and `human_review_required`.

## 2. Security

| Control | Evidence |
|---|---|
| Authentication: OIDC, gateway SSO (SAML, Kerberos, vendor agents), identity keys; sessions with CSRF | `security/oidc.py`, `security/gateway_auth.py`, `docs/operations/ENTERPRISE_SSO.md` |
| Authorisation: roles, permission per route, commercial data scopes, no self-grants, four-eyes on decisions | `security/permissions.py`, `tests/security/test_access_self_grant.py` |
| Licensed data only to licensed people | Licence register gates data-scope grants (`/api/access/market-data-licences`) |
| Audit trail of administrative, data and decision actions | `audit_events`, `GET /api/audit` |
| Secrets held server-side only; configuration contract and start-up preflight | `core/config_contract.py`, `scripts/ops/check_config.py --strict` |
| Transport encryption | HTTPS gateway (Caddy) in the server bundle; internal CAs via `SSL_CERT_FILE` |
| Supply chain: pinned actions, SBOMs, licence and vulnerability audits, provenance attestation, checksums | `.github/workflows/release.yml`, `docs/release/SUPPLY_CHAIN.md` |
| Application security verification | `docs/security/ASVS_CONTROL_MAPPING.md`, security acceptance in CI |

**Findings**

- **S1 (high, release owner):** Windows installers are unsigned until the customer's
  Authenticode certificate is configured (`signing-state.json` says so on every release).
  Required before stable 1.0.0 distribution.
- **S2 (medium, customer IT):** encryption at rest (database volume, backups) is provided
  by the deployment (disk or cloud volume encryption, encrypted backup target), not by the
  application. Record it in the installation run book.
- **S3 (low, customer IT):** gateway SSO trusts headers only with a 32+ character secret;
  the gateway must strip client-supplied identity headers (documented).

## 3. Data protection and residency

Personal data held: identity (name, e-mail, office, job functions), sessions, API key
metadata, preferences, and the audit trail of actions. No market counterparty personal
data is required; ETRM imports carry an optional counterparty label only.

| Obligation | Support |
|---|---|
| Lawful basis and purpose | Employment / legitimate interest of the firm; data limited to access control and accountability |
| Minimisation | Only the fields above; preferences hold no personal content |
| Retention | Audit events kept 5 years by default (`DEFAULT_AUDIT_RETENTION_DAYS = 1827`), configurable 30-3650 days; job records and raw payloads pruned by `prune_runtime_data.py` |
| Access requests | `scripts/ops/personal_data_export.py` exports every record naming the person, secrets withheld, and audits the export |
| Erasure and rectification | Administrators disable the identity and minimise its profile; records the firm must keep by law (audit trail, decision records) are retained, which GDPR Art. 17(3)(b) permits for legal obligations |
| Cross-border transfers | One UK-hosted primary for UK, Canada and Singapore; a separate China installation; transfers only by approved, signed, one-way exports (`docs/architecture/GLOBAL_DEPLOYMENT.md`) |
| China (PIPL, DSL, CSL) | China staff data stays in the China installation; external LLM calls off unless approved there |

**Findings**

- **P1 (medium, product):** erasure is an administrator procedure, not a self-service
  function; acceptable for an employee system, to be confirmed by the customer's DPO.
- **P2 (low, customer DPO):** record the processing activity, the retention period and the
  transfer mechanism (UK adequacy for Canada; standard clauses for Singapore) in the
  customer's register.

## 4. Market regulation

| Rule | Relevance | Support |
|---|---|---|
| REMIT Art. 3-5 (insider dealing, market manipulation, inside information) | REMIT UMMs and the firm's own analysis may be inside information | UMMs are imported from public platforms; decision cases, evidence and access are audited; four-eyes before any hand-off |
| REMIT Art. 8 / Implementing Regulation 1348/2014 (transaction reporting) | Not performed here | The ETRM / registered reporting mechanism reports trades |
| MAR / UK MAR (surveillance, records of orders and decisions) | Decision evidence and rationale | Decision packs with content hash; audit retained 5 years |
| MiFID II Art. 16(6)-(7) record-keeping (where the firm is authorised) | Records of decisions leading to trades | As above; exports are reproducible from snapshots |
| EMIR | Not performed here | ETRM / trade repository |

**Findings**

- **M1 (medium, product):** information barriers between desks (for example a desk with
  inside information about its own assets) rely on separate data scopes today; book- or
  portfolio-level scopes are the planned control (Decision 26). Until then, use separate
  installations where a barrier is mandatory.
- **M2 (low, customer compliance):** add surveillance of decision cases and hand-offs to the
  firm's market-abuse monitoring (the audit trail is exportable).

## 5. Reporting

Internal reports: position ladder by hub, book, business, region or legal entity in a chosen
currency; gas-for-power; NW Europe balance; decision packs. All export as CSV
(`format=csv`) and through the API. Regulatory reports (REMIT, EMIR, MiFIR) are out of scope
by design and stay with the systems of record.

## 6. Data sourcing, scraping and licensing

- Public sources are used under their published terms with attribution
  (`docs/legal/DATA_SOURCE_TERMS.md`).
- Licensed market data enters only under the customer's own licence: connectors or
  file imports, stored under the licence's source family, granted to people only against
  the licence register, which records licence type, display/non-display use, offices,
  seats and holders for vendor audits.
- **No scraping** of exchange or vendor web pages whose terms exclude systematic
  extraction or commercial reuse (`docs/operations/MARKET_DATA_SOURCING.md`); where no
  licensed price exists the product shows the gap, never a substitute.
- Simulated prices are labelled and never used as marks, risk figures or market prices.
- The network map ships with no third-party basemap; an operator configures a licensed one.

**Findings**

- **D1 (low, customer):** confirm reuse terms of the REMIT platform the desk exports UMMs
  from (EEX Transparency, GIE IIP, Gassco UMM).
- **D2 (low, product):** the licence register records display versus non-display use but
  does not yet enforce it per feature (for example, curves and risk are non-display use).

## 7. Open-source and third-party licences

Dependencies are audited for commercial use in CI (Python, npm, Rust), with reviewed
exceptions in `docs/legal/DEPENDENCY_LICENSE_REVIEW.md`; notices ship in
`THIRD_PARTY_NOTICES.md`; SBOMs ship with every release.

## 8. Legal claims and trademarks

- The product makes no investment recommendation and promises no outcome; outputs are
  labelled as decision support for human review.
- Exchange, vendor and platform names (EEX, ICE, Trayport, Kpler, Platts, Argus, ENTSOG,
  GIE, ENTSO-E) are used descriptively to name data sources; no logos or endorsements.
- The product is proprietary (`LICENSE`); liability, warranty and support terms belong in
  the customer contract.

## Re-run

Repeat this audit before each minor release and before 1.0.0, updating the findings table.
Open findings that block 1.0.0: S1 (code signing). Findings for the customer's own
programme: S2, P2, M2, D1.

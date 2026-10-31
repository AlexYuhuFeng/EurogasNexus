# Integrating with ETRM, ERP and reporting systems

Eurogas Nexus is the analysis and decision layer between the market screens and the systems
of record. It never places orders, nominates or settles; those stay in the ETRM, the
trading screen and the TSO platforms, under their own controls. This page lists the
supported integration points and the rules that make them safe.

## Systems of record

| Data | Book of record | Into Eurogas Nexus |
|---|---|---|
| Trades and positions | ETRM (Endur, Allegro, Openlink, RightAngle...) | `scripts/ops/import_etrm_trades.py`: extract by trade id, idempotent; cancellations remove trades; trades land in books |
| Physical supply contracts | ETRM or contract system | `POST /api/route-cost/upstream-contracts` (operator), with edit tokens for concurrent edits |
| Market prices | Exchanges and brokers under the firm's licence | settlement and screen imports, or licensed connectors |
| Books and legal entities | ETRM / finance | `PUT /api/portfolio/books/{id}` mirrors the book hierarchy |
| FX and rates | ECB, BoE, NY Fed, or the firm's WM/Reuters / BFIX fix | scheduled sources and the fix import |

The import refuses a trade whose price is not in the hub's currency or whose book is not
defined, so a reconciliation break shows up as a refused file, not as a silent mismatch.

## Out to downstream systems

| Need | Use |
|---|---|
| Reports into Excel, an ERP or a data warehouse | `format=csv` on the position ladder (by hub, legal entity, region, business or book), gas-for-power and NW Europe balance; the *Export CSV* buttons do the same in the UI |
| Programmatic reads | The versioned REST API (`/api`, OpenAPI at `/openapi.json` in non-release profiles; contract rules in `docs/architecture/API_CONTRACT_EVOLUTION_POLICY.md`) or the Python SDK |
| A decided trade idea to book | `GET /api/decision-cases/{case_id}/handoff`: signed, four-eyes, idempotent (below) |
| Audit evidence | `GET /api/audit` (administration) and decision packs with their content hash |

### Decision hand-off

1. An analyst opens a decision case, attaches evidence, and a reviewer (a different person)
   records the decision. Only then is the case DECIDED.
2. Middleware (MuleSoft, Boomi, BizTalk, an in-house service) reads the hand-off with a
   service identity key. The document carries the case, context, alternatives, decision
   records, the decision pack hash, an `idempotency_key` and an HMAC-SHA256 signature.
3. The receiver verifies the signature with the shared key
   (`EUROGAS_NEXUS_HANDOFF_SIGNING_KEY`, held in both secret stores), ignores an
   `idempotency_key` it has seen, and creates a *proposed* deal or task in the ETRM for a
   trader to book under the ETRM's own limits and approvals.

Verification in Python:

```python
import hashlib, hmac, json
body = dict(document)                      # the "data" object of the response
signature = body.pop("signature")["value"]
canonical = json.dumps(body, sort_keys=True, separators=(",", ":"))
assert hmac.compare_digest(
    signature, hmac.new(KEY.encode(), canonical.encode(), hashlib.sha256).hexdigest()
)
```

## Rules for every integration

- **Service identities, not personal ones.** Create an API key per integration with the
  least role and data scopes it needs; rotate it like any credential.
- **Idempotent by design.** Imports key on the source's own id; hand-offs carry an
  idempotency key; re-sending is always safe.
- **Explicit units and currencies.** Every file names its units and currency; conversions
  go through the shared foundation (Decision 27), never an assumed rate.
- **Times in UTC, dates per market calendar.** Gas days are EU-CAM or NAESB, not the
  server's clock.
- **Evidence kept.** Each import and hand-off is audited with its source reference.

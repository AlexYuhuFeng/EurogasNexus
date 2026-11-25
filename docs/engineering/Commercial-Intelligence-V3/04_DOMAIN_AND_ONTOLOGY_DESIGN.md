# 04 Domain and ontology design

## Market event

| Field | Meaning |
| --- | --- |
| `source_id` | The registered source or desk origin (`firm-marks`, a dataops source id) |
| `event_type` | One of `price.updated`, `fx.updated`, `rate.updated`, `tariff.changed`, `outage.published`, `capacity.changed`, `contract.changed`, `mark.changed`, `assumption.changed`, `limit.changed`, `freight.changed`, `source.ingested`, `fundamental.updated`, `weather.updated`, `news.published` (NEWS-1) |
| `subject_key` | What the event is about, in dependency-key form where one exists (`hub:TTF:2026-12`, `outage:<id>`, `ingestion:<source>`) |
| `market_time_utc` | 1. When the thing happened in the market (trade date, gas day, outage start) |
| `published_at_utc` | 2. When the source published it |
| `ingested_at_utc` | 3. When the platform recorded it |
| `processed_at_utc` | 4. When a consumer finished with it (per delivery) |
| `notified_at_utc` | 5. When a person was told (per delivery, set by a notifying consumer) |
| `payload` | Canonical JSON; Decimals normalised, non-finite numbers refused |
| `dependency_keys` | Input keys the event changes; default the subject when it is an input key |
| `input_class` | The CP-13 class (`prices`, `fx`, `rates`, `tariffs`, `outages`, `capacity`, `book`, `marks`, `assumptions`, `limits`, `freight`) |
| `priority` | 0 (outage) to 4 (background) |
| `identity` | Optional explicit identity (a REMIT message id, an ingestion run id) |
| `correlation_id` | Links the event to a run, actor or request |

**Identity** is `sha256(source, type, subject, market time or explicit identity)[:40]`.
**Content** is `sha256(canonical payload, dependency keys, input class, market time,
subject)[:40]`; it never includes publication or ingestion time, so a re-download of the
same figure is a duplicate. Event ids are `mev-<key[:24]>-r<revision>`.

**Revision decision** (pure, `decide_publication`): nothing held -> new revision 1; same
content as the latest -> duplicate; same content as an older revision, or published before
the latest -> out of order (the correction stands); otherwise revision n+1, superseding n.

## Dependency keys and the ontology

Dependency keys are the join between the event stream and the analytics already in the
database (`opportunity_dependencies`):

| Prefix | Example | Ontology concept |
| --- | --- | --- |
| `hub:` | `hub:TTF:2026-11-18`, `hub:NBP:2027-Q1` | Market hub and delivery period; key forms in `domain/valuation/snapshot.py` (`domain/ontology/markets.py`, `domain/valuation/periods.py`) |
| `contract:` | `contract:demo-haldor-24` | Contract (`domain/contracts`) |
| `assumption:` | `assumption:balancing.long_discount` | Approved assumption set key |
| `fx:` / `rate:` | `fx:EURGBP` (the conversion pair), `rate:EUR` | Currency pair and rate curve (`domain/ontology/currency.py`) |
| `tariff:` | `tariff:<point>:<direction>:<product>:<gas year>` | Transport tariff point |
| `outage:` | `outage:<message id>` | REMIT unavailability |

Firm marks publish `hub:<hub>:<period label>` with a digest of value, unit and note: the
event records that a mark changed, never the mark itself, because marks are desk-private.

## Ontology direction

1. The executable ontology (`domain/ontology`) is the authority; the GRM OWL export and the
   research vocabulary are derived views (consolidation in roadmap M10).
2. Add a counterparty concept before the outcome ledger (M9) needs it.
3. Every new dependency-key prefix gets an ontology concept and a test that parses it.

## How stored figures become events (M5)

| Figure | Event | Subject and dependency key | Identity | Ordering |
| --- | --- | --- | --- | --- |
| Settlement (`market_observations`) | `price.updated` | `hub:<HUB>:<period label>`; rows whose span is no day, month, quarter or season (weekends, balance of month, calendar years) are not inputs and give no event | hub key, venue, trade day | Observation instant (as publication time): an earlier figure found after a later one is out of order |
| FX fixing (`fx_observations`) | `fx.updated` | `fx:<BASE><QUOTE>` | source, pair, value date | A correction for the same value date is a revision |
| REMIT message (`remit_umm_messages`) | `outage.published` | `outage:<message id>` | the message id | Publication time and version: a stale version arriving late changes nothing |

Fixings are quoted against EUR, the pivot every conversion goes through, so the opportunity
consumer treats `fx:EURUSD` as also moving every stored pair that contains USD.

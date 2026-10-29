# RFC-0006: EEX receipt-bound reference-index evidence

Status: Accepted for staged implementation, 2026-10-29, root architecture review
under the Autonomous Execution Policy. No source activation or rights clearance.

## Evidence and problem

The official [EEX page](https://www.eex.com/en/markets/natural-gas/gas-market-transparency)
links the current TTF NGP CSV. A fresh bounded capture returned four usable rows.
[Index Description25](https://www.eex.com/fileadmin/EEX/Downloads/Trading/Indices/Index_Description_v25_clean.pdf),
sections1and2.5, describes Central European seasonal time and daily NGP semantics.
[Contract Specifications0105a](https://www.eex.com/fileadmin/EEX/Downloads/Rules/Contract_Specifications/20261002_EEX_Contract_Spezifications_0105a_E_FINAL.pdf),
section1.2.3, defines the gas delivery day at06:00. Root accepts the resulting
06:00 Europe/Berlin delivery rule, represented by EU-CAM-UTC-2025. This is a
source-to-calendar interpretation with cited evidence, separate from publication.
Neither document explicitly establishes what the CSV's Timestamp Let denotes.
It must not become an asserted first publication instant.

## Decision

Add an explicit receipt-bound mapping alongside the existing strict publication
mapping. Require the actual aware response receipt, matching the parsed capture.
Use receipt as observed/available evidence; keep publication_time_utc null and
raw provider clock text intact. Preserve exact price/volume strings, final versus
temporary status, unknown freshness/unassessed quality and reference-index labels.
A new deterministic normalization namespace prevents confusing this basis with
existing publication-bound rows. Repeated captures preserve first receipt;
changed semantic content at an existing identity must refuse, not overwrite.

The existing publication-based mapper remains strict. The new path never claims
historical availability before capture, executable quotes or redistribution rights.
Staged integration reuses market_observations, raw archives and gated operator
commands; no new service, datastore, page or endpoint. Actual persistence,
consumer adoption, production certification and source-specific rights remain
separate acceptance requirements. Tests must cover causal receipt, exact values,
DST delivery windows, duplicate/revision refusal and real PostgreSQL/HTTP reads.

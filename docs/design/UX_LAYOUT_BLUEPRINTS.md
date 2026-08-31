# UX Layout Blueprints

## Purpose

These text wireframes define the current shell contract. High-fidelity visual
references complement them under `docs/design/references/` but do not replace
runtime, provenance, accessibility, or responsive requirements.

## Web Workspace Desktop Layout

```text
+--------------------------------------------------------------------------------+
| Tools / Network | Search network assets | Gas day / Product | Live / DB / Alerts|
+--------------------------------------------------------------------------------+
| Resource pool rail | Verified and indicative topology map | Decision inspector |
|                    | Layer legend and map controls         | PnL / allocation   |
|                    | never overlap either rail             | warnings / evidence|
+--------------------------------------------------------------------------------+
```

The map search exists only on this workspace. The map surface is not mounted
behind any non-network page.

## Non-Network Workspace Desktop Layout

```text
+--------------------------------------------------------------------------------+
| Tools / Active page | Gas day / Product context        | Live / DB / Alerts    |
+--------------------------------------------------------------------------------+
| WORKFLOW GROUP   Page title         Sibling page tabs                         |
+--------------------------------------------------------------------------------+
| Dense operational content: aligned tables, controls, status, evidence          |
| No duplicate title card; no hidden map; no nested decorative cards             |
+--------------------------------------------------------------------------------+
```

At mobile widths the top bar stacks workspace, status controls, language, and
theme without an empty search row. Sibling page tabs scroll horizontally and
the document must not gain horizontal overflow.

## Scenario Workspace Layout

```text
+--------------------------------------------------------------------------------+
| Status bar                                                                      |
+------+-------------------------------+----------------------------------------+
| Nav  | Scenario inputs               | Assumptions and validation             |
|      | - resource/source             | - missing destination                  |
|      | - destination                 | - stale tariff context                 |
|      | - route preference            | - research_only                        |
|      | - volume                      | - human_review_required                |
|      | - timing                      |                                        |
|      | - price assumptions           |                                        |
+------+-------------------------------+----------------------------------------+
| Research output preview: disabled until backend workflow is available           |
+--------------------------------------------------------------------------------+
```

## Windows First Launch Layout

```text
+---------------------------------------------------------------+
| Eurogas Nexus                                                  |
+---------------------------------------------------------------+
| Backend connection                                             |
|                                                               |
| Backend base URL: [                                    ]       |
| Connection name:   [Local development                  ]       |
|                                                               |
| [Test connection] [Save and continue]                          |
|                                                               |
| Status: not connected                                          |
| Note: do not enter database URLs or vendor credentials here.   |
+---------------------------------------------------------------+
```

## Research Output Review Layout

```text
+--------------------------------------------------------------------------------+
| Candidate comparison                                                            |
+----------------+-------------+--------------+--------------+-------------------+
| Candidate      | Inputs      | Warnings     | Sources      | Review state       |
+----------------+-------------+--------------+--------------+-------------------+
| Corridor A     | partial     | 3 warnings   | 5 refs       | human review       |
| Corridor B     | missing     | 2 warnings   | 4 refs       | blocked            |
+----------------+-------------+--------------+--------------+-------------------+
| Assumptions | Missing inputs | Lineage | Data quality | Export restricted      |
+--------------------------------------------------------------------------------+
```

## Visual Priorities

1. Runtime status and warnings are visible once, in the global shell.
2. Only the active workflow surface is mounted.
3. The map or active workflow surface dominates the screen.
4. Local workflow tabs make adjacent tasks directly reachable.
5. Inspector and evidence surfaces explain selected decisions.
6. Settings never expose secrets.

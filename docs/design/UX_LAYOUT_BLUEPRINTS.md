# UX Layout Blueprints

## Purpose

These text wireframes give future client implementation agents a fixed layout
target before visual design tooling exists.

## Web Workspace Desktop Layout

```text
+--------------------------------------------------------------------------------+
| Eurogas Nexus | API ok | DB degraded | Profile: development | 2 warnings        |
+------+----------------------------------------------+--------------------------+
|      | Search assets, routes, hubs                  | Inspector                |
| Nav  +----------------------------------------------+--------------------------+
|      |                                              | Selected asset           |
| Net  |                                              | Type, country, source    |
| Scn  |                  Map Surface                 | Freshness, warnings      |
| Mkt  |                                              | Lineage tab              |
| Rev  |                                              | Sources tab              |
| Src  |                                              |                          |
| Run  +----------------------------------------------+--------------------------+
| Set  | Candidates | Missing inputs | Warnings | Sources | Lineage              |
+------+-------------------------------------------------------------------------+
```

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

1. Runtime status and warnings are visible.
2. The map or active workflow surface dominates the screen.
3. Inspector explains the selected item.
4. Bottom panel supports comparison and review.
5. Settings never expose secrets.

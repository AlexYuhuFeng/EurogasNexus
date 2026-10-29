# Regional weather weighting: primary-source review, 2026-10-30

Status: evidence only; no runtime policy, source activation or accuracy approval.

The [DESC Weather Analysis, February 2026](https://www.gasgovernance.co.uk/sites/default/files/related-files/2026-02/Strand%201%20Analysis%20Doc%20DESC_030326.pdf), page 2, explicitly supplies the following throughput-based LDZ weights for Gas Year 2024/25 on the 2020 CWV basis. Root retrieved the primary PDF after an initial HTTP429; these are not values inferred from a search snippet. Decimal sum is exactly 1.000.

| LDZ | Weight |
| --- | --- |
| EA | 0.081 |
| EM | 0.106 |
| NE | 0.065 |
| NO | 0.054 |
| NT | 0.109 |
| NW | 0.120 |
| SC | 0.093 |
| SE | 0.104 |
| SO | 0.074 |
| SW | 0.058 |
| WM | 0.090 |
| WN | 0.011 |
| WS | 0.035 |

The [Xoserve 2025 review](https://umbraco.xoserve.com/news/seasonal-normal-weather-review-2025/) says revised parameters apply from 1 October 2025 through 30 September 2030. Therefore the table above is not approved for current 2026/27 use. The 2026 report also does not establish when this exact table was publicly known during 2024/25.

CWV aggregates multiple weather components. Applying these weights to ECMWF temperature/HDD would be a separately labelled approximation requiring measured validation; it would not reproduce official CWV. Exact weather-station identities, coordinates, applicable-year mapping, geographic coverage and source retention/redistribution terms remain to be resolved. Four selected city points remain a transport probe, not national weather coverage.

The next regional policy must bind its exact source version, validity dates, station/grid mapping, weight values and approximation method into feature-policy provenance. No missing region is silently removed or reweighted. Keep regional closure separate from successful GRIB decoding and synthetic numerical tests.

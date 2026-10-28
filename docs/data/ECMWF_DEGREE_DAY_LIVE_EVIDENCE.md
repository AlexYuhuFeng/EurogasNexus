# Authentic ECMWF degree-day integration evidence

Root verification on2026-10-29, source implementation e798e2f.
Public ECMWF IFS0p25/oper run2026-10-28T00Z, 2t instantaneous fields,
steps27,30,33,36,39,42,45,48,51,54. Ten selected GRIB messages were fetched
and decoded by ecCodes2.50.0 under Linux Python3.11.12. Each saved raw hash
was checked against transport, decoded-field and point references before use.

London requested51.5N/-0.1E, one explicitly labelled probe point of weight1.
No regional aggregation, observing-station identity or demand model is implied.
Actual receipt-based prediction origin2026-10-28T23:10:20.829129Z precedes the
requested gas day2026-10-29T05Z through2026-10-30T05Z (EU-CAM-UTC-2025).
The direct application bridge generated nine clipped intervals with explicit
left-hold approximation, maximum180-minute hold and no extrapolation.

Coverage100%; duration24h; mean temperature10.75061950683596degC;
HDD18=7.24938049316404degree-days; CDD20=0. Integrated heating degree-days
also7.24938049316404 for this particular profile. These are approximate physical
calculations, not exact monetary values or evidence of regional model accuracy.
Feature policy hash:
`cae7acbe5b4e9bef326c373cc47d64114502d6b0e51402cccf81dc1fb4364ae7`.

Local raw/decoded/report artifacts reside in ignored runtime directory
`.local-runtime/delivery-20261027/ecmwf-live-gasday-20261029`.
This probe connected authentic captures directly to the bridge, not through a
production database. Repository-to-bridge SQLite tests separately use synthetic
typed inputs. Authentic persistence, historical calibration, regional weights,
API/SDK/Web consumption and backend dependency delivery remain open.

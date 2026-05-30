# V1 R9 Monitoring and Weather-Adjusted Nowcast ExecPlan

## 1. Goal

Implement monitoring alert generation and weather-adjusted demand nowcast
computation. Monitor thresholds for capacity, price, and flow; generate
research alerts. Nowcast adjusts base demand by HDD/CDD weather signals.

## 2. Internet: no

## 3. Files

- `src/eurogas_nexus/workflows/monitoring.py`
- `src/eurogas_nexus/workflows/nowcast.py`
- `src/eurogas_nexus/api/routes/v1/research.py` — add POST endpoints
- `data/release_v1/r9_monitoring_nowcast_report.md`
- `tests/workflows/test_monitoring.py`
- `tests/workflows/test_nowcast.py`

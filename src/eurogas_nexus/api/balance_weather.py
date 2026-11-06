"""Compose authorized stored ECMWF features into the supply-call scenario.

The weather route owns certification, row entitlements and the bounded forecast
reader. This orchestration uses that same path rather than bypassing its gates.
"""

import hashlib
import json
from datetime import date, datetime, timedelta

from fastapi import Request

from eurogas_nexus.api.schemas.nwe_balance import NweBalanceRequest
from eurogas_nexus.application.nwe_balance_scenario import (
    HddInput,
    NweBalanceScenarioRequest,
    WeatherInput,
)


def compose_balance_weather(payload: NweBalanceRequest, request: Request):
    from eurogas_nexus.api.routes.public.weather import compute_weather_degree_days

    runtime_proof = None
    if payload.use_runtime_history:
        payload, runtime_proof = _runtime_history(payload, request)
    base = payload.model_dump(
        exclude={"persisted_weather", "weather_profile_id", "use_runtime_history"}
    )
    profile_version = _reviewed_profile(payload, request) if payload.weather_profile_id else None
    history, forecast, evidence = [], [], []
    warnings = []
    if runtime_proof:
        evidence.append(runtime_proof)
        warnings.append("RUNTIME_BALANCE_AGGREGATION_USES_DECLARED_GCV_AND_CURRENT_SOURCE_COVERAGE")
    policy_hash = None
    for window in payload.persisted_weather:
        envelope = compute_weather_degree_days(window, request)
        meta = envelope["meta"]
        policy_hash = meta["feature_policy_hash"]
        warnings.extend(meta["warnings"])
        for row in envelope["data"].get("daily", []):
            day = date.fromisoformat(row["gas_day"])
            if not row["coverage_complete"] or row["daily_mean_hdd"] is None:
                warnings.append(f"HDD_COVERAGE_MISSING:{day}")
                continue
            if day >= payload.start + timedelta(days=payload.days):
                raise ValueError("stored weather day lies beyond scenario horizon")
            proof = {
                "day": day.isoformat(),
                "source_refs": row["source_refs"],
                "vintage": meta["selected_forecast_vintage"],
                "feature_policy_hash": policy_hash,
                "region_profile_version": profile_version,
            }
            proof_hash = hashlib.sha256(json.dumps(proof, sort_keys=True).encode()).hexdigest()
            point = HddInput(
                day=day,
                hdd=row["daily_mean_hdd"],
                available_at=row["available_at"],
                source_reference=f"ECMWF_OPEN_DATA:degree-days:{day}:{proof_hash}",
            )
            (history if day < payload.start else forecast).append(point)
            evidence.append(proof)
    if history:
        first = payload.persisted_weather[0]
        base["weather"] = WeatherInput(
            region="NWE",
            feature_policy_hash=policy_hash,
            heating_base_c=first.heating_base_c,
            gas_day_calendar=first.gas_day_calendar,
            history=tuple(history),
            forecast=tuple(forecast),
        )
    else:
        warnings.append("PERSISTED_HDD_HISTORY_UNAVAILABLE")
    return NweBalanceScenarioRequest.model_validate(base), evidence, sorted(set(warnings))


def _runtime_history(payload, request):
    from eurogas_nexus.api.dependencies.row_entitlement import require_derived_access
    from eurogas_nexus.api.routes.public.fundamentals import get_nwe_balance
    from eurogas_nexus.application.nwe_balance_scenario import BalanceHistoryInput
    from eurogas_nexus.domain.analysis_contracts import content_hash
    from eurogas_nexus.domain.market.gas_day import gas_day_label

    require_derived_access(request, ("ENTSOG", "GIE", "REMIT"), resource="nwe_balance_history")
    envelope = get_nwe_balance(request, days=payload.days, history_days=800, format="json")
    data = envelope["data"]
    if "history_read_as_of_utc" not in data:
        raise ValueError("runtime balance history is unavailable")
    origin = datetime.fromisoformat(data["history_read_as_of_utc"])
    day = date.fromisoformat(gas_day_label(origin, payload.gas_day_calendar))
    rows = [row for row in data["history"] if date.fromisoformat(row["day"]) < day]
    proof = {
        "evidence_kind": "RUNTIME_BALANCE_CURRENT_AGGREGATE",
        "received_at": origin.isoformat(),
        "assumptions": data["assumptions"],
        "history_content_hash": content_hash(rows),
    }
    supplied = tuple(
        BalanceHistoryInput(
            **{k: v for k, v in row.items() if k != "call_gwh"},
            available_at=origin,
            source_reference=f"runtime-nwe:{proof['history_content_hash']}",
        )
        for row in rows
    )
    return payload.model_copy(
        update={
            "history": supplied,
            "prediction_origin": origin,
            "use_runtime_history": False,
            "persisted_weather": tuple(
                window.model_copy(update={"prediction_origin": origin})
                for window in payload.persisted_weather
            ),
        }
    ), proof


def _reviewed_profile(payload, request):
    from fastapi import HTTPException

    from eurogas_nexus.api.routes.public.functional import factory, load_owned, owner_id
    from eurogas_nexus.application.functional_runs import stale_dependencies
    from eurogas_nexus.application.weather_region_profile import WeatherRegionProfile
    from eurogas_nexus.db.models.functional import FunctionalModelRecord

    with factory()() as session:
        model = session.get(FunctionalModelRecord, payload.weather_profile_id)
        if model is None or model.owner_id != owner_id(session, request):
            raise HTTPException(404, detail={"code": "weather_profile_not_found"})
        if model.target != "NWE_WEATHER_PROFILE" or model.status != "RESEARCH_APPROVED":
            raise HTTPException(409, detail={"code": "weather_profile_not_reviewed"})
        run = load_owned(session, model.run_id, request)
        if stale_dependencies(session, run.run_id):
            raise HTTPException(409, detail={"code": "weather_profile_dependencies_changed"})
        for window in payload.persisted_weather:
            configuration = WeatherRegionProfile.model_validate(
                window.model_dump(exclude={"prediction_origin", "gas_days"})
            ).model_dump(mode="json")
            if configuration != run.inputs:
                raise ValueError("forecast window differs from the reviewed region profile")
        return model.version_hash

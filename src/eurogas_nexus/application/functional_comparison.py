"""Sequential economic attribution between two frozen joint scenarios."""

from pydantic import BaseModel, ConfigDict

from eurogas_nexus.optimization.joint import JointRequest, optimize_joint


class JointComparison(BaseModel):
    model_config = ConfigDict(extra="forbid")
    left: JointRequest
    right: JointRequest


def attribute_joint(payload: JointComparison, checkpoint=lambda: None):
    if payload.left.days != payload.right.days:
        raise ValueError("attribution requires the same delivery horizon")
    current = payload.left.model_dump(mode="json")
    right = payload.right.model_dump(mode="json")
    current["analyze_bottlenecks"] = False
    right["analyze_bottlenecks"] = False
    first = optimize_joint(JointRequest.model_validate(current), checkpoint)
    if first["status"] != "optimal":
        return {"status": "BASELINE_INFEASIBLE", "contributions": []}
    base, value, changes = first["net_value_gbp"], first["net_value_gbp"], []
    for group in ("supplies", "sales", "transports", "stores"):
        checkpoint()
        current[group] = right[group]
        result = optimize_joint(JointRequest.model_validate(current), checkpoint)
        if result["status"] != "optimal":
            return {"status": "INTERMEDIATE_INFEASIBLE", "group": group, "contributions": changes}
        changes.append(
            {"group": group, "incremental_net_value_gbp": result["net_value_gbp"] - value}
        )
        value = result["net_value_gbp"]
    return {
        "status": "COMPLETE",
        "baseline_value_gbp": base,
        "alternative_value_gbp": value,
        "total_change_gbp": value - base,
        "contributions": changes,
        "method": "FIXED_ORDER_SEQUENTIAL_REVALUATION_ORDER_DEPENDENT",
    }

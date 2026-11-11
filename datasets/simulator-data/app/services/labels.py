"""标签/真值服务：复刻旧 get_label(df, t, t1) 语义，并提供 warn 预警提前区。"""
from __future__ import annotations

from app.config import CFG
from app.data import registry


def get_label(machine_id: int, t: int, t1: int = 0):
    if machine_id < 0 or t < 0 or t1 < 0:
        raise ValueError("machine_id / t / t1 必须 >= 0")
    e = registry.get(machine_id)
    T = e["T"]
    t_eff = t % T
    target = t_eff - t1
    if target < 0:
        # D2 修复：流开始前无真值，直接返回 0（旧版此处为不可达分支）
        return {
            "machine_id": machine_id, "t": t, "t1": t1,
            "t_effective": t_eff, "target_effective": target,
            "label": 0, "wrapped_target": False,
            "note": "t-t1 早于当前流起点，返回 0",
        }
    label = e["point_label"][target] if target < T else 0
    return {
        "machine_id": machine_id, "t": t, "t1": t1,
        "t_effective": t_eff, "target_effective": target,
        "label": label,
        "wrapped_target": (t >= T),
        "note": f"label={label} 表示时间点 {target} "
                f"{'处于异常' if label else '正常'}",
    }


def get_warn(machine_id: int, t: int):
    """warn(t) = [t, t+H) 内是否将发生故障（前端橙色预警提前区）。"""
    if machine_id < 0 or t < 0:
        raise ValueError("machine_id / t 必须 >= 0")
    e = registry.get(machine_id)
    T = e["T"]
    t_eff = t % T
    return {
        "machine_id": machine_id, "t": t, "t_effective": t_eff,
        "prediction_horizon": CFG["contract"]["prediction_horizon"],
        "warn": e["warn"][t_eff],
        "label": e["point_label"][t_eff],
    }

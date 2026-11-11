"""前端展示帧服务：组装一帧/一批数据（值 + label + warn + seam 标记）。"""
from __future__ import annotations

from app.config import CFG
from app.data import registry

MAX_COUNT = 300


def get_stream(machine_id: int, from_t: int = 0, count: int = 1,
               features: list[str] | None = None):
    if machine_id < 0 or from_t < 0:
        raise ValueError("machine_id / from_t 必须 >= 0")
    if not 1 <= count <= MAX_COUNT:
        raise ValueError(f"count 必须在 1..{MAX_COUNT}")

    e = registry.get(machine_id)
    c = CFG["contract"]
    T, warmup, step = e["T"], c["warmup_rows"], c["step"]
    H = c["prediction_horizon"]

    feats = [f for f in (features or CFG["display"]["subset"]) if f in e["col"]]
    if not feats:
        raise ValueError("features 中没有有效列名")

    frames, wrapped_at = [], []
    prev_te = None
    for k in range(count):
        t = from_t + k
        te = t % T
        s = warmup + step * te
        row = e["rows"][s] if s < e["L"] else e["rows"][-1]
        values = {f: float(row[e["col"][f]]) for f in feats}
        frames.append({
            "t": t,
            "t_effective": te,
            "wrapped": t >= T,
            "cycles": t // T,
            # 前瞻区 [t, t+H) 是否跨数据集尾部；本服务对 warn 做截断而非循环，
            # 避免把"数据集头部"当作未来真值（见《实施方案》§3.5 口径说明）
            "horizon_wrap": (te + H) > T,
            "values": values,
            "label": e["point_label"][te],
            "warn": e["warn"][te],
        })
        if prev_te is not None and te == 0 and prev_te != 0:
            wrapped_at.append(k)
        prev_te = te

    return {
        "machine_id": machine_id,
        "T": T,
        "prediction_horizon": c["prediction_horizon"],
        "features": feats,
        "frames": frames,
        "wrapped_at": wrapped_at,
    }

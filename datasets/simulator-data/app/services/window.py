"""模型输入窗口服务：复刻旧 get_history_window 语义 + 取模/边界/布局。

旧版：end = 100 + t*2; start = end - 100; window = rows[start:end]  (100 x 15)
本版：t 无上界 → t_effective = t % T；窗口恒为 rows[step*t_eff : +W]。
"""
from __future__ import annotations

from app.config import CFG
from app.data import registry
from app.data.features import FEATURES

LAYOUTS = ("time_major", "channel_major")


def contract_subset():
    c = CFG["contract"]
    return {
        "window_size": c["window_size"],
        "step": c["step"],
        "warmup_rows": c["warmup_rows"],
        "prediction_horizon": c["prediction_horizon"],
        "model_input_shape": c["model_input_shape"],
        "normalization": c["normalization"],
        "version": c["version"],
    }


def get_window(machine_id: int, t: int, layout: str = "time_major"):
    if machine_id < 0:
        raise ValueError("machine_id 必须 >= 0")
    if t < 0:
        raise ValueError("t 必须 >= 0")
    if layout not in LAYOUTS:
        raise ValueError(f"layout 必须是 {LAYOUTS} 之一")

    e = registry.get(machine_id)
    c = CFG["contract"]
    W, step = c["window_size"], c["step"]
    T = e["T"]

    t_eff = t % T
    row_start = step * t_eff
    row_end = row_start + W
    if row_end > e["L"]:
        raise ValueError(f"数据集过短: row_end={row_end} > L={e['L']}")

    idxs = [e["col"][f] for f in FEATURES]
    data = [[float(r[i]) for i in idxs] for r in e["rows"][row_start:row_end]]
    if layout == "channel_major":
        data = [[row[j] for row in data] for j in range(len(FEATURES))]

    return {
        "machine_id": machine_id,
        "t": t,
        "t_effective": t_eff,
        "wrapped": t >= T,
        "cycles": t // T,
        "T": T,
        "contract": contract_subset(),
        "window": {
            "rows": W,
            "cols": len(FEATURES),
            "layout": layout,
            "features": list(FEATURES),
            "row_start": row_start,
            "row_end": row_end,
            "dtype": c["dtype"],
            "normalization": c["normalization"],
            "data": data,
            "note": "JSON 数值为双精度，送入模型前 cast 为 float32（等价于旧版 "
                    "torch.from_numpy(win).float()）；time_major 需 "
                    "unsqueeze(0).permute(0,2,1) 得 (1,15,100)。",
        },
    }

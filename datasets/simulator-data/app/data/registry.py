"""机器数据集注册与惰性加载。

- 已随包附带的 machine_0..14.csv 原样读取（逐值一致，不重新生成）；
- machine_id >= pre_generated_machines 时按需确定性生成并落盘；
- LRU 缓存限制常驻内存；生成过程加锁，避免并发重复生成。
"""
from __future__ import annotations

import csv
import functools
import pathlib
import threading

from app.config import CFG
from app.data.features import FEATURES
from app.data.generator import ensure_machine_file

_GEN_LOCK = threading.Lock()


def _point_labels(row_label, T, warmup, step, L):
    """时间点 t 的标签 = rows[warmup+step*t : +2] 中任一 label=1。"""
    out = [0] * T
    for t in range(T):
        s = warmup + step * t
        e = min(s + step, L)
        out[t] = 1 if any(row_label[j] == 1 for j in range(s, e)) else 0
    return out


def _warn_labels(point_label, T, horizon):
    """warn(t) = [t, t+H) 内是否将发生故障（与模型 prediction_horizon 对齐）。"""
    out = [0] * T
    for t in range(T):
        out[t] = 1 if any(point_label[s] for s in range(t, min(t + horizon, T))) else 0
    return out


def _load(machine_id: int):
    c = CFG["contract"]
    warmup, step, W, H = (c["warmup_rows"], c["step"],
                          c["window_size"], c["prediction_horizon"])

    path = pathlib.Path(CFG["data"]["output_dir"]) / f"machine_{machine_id}.csv"
    if not path.exists():
        with _GEN_LOCK:
            if not path.exists():
                ensure_machine_file(machine_id, CFG)

    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.reader(f)
        header = next(reader)
        rows = list(reader)

    missing = [f for f in FEATURES if f not in header]
    if missing or "label" not in header:
        raise ValueError(f"{path.name} 缺少必要列: {missing or 'label'}")

    col = {name: header.index(name) for name in FEATURES}
    label_i = header.index("label")
    L = len(rows)
    T = (L - W) // step + 1
    if T <= 0:
        raise ValueError(f"{path.name} 数据过短(L={L})，无法凑出窗口")

    row_label = [int(float(r[label_i])) for r in rows]
    point_label = _point_labels(row_label, T, warmup, step, L)
    warn = _warn_labels(point_label, T, H)

    return {
        "path": str(path),
        "header": header,
        "rows": rows,
        "col": col,
        "L": L,
        "T": T,
        "row_label": row_label,
        "point_label": point_label,
        "warn": warn,
        "anomaly_ratio": sum(point_label) / T,
        "pre_generated": machine_id < CFG["data"]["pre_generated_machines"],
    }


@functools.lru_cache(maxsize=8)
def get(machine_id: int):
    """取一台机器的数据（带 LRU 缓存）。"""
    if machine_id < 0:
        raise ValueError("machine_id 必须 >= 0")
    return _load(machine_id)


def list_machines():
    """列出随包附带 + 已生成的所有机器。"""
    out_dir = pathlib.Path(CFG["data"]["output_dir"])
    ids = set(range(CFG["data"]["pre_generated_machines"]))
    if out_dir.exists():
        for p in out_dir.glob("machine_*.csv"):
            try:
                ids.add(int(p.stem.split("_")[1]))
            except (IndexError, ValueError):
                pass
    out = []
    for mid in sorted(ids):
        e = get(mid)
        out.append({
            "machine_id": mid,
            "rows": e["L"],
            "T": e["T"],
            "pre_generated": e["pre_generated"],
            "anomaly_ratio": round(e["anomaly_ratio"], 4),
            "label_count": sum(e["point_label"]),
        })
    return out

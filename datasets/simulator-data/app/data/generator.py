"""机器数据集生成器。

默认行为忠实复刻 production_simulator 的 generate_machine_datasets
（同一真实基底 anomaly.csv、同样的切块拼接参数），仅用于「按需新生成」
的机器（machine_id >= pre_generated_machines）。已随包附带的 15 台原样使用，
不经过本生成器，从而保证 /window 与旧版逐值一致。

保底修复：D4 头/尾 guard 正常段。
可选增强（默认关闭）：E1 多异常模板 / E2 逐机器扰动 / E3 泊松排布 /
E4 渐变劣化前兆。E5（smooth_wrap）不在数据层做，改由 /window 的 wrapped
标记实现，避免改写真实样点。
"""
from __future__ import annotations

import csv
import pathlib
import random

from app.data.features import CONTINUOUS, FEATURES


def _load_base(path):
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.reader(f)
        header = next(reader)
        rows = list(reader)
    return header, rows


def _build_templates(p1_l1, p2_l1, max_anomaly, al_lo, al_hi, count, rng):
    """E1: 从同一真实异常片段派生 K 个不同截断/相位模板。"""
    k = max(1, int(count))
    out = []
    for i in range(k):
        x = al_lo + (al_hi - al_lo) * i // max(1, k - 1)
        z = max(0, min((max_anomaly - x) // 2, min(len(p1_l1), len(p2_l1)) - 1))
        out.append([list(r) for r in p1_l1[:len(p1_l1) - z]] +
                   [list(r) for r in p2_l1[z:]])
    return out


def _ramp(last_row, first_anomaly, n_rows, header):
    """E4: 在异常前插入一段 normal→anomaly 线性过渡（仅连续特征，label=0）。"""
    if last_row is None or n_rows <= 0:
        return []
    cont = [i for i, c in enumerate(header) if c in CONTINUOUS]
    label_i = header.index("label")
    out = []
    for j in range(1, n_rows + 1):
        a = j / (n_rows + 1)
        row = list(last_row)
        for i in cont:
            try:
                v = float(last_row[i]) + (float(first_anomaly[i]) - float(last_row[i])) * a
                row[i] = f"{v:.10g}"
            except ValueError:
                pass
        row[label_i] = "0"
        out.append(row)
    return out


def _jitter(rows, header, rng, std):
    """E2: 逐机器确定性微增益/偏移 + 轻噪声，仅作用于连续特征。"""
    cont = [i for i, c in enumerate(header) if c in CONTINUOUS]
    gain = [rng.gauss(0.0, std) for _ in cont]
    bias = [rng.gauss(0.0, std) for _ in cont]
    for row in rows:
        for k, i in enumerate(cont):
            try:
                row[i] = f"{float(row[i]) * (1 + gain[k]) + bias[k]:.10g}"
            except ValueError:
                pass


def generate_rows(machine_id: int, cfg: dict):
    """生成一台机器的数据，返回 (header, rows)。rows 不含表头。"""
    d = cfg["data"]
    enh = d["enhancements"]
    header, base = _load_base(d["base_data_path"])

    # 与旧版完全一致的四段切分
    p1_l0_all = base[0:2000]
    p1_l1_all = base[2000:2020]
    p2_l1_all = base[2020:2039]
    p2_l0_all = base[2039:4040]

    rng = random.Random(d["base_seed"] + machine_id)

    min_len = d["min_len"] * 2
    nl_lo = d["normal_len_lower"] * 2
    nl_hi = min(d["normal_len_upper"] * 2, len(p1_l0_all) + len(p2_l0_all))
    al_lo = d["anomaly_len_lower"] * 2
    al_hi = min(d["anomaly_len_upper"] * 2, len(p1_l1_all) + len(p2_l1_all))
    max_anomaly = len(p1_l1_all) + len(p2_l1_all)  # 39
    templates = _build_templates(p1_l1_all, p2_l1_all, max_anomaly,
                                 al_lo, al_hi, enh["anomaly_template_count"], rng)

    segments = []
    current_len = 0
    while current_len <= min_len:
        # --- 异常段 ---
        if enh["multi_anomaly_templates"]:
            anomaly = [list(r) for r in rng.choice(templates)]
        else:
            x = rng.randint(al_lo, al_hi)
            z = (max_anomaly - x) // 2
            anomaly = ([list(r) for r in p1_l1_all[:len(p1_l1_all) - z]] +
                       [list(r) for r in p2_l1_all[z:]])

        # --- 正常段长度 ---
        if enh["poisson_placement"]:
            mean = (nl_lo + nl_hi) / 2.0
            total = max(nl_lo, min(nl_hi, int(rng.expovariate(1.0 / mean))))
        else:
            total = rng.randint(nl_lo, nl_hi)
        len_p1 = min(total // 2, len(p1_l0_all))
        len_p2 = min(total - len_p1, len(p2_l0_all))
        p1_l0 = [list(r) for r in p1_l0_all[len(p1_l0_all) - len_p1:]]
        p2_l0 = [list(r) for r in p2_l0_all[:len_p2]]

        seg = list(p1_l0)
        if enh["pre_failure_ramp"] and anomaly:
            seg += _ramp(seg[-1] if seg else None, anomaly[0],
                         enh["ramp_len_timepoints"] * 2, header)
        seg += anomaly + p2_l0
        segments.append(seg)
        current_len += len(seg)

    # --- D4: 头/尾 guard 正常段，保证 wrap 处两侧均为正常数据 ---
    head = [list(r) for r in p1_l0_all[:d["head_guard_rows"]]]
    tail = ([list(r) for r in p2_l0_all[-d["tail_guard_rows"]:]]
            if d["tail_guard_rows"] else [])
    rows = head + [r for seg in segments for r in seg] + tail

    if enh["per_machine_jitter"]:
        _jitter(rows, header, rng, enh["jitter_std"])

    ts_i = header.index("timestamp")
    for i, row in enumerate(rows):
        row[ts_i] = str(i)
    return header, rows


def ensure_machine_file(machine_id: int, cfg: dict) -> pathlib.Path:
    """文件已存在则直接返回；否则原子地生成并落盘。"""
    out = pathlib.Path(cfg["data"]["output_dir"])
    out.mkdir(parents=True, exist_ok=True)
    path = out / f"machine_{machine_id}.csv"
    if path.exists():
        return path
    header, rows = generate_rows(machine_id, cfg)
    tmp = path.with_suffix(".csv.tmp")
    with open(tmp, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)
    tmp.replace(path)
    return path

"""15 特征的单一事实来源：固定顺序、类型、量纲、展示标记。

模型输入契约要求列数与顺序不可变。新增/重排特征必须升 contract.version
并重跑 tests/test_contract_regression.py。
"""

# 固定顺序（= machine_*.csv 表头去掉 timestamp/label 后的顺序）
FEATURES = [
    "TP2", "TP3", "H1", "DV_pressure", "Reservoirs",
    "Oil_temperature", "Motor_current", "COMP", "DV_eletric",
    "Towers", "MPG", "LPS", "Pressure_switch", "Oil_level",
    "Caudal_impulses",
]

CONTINUOUS = [
    "TP2", "TP3", "H1", "DV_pressure", "Reservoirs",
    "Oil_temperature", "Motor_current",
]
BINARY = [
    "COMP", "DV_eletric", "Towers", "MPG", "LPS",
    "Pressure_switch", "Oil_level", "Caudal_impulses",
]
# 近似常量：无信息量，但必须保留在模型输入的 15 列中；仅在展示层剔除
CONSTANT = {"LPS": 0, "Oil_level": 1, "Caudal_impulses": 1}

# 前端默认展示子集（连续小多图 + 二值状态轨），剔除 3 个常量与高相关冗余特征
DISPLAY_SUBSET = [
    "TP2", "Oil_temperature", "Motor_current", "DV_pressure",
    "COMP", "DV_eletric", "Towers", "MPG", "Pressure_switch",
]

# Okabe-Ito 色盲友好调色板（与 config.yaml 一致；config 可覆盖）
COLORS = {
    "normal": "#0072B2",
    "warn": "#E69F00",
    "fault": "#D55E00",
    "prediction": "#CC79A7",
    "unavailable": "#999999",
}

# 量纲/范围（实测自基底 anomaly.csv），供 /meta 与前端独立 y 轴使用
FEATURE_META = {
    "TP2":              ("continuous", -0.026, 10.526, "bar"),
    "TP3":              ("continuous", 8.024, 10.174, "bar"),
    "H1":               ("continuous", -0.028, 10.182, "bar"),
    "DV_pressure":      ("continuous", -0.022, 5.992, "bar"),
    "Reservoirs":       ("continuous", 8.026, 10.176, "bar"),
    "Oil_temperature":  ("continuous", 57.6, 76.0, "°C"),
    "Motor_current":    ("continuous", 0.035, 6.3125, "A"),
    "COMP":             ("binary", 0, 1, "0/1"),
    "DV_eletric":       ("binary", 0, 1, "0/1"),
    "Towers":           ("binary", 0, 1, "0/1"),
    "MPG":              ("binary", 0, 1, "0/1"),
    "LPS":              ("constant", 0, 0, "0"),
    "Pressure_switch":  ("binary", 0, 1, "0/1"),
    "Oil_level":        ("constant", 1, 1, "1"),
    "Caudal_impulses":  ("constant", 1, 1, "1"),
}


def features_detail(display_subset=None):
    ds = set(display_subset if display_subset is not None else DISPLAY_SUBSET)
    out = []
    for name in FEATURES:
        typ, lo, hi, unit = FEATURE_META[name]
        item = {"name": name, "type": typ, "min": lo, "max": hi,
                "unit": unit, "display": name in ds}
        if name in CONSTANT:
            item["value"] = CONSTANT[name]
        out.append(item)
    return out

"""配置加载：默认值 + config.yaml 覆盖 + 相对路径解析。

所有数据路径在加载时解析为「相对工程根目录」的绝对路径，
因此服务从任意 cwd 启动、或整个文件夹被搬到别的服务器，都不需要改配置。
"""
from __future__ import annotations

import copy
import pathlib

import yaml

from app.data.features import FEATURES, DISPLAY_SUBSET, COLORS

ROOT = pathlib.Path(__file__).resolve().parent.parent

_DEFAULTS = {
    "server": {"host": "0.0.0.0", "port": 8000, "cors_origins": ["*"]},
    "data": {
        "base_data_path": "data/anomaly.csv",
        "output_dir": "data/machines",
        "pre_generated_machines": 15,
        "base_seed": 42,
        "min_len": 10000,
        "normal_len_lower": 250,
        "normal_len_upper": 1250,
        "anomaly_len_lower": 10,
        "anomaly_len_upper": 19,
        "head_guard_rows": 200,
        "tail_guard_rows": 200,
        "enhancements": {
            "per_machine_jitter": False,
            "multi_anomaly_templates": False,
            "poisson_placement": False,
            "pre_failure_ramp": False,
            "smooth_wrap": False,
            "jitter_std": 0.01,
            "anomaly_template_count": 4,
            "ramp_len_timepoints": 20,
        },
    },
    "contract": {
        "window_size": 100,
        "step": 2,
        "warmup_rows": 100,
        "prediction_horizon": 20,
        "time_step": 20,
        "normalization": "none",
        "dtype": "float32",
        "model_input_shape": [1, 15, 100],
        "version": "1.0",
    },
    "display": {"subset": list(DISPLAY_SUBSET), "colors": dict(COLORS)},
}


def _merge(base, override):
    for k, v in (override or {}).items():
        if isinstance(v, dict) and isinstance(base.get(k), dict):
            _merge(base[k], v)
        else:
            base[k] = v
    return base


def load_config(path=None):
    p = pathlib.Path(path) if path else ROOT / "config.yaml"
    raw = yaml.safe_load(p.read_text(encoding="utf-8")) if p.exists() else {}
    cfg = _merge(copy.deepcopy(_DEFAULTS), raw)
    # 特征顺序单一事实来源，不信任 config 里的任何副本
    cfg["contract"]["features"] = list(FEATURES)
    # 相对路径 → 相对工程根目录的绝对路径
    for key in ("base_data_path", "output_dir"):
        v = pathlib.Path(cfg["data"][key])
        cfg["data"][key] = str(v if v.is_absolute() else (ROOT / v).resolve())
    return cfg


CFG = load_config()

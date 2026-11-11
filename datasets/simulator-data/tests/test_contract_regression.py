"""★ 关键验收：契约一致性回归测试。

证明「换成独立服务后，模型看到的数据与旧版 production_simulator 逐值一致」。
旧版 get_history_window / get_label 的语义以冻结副本内置于此，不依赖原工程，
因此本测试在工程整体打包到别的服务器后仍可运行。

注：旧版"同模型概率一致"一项需要外部部署的 CNN-LSTM 权重，本测试只做
输入张量逐值比对——输入一致则同模型推理结果必然一致（deterministic eval）。
"""
from __future__ import annotations

import csv
import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.config import CFG                      # noqa: E402
from app.data.features import FEATURES         # noqa: E402
from app.services import window as svc_window  # noqa: E402
from app.services import labels as svc_labels  # noqa: E402

CSV = pathlib.Path(CFG["data"]["output_dir"]) / "machine_0.csv"


# ---- 旧版冻结副本（对应 model_predict/online_inference.py）----
def legacy_get_history_window(path, t, window_len=100):
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.reader(f)
        header = next(reader)
        rows = list(reader)
    end_row_idx = 100 + t * 2
    start_row_idx = end_row_idx - window_len
    if start_row_idx < 0 or end_row_idx > len(rows):
        raise ValueError("越界")
    valid = [i for i, c in enumerate(header) if c not in ("timestamp", "label")]
    return [[float(r[i]) for i in valid] for r in rows[start_row_idx:end_row_idx]]


def legacy_get_label(path, t, t1):
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.reader(f)
        header = next(reader)
        rows = list(reader)
    li = header.index("label")
    s = 100 + (t - t1) * 2
    if s < 0:
        return 0
    return 1 if any(rows[j][li] == "1" for j in range(s, min(s + 2, len(rows)))) else 0


class TestContractRegression(unittest.TestCase):
    def test_window_exact_match_with_legacy(self):
        """核心：/window 的 time_major.data 与旧版逐值、逐序一致。"""
        with open(CSV, encoding="utf-8") as f:
            T = (sum(1 for _ in f) - 1 - 100) // 2 + 1
        for t in [0, 1, 2, 7, 50, 99, 100, 500, 1000, T - 2, T - 1]:
            legacy = legacy_get_history_window(CSV, t)
            got = svc_window.get_window(0, t)["window"]["data"]
            self.assertEqual(len(got), 100)
            self.assertEqual(len(got[0]), 15)
            self.assertEqual(got, legacy, f"t={t} 与旧版不一致")

    def test_wrap_is_equivalent_to_modulo(self):
        """t >= T 时取模后的窗口，与旧版在 t%T 处的窗口逐值一致。"""
        with open(CSV, encoding="utf-8") as f:
            T = (sum(1 for _ in f) - 1 - 100) // 2 + 1
        for t in [T, T + 1, T + 7, 2 * T + 33, 10 * T + 5]:
            te = t % T
            r = svc_window.get_window(0, t)
            self.assertTrue(r["wrapped"])
            self.assertEqual(r["t_effective"], te)
            self.assertEqual(r["window"]["data"], legacy_get_history_window(CSV, te))

    def test_channel_major_is_transpose(self):
        a = svc_window.get_window(0, 5, "time_major")["window"]["data"]
        b = svc_window.get_window(0, 5, "channel_major")["window"]["data"]
        self.assertEqual(len(b), 15)
        self.assertEqual(len(b[0]), 100)
        self.assertEqual(b, [[row[j] for row in a] for j in range(15)])

    def test_no_label_leakage_in_window(self):
        """模型输入窗口不得含任何标签字段。"""
        r = svc_window.get_window(0, 10)
        blob = repr(r).lower()
        self.assertNotIn('"label"', blob)
        self.assertNotIn('"warn"', blob)
        self.assertEqual(r["window"]["features"], FEATURES)
        self.assertEqual(r["contract"]["normalization"], "none")
        self.assertEqual(r["contract"]["model_input_shape"], [1, 15, 100])

    def test_label_matches_legacy(self):
        for t in [10, 50, 100, 500, 1000]:
            for t1 in [0, 10]:
                self.assertEqual(
                    svc_labels.get_label(0, t, t1)["label"],
                    legacy_get_label(CSV, t, t1),
                    f"t={t}, t1={t1}",
                )

    def test_label_before_stream_start_returns_zero(self):
        self.assertEqual(svc_labels.get_label(0, 0, 10)["label"], 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)

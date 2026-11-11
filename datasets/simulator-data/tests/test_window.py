"""窗口/取模/标签/展示/惰性生成的不变量测试（仅用标准库 unittest）。"""
from __future__ import annotations

import pathlib
import shutil
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app import config                        # noqa: E402
from app.data import generator, registry      # noqa: E402
from app.services import (window as svc_window, labels as svc_labels,
                          display as svc_display)  # noqa: E402

CFG = config.CFG


class TestWindowInvariants(unittest.TestCase):
    def test_shape_bounds_and_no_nan(self):
        for mid in [0, 1, 14]:
            for t in [0, 1, 100, 5000, 99999]:
                r = svc_window.get_window(mid, t)
                w = r["window"]
                self.assertEqual((w["rows"], w["cols"]), (100, 15))
                self.assertEqual(len(w["data"]), 100)
                self.assertTrue(all(len(row) == 15 for row in w["data"]))
                self.assertLessEqual(w["row_end"], registry.get(mid)["L"])
                self.assertEqual(w["row_start"], 2 * r["t_effective"])
                for row in w["data"]:
                    for v in row:
                        self.assertFalse(v != v, "出现 NaN")

    def test_modulo_and_wrapped_flag(self):
        T = registry.get(0)["T"]
        self.assertEqual(svc_window.get_window(0, T)["t_effective"], 0)
        self.assertTrue(svc_window.get_window(0, T)["wrapped"])
        self.assertFalse(svc_window.get_window(0, T - 1)["wrapped"])
        self.assertEqual(svc_window.get_window(0, 3 * T + 8)["t_effective"], 8)

    def test_T_formula(self):
        for mid in [0, 1, 14]:
            e = registry.get(mid)
            self.assertEqual(e["T"], (e["L"] - 100) // 2 + 1)

    def test_determinism(self):
        a = svc_window.get_window(0, 4321)
        b = svc_window.get_window(0, 4321)
        self.assertEqual(a, b)

    def test_invalid_params(self):
        for bad in [(-1, 0), (0, -1)]:
            with self.assertRaises(ValueError):
                svc_window.get_window(*bad)
        with self.assertRaises(ValueError):
            svc_window.get_window(0, 1, "bad_layout")


class TestDataAndLabels(unittest.TestCase):
    def test_head_tail_are_normal(self):
        """D4: 头部 100 行与 t=T-1 窗口均为正常段（wrap 平滑前提）。"""
        for mid in [0, 1, 14]:
            e = registry.get(mid)
            self.assertEqual(sum(e["row_label"][:100]), 0, f"machine_{mid} 头部异常")
            te = e["T"] - 1
            self.assertEqual(sum(e["row_label"][2 * te:100 + 2 * te]), 0,
                             f"machine_{mid} 尾部窗口异常")

    def test_warn_alignment(self):
        """warn(t) == 1 当且仅当 [t, t+H) 内有 label=1。"""
        e = registry.get(0)
        H = CFG["contract"]["prediction_horizon"]
        for t in [0, 50, 200, 1000, e["T"] - 30]:
            expect = 1 if any(e["point_label"][s]
                              for s in range(t, min(t + H, e["T"]))) else 0
            self.assertEqual(e["warn"][t], expect, f"t={t}")

    def test_stream_count_and_features(self):
        r = svc_display.get_stream(0, 200, 5)
        self.assertEqual(len(r["frames"]), 5)
        self.assertEqual(r["frames"][0]["t"], 200)
        self.assertIn("label", r["frames"][0])
        self.assertIn("warn", r["frames"][0])
        self.assertNotIn("LPS", r["features"])      # 常量特征不展示
        for f in r["frames"]:
            self.assertIn(f["label"], (0, 1))
            self.assertIn(f["warn"], (0, 1))
        with self.assertRaises(ValueError):
            svc_display.get_stream(0, 0, 999)

    def test_stream_wrapped_at(self):
        T = registry.get(0)["T"]
        r = svc_display.get_stream(0, T - 2, 6)
        self.assertIn(2, r["wrapped_at"])
        self.assertEqual(r["frames"][2]["t_effective"], 0)
        self.assertTrue(r["frames"][2]["wrapped"])
        self.assertEqual(r["frames"][2]["cycles"], 1)

    def test_cycles_and_horizon_wrap(self):
        """评审 P0-3：wrap / cycles / horizon_wrap 元数据齐全且语义正确。"""
        from app.services import window as w
        T = registry.get(0)["T"]
        H = CFG["contract"]["prediction_horizon"]
        r = w.get_window(0, 2 * T + 7)
        self.assertEqual(r["t_effective"], 7)
        self.assertEqual(r["cycles"], 2)
        self.assertTrue(r["wrapped"])
        # 尾部最后一帧的前瞻区必然跨数据集尾
        tail = svc_display.get_stream(0, T - 1, 1)["frames"][0]
        self.assertTrue(tail["horizon_wrap"])
        self.assertEqual(tail["t_effective"] + H > T, tail["horizon_wrap"])
        # 中部帧不跨
        mid = svc_display.get_stream(0, 100, 1)["frames"][0]
        self.assertFalse(mid["horizon_wrap"])
        self.assertEqual(mid["cycles"], 0)

    def test_label_t1_semantics(self):
        e = registry.get(0)
        self.assertEqual(svc_labels.get_label(0, 210, 10)["label"],
                         e["point_label"][200])
        self.assertEqual(svc_labels.get_label(0, 0, 10)["label"], 0)


class TestLazyGeneration(unittest.TestCase):
    """按需生成：确定性、落盘、guard 正常段；只写临时目录，不污染工程。"""

    def test_lazy_generate_to_temp(self):
        orig = CFG["data"]["output_dir"]
        tmp = tempfile.mkdtemp(prefix="sim_lazy_")
        registry.get.cache_clear()
        try:
            CFG["data"]["output_dir"] = tmp
            e1 = registry.get(15)
            self.assertGreater(e1["L"], 20000)
            self.assertGreater(e1["T"], 1000)
            self.assertEqual(sum(e1["row_label"][:100]), 0)   # head guard
            te = e1["T"] - 1
            self.assertEqual(sum(e1["row_label"][2 * te:100 + 2 * te]), 0)  # tail guard
            self.assertTrue(pathlib.Path(tmp, "machine_15.csv").exists())

            # 重启/清缓存后结果完全一致
            registry.get.cache_clear()
            e2 = registry.get(15)
            self.assertEqual(e1["rows"], e2["rows"])
            self.assertEqual(e1["point_label"], e2["point_label"])
        finally:
            CFG["data"]["output_dir"] = orig
            registry.get.cache_clear()
            shutil.rmtree(tmp, ignore_errors=True)

    def test_generator_is_deterministic(self):
        h1, r1 = generator.generate_rows(77, CFG)
        h2, r2 = generator.generate_rows(77, CFG)
        self.assertEqual(h1, h2)
        self.assertEqual(r1, r2)
        self.assertEqual(len(r1[0]), 17)     # timestamp + 15 + label
        self.assertEqual(r1[0][0], "0")
        self.assertEqual(r1[-1][0], str(len(r1) - 1))


if __name__ == "__main__":
    unittest.main(verbosity=2)

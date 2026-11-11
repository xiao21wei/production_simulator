import json
import tempfile
import unittest
from pathlib import Path

from simulator.config import DEFAULT_CONFIG_PATH, load_simulator_config


class SimulatorConfigTest(unittest.TestCase):
    def test_default_config_contains_scheduling_environment(self):
        config = load_simulator_config()

        self.assertEqual(
            Path(DEFAULT_CONFIG_PATH).resolve(),
            Path("simulator_config.json").resolve(),
        )
        self.assertEqual(config["time"]["speed"], 10.0)
        self.assertEqual(config["visualization"]["speed"], 2.0)
        self.assertEqual(
            config["visualization"]["display_percent"], 100
        )
        self.assertEqual(config["visualization"]["host"], "0.0.0.0")
        self.assertEqual(config["visualization"]["port"], 8000)
        self.assertEqual(
            config["detection_data"]["base_url"],
            "http://192.168.1.68:8068",
        )
        self.assertEqual(
            config["detection_data"]["history_points"],
            60,
        )
        self.assertEqual(
            config["detection_data"]["poll_interval_ms"],
            1000,
        )
        self.assertEqual(
            config["detection_data"]["prediction_interval"],
            5,
        )
        self.assertIn("dataset_root", config["paths"])
        self.assertIn("input_file", config["paths"])
        self.assertIn("additional_file", config["paths"])
        self.assertTrue(config["paths"]["input_file"].startswith("datasets/raw/"))
        self.assertTrue(config["paths"]["additional_file"].startswith("datasets/add/"))
        self.assertIn("schedule_file", config["paths"])
        self.assertIn("gantt_file", config["paths"])
        self.assertIn("seed", config["simulation"])
        self.assertNotIn("model", config)

    def test_custom_config_path_is_loaded(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            custom_path = Path(temp_dir) / "custom.json"
            config = json.loads(Path(DEFAULT_CONFIG_PATH).read_text("utf-8"))
            config["time"]["speed"] = 25
            custom_path.write_text(
                json.dumps(config, ensure_ascii=False),
                encoding="utf-8",
            )

            loaded = load_simulator_config(custom_path)

        self.assertEqual(loaded["time"]["speed"], 25)

    def test_invalid_speed_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            custom_path = Path(temp_dir) / "invalid.json"
            config = json.loads(Path(DEFAULT_CONFIG_PATH).read_text("utf-8"))
            config["time"]["speed"] = 0
            custom_path.write_text(json.dumps(config), encoding="utf-8")

            with self.assertRaises(ValueError):
                load_simulator_config(custom_path)

    def test_invalid_detection_history_size_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            custom_path = Path(temp_dir) / "invalid-detection.json"
            config = json.loads(Path(DEFAULT_CONFIG_PATH).read_text("utf-8"))
            config["detection_data"]["history_points"] = 301
            custom_path.write_text(json.dumps(config), encoding="utf-8")

            with self.assertRaises(ValueError):
                load_simulator_config(custom_path)

    def test_invalid_detection_prediction_interval_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            custom_path = Path(temp_dir) / "invalid-prediction.json"
            config = json.loads(Path(DEFAULT_CONFIG_PATH).read_text("utf-8"))
            config["detection_data"]["prediction_interval"] = 0
            custom_path.write_text(json.dumps(config), encoding="utf-8")

            with self.assertRaises(ValueError):
                load_simulator_config(custom_path)


if __name__ == "__main__":
    unittest.main()

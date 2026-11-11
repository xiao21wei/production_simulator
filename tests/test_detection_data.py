import unittest

from simulator.detection_data import (
    DETECTION_FIELDS,
    MachineDetectionDataProvider,
)


class MachineDetectionDataTest(unittest.TestCase):
    def setUp(self):
        self.provider = MachineDetectionDataProvider(
            base_url="http://detection.test",
            history_points=60,
            poll_interval_ms=1000,
        )
        self.requested_paths = []
        self.provider._get_json = self._fake_get_json

    def _fake_get_json(self, path, query=None):
        self.requested_paths.append(path)
        if path == "/api/v1/meta":
            return {
                "contract": {"prediction_horizon": 20},
                "features_detail": [
                    {
                        "name": name,
                        "type": "continuous",
                        "min": 0,
                        "max": 100,
                        "unit": "",
                    }
                    for name in DETECTION_FIELDS
                ],
            }
        if path == "/api/v1/machines":
            return {
                "machines": [
                    {"machine_id": machine_id, "T": 100}
                    for machine_id in range(15)
                ]
            }
        if path == "/api/v1/overview":
            timestamp = int(query["t"])
            count = int(query.get("machine_count", 15))
            return {
                "t": timestamp,
                "prediction_horizon": 20,
                "features": list(DETECTION_FIELDS),
                "machines": [
                    {
                        "machine_id": machine_id,
                        "T": 100,
                        "t_effective": timestamp % 100,
                        "label": int(timestamp % 100 in range(80, 90)),
                        "warn": int(timestamp % 100 in range(75, 90)),
                        "values": {
                            field: index + timestamp / 100
                            for index, field in enumerate(DETECTION_FIELDS)
                        },
                    }
                    for machine_id in range(count)
                ],
            }
        if path == "/api/v1/predict":
            timestamp = int(query["t"])
            machine_id = int(query["machine_id"])
            return {
                "machine_id": machine_id,
                "t": timestamp,
                "t_effective": timestamp % 100,
                "prediction_horizon": 20,
                "probability": 0.95 if machine_id == 1 else 0.1,
                "threshold": 0.93,
                "is_alarm": machine_id == 1,
                "model": {
                    "loaded": True,
                    "device": "cpu",
                    "error": None,
                },
            }
        raise AssertionError(f"Unexpected endpoint: {path}")

    def test_metadata_only_requests_supported_endpoints(self):
        meta = self.provider.meta()
        machines = self.provider.machines()

        self.assertEqual(meta["history_points"], 60)
        self.assertEqual(meta["poll_interval_ms"], 1000)
        self.assertEqual(meta["prediction_interval"], 5)
        self.assertEqual(
            {
                item["anomaly_type"]: item["default_duration"]
                for item in meta["prediction_anomaly_options"]
            },
            {
                "short_failure": 3,
                "medium_failure": 10,
                "long_failure": 30,
                "degraded": 15,
            },
        )
        self.assertEqual(
            [item["name"] for item in meta["selected_features"]],
            list(DETECTION_FIELDS),
        )
        self.assertEqual(len(machines["machines"]), 15)
        self.assertNotIn("/api/v1/stream", self.requested_paths)
        self.assertNotIn("/api/v1/overview", self.requested_paths)

    def test_overview_returns_all_machine_snapshots(self):
        payload = self.provider.overview(87, machine_count=6)

        self.assertEqual(payload["t"], 87)
        self.assertEqual(len(payload["machines"]), 6)
        for machine in payload["machines"]:
            self.assertEqual(
                set(machine["values"]),
                set(DETECTION_FIELDS),
            )
            self.assertIn("label", machine)
            self.assertIn("warn", machine)
            self.assertIn("t_effective", machine)
        self.assertIn("/api/v1/overview", self.requested_paths)
        self.assertNotIn("/api/v1/stream", self.requested_paths)

    def test_predict_uses_overview_aligned_time_for_each_machine(self):
        payload = self.provider.predict(85, machine_count=3)

        self.assertEqual(payload["t"], 85)
        self.assertEqual(payload["prediction_interval"], 5)
        self.assertNotIn("anomaly_type", payload)
        self.assertNotIn("anomaly_duration", payload)
        self.assertEqual(len(payload["predictions"]), 3)
        self.assertEqual(
            [item["machine_id"] for item in payload["predictions"]],
            [0, 1, 2],
        )
        self.assertEqual(
            [item["is_alarm"] for item in payload["predictions"]],
            [False, True, False],
        )
        self.assertTrue(
            all(item["t"] == 85 for item in payload["predictions"])
        )
        self.assertEqual(
            self.requested_paths.count("/api/v1/predict"),
            3,
        )
        self.assertNotIn("/api/v1/stream", self.requested_paths)


if __name__ == "__main__":
    unittest.main()

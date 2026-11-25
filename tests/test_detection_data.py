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
        if path == "/api/v1/window":
            return {
                "machine_id": int(query["machine_id"]),
                "t": int(query["t"]),
                "t_effective": int(query["t"]) % 100,
                "T": 100,
                "window": {
                    "features": list(DETECTION_FIELDS),
                    "data": [
                        [index + row for index in range(15)]
                        for row in range(100)
                    ],
                },
            }
        if path == "/api/v1/truth":
            return {
                "machine_id": int(query["machine_id"]),
                "t": int(query["t"]),
                "label": 1,
                "warn": 1,
                "next_anomaly_t": 90,
            }
        if path == "/api/v1/events":
            return {
                "machine_id": int(query["machine_id"]),
                "T": 100,
                "count": 1,
                "events": [{"start": 85, "end": 90, "duration": 6}],
            }
        if path == "/api/v1/stream":
            start = int(query["from_t"])
            count = int(query["count"])
            return {
                "machine_id": int(query["machine_id"]),
                "T": 100,
                "prediction_horizon": 20,
                "features": list(DETECTION_FIELDS),
                "frames": [
                    {
                        "t": start + index,
                        "label": int(start + index >= 85),
                        "warn": 1,
                        "values": {},
                    }
                    for index in range(count)
                ],
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
                "short_failure": 10,
                "medium_failure": 20,
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

    def test_detailed_model_evidence_uses_legacy_endpoints(self):
        window = self.provider.window(machine_id=2, t=85)
        prediction = self.provider.predict_one(machine_id=2, t=85)
        truth = self.provider.truth(machine_id=2, t=85)
        events = self.provider.events(machine_id=2)
        stream = self.provider.stream(
            machine_id=2,
            from_t=85,
            count=20,
        )

        self.assertEqual(window["window"]["features"], list(DETECTION_FIELDS))
        self.assertEqual(len(window["window"]["data"]), 100)
        self.assertEqual(prediction["machine_id"], 2)
        self.assertEqual(prediction["threshold"], 0.93)
        self.assertEqual(truth["label"], 1)
        self.assertEqual(events["events"][0]["start"], 85)
        self.assertEqual(len(stream["frames"]), 20)
        self.assertIn("/api/v1/window", self.requested_paths)
        self.assertIn("/api/v1/truth", self.requested_paths)
        self.assertIn("/api/v1/events", self.requested_paths)
        self.assertIn("/api/v1/stream", self.requested_paths)


class MfddtDetectionDataTest(unittest.TestCase):
    def setUp(self):
        self.provider = MachineDetectionDataProvider(
            base_url="http://detection.test",
            protocol="mfddt",
            history_points=60,
            poll_interval_ms=1000,
        )
        self.requests = []
        self.provider._get_json = self._fake_get_json

    def _fake_get_json(self, path, query=None):
        self.requests.append((path, dict(query or {})))
        if path == "/api/v1/meta":
            return {
                "service": "mfddt-anomaly-simulator",
                "features_detail": [
                    {
                        "name": "ref",
                        "index": 0,
                        "label": "键相参考信号",
                        "unit": "V",
                        "agg_min": 0,
                        "agg_max": 3.61,
                    },
                    {
                        "name": "torque",
                        "index": 1,
                        "label": "电机转矩",
                        "unit": "N·m",
                        "agg_min": -0.6,
                        "agg_max": 0.6,
                    },
                ],
            }
        if path == "/api/v1/machines":
            return {
                "machines": [
                    {"machine_id": machine_id, "T": 4000}
                    for machine_id in range(6)
                ]
            }
        if path == "/api/v1/overview":
            timestamp = int(query["t"])
            count = int(query["machine_count"])
            return {
                "t": timestamp,
                "features": ["ref", "torque"],
                "machines": [
                    {
                        "machine_id": machine_id,
                        "T": 4000,
                        "t_effective": timestamp % 4000,
                        "label": 1,
                        "values": {
                            "ref": 1.2,
                            "torque": 0.4,
                        },
                    }
                    for machine_id in range(count)
                ],
            }
        if path == "/api/v1/detect/batch":
            timestamp = int(query["t"])
            count = int(query["machine_count"])
            return {
                "t": timestamp,
                "results": [
                    {
                        "machine_id": machine_id,
                        "t": timestamp,
                        "t_effective": timestamp % 4000,
                        "prediction": int(machine_id == 1),
                        "is_alarm": machine_id == 1,
                        "anomaly_score": (
                            0.95 if machine_id == 1 else 0.1
                        ),
                        "severity_level": (
                            "L3" if machine_id == 1 else "L0"
                        ),
                        "severity_name": (
                            "严重" if machine_id == 1 else "正常"
                        ),
                        "anomaly_type": (
                            "medium_failure"
                            if machine_id == 1
                            else "normal"
                        ),
                        "recommended_duration": (
                            10 if machine_id == 1 else 0
                        ),
                    }
                    for machine_id in range(count)
                ],
            }
        raise AssertionError(f"Unexpected endpoint: {path}")

    def test_mfddt_meta_and_overview_use_configured_channels(self):
        meta = self.provider.meta()
        overview = self.provider.overview(85, machine_count=6)

        self.assertEqual(meta["protocol"], "mfddt")
        self.assertEqual(
            [field["name"] for field in meta["selected_features"]],
            ["ref", "torque"],
        )
        self.assertEqual(overview["machines"][0]["label"], 0)
        self.assertEqual(overview["machines"][0]["warn"], 0)
        self.assertEqual(
            overview["machines"][0]["values"],
            {"ref": 1.2, "torque": 0.4},
        )
        overview_request = next(
            query
            for path, query in self.requests
            if path == "/api/v1/overview"
        )
        self.assertEqual(overview_request["agg"], "default")

    def test_mfddt_predict_uses_batch_detection(self):
        payload = self.provider.predict(315, machine_count=6)

        self.assertEqual(len(payload["predictions"]), 6)
        self.assertTrue(payload["predictions"][1]["is_alarm"])
        self.assertEqual(
            payload["predictions"][1]["severity_level"],
            "L3",
        )
        self.assertEqual(
            payload["predictions"][1]["anomaly_type"],
            "medium_failure",
        )
        self.assertEqual(
            self.requests.count(("/api/v1/detect/batch", {
                "t": 315,
                "machine_count": 6,
                "include_detail": "true",
                "include_truth": "false",
            })),
            1,
        )


if __name__ == "__main__":
    unittest.main()

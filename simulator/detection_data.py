"""Proxy client for the anomaly-detection overview HTTP API."""

import json
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlencode
from urllib.request import urlopen

from simulator.anomaly import (
    MACHINE_ANOMALY_DEFAULT_DURATIONS,
    MachineAnomalyType,
)


DEFAULT_DETECTION_API_URL = "http://192.168.1.68:8068"
DETECTION_FIELDS = (
    "TP2",
    "TP3",
    "H1",
    "DV_pressure",
    "Reservoirs",
    "Oil_temperature",
    "Motor_current",
)
DETECTION_FIELD_LABELS = {
    "TP2": "TP2 压力",
    "TP3": "TP3 压力",
    "H1": "H1 压力",
    "DV_pressure": "压差",
    "Reservoirs": "储气罐压力",
    "Oil_temperature": "油温",
    "Motor_current": "电机电流",
}
HISTORY_POINT_COUNT = 60
PREDICTION_INTERVAL = 5


class MachineDetectionDataProvider:
    """Read metadata, machine IDs and one-second overview snapshots."""

    def __init__(
        self,
        base_url=DEFAULT_DETECTION_API_URL,
        timeout=10,
        history_points=HISTORY_POINT_COUNT,
        poll_interval_ms=1000,
        prediction_interval=PREDICTION_INTERVAL,
    ):
        self.base_url = str(base_url).rstrip("/")
        self.timeout = float(timeout)
        self.history_points = int(history_points)
        self.poll_interval_ms = int(poll_interval_ms)
        self.prediction_interval = int(prediction_interval)
        if self.prediction_interval < 1:
            raise ValueError(
                "prediction_interval must be a positive integer."
            )
        self.meta_payload = None
        self.machines_payload = None
        self.feature_meta = {}

    def _get_json(self, path, query=None):
        url = f"{self.base_url}{path}"
        if query:
            url += "?" + urlencode(query)
        with urlopen(url, timeout=self.timeout) as response:
            return json.loads(response.read().decode("utf-8"))

    def _initialize(self):
        if self.meta_payload is not None:
            return
        self.meta_payload = self._get_json("/api/v1/meta")
        self.machines_payload = self._get_json("/api/v1/machines")
        self.feature_meta = {
            feature["name"]: feature
            for feature in self.meta_payload.get("features_detail", [])
            if feature.get("name") in DETECTION_FIELDS
        }

    def meta(self):
        self._initialize()
        return {
            **self.meta_payload,
            "selected_features": [
                {
                    "name": name,
                    "label": DETECTION_FIELD_LABELS.get(name, name),
                    **self.feature_meta.get(name, {}),
                }
                for name in DETECTION_FIELDS
            ],
            "history_points": self.history_points,
            "poll_interval_ms": self.poll_interval_ms,
            "prediction_interval": self.prediction_interval,
            "prediction_anomaly_options": [
                {
                    "anomaly_type": anomaly.value,
                    "default_duration": (
                        MACHINE_ANOMALY_DEFAULT_DURATIONS[anomaly]
                    ),
                }
                for anomaly in MachineAnomalyType
            ],
        }

    def machines(self):
        self._initialize()
        return {
            **self.machines_payload,
            "machines": [
                {
                    "machine_id": int(machine["machine_id"]),
                    "T": int(machine.get("T", 0)),
                }
                for machine in self.machines_payload.get("machines", [])
            ],
        }

    def overview(self, t=0, machine_count=None):
        self._initialize()
        query = {
            "t": max(0, int(t)),
            "features": ",".join(DETECTION_FIELDS),
        }
        if machine_count is not None:
            normalized_count = int(machine_count)
            if not 1 <= normalized_count <= 500:
                raise ValueError(
                    "machine_count must be between 1 and 500."
                )
            query["machine_count"] = normalized_count
        payload = self._get_json(
            "/api/v1/overview",
            query,
        )
        machines = []
        for machine in payload.get("machines", []):
            values = machine.get("values", {})
            machines.append(
                {
                    "machine_id": int(machine["machine_id"]),
                    "T": int(machine.get("T", 0)),
                    "t_effective": int(machine.get("t_effective", 0)),
                    "label": int(machine.get("label", 0)),
                    "warn": int(machine.get("warn", 0)),
                    "values": {
                        name: float(values.get(name, 0))
                        for name in DETECTION_FIELDS
                    },
                }
            )
        return {
            "t": int(payload.get("t", t)),
            "prediction_horizon": int(
                payload.get("prediction_horizon", 20)
            ),
            "features": payload.get("features", list(DETECTION_FIELDS)),
            "machines": machines,
        }

    def predict(self, t=0, machine_count=1):
        machine_count = int(machine_count)
        if not 1 <= machine_count <= 500:
            raise ValueError(
                "machine_count must be between 1 and 500."
            )
        machine_ids = range(machine_count)
        with ThreadPoolExecutor(
            max_workers=min(4, max(1, machine_count))
        ) as executor:
            futures = {
                machine_id: executor.submit(
                    self._get_json,
                    "/api/v1/predict",
                    {
                        "machine_id": machine_id,
                        "t": max(0, int(t)),
                        "include_truth": "false",
                    },
                )
                for machine_id in machine_ids
            }
            predictions = []
            for machine_id, future in futures.items():
                try:
                    payload = future.result()
                    predictions.append(
                        {
                            "machine_id": machine_id,
                            "t": int(payload.get("t", t)),
                            "t_effective": int(
                                payload.get("t_effective", 0)
                            ),
                            "prediction_horizon": int(
                                payload.get("prediction_horizon", 20)
                            ),
                            "probability": float(
                                payload.get("probability", 0)
                            ),
                            "threshold": float(
                                payload.get("threshold", 0)
                            ),
                            "is_alarm": bool(
                                payload.get("is_alarm", False)
                            ),
                            "model": payload.get("model"),
                        }
                    )
                except Exception as exc:
                    predictions.append(
                        {
                            "machine_id": machine_id,
                            "t": int(t),
                            "error": str(exc),
                            "is_alarm": False,
                        }
                    )
        return {
            "t": int(t),
            "prediction_interval": self.prediction_interval,
            "predictions": predictions,
        }

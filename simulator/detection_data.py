"""Proxy client for the anomaly-detection overview HTTP API."""

import json
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlencode
from urllib.request import urlopen

from simulator.anomaly import (
    MACHINE_ANOMALY_DEFAULT_DURATIONS,
    MachineAnomalyType,
)


DEFAULT_DETECTION_API_URL = "http://127.0.0.1:8068"
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
        protocol="legacy",
        timeout=10,
        history_points=HISTORY_POINT_COUNT,
        poll_interval_ms=1000,
        prediction_interval=PREDICTION_INTERVAL,
    ):
        self.base_url = str(base_url).rstrip("/")
        self.protocol = str(protocol or "legacy").lower()
        if self.protocol not in {"legacy", "mfddt"}:
            raise ValueError("protocol must be 'legacy' or 'mfddt'.")
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
        self.selected_features = list(DETECTION_FIELDS)

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
        features_detail = self.meta_payload.get("features_detail", [])
        if self.protocol == "mfddt":
            ordered_features = sorted(
                features_detail,
                key=lambda feature: int(feature.get("index", 0)),
            )
            self.selected_features = [
                feature["name"]
                for feature in ordered_features
                if feature.get("name")
            ] or [
                "ref",
                "torque",
                "vib_x",
                "vib_y",
                "vib_z",
                "cur_a",
                "cur_b",
                "cur_c",
            ]
            self.feature_meta = {
                feature["name"]: feature
                for feature in features_detail
                if feature.get("name") in self.selected_features
            }
        else:
            self.feature_meta = {
                feature["name"]: feature
                for feature in features_detail
                if feature.get("name") in DETECTION_FIELDS
            }

    def meta(self):
        self._initialize()
        selected_features = [
            {
                "name": name,
                "label": (
                    self.feature_meta.get(name, {}).get("label")
                    or DETECTION_FIELD_LABELS.get(name, name)
                ),
                "type": "continuous",
                **self.feature_meta.get(name, {}),
            }
            for name in self.selected_features
        ]
        payload = {
            **self.meta_payload,
            "protocol": self.protocol,
            "selected_features": selected_features,
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
        return payload

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
            "features": ",".join(self.selected_features),
        }
        if self.protocol == "mfddt":
            query["agg"] = "default"
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
                    "label": (
                        0
                        if self.protocol == "mfddt"
                        else int(machine.get("label", 0))
                    ),
                    "warn": (
                        0
                        if self.protocol == "mfddt"
                        else int(machine.get("warn", 0))
                    ),
                    "values": {
                        name: float(values.get(name, 0))
                        for name in self.selected_features
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

    def _require_legacy_analysis(self):
        if self.protocol != "legacy":
            raise ValueError(
                "Detailed model-test evidence is only available for "
                "the legacy MetroPT detection protocol."
            )

    def window(self, machine_id=0, t=0, layout="time_major"):
        """Return one model input window for the selected machine."""
        self._require_legacy_analysis()
        machine_id = int(machine_id)
        timestamp = int(t)
        if machine_id < 0 or timestamp < 0:
            raise ValueError("machine_id and t must be non-negative.")
        return self._get_json(
            "/api/v1/window",
            {
                "machine_id": machine_id,
                "t": timestamp,
                "layout": layout,
            },
        )

    def predict_one(self, machine_id=0, t=0):
        """Return the detailed prediction for one machine and time point."""
        self._require_legacy_analysis()
        machine_id = int(machine_id)
        timestamp = int(t)
        if machine_id < 0 or timestamp < 0:
            raise ValueError("machine_id and t must be non-negative.")
        payload = self._get_json(
            "/api/v1/predict",
            {
                "machine_id": machine_id,
                "t": timestamp,
                "include_truth": "false",
            },
        )
        return {
            **payload,
            "machine_id": int(payload.get("machine_id", machine_id)),
            "t": int(payload.get("t", timestamp)),
            "t_effective": int(
                payload.get("t_effective", timestamp)
            ),
            "prediction_horizon": int(
                payload.get("prediction_horizon", 20)
            ),
            "probability": float(payload.get("probability", 0)),
            "threshold": float(payload.get("threshold", 0)),
            "is_alarm": bool(payload.get("is_alarm", False)),
        }

    def truth(self, machine_id=0, t=0):
        """Return the dataset truth and warning state for one time point."""
        self._require_legacy_analysis()
        machine_id = int(machine_id)
        timestamp = int(t)
        if machine_id < 0 or timestamp < 0:
            raise ValueError("machine_id and t must be non-negative.")
        return self._get_json(
            "/api/v1/truth",
            {
                "machine_id": machine_id,
                "t": timestamp,
            },
        )

    def events(self, machine_id=0):
        """Return all labelled fault intervals for one machine."""
        self._require_legacy_analysis()
        machine_id = int(machine_id)
        if machine_id < 0:
            raise ValueError("machine_id must be non-negative.")
        return self._get_json(
            "/api/v1/events",
            {"machine_id": machine_id},
        )

    def stream(self, machine_id=0, from_t=0, count=20, features=None):
        """Return a short sequence used for future-label visualisation."""
        self._require_legacy_analysis()
        machine_id = int(machine_id)
        from_t = int(from_t)
        count = int(count)
        if machine_id < 0 or from_t < 0:
            raise ValueError("machine_id and from_t must be non-negative.")
        if not 1 <= count <= 300:
            raise ValueError("count must be between 1 and 300.")
        selected = list(features or self.selected_features)
        return self._get_json(
            "/api/v1/stream",
            {
                "machine_id": machine_id,
                "from_t": from_t,
                "count": count,
                "features": ",".join(selected),
            },
        )

    def predict(self, t=0, machine_count=1):
        machine_count = int(machine_count)
        if not 1 <= machine_count <= 500:
            raise ValueError(
                "machine_count must be between 1 and 500."
            )
        if self.protocol == "mfddt":
            payload = self._get_json(
                "/api/v1/detect/batch",
                {
                    "t": max(0, int(t)),
                    "machine_count": machine_count,
                    "include_detail": "true",
                    "include_truth": "false",
                },
            )
            predictions = []
            for result in payload.get("results", []):
                predictions.append(
                    {
                        **result,
                        "machine_id": int(result["machine_id"]),
                        "t": int(result.get("t", t)),
                        "probability": float(
                            result.get(
                                "anomaly_score",
                                result.get("probability", 0),
                            )
                        ),
                        "is_alarm": bool(
                            result.get(
                                "is_alarm",
                                result.get("prediction", 0),
                            )
                        ),
                    }
                )
            return {
                "t": int(payload.get("t", t)),
                "prediction_interval": self.prediction_interval,
                "predictions": predictions,
            }
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

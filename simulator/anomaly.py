import math
from enum import Enum


class MachineAnomalyType(str, Enum):
    LONG_FAILURE = "long_failure"
    SHORT_FAILURE = "short_failure"
    MEDIUM_FAILURE = "medium_failure"
    DEGRADED = "degraded"

    @classmethod
    def normalize(cls, value):
        if isinstance(value, cls):
            return value
        if not isinstance(value, str):
            raise ValueError("Unknown machine anomaly type.")
        normalized = value.strip().lower().replace("-", "_")
        aliases = {
            "long": cls.LONG_FAILURE,
            "long_downtime": cls.LONG_FAILURE,
            "failure": cls.LONG_FAILURE,
            "short": cls.SHORT_FAILURE,
            "short_downtime": cls.SHORT_FAILURE,
            "medium": cls.MEDIUM_FAILURE,
            "medium_downtime": cls.MEDIUM_FAILURE,
            "efficiency_loss": cls.DEGRADED,
            "performance_degraded": cls.DEGRADED,
        }
        if normalized in aliases:
            return aliases[normalized]
        try:
            return cls(normalized)
        except ValueError as exc:
            raise ValueError(
                "anomaly_type must be one of: long_failure, "
                "short_failure, medium_failure, degraded."
            ) from exc


DEGRADED_PROCESSING_FACTOR = 1.5

MACHINE_ANOMALY_DURATION_RANGES = {
    MachineAnomalyType.SHORT_FAILURE: (1, 5),
    MachineAnomalyType.MEDIUM_FAILURE: (5, 15),
    MachineAnomalyType.LONG_FAILURE: (15, 45),
    MachineAnomalyType.DEGRADED: (10, 20),
}
MACHINE_ANOMALY_DEFAULT_DURATIONS = {
    MachineAnomalyType.SHORT_FAILURE: 3,
    MachineAnomalyType.MEDIUM_FAILURE: 10,
    MachineAnomalyType.LONG_FAILURE: 30,
    MachineAnomalyType.DEGRADED: 15,
}


def validate_machine_anomaly_duration(anomaly, duration):
    """Return an integer duration that is valid for the anomaly type."""
    try:
        numeric_duration = float(duration)
    except (TypeError, ValueError) as exc:
        raise ValueError("duration must be an integer.") from exc
    if (
        not math.isfinite(numeric_duration)
        or not numeric_duration.is_integer()
    ):
        raise ValueError("duration must be an integer.")

    normalized_duration = int(numeric_duration)
    minimum, maximum = MACHINE_ANOMALY_DURATION_RANGES[anomaly]
    if not minimum <= normalized_duration <= maximum:
        raise ValueError(
            f"duration for {anomaly.value} must be between "
            f"{minimum} and {maximum}."
        )
    return normalized_duration

import json
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG_PATH = PROJECT_ROOT / "simulator_config.json"


def load_simulator_config(config_path=None):
    """Load and validate the simulator JSON configuration."""
    path = Path(config_path or DEFAULT_CONFIG_PATH).expanduser()
    if not path.is_absolute():
        path = Path.cwd() / path

    try:
        with path.open("r", encoding="utf-8") as config_file:
            config = json.load(config_file)
    except FileNotFoundError as exc:
        raise FileNotFoundError(
            f"Simulator config file not found: {path}"
        ) from exc
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"Invalid simulator config JSON at {path}: {exc}"
        ) from exc

    _validate_config(config)
    return config


def _validate_config(config):
    if not isinstance(config, dict):
        raise ValueError("Simulator config root must be a JSON object.")

    for section in ("time", "paths", "simulation"):
        if not isinstance(config.get(section), dict):
            raise ValueError(f"Simulator config section '{section}' is required.")

    _require_positive_number(config["time"], "real_time_step", "time")
    _require_positive_number(config["time"], "speed", "time")

    if not isinstance(config["time"].get("realtime"), bool):
        raise ValueError("time.realtime must be a boolean.")

    for key in (
        "dataset_root",
        "log_dir",
        "input_file",
        "additional_file",
        "schedule_file",
        "gantt_file",
    ):
        value = config["paths"].get(key)
        if not isinstance(value, str) or not value:
            raise ValueError(f"paths.{key} must be a non-empty string.")

    _require_positive_number(
        config["simulation"], "due_time_factor", "simulation"
    )

    seed = config["simulation"].get("seed")
    if not isinstance(seed, int) or isinstance(seed, bool):
        raise ValueError("simulation.seed must be an integer.")

    auxiliary_energy = config["simulation"].get("auxiliary_energy")
    if (
        not isinstance(auxiliary_energy, (int, float))
        or isinstance(auxiliary_energy, bool)
        or auxiliary_energy < 0
    ):
        raise ValueError(
            "simulation.auxiliary_energy must be a non-negative number."
        )

    batch_window = config["simulation"].get(
        "process_stage_batch_window",
        10.0,
    )
    if (
        not isinstance(batch_window, (int, float))
        or isinstance(batch_window, bool)
        or batch_window < 0
    ):
        raise ValueError(
            "simulation.process_stage_batch_window must be a "
            "non-negative number."
        )

    replenishment_lead_time = config["simulation"].get(
        "material_replenishment_lead_time",
        5.0,
    )
    if (
        not isinstance(replenishment_lead_time, (int, float))
        or isinstance(replenishment_lead_time, bool)
        or replenishment_lead_time < 0
    ):
        raise ValueError(
            "simulation.material_replenishment_lead_time must be a "
            "non-negative number."
        )

    replenishment_target_factor = config["simulation"].get(
        "material_replenishment_target_factor",
        3.0,
    )
    if (
        not isinstance(replenishment_target_factor, (int, float))
        or isinstance(replenishment_target_factor, bool)
        or replenishment_target_factor < 1
    ):
        raise ValueError(
            "simulation.material_replenishment_target_factor must be "
            "a number greater than or equal to 1."
        )

    if not isinstance(config["simulation"].get("log_tag"), bool):
        raise ValueError("simulation.log_tag must be a boolean.")

    anomaly_handling = config.get("anomaly_handling", {})
    if not isinstance(anomaly_handling, dict):
        raise ValueError("anomaly_handling must be a JSON object.")
    if not isinstance(anomaly_handling.get("enabled", False), bool):
        raise ValueError("anomaly_handling.enabled must be a boolean.")

    visualization = config.get("visualization", {})
    if not isinstance(visualization, dict):
        raise ValueError("visualization must be a JSON object.")
    if "speed" in visualization:
        _require_positive_number(visualization, "speed", "visualization")
    if "display_percent" in visualization:
        display_percent = visualization["display_percent"]
        if (
            not isinstance(display_percent, (int, float))
            or isinstance(display_percent, bool)
            or not 25 <= display_percent <= 300
        ):
            raise ValueError(
                "visualization.display_percent must be between 25 and 300."
            )
    if "host" in visualization and (
        not isinstance(visualization["host"], str)
        or not visualization["host"]
    ):
        raise ValueError("visualization.host must be a non-empty string.")
    if "public_host" in visualization and (
        not isinstance(visualization["public_host"], str)
        or not visualization["public_host"]
    ):
        raise ValueError(
            "visualization.public_host must be a non-empty string."
        )
    if "port" in visualization and (
        not isinstance(visualization["port"], int)
        or isinstance(visualization["port"], bool)
        or not 1 <= visualization["port"] <= 65535
    ):
        raise ValueError("visualization.port must be between 1 and 65535.")

    detection_data = config.get("detection_data")
    if detection_data is not None:
        if not isinstance(detection_data, dict):
            raise ValueError("detection_data must be a JSON object.")
        if "base_url" in detection_data and (
            not isinstance(detection_data["base_url"], str)
            or not detection_data["base_url"]
        ):
            raise ValueError("detection_data.base_url must be non-empty.")
        process_base_urls = detection_data.get("process_base_urls", {})
        if not isinstance(process_base_urls, dict):
            raise ValueError(
                "detection_data.process_base_urls must be a JSON object."
            )
        for process_id, base_url in process_base_urls.items():
            try:
                normalized_process_id = int(process_id)
            except (TypeError, ValueError) as exc:
                raise ValueError(
                    "detection_data.process_base_urls keys must be integers."
                ) from exc
            if normalized_process_id < 1:
                raise ValueError(
                    "detection_data.process_base_urls keys must be positive."
                )
            if not isinstance(base_url, str) or not base_url:
                raise ValueError(
                    "detection_data.process_base_urls values must be "
                    "non-empty strings."
                )
        process_protocols = detection_data.get("process_protocols", {})
        if not isinstance(process_protocols, dict):
            raise ValueError(
                "detection_data.process_protocols must be a JSON object."
            )
        for process_id, protocol in process_protocols.items():
            try:
                normalized_process_id = int(process_id)
            except (TypeError, ValueError) as exc:
                raise ValueError(
                    "detection_data.process_protocols keys must be integers."
                ) from exc
            if normalized_process_id < 1:
                raise ValueError(
                    "detection_data.process_protocols keys must be positive."
                )
            if protocol not in {"legacy", "mfddt"}:
                raise ValueError(
                    "detection_data.process_protocols values must be "
                    "'legacy' or 'mfddt'."
                )
        _require_positive_number(
            detection_data,
            "timeout",
            "detection_data",
        )
        history_points = detection_data.get("history_points")
        if (
            not isinstance(history_points, int)
            or isinstance(history_points, bool)
            or not 1 <= history_points <= 300
        ):
            raise ValueError(
                "detection_data.history_points must be between 1 and 300."
            )
        poll_interval_ms = detection_data.get("poll_interval_ms")
        if (
            not isinstance(poll_interval_ms, int)
            or isinstance(poll_interval_ms, bool)
            or poll_interval_ms < 1
        ):
            raise ValueError(
                "detection_data.poll_interval_ms must be a positive integer."
            )
        prediction_interval = detection_data.get(
            "prediction_interval",
            5,
        )
        if (
            not isinstance(prediction_interval, int)
            or isinstance(prediction_interval, bool)
            or not 1 <= prediction_interval <= 100
        ):
            raise ValueError(
                "detection_data.prediction_interval must be an integer "
                "between 1 and 100."
            )


def _require_positive_number(section, key, section_name):
    value = section.get(key)
    if (
        not isinstance(value, (int, float))
        or isinstance(value, bool)
        or value <= 0
    ):
        raise ValueError(f"{section_name}.{key} must be a positive number.")

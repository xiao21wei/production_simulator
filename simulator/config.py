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

    if not isinstance(config["simulation"].get("log_tag"), bool):
        raise ValueError("simulation.log_tag must be a boolean.")

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
    if "port" in visualization and (
        not isinstance(visualization["port"], int)
        or isinstance(visualization["port"], bool)
        or not 1 <= visualization["port"] <= 65535
    ):
        raise ValueError("visualization.port must be between 1 and 65535.")


def _require_positive_number(section, key, section_name):
    value = section.get(key)
    if (
        not isinstance(value, (int, float))
        or isinstance(value, bool)
        or value <= 0
    ):
        raise ValueError(f"{section_name}.{key} must be a positive number.")

"""Unified construction-method client for InfluenceAwareConstruct."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DATASET_ROOT = PROJECT_ROOT / "datasets"
DEFAULT_EXECUTABLE = (
    PROJECT_ROOT
    / "InfluenceAwareConstruct"
    / "build"
    / "influence_aware_scheduler"
)
DEFAULT_METHOD = "InfluenceAwareConstruct"
CONSTRUCTION_METHODS = (
    "FIFO_SPT",
    "FIFO_EET",
    "MOPNR_SPT",
    "MOPNR_EET",
    "MWKR_SPT",
    "MWKR_EET",
    "InfluenceAwareConstruct",
)
METHOD_ALIASES = {
    "influenceaware": "InfluenceAwareConstruct",
    "influenceawareconstruct": "InfluenceAwareConstruct",
}
PROCESS_DIRECTORIES = {
    1: ("raw", "add"),
    2: ("raw1", "add1"),
    3: ("raw2", "add2"),
    4: ("raw3", "add3"),
}


class ConstructionError(RuntimeError):
    """Raised when a construction request or solver invocation fails."""


def normalize_construction_method(method):
    """Return the canonical construction method name."""
    if not isinstance(method, str) or not method.strip():
        raise ValueError(
            "method must be one of: " + ", ".join(CONSTRUCTION_METHODS)
        )
    requested = method.strip()
    canonical = next(
        (
            name
            for name in CONSTRUCTION_METHODS
            if name.casefold() == requested.casefold()
        ),
        None,
    )
    if canonical is None:
        canonical = METHOD_ALIASES.get(requested.casefold())
    if canonical is None:
        raise ValueError(
            f"Unsupported construction method '{method}'. "
            "Available methods: " + ", ".join(CONSTRUCTION_METHODS)
        )
    return canonical


def _absolute_path(path, dataset_root):
    candidate = Path(path).expanduser()
    if candidate.is_absolute():
        return candidate.resolve()
    working_directory_path = (Path.cwd() / candidate).resolve()
    if working_directory_path.exists():
        return working_directory_path
    return (dataset_root / candidate).resolve()


def _infer_add_path(raw_path):
    for directory in (raw_path.parent, *raw_path.parent.parents):
        if directory.name.startswith("raw"):
            add_directory = "add" + directory.name[3:]
            return (
                directory.parent
                / add_directory
                / raw_path.relative_to(directory)
            )
    return raw_path


def resolve_construction_paths(
    *,
    dataset_root=None,
    instance=None,
    process_id=1,
    raw_file=None,
    additional_file=None,
    delivery_cost_file=None,
):
    """Resolve one raw/add/delivery-cost path configuration."""
    dataset_root_path = Path(
        dataset_root or DEFAULT_DATASET_ROOT
    ).expanduser().resolve()
    try:
        process_id = int(process_id)
    except (TypeError, ValueError) as exc:
        raise ValueError("process_id must be an integer.") from exc
    if process_id not in PROCESS_DIRECTORIES:
        raise ValueError("process_id must be between 1 and 4.")

    raw_dirs, add_dirs = PROCESS_DIRECTORIES[process_id]
    if raw_file is None:
        if not instance:
            raise ValueError(
                "raw_file or instance must be provided to locate the dataset."
            )
        instance_name = Path(str(instance)).name
        if not instance_name.endswith(".fjs"):
            instance_name += ".fjs"
        raw_path = (dataset_root_path / raw_dirs / instance_name).resolve()
    else:
        raw_path = _absolute_path(raw_file, dataset_root_path)
        if not raw_path.is_file():
            alternate = raw_path.parent.parent / raw_dirs / raw_path.name
            if alternate.is_file():
                raw_path = alternate.resolve()
        if dataset_root is None:
            for directory in raw_path.parents:
                if directory.name.startswith("raw"):
                    dataset_root_path = directory.parent.resolve()
                    break

    if additional_file is None:
        add_path = (
            dataset_root_path / add_dirs / raw_path.name
        ).resolve()
        if not add_path.is_file():
            add_path = _infer_add_path(raw_path).resolve()
    else:
        add_path = _absolute_path(additional_file, dataset_root_path)

    if delivery_cost_file is None:
        delivery_path = (
            dataset_root_path / "delivery_cost" / raw_path.name
        ).resolve()
        if not delivery_path.is_file():
            inferred = (
                add_path.parent.parent
                / "delivery_cost"
                / add_path.name
            ).resolve()
            delivery_path = inferred if inferred.is_file() else None
    else:
        delivery_path = _absolute_path(
            delivery_cost_file,
            dataset_root_path,
        )

    if not raw_path.is_file():
        raise FileNotFoundError(f"Raw dataset not found: {raw_path}")
    if not add_path.is_file():
        raise FileNotFoundError(f"Additional dataset not found: {add_path}")
    if delivery_path is not None and not delivery_path.is_file():
        raise FileNotFoundError(
            f"Delivery-cost dataset not found: {delivery_path}"
        )

    return {
        "dataset_root": str(dataset_root_path),
        "instance": raw_path.name,
        "process_id": process_id,
        "raw_file": str(raw_path),
        "additional_file": str(add_path),
        "delivery_cost_file": (
            str(delivery_path) if delivery_path is not None else None
        ),
    }


def _resolve_executable(executable):
    configured = executable or os.environ.get(
        "INFLUENCE_AWARE_SCHEDULER_BIN"
    )
    path = Path(configured).expanduser() if configured else DEFAULT_EXECUTABLE
    if not path.is_absolute():
        path = Path.cwd() / path
    path = path.resolve()
    if not path.is_file():
        raise FileNotFoundError(
            f"InfluenceAwareConstruct executable not found: {path}. "
            "Build it with: cmake -S InfluenceAwareConstruct "
            "-B InfluenceAwareConstruct/build && "
            "cmake --build InfluenceAwareConstruct/build"
        )
    return path


def construct_schedule(
    raw_file=None,
    additional_file=None,
    delivery_cost_file=None,
    method=DEFAULT_METHOD,
    *,
    dataset_root=None,
    instance=None,
    process_id=1,
    executable=None,
    timeout=600,
):
    """Run one selected construction method on a split dataset.

    ``raw_file``/``additional_file``/``delivery_cost_file`` may be omitted
    when ``instance`` and ``process_id`` identify files below ``dataset_root``.
    The returned dictionary is the normalized solver JSON response.
    """
    canonical_method = normalize_construction_method(method)
    paths = resolve_construction_paths(
        dataset_root=dataset_root,
        instance=instance,
        process_id=process_id,
        raw_file=raw_file,
        additional_file=additional_file,
        delivery_cost_file=delivery_cost_file,
    )
    binary = _resolve_executable(executable)
    command = [
        str(binary),
        "--construct",
        canonical_method,
        "--dataset-root",
        paths["dataset_root"],
        "--raw",
        paths["raw_file"],
        "--add",
        paths["additional_file"],
    ]
    if paths["delivery_cost_file"] is not None:
        command.extend(
            ["--delivery-cost", paths["delivery_cost_file"]]
        )

    try:
        completed = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=float(timeout),
        )
    except subprocess.TimeoutExpired as exc:
        raise ConstructionError(
            f"Construction method {canonical_method} exceeded "
            f"{timeout:g} seconds."
        ) from exc
    except OSError as exc:
        raise ConstructionError(
            f"Could not execute InfluenceAwareConstruct: {exc}"
        ) from exc

    if completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip()
        raise ConstructionError(
            f"Construction method {canonical_method} failed: "
            f"{detail or 'unknown solver error'}"
        )
    try:
        result = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise ConstructionError(
            "InfluenceAwareConstruct returned invalid JSON output."
        ) from exc
    if not isinstance(result, dict) or not result.get("success"):
        raise ConstructionError(
            "InfluenceAwareConstruct did not return a successful result."
        )
    result["process_id"] = paths["process_id"]
    result["request"] = {
        **paths,
        "method": canonical_method,
    }
    return result

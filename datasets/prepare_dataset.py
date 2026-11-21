#!/usr/bin/env python3
"""Convert the flat benchmark files into the runtime raw/add layout.

The source benchmark files use zero-based machine identifiers and contain no
multi-objective metadata. This script:

1. converts machine identifiers to the one-based convention used by env/load_data.py;
2. excludes instances containing zero processing times, which the loader treats as unavailable;
3. creates deterministic processing energy, delivery-cost and transport data;
4. writes raw/add plus one shared delivery_cost file per instance and a manifest.

The original .txt files are never modified.
"""

from __future__ import annotations

import hashlib
import json
import random
from collections import Counter
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent
RAW_DIR = ROOT / "raw"
ADD_DIR = ROOT / "add"
DELIVERY_COST_DIR = ROOT / "delivery_cost"
MANIFEST_PATH = ROOT / "manifest.json"
DELIVERY_HEADER = (
    "# priority ready_time due_time earliness_cost tardiness_cost"
)


class UnsupportedInstanceError(ValueError):
    """Raised when an instance cannot be represented by the current loader."""


def parse_instance(source: Path) -> dict[str, Any]:
    lines = source.read_text(encoding="utf-8-sig").splitlines()
    if not lines:
        raise ValueError("empty file")

    header = [int(value) for value in lines[0].split()]
    if len(header) < 2:
        raise ValueError("header must contain at least num_jobs and num_machines")
    num_jobs, num_machines = header[:2]
    if len(lines) != num_jobs + 1:
        raise ValueError(
            f"expected {num_jobs + 1} non-empty rows, found {len(lines)}"
        )

    jobs: list[list[dict[str, Any]]] = []
    num_options = 0

    for job_index, line in enumerate(lines[1:], start=1):
        values = [int(value) for value in line.split()]
        if not values:
            raise ValueError(f"job {job_index} is empty")
        num_operations = values[0]
        cursor = 1
        operations: list[dict[str, Any]] = []

        for operation_index in range(num_operations):
            if cursor >= len(values):
                raise ValueError(
                    f"job {job_index} operation {operation_index + 1} is truncated"
                )
            option_count = values[cursor]
            cursor += 1
            if option_count <= 0 or cursor + option_count * 2 > len(values):
                raise ValueError(
                    f"job {job_index} operation {operation_index + 1} has an "
                    f"invalid option count: {option_count}"
                )

            options = []
            for _ in range(option_count):
                machine_id = values[cursor]
                processing_time = values[cursor + 1]
                cursor += 2
                if not 0 <= machine_id < num_machines:
                    raise ValueError(
                        f"machine {machine_id} is outside 0..{num_machines - 1}"
                    )
                if processing_time < 0:
                    raise ValueError("processing time must not be negative")
                if processing_time == 0:
                    raise UnsupportedInstanceError(
                        f"job {job_index} operation {operation_index + 1} "
                        f"contains a zero processing time"
                    )
                options.append(
                    {
                        "machine": machine_id + 1,
                        "time": processing_time,
                    }
                )
            operations.append({"options": options})
            num_options += option_count

        if cursor != len(values):
            raise ValueError(
                f"job {job_index} has {len(values) - cursor} trailing values"
            )
        jobs.append(operations)

    return {
        "header": header,
        "num_jobs": num_jobs,
        "num_machines": num_machines,
        "num_operations": sum(len(job) for job in jobs),
        "num_options": num_options,
        "jobs": jobs,
    }


def make_additional_data(
    parsed: dict[str, Any], seed: int
) -> tuple[list[str], list[str], list[str]]:
    rng = random.Random(seed)
    num_jobs = parsed["num_jobs"]
    num_machines = parsed["num_machines"]
    energy_rows = []
    feature_rows = []

    for operations in parsed["jobs"]:
        energy_values = [len(operations)]
        operation_means = []
        for operation in operations:
            options = operation["options"]
            energy_values.append(len(options))
            for option in options:
                energy_values.extend([option["machine"], rng.randint(4, 15)])
            operation_means.append(
                sum(option["time"] for option in options) / len(options)
            )
        energy_rows.append(" ".join(str(value) for value in energy_values))

        weight = rng.randint(1, 5)
        ready_time = rng.randint(0, 20)
        early_penalty = rng.randint(1, 10)
        tardy_penalty = rng.randint(1, 10)
        due_time = int(ready_time + sum(operation_means) * 1.5)
        feature_rows.append(
            f"{weight}\t{ready_time}\t{due_time}\t"
            f"{early_penalty}\t{tardy_penalty}"
        )

    transport_time = [[0] * num_machines for _ in range(num_machines)]
    transport_energy = [[0] * num_machines for _ in range(num_machines)]
    for first in range(num_machines):
        for second in range(first + 1, num_machines):
            duration = rng.randint(1, 3)
            energy = rng.randint(1, 4)
            transport_time[first][second] = duration
            transport_time[second][first] = duration
            transport_energy[first][second] = energy
            transport_energy[second][first] = energy

    matrix_rows = [
        " ".join(str(value) for value in row) for row in transport_time
    ]
    matrix_rows.extend(
        " ".join(str(value) for value in row) for row in transport_energy
    )
    return energy_rows, feature_rows, matrix_rows


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_dataset(source: Path) -> dict[str, Any]:
    parsed = parse_instance(source)
    seed = int(hashlib.sha256(source.name.encode("utf-8")).hexdigest()[:16], 16)
    energy_rows, feature_rows, matrix_rows = make_additional_data(
        parsed,
        seed,
    )

    raw_rows = ["\t".join(str(value) for value in parsed["header"])]
    for operations in parsed["jobs"]:
        values = [len(operations)]
        for operation in operations:
            options = operation["options"]
            values.append(len(options))
            for option in options:
                values.extend([option["machine"], option["time"]])
        raw_rows.append(" ".join(str(value) for value in values))

    output_name = source.with_suffix(".fjs").name
    raw_path = RAW_DIR / output_name
    add_path = ADD_DIR / output_name
    delivery_path = DELIVERY_COST_DIR / output_name
    raw_path.write_text("\n".join(raw_rows) + "\n", encoding="utf-8")
    add_path.write_text(
        "\n".join(energy_rows + matrix_rows) + "\n",
        encoding="utf-8",
    )
    delivery_path.write_text(
        DELIVERY_HEADER + "\n" + "\n".join(feature_rows) + "\n",
        encoding="utf-8",
    )

    return {
        "source": source.name,
        "source_sha256": sha256(source),
        "raw": f"raw/{raw_path.name}",
        "add": f"add/{add_path.name}",
        "delivery_cost": (
            f"delivery_cost/{delivery_path.name}"
        ),
        "raw_sha256": sha256(raw_path),
        "add_sha256": sha256(add_path),
        "delivery_cost_sha256": sha256(delivery_path),
        "family": source.name.split(".", 1)[0],
        "benchmark": source.name.split(".")[1],
        "num_jobs": parsed["num_jobs"],
        "num_machines": parsed["num_machines"],
        "header_metadata": parsed["header"][2:],
        "num_operations": parsed["num_operations"],
        "num_options": parsed["num_options"],
    }


def main() -> None:
    sources = sorted(ROOT.glob("*.txt"))
    if not sources:
        raise SystemExit(f"No .txt benchmark files found in {ROOT}")

    RAW_DIR.mkdir(exist_ok=True)
    ADD_DIR.mkdir(exist_ok=True)
    DELIVERY_COST_DIR.mkdir(parents=True, exist_ok=True)
    instances = []
    skipped = []
    errors = []
    for source in sources:
        try:
            instances.append(write_dataset(source))
        except UnsupportedInstanceError as exc:
            skipped.append({"source": source.name, "reason": str(exc)})
        except Exception as exc:
            errors.append({"source": source.name, "error": str(exc)})

    if errors:
        raise SystemExit(
            "Dataset conversion failed:\n"
            + "\n".join(
                f"- {item['source']}: {item['error']}" for item in errors
            )
        )

    expected = {item["source"] for item in instances}
    generated_raw = {path.stem + ".txt" for path in RAW_DIR.glob("*.fjs")}
    generated_add = {path.stem + ".txt" for path in ADD_DIR.glob("*.fjs")}
    expected_file_names = {
        source.with_suffix(".fjs").name for source in sources
    } - {Path(item["source"]).with_suffix(".fjs").name for item in skipped}
    for output_dir in (RAW_DIR, ADD_DIR, DELIVERY_COST_DIR):
        for output_path in output_dir.glob("*.fjs"):
            if output_path.name not in expected_file_names:
                output_path.unlink()
    generated_raw = {path.stem + ".txt" for path in RAW_DIR.glob("*.fjs")}
    generated_add = {path.stem + ".txt" for path in ADD_DIR.glob("*.fjs")}
    generated_delivery = {
        path.stem + ".txt" for path in DELIVERY_COST_DIR.glob("*.fjs")
    }
    if (
        expected != generated_raw
        or expected != generated_add
        or expected != generated_delivery
    ):
        raise SystemExit(
            "Generated raw/add/delivery-cost files do not match "
            "the supported source set"
        )

    shape_counts = Counter(
        (item["num_jobs"], item["num_machines"]) for item in instances
    )
    manifest = {
        "format_version": 2,
        "layout": {
            "raw": "raw/<name>.fjs",
            "add": "add/<name>.fjs",
            "delivery_cost": (
                "delivery_cost/<name>.fjs"
            ),
            "machine_id_convention": "one-based",
        },
        "generation_rules": {
            "source_machine_ids": "converted from zero-based to one-based",
            "zero_processing_time": "instance excluded because the loader treats zero as unavailable",
            "processing_energy_range": [4, 15],
            "job_weight_range": [1, 5],
            "job_ready_time_range": [0, 20],
            "earliness_penalty_range": [1, 10],
            "tardiness_penalty_range": [1, 10],
            "due_time": "ready_time + int(sum(operation_mean_processing_time) * 1.5)",
            "delivery_cost_fields": [
                "priority",
                "ready_time",
                "due_time",
                "earliness_cost",
                "tardiness_cost",
            ],
            "transport_time_range_off_diagonal": [1, 3],
            "transport_energy_range_off_diagonal": [1, 4],
            "randomness": "deterministic SHA-256 seed derived from source filename",
        },
        "summary": {
            "total_instances": len(instances),
            "jsp_instances": sum(item["family"] == "jsp" for item in instances),
            "fjsp_instances": sum(item["family"] == "fjsp" for item in instances),
            "shape_counts": {
                f"{jobs}j_{machines}m": count
                for (jobs, machines), count in sorted(shape_counts.items())
            },
            "excluded_instances": len(skipped),
        },
        "excluded_sources": skipped,
        "instances": instances,
    }
    MANIFEST_PATH.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(
        f"Prepared {len(instances)} instances and excluded {len(skipped)}: "
        f"{RAW_DIR}, {ADD_DIR} and {DELIVERY_COST_DIR}; "
        f"manifest={MANIFEST_PATH}"
    )


if __name__ == "__main__":
    main()

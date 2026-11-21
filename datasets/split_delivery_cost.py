#!/usr/bin/env python3
"""Create one delivery-cost file per dataset instance.

Delivery fields are stored in::

    delivery_cost/<name>.fjs

The same delivery information is shared by stamping, welding, painting and
assembly. The add/addN files keep only processing energy and transport data.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parent
DELIVERY_ROOT = ROOT / "delivery_cost"
DELIVERY_HEADER = (
    "# priority ready_time due_time earliness_cost tardiness_cost"
)
LEGACY_PROCESS_DIRS = tuple(
    DELIVERY_ROOT / f"process{index}" for index in range(1, 5)
)
PROCESS_LAYOUTS = (
    ("raw", "add"),
    ("raw1", "add1"),
    ("raw2", "add2"),
    ("raw3", "add3"),
)
MANIFEST_PATH = ROOT / "manifest.json"


def read_lines(path: Path) -> list[str]:
    return [
        line.strip()
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def add_layout(raw_path: Path):
    header = read_lines(raw_path)[0].split()
    return int(header[0]), int(header[1])


def delivery_rows(path: Path, num_jobs: int) -> list[str]:
    if not path.is_file():
        raise FileNotFoundError(
            f"Delivery-cost dataset not found: {path}"
        )
    rows = [
        line for line in read_lines(path) if not line.startswith("#")
    ]
    if len(rows) != num_jobs:
        raise ValueError(
            f"{path}: expected {num_jobs} delivery rows, found {len(rows)}"
        )
    if any(len(row.split()) != 5 for row in rows):
        raise ValueError(
            f"{path}: every delivery row must contain 5 values"
        )
    return rows


def split_dataset(
    raw_path: Path,
    add_path: Path,
    delivery_path: Path,
) -> tuple[str, str | None]:
    num_jobs, num_machines = add_layout(raw_path)
    add_lines = read_lines(add_path)
    matrix_rows = num_machines * 2
    split_line_count = num_jobs + matrix_rows
    embedded_line_count = num_jobs * 2 + matrix_rows

    if len(add_lines) == split_line_count:
        delivery_rows(delivery_path, num_jobs)
        return "\n".join(add_lines) + "\n", None

    if len(add_lines) != embedded_line_count:
        raise ValueError(
            f"{add_path}: expected {embedded_line_count} lines, "
            f"found {len(add_lines)}"
        )
    rows = add_lines[num_jobs:num_jobs * 2]
    if any(len(row.split()) != 5 for row in rows):
        raise ValueError(f"{add_path}: delivery rows must contain 5 values")
    return (
        "\n".join(add_lines[:num_jobs] + add_lines[num_jobs * 2:])
        + "\n",
        DELIVERY_HEADER + "\n" + "\n".join(rows) + "\n",
    )


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def update_manifest() -> None:
    if not MANIFEST_PATH.is_file():
        return
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    manifest["format_version"] = 3
    manifest.setdefault("layout", {})["delivery_cost"] = (
        "delivery_cost/<name>.fjs"
    )
    manifest.setdefault("generation_rules", {})["delivery_cost_fields"] = [
        "priority",
        "ready_time",
        "due_time",
        "earliness_cost",
        "tardiness_cost",
    ]
    manifest["generation_rules"]["delivery_scope"] = (
        "one delivery record per Job, shared by all processes"
    )
    for instance in manifest.get("instances", []):
        raw_name = Path(instance["raw"]).name
        add_path = ROOT / instance["add"]
        delivery_path = DELIVERY_ROOT / raw_name
        if not add_path.is_file() or not delivery_path.is_file():
            continue
        instance["add_sha256"] = file_sha256(add_path)
        instance["delivery_cost"] = f"delivery_cost/{raw_name}"
        instance["delivery_cost_sha256"] = file_sha256(delivery_path)
    MANIFEST_PATH.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def remove_legacy_process_directories() -> None:
    for directory in LEGACY_PROCESS_DIRS:
        if not directory.is_dir():
            continue
        for path in directory.glob("*.fjs"):
            path.unlink()
        try:
            directory.rmdir()
        except OSError:
            pass


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Create one delivery-cost file per instance and remove "
            "per-process delivery directories."
        )
    )
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    mismatches = []
    total = 0

    legacy_primary = DELIVERY_ROOT / "process1"
    if not args.check:
        DELIVERY_ROOT.mkdir(exist_ok=True)
    if legacy_primary.is_dir():
        for legacy_path in legacy_primary.glob("*.fjs"):
            target = DELIVERY_ROOT / legacy_path.name
            if not args.check:
                target.write_bytes(legacy_path.read_bytes())

    expected_names = {
        raw_path.name for raw_path in (ROOT / "raw").glob("*.fjs")
    }
    for raw_directory, add_directory in PROCESS_LAYOUTS:
        count = 0
        for add_path in sorted((ROOT / add_directory).glob("*.fjs")):
            raw_path = ROOT / raw_directory / add_path.name
            if not raw_path.is_file():
                continue
            delivery_path = DELIVERY_ROOT / add_path.name
            expected_add, expected_delivery = split_dataset(
                raw_path,
                add_path,
                delivery_path,
            )
            count += 1
            if args.check:
                expected_paths = [(add_path, expected_add)]
                if expected_delivery is not None:
                    expected_paths.append(
                        (delivery_path, expected_delivery)
                    )
                for path, expected in expected_paths:
                    if (
                        not path.is_file()
                        or path.read_text(encoding="utf-8") != expected
                    ):
                        mismatches.append(str(path))
            else:
                add_path.write_text(expected_add, encoding="utf-8")
                if expected_delivery is not None:
                    delivery_path.write_text(
                        expected_delivery,
                        encoding="utf-8",
                    )
        total += count
        print(f"{add_directory}: {count} files")

    if not args.check:
        for stale_path in DELIVERY_ROOT.glob("*.fjs"):
            if stale_path.name not in expected_names:
                stale_path.unlink()
        remove_legacy_process_directories()
        update_manifest()
    elif any(directory.exists() for directory in LEGACY_PROCESS_DIRS):
        mismatches.append("legacy delivery_cost/process* directories exist")

    if mismatches:
        raise SystemExit(
            "Delivery split check failed for:\n"
            + "\n".join(mismatches[:20])
        )
    print(f"checked={args.check} total={total}")


if __name__ == "__main__":
    main()

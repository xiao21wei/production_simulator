#!/usr/bin/env python3
"""Generate the additional multi-objective data for raw FJSP instances."""

from __future__ import annotations

import argparse
import random
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATASET = ROOT / "datasets"


def parse_job_line(line: str) -> tuple[int, list[list[tuple[int, int]]], float]:
    numbers = [int(value) for value in line.split()]
    operation_count = numbers[0]
    index = 1
    operation_mean_times = []
    operations = []

    for _ in range(operation_count):
        machine_count = numbers[index]
        index += 1
        options = []
        time_sum = 0
        for _ in range(machine_count):
            machine = numbers[index]
            processing_time = numbers[index + 1]
            options.append((machine, processing_time))
            time_sum += processing_time
            index += 2
        operation_mean_times.append(time_sum / machine_count)
        operations.append(options)

    return operation_count, operations, sum(operation_mean_times)


def format_job_line(
    operation_count: int,
    operations: list[list[tuple[int, int]]],
) -> str:
    parts = [str(operation_count)]
    for options in operations:
        parts.append(str(len(options)))
        for machine, _ in options:
            parts.append(str(machine))
            parts.append(str(random.randint(4, 15)))
    return " ".join(parts)


def build_transport_matrix(machine_count: int, upper_bound: int) -> list[list[int]]:
    matrix = [[0 for _ in range(machine_count)] for _ in range(machine_count)]
    for source in range(machine_count):
        for target in range(source + 1, machine_count):
            value = random.randint(1, upper_bound)
            matrix[source][target] = value
            matrix[target][source] = value
    return matrix


def matrix_lines(matrix: list[list[int]]) -> list[str]:
    return [" ".join(str(value) for value in row) for row in matrix]


def create_instance(input_path: Path, output_path: Path, seed: int) -> None:
    lines = [
        line.strip()
        for line in input_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    if not lines:
        raise ValueError(f"empty input file: {input_path}")

    header = lines[0].split()
    job_count = int(header[0])
    machine_count = int(header[1])
    job_structures = [parse_job_line(line) for line in lines[1:]]
    if len(job_structures) != job_count:
        raise ValueError(
            f"{input_path}: expected {job_count} jobs, got {len(job_structures)}"
        )

    random.seed(seed)
    energy_lines = [
        format_job_line(operation_count, operations)
        for operation_count, operations, _ in job_structures
    ]

    job_info_lines = []
    for _, _, duration in job_structures:
        weight = random.randint(1, 5)
        ready_time = random.randint(0, 20)
        due_time = int(ready_time + duration * 1.5)
        early_penalty = random.randint(1, 10)
        late_penalty = random.randint(1, 10)
        job_info_lines.append(
            f"{weight} {ready_time} {due_time} {early_penalty} {late_penalty}"
        )

    transport_time = build_transport_matrix(machine_count, 3)
    transport_energy = build_transport_matrix(machine_count, 4)
    output_lines = (
        energy_lines
        + job_info_lines
        + matrix_lines(transport_time)
        + matrix_lines(transport_energy)
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(output_lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate add/*.fjs data for the InfluenceAware scheduler."
    )
    parser.add_argument(
        "--dataset",
        type=Path,
        default=DEFAULT_DATASET,
        help="Dataset root containing raw/Brandimarte and add/Brandimarte.",
    )
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    raw_dir = args.dataset / "raw" / "Brandimarte"
    add_dir = args.dataset / "add" / "Brandimarte"
    instances = sorted(raw_dir.glob("*.fjs"))
    if not instances:
        raise FileNotFoundError(f"No .fjs files found in {raw_dir}")

    for raw_path in instances:
        create_instance(raw_path, add_dir / raw_path.name, args.seed)
    print(f"Generated {len(instances)} additional instances in {add_dir}")


if __name__ == "__main__":
    main()

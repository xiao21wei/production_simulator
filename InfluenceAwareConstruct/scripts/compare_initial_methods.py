#!/usr/bin/env python3
"""对比各初始解构造方法在 Brandimarte 算例上的表现。"""

from __future__ import annotations

import argparse
import csv
import subprocess
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BIN = ROOT / "build" / "influence_aware_scheduler"
DEFAULT_DATASET = ROOT / "datasets" / "raw" / "Brandimarte"

METHODS = [
    "FIFO_SPT",
    "FIFO_EET",
    "MOPNR_SPT",
    "MOPNR_EET",
    "MWKR_SPT",
    "MWKR_EET",
    "InfluenceAwareConstruct",
]


def parse_compare_output(
    text: str,
) -> tuple[str, dict[str, float], dict[str, dict[str, float]], str]:
    instance = ""
    fifo_baseline: dict[str, float] = {}
    rows: dict[str, dict[str, float]] = {}
    best_method = ""
    in_table = False

    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        if line.startswith("instance,"):
            instance = line.split(",", 1)[1]
            continue
        if line.startswith("fifo_makespan,"):
            fifo_baseline["fifo_makespan"] = float(line.split(",", 1)[1])
            continue
        if line.startswith("fifo_cost,"):
            fifo_baseline["fifo_cost"] = float(line.split(",", 1)[1])
            continue
        if line.startswith("fifo_energy,"):
            fifo_baseline["fifo_energy"] = float(line.split(",", 1)[1])
            continue
        if line.startswith("best_method,"):
            best_method = line.split(",", 1)[1]
            continue
        if line == "method,makespan,cost,energy,combined_objective":
            in_table = True
            continue
        if in_table and "," in line:
            parts = line.split(",")
            if len(parts) != 5:
                continue
            method, makespan, cost, energy, combined = parts
            rows[method] = {
                "makespan": int(makespan),
                "cost": int(cost),
                "energy": int(energy),
                "combined_objective": float(combined),
            }
    return instance, fifo_baseline, rows, best_method


def run_instance(
    instance_path: Path,
) -> tuple[str, dict[str, float], dict[str, dict[str, float]], str]:
    proc = subprocess.run(
        [str(BIN), str(instance_path), "--compare-initial"],
        check=True,
        capture_output=True,
        text=True,
    )
    return parse_compare_output(proc.stdout)


def build_objective_ratios(
    metrics: dict[str, float], fifo_baseline: dict[str, float]
) -> dict[str, float]:
    return {
        "ratio_makespan": metrics["makespan"] / fifo_baseline["fifo_makespan"],
        "ratio_cost": metrics["cost"] / fifo_baseline["fifo_cost"],
        "ratio_energy": metrics["energy"] / fifo_baseline["fifo_energy"],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Compare initial scheduling heuristics")
    parser.add_argument(
        "--dataset",
        type=Path,
        default=DEFAULT_DATASET,
        help="Directory containing .fjs instances",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "results" / "initial_method_comparison.csv",
        help="CSV output path",
    )
    args = parser.parse_args()

    if not BIN.exists():
        raise FileNotFoundError(f"Missing executable: {BIN}. Build production_scheduling first.")

    instances = sorted(args.dataset.glob("*.fjs"))
    if not instances:
        raise FileNotFoundError(f"No .fjs files found in {args.dataset}")

    all_rows: list[dict[str, object]] = []
    summary = defaultdict(lambda: defaultdict(float))
    fifo_summary = defaultdict(float)
    win_count = defaultdict(int)

    numeric_keys = (
        "makespan",
        "cost",
        "energy",
        "fifo_makespan",
        "fifo_cost",
        "fifo_energy",
        "ratio_makespan",
        "ratio_cost",
        "ratio_energy",
        "combined_objective",
    )

    for instance_path in instances:
        instance, fifo_baseline, method_rows, best_method = run_instance(instance_path)
        for method in METHODS:
            metrics = method_rows[method]
            ratios = build_objective_ratios(metrics, fifo_baseline)
            row = {
                "instance": instance,
                "method": method,
                "makespan": metrics["makespan"],
                "cost": metrics["cost"],
                "energy": metrics["energy"],
                "fifo_makespan": int(fifo_baseline["fifo_makespan"]),
                "fifo_cost": int(fifo_baseline["fifo_cost"]),
                "fifo_energy": int(fifo_baseline["fifo_energy"]),
                "ratio_makespan": ratios["ratio_makespan"],
                "ratio_cost": ratios["ratio_cost"],
                "ratio_energy": ratios["ratio_energy"],
                "combined_objective": metrics["combined_objective"],
                "is_best": int(method == best_method),
            }
            all_rows.append(row)
            for key in numeric_keys:
                summary[method][key] += row[key]
        for key in ("fifo_makespan", "fifo_cost", "fifo_energy"):
            fifo_summary[key] += fifo_baseline[key]
        win_count[best_method] += 1

    dataset_name = args.dataset.name
    n = len(instances)
    average_rows: list[dict[str, object]] = []
    for method in METHODS:
        average_rows.append(
            {
                "instance": f"{dataset_name}_AVERAGE",
                "method": method,
                "makespan": round(summary[method]["makespan"] / n, 4),
                "cost": round(summary[method]["cost"] / n, 4),
                "energy": round(summary[method]["energy"] / n, 4),
                "fifo_makespan": round(fifo_summary["fifo_makespan"] / n, 4),
                "fifo_cost": round(fifo_summary["fifo_cost"] / n, 4),
                "fifo_energy": round(fifo_summary["fifo_energy"] / n, 4),
                "ratio_makespan": round(summary[method]["ratio_makespan"] / n, 6),
                "ratio_cost": round(summary[method]["ratio_cost"] / n, 6),
                "ratio_energy": round(summary[method]["ratio_energy"] / n, 6),
                "combined_objective": round(summary[method]["combined_objective"] / n, 6),
                "is_best": win_count[method],
            }
        )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "instance",
        "method",
        "makespan",
        "cost",
        "energy",
        "fifo_makespan",
        "fifo_cost",
        "fifo_energy",
        "ratio_makespan",
        "ratio_cost",
        "ratio_energy",
        "combined_objective",
        "is_best",
    ]
    with args.output.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(all_rows)
        writer.writerows(average_rows)

    print(f"Compared {n} instances. Detailed CSV: {args.output}")
    print()
    print("Average metrics (lower is better):")
    print(f"{'Method':<16} {'Makespan':>10} {'Cost':>12} {'Energy':>10} {'Combined':>10} {'Wins':>6}")
    for method in METHODS:
        avg = summary[method]
        print(
            f"{method:<16} "
            f"{avg['makespan'] / n:>10.1f} "
            f"{avg['cost'] / n:>12.1f} "
            f"{avg['energy'] / n:>10.1f} "
            f"{avg['combined_objective'] / n:>10.4f} "
            f"{win_count[method]:>6}"
        )


if __name__ == "__main__":
    main()

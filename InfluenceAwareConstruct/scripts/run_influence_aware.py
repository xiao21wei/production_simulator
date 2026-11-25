#!/usr/bin/env python3
"""Run InfluenceAwareConstruct on one instance and print its objectives."""

from __future__ import annotations

import argparse
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BIN = ROOT / "build" / "influence_aware_scheduler"
DEFAULT_INSTANCE = (
    ROOT / "datasets" / "raw" / "Brandimarte" / "BrandimarteMk3.fjs"
)


def parse_rows(output: str) -> dict[str, dict[str, float]]:
    rows: dict[str, dict[str, float]] = {}
    in_table = False
    for raw_line in output.splitlines():
        line = raw_line.strip()
        if line == "method,makespan,cost,energy,combined_objective":
            in_table = True
            continue
        if not in_table or line.startswith("best_method,"):
            continue
        parts = line.split(",")
        if len(parts) != 5:
            continue
        method, makespan, cost, energy, combined = parts
        rows[method] = {
            "makespan": float(makespan),
            "cost": float(cost),
            "energy": float(energy),
            "combined_objective": float(combined),
        }
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Evaluate InfluenceAwareConstruct as an initial FJSP schedule."
    )
    parser.add_argument("instance", nargs="?", type=Path, default=DEFAULT_INSTANCE)
    args = parser.parse_args()

    if not BIN.is_file():
        raise FileNotFoundError(
            f"Missing executable: {BIN}. Build the project with CMake first."
        )

    completed = subprocess.run(
        [str(BIN), str(args.instance.resolve()), "--compare-initial"],
        check=True,
        capture_output=True,
        text=True,
    )
    rows = parse_rows(completed.stdout)
    if "InfluenceAwareConstruct" not in rows:
        raise RuntimeError(
            "InfluenceAwareConstruct result was not present in solver output"
        )

    result = rows["InfluenceAwareConstruct"]
    print(f"instance: {args.instance.name}")
    print(f"makespan: {result['makespan']:.4f}")
    print(f"cost: {result['cost']:.4f}")
    print(f"energy: {result['energy']:.4f}")
    print(f"combined_objective: {result['combined_objective']:.6f}")


if __name__ == "__main__":
    main()

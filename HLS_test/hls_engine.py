from __future__ import annotations

import json
import os
import re
import shutil
import stat
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any


class HLSDeploymentEngine:
    def __init__(
        self,
        config: dict[str, Any],
        executable: Path,
    ) -> None:
        self.config = config
        self.executable = self._prepare_executable(executable)

    @staticmethod
    def _prepare_executable(executable: Path) -> Path:
        """Restore the execute bit lost by archive uploads when necessary."""
        executable = Path(executable).resolve()
        if not executable.is_file():
            raise FileNotFoundError(f"HLS executable not found: {executable}")

        if os.access(executable, os.X_OK):
            return executable

        try:
            executable.chmod(
                executable.stat().st_mode
                | stat.S_IXUSR
                | stat.S_IXGRP
                | stat.S_IXOTH
            )
        except OSError:
            pass
        if os.access(executable, os.X_OK):
            return executable

        runtime_dir = Path(tempfile.mkdtemp(prefix="hls_runtime_"))
        copied = runtime_dir / executable.name
        try:
            shutil.copy2(executable, copied)
            copied.chmod(0o755)
        except OSError as exc:
            raise PermissionError(
                f"Could not prepare HLS executable: {executable}"
            ) from exc
        if not os.access(copied, os.X_OK):
            raise PermissionError(
                f"Copied HLS executable is not executable: {copied}"
            )
        return copied

    def predict(self, request: dict[str, Any] | None) -> dict[str, Any]:
        request = request or {}
        if not isinstance(request, dict):
            raise ValueError("request must be a JSON object")

        inference = self.config["inference"]
        defaults = self.config["search_defaults"]
        raw_lines = self._required_text(request, "raw_lines")
        additional_lines = request.get("additional_lines")
        if additional_lines is not None and not isinstance(additional_lines, str):
            raise ValueError("additional_lines must be a string when provided")
        additional_lines = additional_lines or ""
        total_chars = len(raw_lines) + len(additional_lines)
        if total_chars > int(inference["max_input_chars"]):
            raise ValueError(
                f"input text exceeds {inference['max_input_chars']} characters"
            )

        normalized_raw, dimensions = self._normalize_raw(raw_lines)
        additional_valid = False
        if additional_lines.strip():
            self._validate_additional(
                additional_lines,
                dimensions["num_jobs"],
                dimensions["num_machines"],
                dimensions["job_operation_counts"],
            )
            additional_valid = True

        instance_name = self._safe_instance_name(request.get("instance_name"))
        seed = self._integer(request, "seed", int(defaults["seed"]))
        total_time = self._integer(
            request,
            "total_time_seconds",
            int(inference["default_total_time_seconds"]),
        )
        if not 1 <= total_time <= int(inference["max_total_time_seconds"]):
            raise ValueError(
                "total_time_seconds must be between 1 and "
                f"{inference['max_total_time_seconds']}"
            )
        if not 0 <= seed <= 4294967295:
            raise ValueError("seed must be between 0 and 4294967295")
        search_mode = self._unit_interval(
            request, "search_mode", float(defaults["search_mode"])
        )
        random_strategy = self._unit_interval(
            request, "random_strategy", float(defaults["random_strategy"])
        )
        max_repeat = self._integer(
            request, "max_repeat_count", int(defaults["max_repeat_count"])
        )
        max_iter = self._integer(
            request, "max_iter_count", int(defaults["max_iter_count"])
        )
        population = self._integer(
            request, "population_size", int(defaults["population_size"])
        )
        tabu_length = self._integer(
            request, "tabu_length", int(defaults["tabu_length"])
        )
        if max_repeat <= 0 or max_iter <= 0 or population < 2 or tabu_length <= 0:
            raise ValueError(
                "max_repeat_count, max_iter_count and tabu_length must be positive; "
                "population_size must be at least 2"
            )

        with tempfile.TemporaryDirectory(prefix="hls_fjsp_") as temp_dir:
            instance_path = Path(temp_dir) / f"{instance_name}.fjs"
            instance_path.write_text(normalized_raw, encoding="utf-8")
            command = [
                str(self.executable),
                str(instance_path),
                str(search_mode),
                str(random_strategy),
                str(max_repeat),
                str(max_iter),
                str(population),
                str(tabu_length),
                "0",
                str(total_time),
                str(seed),
            ]
            environment = os.environ.copy()
            environment.update(
                {
                    "HLS_ENABLE_GREEDY": "1",
                    "HLS_ENABLE_GENETIC": "1",
                    "HLS_ENABLE_TABU": "1",
                    "HLS_ENABLE_GUIDED_SEARCH": "1",
                    "HLS_ENABLE_RESTARTS": "1",
                    "HLS_GREEDY_RL": "0",
                    "HLS_TABU_RL": "0",
                    "HLS_PRINT_RESULT_JSON": "1",
                    "OMP_NUM_THREADS": "1",
                }
            )
            started_at = time.monotonic()
            try:
                completed = subprocess.run(
                    command,
                    check=False,
                    capture_output=True,
                    text=True,
                    timeout=total_time + 20.0,
                    env=environment,
                )
            except subprocess.TimeoutExpired as exc:
                raise RuntimeError(
                    f"HLS solver exceeded the {total_time + 20.0:.0f}s process limit"
                ) from exc
            elapsed = time.monotonic() - started_at

        if completed.returncode != 0:
            detail = (completed.stderr or completed.stdout)[-2000:].strip()
            raise RuntimeError(
                f"HLS solver exited with status {completed.returncode}: {detail}"
            )
        result = self._parse_result(completed.stdout)
        schedule = result["schedule"]
        self._validate_schedule(schedule, dimensions)
        return {
            "success": True,
            "instance_name": instance_name,
            "model": self.executable.name,
            "device": "cpu",
            "n_jobs": dimensions["num_jobs"],
            "n_machines": dimensions["num_machines"],
            "n_operations": dimensions["num_operations"],
            "objectives": {"makespan": int(result["makespan"])},
            "runtime_seconds": round(elapsed, 3),
            "seed": seed,
            "copt_enabled": False,
            "additional_data_used": False,
            "additional_data_valid": additional_valid,
            "feasible": True,
            "schedule": schedule,
        }

    @staticmethod
    def _required_text(request: dict[str, Any], field: str) -> str:
        value = request.get(field)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{field} must be a non-empty string")
        if "\x00" in value:
            raise ValueError(f"{field} must not contain NUL characters")
        return value

    @staticmethod
    def _safe_instance_name(value: Any) -> str:
        candidate = Path(str(value or "instance")).name
        if candidate.lower().endswith(".fjs"):
            candidate = candidate[:-4]
        candidate = re.sub(r"[^A-Za-z0-9_.-]+", "_", candidate)
        return candidate[:80] if candidate not in {"", ".", ".."} else "instance"

    @staticmethod
    def _integer(request: dict[str, Any], field: str, default: int) -> int:
        value = request.get(field, default)
        if isinstance(value, bool):
            raise ValueError(f"{field} must be an integer")
        try:
            parsed = int(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{field} must be an integer") from exc
        return parsed

    @staticmethod
    def _number(request: dict[str, Any], field: str, default: float) -> float:
        value = request.get(field, default)
        if isinstance(value, bool):
            raise ValueError(f"{field} must be a number")
        try:
            parsed = float(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{field} must be a number") from exc
        return parsed

    def _unit_interval(
        self,
        request: dict[str, Any],
        field: str,
        default: float,
    ) -> float:
        value = self._number(request, field, default)
        if not 0.0 <= value <= 1.0:
            raise ValueError(f"{field} must be between 0 and 1")
        return value

    def _normalize_raw(self, raw_lines: str) -> tuple[str, dict[str, Any]]:
        text = raw_lines.replace("\r\n", "\n").replace("\r", "\n")
        text = text.lstrip("\ufeff")
        lines = text.splitlines()
        while lines and not lines[-1].strip():
            lines.pop()
        if not lines:
            raise ValueError("raw_lines is empty")
        header = lines[0].split()
        if len(header) < 2:
            raise ValueError(
                "raw_lines header must contain num_jobs and num_machines"
            )
        try:
            num_jobs, num_machines = int(header[0]), int(header[1])
        except ValueError as exc:
            raise ValueError("raw_lines header fields 1 and 2 must be integers") from exc
        if num_jobs <= 0 or num_machines <= 0:
            raise ValueError("num_jobs and num_machines must be positive")
        if len(lines) != num_jobs + 1:
            raise ValueError(
                f"raw_lines declares {num_jobs} jobs but contains {len(lines) - 1} rows"
            )
        metadata = header[2] if len(header) >= 3 else "0"
        try:
            float(metadata)
        except ValueError as exc:
            raise ValueError("raw_lines header metadata must be numeric") from exc

        parsed_jobs: list[list[list[tuple[int, int]]]] = []
        machine_ids: list[int] = []
        for job_index, line in enumerate(lines[1:], start=1):
            try:
                values = [int(value) for value in line.split()]
            except ValueError as exc:
                raise ValueError(f"raw_lines job {job_index} contains a non-integer") from exc
            if not values or values[0] <= 0:
                raise ValueError(f"raw_lines job {job_index} has no operations")
            cursor = 1
            operations = []
            for operation_index in range(values[0]):
                if cursor >= len(values):
                    raise ValueError(
                        f"raw_lines job {job_index} operation {operation_index + 1} is truncated"
                    )
                option_count = values[cursor]
                cursor += 1
                if option_count <= 0 or cursor + 2 * option_count > len(values):
                    raise ValueError(
                        f"raw_lines job {job_index} operation "
                        f"{operation_index + 1} has an invalid option count"
                    )
                options = []
                for _ in range(option_count):
                    machine_id, processing_time = values[cursor : cursor + 2]
                    cursor += 2
                    if processing_time <= 0:
                        raise ValueError("processing times must be positive")
                    machine_ids.append(machine_id)
                    options.append((machine_id, processing_time))
                operations.append(options)
            if cursor != len(values):
                raise ValueError(f"raw_lines job {job_index} has trailing values")
            parsed_jobs.append(operations)

        zero_based = 0 in machine_ids
        normalized_jobs = []
        for operations in parsed_jobs:
            normalized_operations = []
            for options in operations:
                normalized_options = []
                for machine_id, processing_time in options:
                    normalized_machine = machine_id + 1 if zero_based else machine_id
                    if not 1 <= normalized_machine <= num_machines:
                        raise ValueError(
                            f"machine {machine_id} is outside the valid range for "
                            f"{num_machines} machines"
                        )
                    normalized_options.append((normalized_machine, processing_time))
                normalized_operations.append(normalized_options)
            normalized_jobs.append(normalized_operations)

        normalized_lines = [f"{num_jobs} {num_machines} {metadata}"]
        for operations in normalized_jobs:
            values = [str(len(operations))]
            for options in operations:
                values.append(str(len(options)))
                for machine_id, processing_time in options:
                    values.extend((str(machine_id), str(processing_time)))
            normalized_lines.append(" ".join(values))
        return (
            "\n".join(normalized_lines) + "\n",
            {
                "num_jobs": num_jobs,
                "num_machines": num_machines,
                "num_operations": sum(len(job) for job in parsed_jobs),
                "job_operation_counts": tuple(len(job) for job in parsed_jobs),
            },
        )

    @staticmethod
    def _validate_additional(
        additional_lines: str,
        num_jobs: int,
        num_machines: int,
        job_operation_counts: tuple[int, ...],
    ) -> None:
        lines = [
            line
            for line in additional_lines.replace("\r\n", "\n").splitlines()
            if line.strip()
        ]
        expected = 2 * num_jobs + 2 * num_machines
        if len(lines) != expected:
            raise ValueError(
                f"additional_lines must contain {expected} rows for "
                f"{num_jobs} jobs and {num_machines} machines"
            )
        values = []
        for index, line in enumerate(lines, start=1):
            try:
                values.append([int(value) for value in line.split()])
            except ValueError as exc:
                raise ValueError(
                    f"additional_lines row {index} contains a non-integer"
                ) from exc
        cursor = 0
        for job_index, operation_count in enumerate(job_operation_counts):
            row = values[cursor]
            cursor += 1
            if not row or row[0] != operation_count:
                raise ValueError(
                    f"additional_lines energy row {job_index + 1} must declare "
                    f"{operation_count} operations"
                )
            position = 1
            for operation_index in range(operation_count):
                if position >= len(row):
                    raise ValueError(
                        f"additional_lines energy row {job_index + 1} operation "
                        f"{operation_index + 1} is truncated"
                    )
                option_count = row[position]
                position += 1
                if option_count <= 0 or position + 2 * option_count > len(row):
                    raise ValueError(
                        f"additional_lines energy row {job_index + 1} operation "
                        f"{operation_index + 1} has an invalid option count"
                    )
                for _ in range(option_count):
                    machine_id = row[position]
                    position += 2
                    if not 1 <= machine_id <= num_machines:
                        raise ValueError(
                            f"additional_lines energy row {job_index + 1} contains "
                            f"an invalid machine id"
                        )
            if position != len(row):
                raise ValueError(
                    f"additional_lines energy row {job_index + 1} contains "
                    "trailing values"
                )
        for job_index in range(num_jobs):
            if len(values[cursor]) != 5:
                raise ValueError(
                    f"additional_lines feature row {job_index + 1} must contain 5 values"
                )
            cursor += 1
        for matrix_name in ("transport-time", "transport-energy"):
            for row_index in range(num_machines):
                if len(values[cursor]) != num_machines:
                    raise ValueError(
                        f"additional_lines {matrix_name} row {row_index + 1} "
                        f"must contain {num_machines} values"
                    )
                cursor += 1

    @staticmethod
    def _parse_result(stdout: str) -> dict[str, Any]:
        marker = "HLS_RESULT_JSON: "
        for line in reversed(stdout.splitlines()):
            if line.startswith(marker):
                try:
                    return json.loads(line[len(marker) :])
                except json.JSONDecodeError as exc:
                    raise RuntimeError("HLS returned malformed result JSON") from exc
        raise RuntimeError("HLS did not return a machine-readable result")

    @staticmethod
    def _validate_schedule(
        schedule: list[dict[str, Any]],
        dimensions: dict[str, Any],
    ) -> None:
        if not isinstance(schedule, list) or not schedule:
            raise RuntimeError("HLS returned an empty schedule")
        actual = {
            (int(row["job_id"]), int(row["operation_index"]))
            for row in schedule
        }
        if (
            len(actual) != len(schedule)
            or len(schedule) != dimensions["num_operations"]
        ):
            raise RuntimeError("HLS returned duplicate or missing operations")

        by_machine: dict[int, list[dict[str, Any]]] = {}
        by_job: dict[int, list[dict[str, Any]]] = {}
        for row in schedule:
            start = float(row["start_time"])
            end = float(row["end_time"])
            if start < 0 or end < start:
                raise RuntimeError("HLS returned an invalid time interval")
            machine_id = int(row["machine_id"])
            if not 0 <= machine_id < dimensions["num_machines"]:
                raise RuntimeError("HLS returned an invalid machine identifier")
            by_machine.setdefault(machine_id, []).append(row)
            by_job.setdefault(int(row["job_id"]), []).append(row)

        for rows in by_machine.values():
            rows.sort(key=lambda row: (row["start_time"], row["end_time"]))
            if any(
                float(left["end_time"]) > float(right["start_time"])
                for left, right in zip(rows, rows[1:])
            ):
                raise RuntimeError("HLS schedule contains overlapping machine work")
        for rows in by_job.values():
            rows.sort(key=lambda row: row["operation_index"])
            if [row["operation_index"] for row in rows] != list(range(len(rows))):
                raise RuntimeError("HLS returned a gap in job operation indices")
            if any(
                float(left["end_time"]) > float(right["start_time"])
                for left, right in zip(rows, rows[1:])
            ):
                raise RuntimeError("HLS schedule violates job precedence")

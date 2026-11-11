#!/usr/bin/env python3
"""Inject repeated machine anomalies into the running Web simulator."""

import argparse
import json
import time
import urllib.error
import urllib.request


DEFAULT_BASE_URL = "http://127.0.0.1:8000"
ANOMALY_ORDER = (
    "long_failure",
    "short_failure",
    "medium_failure",
    "degraded",
)
DEFAULT_DURATIONS = {
    "long_failure": (15, 20),
    "short_failure": (2, 3),
    "medium_failure": (5, 7),
    "degraded": (10, 12),
}
ACTIVE_ANOMALY_STATUSES = {"failed", "repairing", "degraded"}


def request_json(base_url, path, payload=None, timeout=240):
    data = None
    headers = {}
    method = "GET"
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
        method = "POST"
    request = urllib.request.Request(
        f"{base_url}{path}",
        data=data,
        headers=headers,
        method=method,
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        response_body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(
            f"HTTP {exc.code} for {path}: {response_body}"
        ) from exc


def wait_for_state(base_url, accepted, timeout=30):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        state = request_json(base_url, "/api/state", timeout=10)
        if state.get("status") in accepted:
            return state
        time.sleep(0.5)
    raise RuntimeError(
        "Simulation did not reach state: " + ", ".join(sorted(accepted))
    )


def ensure_running(base_url):
    state = request_json(base_url, "/api/state", timeout=10)
    if state.get("status") == "paused":
        request_json(base_url, "/api/pause", {"paused": False})
        state = wait_for_state(base_url, {"running"})
    if state.get("status") == "reoptimizing":
        return wait_for_state(base_url, {"running"})
    if state.get("status") == "running":
        return state
    if state.get("status") == "preparing":
        return wait_for_state(base_url, {"running"})
    if state.get("status") not in {"idle", "finished", "failed"}:
        raise RuntimeError(
            f"Cannot start simulation from state {state.get('status')!r}."
        )

    catalog = request_json(base_url, "/api/datasets", timeout=10)
    dataset_id = catalog["default_dataset"]
    started = request_json(
        base_url,
        "/api/start",
        {"dataset_id": dataset_id},
        timeout=30,
    )
    if not started.get("started"):
        raise RuntimeError(started.get("error", "Failed to start simulation."))
    return wait_for_state(base_url, {"running"})


def available_machines(state, allowed_machine_ids):
    machines = []
    for machine in state.get("machine_states", []):
        machine_id = int(machine["id"])
        if allowed_machine_ids and machine_id not in allowed_machine_ids:
            continue
        if machine.get("status") in ACTIVE_ANOMALY_STATUSES:
            continue
        machines.append(machine)
    return sorted(
        machines,
        key=lambda item: (
            item.get("status") != "busy",
            -int(item.get("pending", 0)),
            int(item["id"]),
        ),
    )


def wait_for_available_machine(
    base_url,
    allowed_machine_ids,
    excluded_machine_ids,
    timeout=120,
):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        state = request_json(base_url, "/api/state", timeout=10)
        if state.get("status") == "finished":
            raise RuntimeError(
                "Simulation finished before all anomalies were injected."
            )
        for machine in available_machines(state, allowed_machine_ids):
            if int(machine["id"]) not in excluded_machine_ids:
                return machine
        time.sleep(1)
    raise RuntimeError(
        "No machine became available within the configured timeout."
    )


def inject_anomaly(
    base_url,
    machine,
    anomaly_type,
    duration,
):
    payload = {
        "machine_id": int(machine["id"]),
        "anomaly_type": anomaly_type,
        "duration": duration,
    }
    result = request_json(
        base_url,
        "/api/anomalies/machine",
        payload,
    )
    if not result.get("success"):
        raise RuntimeError(result.get("error", "Anomaly injection failed."))
    return {
        "request": payload,
        "machine_status_before": machine.get("status"),
        "machine_status": result.get("machine_status"),
        "recovery_time": result.get("recovery_time"),
        "affected_operation_count": len(
            result.get("affected_operations", [])
        ),
        "reschedule_method": result.get("reschedule_method"),
    }


def wait_for_finish(base_url, timeout):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        state = request_json(base_url, "/api/state", timeout=10)
        if state.get("status") in {"finished", "failed"}:
            return state
        time.sleep(1)
    raise RuntimeError(
        f"Simulation did not finish within {timeout} seconds."
    )


def parse_machine_ids(value):
    if not value:
        return set()
    return {
        int(item.strip())
        for item in value.split(",")
        if item.strip()
    }


def main():
    parser = argparse.ArgumentParser(
        description="Inject repeated machine anomalies into the simulator."
    )
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument(
        "--rounds",
        type=int,
        default=4,
        help="Rounds for short, medium and degraded anomalies (default: 4).",
    )
    parser.add_argument(
        "--long-failure-count",
        type=int,
        default=None,
        help=(
            "Number of long failures; defaults to half of --rounds, "
            "with a minimum of 1."
        ),
    )
    parser.add_argument(
        "--interval",
        type=float,
        default=1.0,
        help="Wall-clock seconds between anomaly requests.",
    )
    parser.add_argument(
        "--speed",
        type=float,
        default=2.0,
        help="Set simulator speed before anomaly injection.",
    )
    parser.add_argument(
        "--machine-ids",
        default="",
        help="Optional comma-separated machine IDs.",
    )
    parser.add_argument(
        "--wait-finish-timeout",
        type=float,
        default=600.0,
        help="Seconds to wait for final simulation completion.",
    )
    args = parser.parse_args()
    if args.rounds <= 0:
        parser.error("--rounds must be positive.")
    long_failure_count = (
        max(1, args.rounds // 2)
        if args.long_failure_count is None
        else args.long_failure_count
    )
    if long_failure_count < 0 or long_failure_count > args.rounds:
        parser.error(
            "--long-failure-count must be between 0 and --rounds."
        )
    if args.interval < 0:
        parser.error("--interval must be non-negative.")

    base_url = args.base_url.rstrip("/")
    allowed_machine_ids = parse_machine_ids(args.machine_ids)
    ensure_running(base_url)
    if args.speed is not None:
        request_json(base_url, "/api/speed", {"speed": args.speed})

    results = []
    for round_index in range(args.rounds):
        used_machine_ids = set()
        for anomaly_type in ANOMALY_ORDER:
            if (
                anomaly_type == "long_failure"
                and round_index >= long_failure_count
            ):
                continue
            machine = wait_for_available_machine(
                base_url,
                allowed_machine_ids,
                used_machine_ids,
            )
            used_machine_ids.add(int(machine["id"]))
            durations = DEFAULT_DURATIONS[anomaly_type]
            duration = durations[round_index % len(durations)]
            result = inject_anomaly(
                base_url,
                machine,
                anomaly_type,
                duration,
            )
            results.append(result)
            print(json.dumps(result, ensure_ascii=False), flush=True)
            if args.interval > 0:
                time.sleep(args.interval)

    final_state = wait_for_finish(base_url, args.wait_finish_timeout)
    summary = {
        "injected_count": len(results),
        "rounds": args.rounds,
        "long_failure_count": long_failure_count,
        "by_type": {
            anomaly_type: sum(
                result["request"]["anomaly_type"] == anomaly_type
                for result in results
            )
            for anomaly_type in ANOMALY_ORDER
        },
        "final_status": final_state.get("status"),
        "finished_jobs": final_state.get("finished_jobs"),
        "canceled_jobs": final_state.get("canceled_jobs"),
        "makespan": final_state.get("makespan"),
    }
    print(json.dumps(summary, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()

import argparse
import json
import mimetypes
import socket
import tempfile
import threading
import traceback
from dataclasses import asdict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from simulator.config import DEFAULT_CONFIG_PATH, load_simulator_config
from simulator.dataset import list_dataset_sources
from simulator.run_log import SimulationRunLogger
from simulator.simulator import Simulator


PROJECT_ROOT = Path(__file__).resolve().parent
WEB_ROOT = PROJECT_ROOT / "web"
HLS_TEST_ROOT = PROJECT_ROOT / "HLS_test"
HLS_OPTION_FIELDS = (
    "total_time_seconds",
    "search_mode",
    "random_strategy",
    "max_repeat_count",
    "max_iter_count",
    "population_size",
    "tabu_length",
)
REOPTIMIZATION_COMMAND_ALIASES = {
    "drl": "drl",
    "mofjsp": "drl",
    "hls": "hls",
}
REOPTIMIZATION_COMMAND_CONFIG_FIELDS = {
    "drl": {"num_samples", "seed"},
    "hls": {"seed", *HLS_OPTION_FIELDS},
}
EVENT_FIELDS = (
    "job_id",
    "operation_id",
    "machine_id",
)


def serialize_event(event, simulator):
    event_data = {
        "id": event.id,
        "timestamp": event.timestamp,
        "type": type(event).__name__,
    }
    for field in EVENT_FIELDS:
        if hasattr(event, field):
            event_data[field] = getattr(event, field)

    if type(event).__name__ == "OperationStartEvent":
        event_data["processing_time"] = simulator.jobs[
            event.job_id
        ].operation_times[event.operation_id][event.machine_id]

    return event_data


def serialize_plan(planned_operations):
    return [asdict(operation) for operation in planned_operations]


class DashboardState:
    def __init__(self, display_percent=100):
        self.lock = threading.RLock()
        self.status = "idle"
        self.generation = 0
        self.events = []
        self.plan = []
        self.current_time = 0
        self.makespan = 0
        self.speed = 5.0
        self.horizon = 100
        self.finished_jobs = 0
        self.total_jobs = 0
        self.machine_states = []
        self.objectives = {}
        self.selected_dataset = None
        self.error = None
        self.plan_revision = 0
        self.display_percent = float(display_percent)
        self.auto_job_submission_enabled = False
        self.auto_job_submission_triggered = False
        self.auto_job_submission_count = 0
        self.auto_job_submission_threshold = None

    def prepare(self, speed):
        with self.lock:
            self.generation += 1
            self.status = "preparing"
            self.events = []
            self.plan = []
            self.current_time = 0
            self.makespan = 0
            self.speed = speed
            self.horizon = 100
            self.finished_jobs = 0
            self.total_jobs = 0
            self.machine_states = []
            self.objectives = {}
            self.selected_dataset = None
            self.error = None
            self.plan_revision = 0
            self.auto_job_submission_triggered = False
            self.auto_job_submission_count = 0
            self.auto_job_submission_threshold = None

    def set_running(self, simulator):
        with self.lock:
            self.status = "running"
            self.speed = simulator.speed
            self.total_jobs = len(simulator.jobs)
            self.plan = serialize_plan(simulator.planned_operations)
            self.plan_revision += 1
            self._update_simulator(simulator)

    def record_event(self, event, simulator):
        event_data = serialize_event(event, simulator)
        with self.lock:
            self.events.append(event_data)
            self._update_simulator(simulator)

    def finish(self, simulator):
        with self.lock:
            self.status = "finished"
            self._update_simulator(simulator)

    def fail(self, error):
        with self.lock:
            self.status = "failed"
            self.error = str(error)

    def set_display_percent(self, display_percent):
        display_percent = float(display_percent)
        if not 25 <= display_percent <= 300:
            raise ValueError(
                "Display percent must be between 25 and 300."
            )
        with self.lock:
            self.display_percent = display_percent

    def snapshot(self, after=0):
        with self.lock:
            if after < 0 or after > len(self.events):
                after = 0
            events = self.events[after:]
            return {
                "status": self.status,
                "generation": self.generation,
                "events": events,
                "next_event_index": after + len(events),
                "plan": self.plan,
                "plan_revision": self.plan_revision,
                "current_time": self.current_time,
                "makespan": self.makespan,
                "speed": self.speed,
                "display_percent": self.display_percent,
                "horizon": self.horizon,
                "finished_jobs": self.finished_jobs,
                "total_jobs": self.total_jobs,
                "machine_states": self.machine_states,
                "objectives": self.objectives,
                "selected_dataset": self.selected_dataset,
                "error": self.error,
                "auto_job_submission": {
                    "enabled": self.auto_job_submission_enabled,
                    "triggered": self.auto_job_submission_triggered,
                    "count": self.auto_job_submission_count,
                    "threshold": self.auto_job_submission_threshold,
                },
            }

    def _update_simulator(self, simulator):
        self.current_time = simulator.curr_time
        self.makespan = simulator.makespan
        self.finished_jobs = len(simulator.finished_queue)
        self.total_jobs = len(simulator.jobs)
        self.horizon = max(
            100,
            int(self.current_time) + 20,
            max(
                (operation.end_time for operation in simulator.planned_operations),
                default=0,
            ),
        )
        self.machine_states = [
            {
                "id": machine.machine_id,
                "status": machine.machine_status,
                "pending": len(machine.pending_operations),
            }
            for machine in simulator.machines
        ]
        self.objectives = dict(getattr(simulator, "objectives", {}))


class SimulationManager:
    def __init__(
        self,
        config_path,
        speed,
        display_percent=100,
        real_time_step=None,
        realtime=None,
        scheduler_factory=None,
        hls_scheduler_factory=None,
        log_dir=None,
    ):
        self.config_path = Path(config_path).resolve()
        config = load_simulator_config(self.config_path)
        self.speed = float(speed)
        self.real_time_step = real_time_step
        self.realtime = realtime
        self.state = DashboardState(display_percent)
        self.simulator = None
        self.selected_source = None
        self.thread = None
        self.start_lock = threading.Lock()
        self.mutation_lock = threading.RLock()
        self.scheduler_lock = threading.Lock()
        self.scheduler_factory = scheduler_factory
        self.hls_scheduler_factory = hls_scheduler_factory
        self._scheduler = None
        self._hls_scheduler = None
        self.auto_job_submission_enabled = False
        self.auto_job_submission_triggered = False
        self.auto_job_submission_count = 0
        self.run_logger = None
        self.dataset_root = (
            self.config_path.parent / config["paths"]["dataset_root"]
        ).resolve()
        self.log_dir = (
            Path(log_dir).resolve()
            if log_dir is not None
            else (self.config_path.parent / config["paths"]["log_dir"]).resolve()
        )
        default_raw_path = (
            self.config_path.parent / config["paths"]["input_file"]
        ).resolve()
        self.datasets = list_dataset_sources(
            self.dataset_root,
            default_raw_path,
        )
        if not self.datasets:
            raise RuntimeError(
                f"No raw/add dataset pairs found under {self.dataset_root}"
            )
        self.datasets_by_id = {
            dataset["id"]: dataset for dataset in self.datasets
        }
        default_source = next(
            (source for source in self.datasets if source["is_default"]),
            self.datasets[0],
        )
        self.default_dataset_id = default_source["id"]
        self.output_dir = Path(
            tempfile.mkdtemp(prefix="production_simulator_web_")
        )

    def start(self, dataset_id=None):
        with self.start_lock:
            if self.thread is not None and self.thread.is_alive():
                return False
            dataset_id = dataset_id or self.default_dataset_id
            source = self.datasets_by_id.get(dataset_id)
            if source is None:
                raise ValueError(f"Unknown dataset ID: {dataset_id}")
            self.selected_source = source
            self.state.prepare(self.speed)
            self.state.selected_dataset = {
                "id": source["id"],
                "name": source["name"],
                "label": source["label"],
            }
            self.thread = threading.Thread(
                target=self._run,
                name="simulation-runner",
                daemon=True,
            )
            self.thread.start()
            return True

    def set_speed(self, speed):
        speed = float(speed)
        if speed <= 0:
            raise ValueError("Speed must be greater than zero.")
        self.speed = speed
        if self.simulator is not None:
            self.simulator.set_speed(speed)
        with self.state.lock:
            self.state.speed = speed

    def set_display_percent(self, display_percent):
        self.state.set_display_percent(display_percent)

    def _run(self):
        try:
            self.run_logger = SimulationRunLogger(self.log_dir)
            self.run_logger.start(
                {
                    "dataset": self.state.selected_dataset,
                    "dataset_raw_file": self.selected_source["raw_file"],
                    "dataset_additional_file": self.selected_source[
                        "additional_file"
                    ],
                    "config_path": str(self.config_path),
                    "speed": self.speed,
                    "real_time_step": self.real_time_step,
                    "realtime": self.realtime,
                }
            )
            self.simulator = Simulator(
                config_path=self.config_path,
                speed=self.speed,
                real_time_step=self.real_time_step,
                realtime=self.realtime,
            )
            self.simulator.log_tag = False
            self.simulator.schedule_file = str(
                self.output_dir / "web_result_schedule.csv"
            )
            self.simulator.gantt_file = str(
                self.output_dir / "web_gantt_chart.txt"
            )
            self.simulator.init(
                file_path=self.selected_source["raw_file"],
                additional_file_path=self.selected_source["additional_file"],
            )
            self.simulator.event_lock = self.mutation_lock
            self.auto_job_submission_triggered = False
            self.auto_job_submission_count = 0
            self.state.auto_job_submission_enabled = (
                self.auto_job_submission_enabled
            )
            self.state.auto_job_submission_triggered = False
            self.state.auto_job_submission_count = 0
            self.state.auto_job_submission_threshold = (
                self._auto_job_submission_threshold()
            )

            self.state.set_running(self.simulator)
            original_handle_event = self.simulator.handleEvent

            def handle_and_publish(event):
                with self.mutation_lock:
                    original_handle_event(event)
                    self.state.record_event(event, self.simulator)
                    self.run_logger.record_event(event, self.simulator)
                    self._maybe_auto_submit_jobs()

            self.simulator.handleEvent = handle_and_publish
            self.simulator.run()
            self.run_logger.finish(self.simulator)
            self.state.finish(self.simulator)
        except Exception as exc:
            traceback.print_exc()
            self.state.fail(exc)
            if self.run_logger is not None:
                self.run_logger.fail(exc)

    def reoptimize(self, num_samples=1, seed=0):
        """Use the mofjsp model to reassign all unfinished operations."""
        with self.mutation_lock:
            with self.state.lock:
                if self.simulator is None:
                    raise ValueError("Simulation has not been started.")
                if self.state.status != "running":
                    raise ValueError("Simulation must be running to reoptimize.")
                source = self.selected_source
                self.state.status = "reoptimizing"

            self.simulator.pause()
            try:
                scheduler = self._get_scheduler()
                raw_text = Path(source["raw_file"]).read_text(encoding="utf-8")
                additional_text = Path(
                    source["additional_file"]
                ).read_text(encoding="utf-8")
                model_result = scheduler.predict(
                    {
                        "raw_lines": raw_text,
                        "additional_lines": additional_text,
                        "instance_name": source["id"],
                        "num_samples": int(num_samples),
                        "seed": int(seed),
                    }
                )
                assignments = {
                    (row["job_id"], row["operation_index"]): row[
                        "machine_id"
                    ]
                    for row in model_result["schedule"]
                }
                assignments = self._completeUnfinishedAssignments(
                    assignments
                )
                reoptimization = (
                    self.simulator.reoptimizeUnfinishedOperations(
                        assignments,
                        current_time=max(
                            self.simulator.curr_time,
                            self.simulator.clock.current_simulation_time,
                            self.simulator.pending_event_timestamp
                            or self.simulator.curr_time,
                        ),
                    )
                )
                with self.state.lock:
                    self.state.plan = serialize_plan(
                        self.simulator.planned_operations
                    )
                    self.state.plan_revision += 1
                    self.state.status = "running"
                    self.state._update_simulator(self.simulator)
            except Exception as exc:
                with self.state.lock:
                    self.state.status = "running"
                if self.run_logger is not None:
                    self.run_logger.record_reoptimization(
                        {
                            "num_samples": int(num_samples),
                            "seed": int(seed),
                            "simulation_time": self.simulator.curr_time,
                        },
                        {
                            "success": False,
                            "error_type": type(exc).__name__,
                            "error": str(exc),
                        },
                        self.simulator,
                    )
                raise
            finally:
                self.simulator.resume()

            response = {
                "success": True,
                "model": model_result.get("model"),
                "num_samples": model_result.get("num_samples"),
                "model_objectives": model_result.get("objectives"),
                **reoptimization,
            }
            if self.run_logger is not None:
                self.run_logger.record_reoptimization(
                    {
                        "num_samples": int(num_samples),
                        "seed": int(seed),
                        "simulation_time": self.simulator.curr_time,
                    },
                    response,
                    self.simulator,
                )
            return response

    def hls_reoptimize(self, seed=0, **hls_options):
        """
        Use HLS to optimize makespan and apply only its machine assignments.

        HLS does not model transport time, so its returned schedule timestamps
        are intentionally ignored. The simulator rebuilds every remaining
        operation's start time, transport interval and transport energy.
        """
        with self.mutation_lock:
            with self.state.lock:
                if self.simulator is None:
                    raise ValueError("Simulation has not been started.")
                if self.state.status != "running":
                    raise ValueError("Simulation must be running to reoptimize.")
                source = self.selected_source
                self.state.status = "reoptimizing"

            self.simulator.pause()
            try:
                request = {
                    "raw_lines": Path(source["raw_file"]).read_text(
                        encoding="utf-8"
                    ),
                    "additional_lines": Path(
                        source["additional_file"]
                    ).read_text(encoding="utf-8"),
                    "instance_name": source["id"],
                    "seed": int(seed),
                }
                request.update(
                    {
                        key: hls_options[key]
                        for key in HLS_OPTION_FIELDS
                        if key in hls_options
                    }
                )
                scheduler = self._get_hls_scheduler()
                model_result = scheduler.predict(request)
                unfinished_keys = {
                    (job.job_id, task.operation_id)
                    for job in self.simulator.jobs
                    for task in job.tasks
                    if task.status in {"pending", "scheduled"}
                }
                assignments = {
                    (row["job_id"], row["operation_index"]): row[
                        "machine_id"
                    ]
                    for row in model_result["schedule"]
                    if (
                        row["job_id"],
                        row["operation_index"],
                    )
                    in unfinished_keys
                }
                assignments = self._completeUnfinishedAssignments(
                    assignments
                )
                reoptimization = (
                    self.simulator.reoptimizeUnfinishedOperations(
                        assignments,
                        current_time=max(
                            self.simulator.curr_time,
                            self.simulator.clock.current_simulation_time,
                            self.simulator.pending_event_timestamp
                            or self.simulator.curr_time,
                        ),
                    )
                )
                with self.state.lock:
                    self.state.plan = serialize_plan(
                        self.simulator.planned_operations
                    )
                    self.state.plan_revision += 1
                    self.state.status = "running"
                    self.state._update_simulator(self.simulator)
            except Exception as exc:
                with self.state.lock:
                    self.state.status = "running"
                if self.run_logger is not None:
                    self.run_logger.record_reoptimization(
                        {
                            "optimizer": "hls",
                            "seed": int(seed),
                            "simulation_time": self.simulator.curr_time,
                            "options": dict(hls_options),
                        },
                        {
                            "success": False,
                            "error_type": type(exc).__name__,
                            "error": str(exc),
                        },
                        self.simulator,
                    )
                raise
            finally:
                self.simulator.resume()

            response = {
                "success": True,
                "optimizer": "hls",
                "model": model_result.get("model"),
                "hls_objectives": model_result.get("objectives"),
                "hls_runtime_seconds": model_result.get("runtime_seconds"),
                "hls_seed": model_result.get("seed"),
                "hls_schedule_times_used": False,
                "transport_time_recalculated": True,
                "assignment_scope": "pending_and_scheduled_operations",
                "hls_assignment_count": len(assignments),
                "additional_data_used": model_result.get(
                    "additional_data_used",
                    False,
                ),
                **reoptimization,
            }
            if self.run_logger is not None:
                self.run_logger.record_reoptimization(
                    {
                        "optimizer": "hls",
                        "seed": int(seed),
                        "simulation_time": self.simulator.curr_time,
                        "options": dict(hls_options),
                    },
                    response,
                    self.simulator,
                )
            return response

    def reoptimize_command(self, method, config=None):
        """Dispatch a DRL or HLS reoptimization command."""
        normalized_method = self._normalize_reoptimization_method(method)
        if config is None:
            config = {}
        if not isinstance(config, dict):
            raise ValueError("config must be a JSON object.")

        allowed_fields = REOPTIMIZATION_COMMAND_CONFIG_FIELDS[
            normalized_method
        ]
        unknown_fields = sorted(set(config) - allowed_fields)
        if unknown_fields:
            raise ValueError(
                f"Unsupported {normalized_method.upper()} config fields: "
                + ", ".join(unknown_fields)
            )

        normalized_config = dict(config)
        if normalized_method == "hls":
            result = self.hls_reoptimize(**normalized_config)
        else:
            result = self.reoptimize(**normalized_config)
        return {
            **result,
            "optimizer": normalized_method,
            "command_config": normalized_config,
        }

    def submit_random_jobs(self, seed=0):
        """Submit a generated Job batch and reschedule unfinished work."""
        with self.mutation_lock:
            with self.state.lock:
                if self.simulator is None:
                    raise ValueError("Simulation has not been started.")
                if self.state.status != "running":
                    raise ValueError("Simulation must be running to submit a job.")
                self.state.status = "reoptimizing"

            self.simulator.pause()
            try:
                result = self.simulator.submitRandomJobsAndReoptimize(
                    current_time=max(
                        self.simulator.curr_time,
                        self.simulator.clock.current_simulation_time,
                        self.simulator.pending_event_timestamp
                        or self.simulator.curr_time,
                    ),
                    seed=int(seed),
                )
                with self.state.lock:
                    self.state.plan = serialize_plan(
                        self.simulator.planned_operations
                    )
                    self.state.plan_revision += 1
                    self.state.status = "running"
                    self.state._update_simulator(self.simulator)
            except Exception as exc:
                with self.state.lock:
                    self.state.status = "running"
                if self.run_logger is not None:
                    self.run_logger.record_reoptimization(
                        {
                            "optimizer": "dynamic_job_submit",
                            "seed": int(seed),
                            "simulation_time": self.simulator.curr_time,
                        },
                        {
                            "success": False,
                            "error_type": type(exc).__name__,
                            "error": str(exc),
                        },
                        self.simulator,
                    )
                raise
            finally:
                self.simulator.resume()

            response = {
                "success": True,
                "optimizer": "dynamic_job_submit",
                **result,
            }
            if self.run_logger is not None:
                self.run_logger.record_reoptimization(
                    {
                        "optimizer": "dynamic_job_submit",
                        "seed": int(seed),
                        "simulation_time": self.simulator.curr_time,
                    },
                    response,
                    self.simulator,
                )
            return response

    def submit_random_job(self, seed=0):
        """Backward-compatible alias for batch Job submission."""
        return self.submit_random_jobs(seed=seed)

    def set_auto_job_submission(self, enabled):
        if not isinstance(enabled, bool):
            raise ValueError("enabled must be a boolean.")
        with self.mutation_lock:
            self.auto_job_submission_enabled = enabled
            with self.state.lock:
                self.state.auto_job_submission_enabled = enabled
            if (
                enabled
                and self.simulator is not None
                and self.state.status == "running"
            ):
                self._maybe_auto_submit_jobs()

    def _auto_job_submission_threshold(self):
        if self.simulator is None:
            return None
        return max(1, self.simulator.initial_job_count // 3)

    def _maybe_auto_submit_jobs(self):
        if (
            not self.auto_job_submission_enabled
            or self.simulator is None
        ):
            return
        threshold = self._auto_job_submission_threshold()
        remaining_jobs = (
            len(self.simulator.jobs)
            - len(self.simulator.finished_queue)
        )
        if remaining_jobs > threshold:
            return

        self.auto_job_submission_triggered = True
        self.auto_job_submission_count += 1
        with self.state.lock:
            self.state.auto_job_submission_triggered = True
            self.state.auto_job_submission_count = (
                self.auto_job_submission_count
            )
            self.state.auto_job_submission_threshold = threshold
        self.submit_random_jobs(
            seed=self.simulator.seed + self.auto_job_submission_count * 1000
        )

    @staticmethod
    def _normalize_reoptimization_method(method):
        if not isinstance(method, str) or not method.strip():
            raise ValueError("method must be one of: DRL, HLS.")
        normalized_method = REOPTIMIZATION_COMMAND_ALIASES.get(
            method.strip().lower()
        )
        if normalized_method is None:
            raise ValueError("method must be one of: DRL, HLS.")
        return normalized_method

    def _get_scheduler(self):
        with self.scheduler_lock:
            if self._scheduler is not None:
                return self._scheduler
            if self.scheduler_factory is not None:
                self._scheduler = self.scheduler_factory()
                return self._scheduler

            from mofjsp.drl_fjsp.inference import FJSPScheduler

            self._scheduler = FJSPScheduler(PROJECT_ROOT / "mofjsp")
            return self._scheduler

    def preload_scheduler(self):
        """Load the DRL scheduler before the first reoptimization request."""
        return self._get_scheduler()

    def _completeUnfinishedAssignments(self, assignments):
        """Keep model-compatible assignments and cover dynamically added Jobs."""
        completed = dict(assignments)
        for job in self.simulator.jobs:
            for task in job.tasks:
                if task.status not in {"pending", "scheduled"}:
                    continue
                key = (job.job_id, task.operation_id)
                if key in completed:
                    continue
                if task.assigned_machine in task.eligible_machines:
                    completed[key] = task.assigned_machine
                else:
                    completed[key] = min(
                        task.eligible_machines,
                        key=lambda machine_id: (
                            task.processing_times[machine_id],
                            machine_id,
                        ),
                    )
        return completed

    def _get_hls_scheduler(self):
        with self.scheduler_lock:
            if self._hls_scheduler is not None:
                return self._hls_scheduler
            if self.hls_scheduler_factory is not None:
                self._hls_scheduler = self.hls_scheduler_factory()
                return self._hls_scheduler

            from HLS_test.hls_engine import HLSDeploymentEngine

            config_path = HLS_TEST_ROOT / "config.json"
            with config_path.open(encoding="utf-8") as stream:
                config = json.load(stream)
            executable = HLS_TEST_ROOT / config["runtime"]["binary"]
            self._hls_scheduler = HLSDeploymentEngine(config, executable)
            return self._hls_scheduler

class EmbeddedSimulationManager:
    """Expose an existing simulator to the dashboard HTTP API."""

    def __init__(self, state, speed):
        self.state = state
        self.speed = float(speed)
        self.simulator = None

    def attach(self, simulator):
        self.simulator = simulator
        self.speed = simulator.speed
        self.state.set_running(simulator)

    def start(self):
        return False

    def set_speed(self, speed):
        speed = float(speed)
        if speed <= 0:
            raise ValueError("Speed must be greater than zero.")
        self.speed = speed
        self.simulator.set_speed(speed)
        with self.state.lock:
            self.state.speed = speed

    def set_display_percent(self, display_percent):
        self.state.set_display_percent(display_percent)


class DashboardRequestHandler(BaseHTTPRequestHandler):
    server_version = "ProductionSimulatorWeb/1.0"

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/api/state":
            after = int(parse_qs(parsed.query).get("after", ["0"])[0])
            self._send_json(self.server.manager.state.snapshot(after))
            return
        if parsed.path == "/api/datasets":
            datasets = [
                {
                    "id": source["id"],
                    "name": source["name"],
                    "label": source["label"],
                    "num_jobs": source["num_jobs"],
                    "num_machines": source["num_machines"],
                    "is_default": source["is_default"],
                }
                for source in self.server.manager.datasets
            ]
            self._send_json(
                {
                    "default_dataset": (
                        self.server.manager.default_dataset_id
                    ),
                    "datasets": datasets,
                }
            )
            return
        if parsed.path == "/api/health":
            self._send_json({"ok": True})
            return
        self._serve_static(parsed.path)

    def do_POST(self):
        parsed = urlparse(self.path)
        body = self._read_json_body()
        if parsed.path == "/api/start":
            try:
                started = self.server.manager.start(
                    body.get("dataset_id")
                )
                self._send_json(
                    {
                        "started": started,
                        "status": self.server.manager.state.status,
                        "dataset_id": (
                            self.server.manager.selected_source["id"]
                        ),
                    }
                )
            except (TypeError, ValueError) as exc:
                self._send_json(
                    {"started": False, "error": str(exc)},
                    status=400,
                )
            return
        if parsed.path == "/api/speed":
            try:
                self.server.manager.set_speed(body.get("speed"))
                self._send_json(
                    {
                        "ok": True,
                        "speed": self.server.manager.speed,
                    }
                )
            except (TypeError, ValueError) as exc:
                self._send_json({"ok": False, "error": str(exc)}, status=400)
            return
        if parsed.path == "/api/display-percent":
            try:
                self.server.manager.set_display_percent(
                    body.get("display_percent")
                )
                self._send_json(
                    {
                        "ok": True,
                        "display_percent": (
                            self.server.manager.state.display_percent
                        ),
                    }
                )
            except (TypeError, ValueError) as exc:
                self._send_json({"ok": False, "error": str(exc)}, status=400)
            return
        if parsed.path == "/api/auto-job-submission":
            try:
                self.server.manager.set_auto_job_submission(
                    body.get("enabled")
                )
                self._send_json(
                    {
                        "ok": True,
                        "auto_job_submission": (
                            self.server.manager.state.snapshot()[
                                "auto_job_submission"
                            ]
                        ),
                    }
                )
            except (TypeError, ValueError) as exc:
                self._send_json(
                    {"ok": False, "error": str(exc)},
                    status=400,
                )
            return
        if parsed.path == "/api/reoptimize":
            try:
                result = self.server.manager.reoptimize(
                    num_samples=body.get("num_samples", 1),
                    seed=body.get("seed", 0),
                )
                self._send_json(result)
            except (TypeError, ValueError) as exc:
                self._send_json(
                    {"success": False, "error": str(exc)},
                    status=400,
                )
            except Exception as exc:
                traceback.print_exc()
                self._send_json(
                    {"success": False, "error": str(exc)},
                    status=500,
                )
            return
        if parsed.path == "/api/hls-reoptimize":
            try:
                options = {
                    key: body[key]
                    for key in HLS_OPTION_FIELDS
                    if key in body
                }
                result = self.server.manager.hls_reoptimize(
                    seed=body.get("seed", 0),
                    **options,
                )
                self._send_json(result)
            except (TypeError, ValueError) as exc:
                self._send_json(
                    {"success": False, "error": str(exc)},
                    status=400,
                )
            except Exception as exc:
                traceback.print_exc()
                self._send_json(
                    {"success": False, "error": str(exc)},
                    status=500,
                )
            return
        if parsed.path == "/api/reoptimize-command":
            try:
                method = body.get("method", body.get("command"))
                config = body.get("config", body.get("parameters", {}))
                result = self.server.manager.reoptimize_command(
                    method,
                    config,
                )
                self._send_json(result)
            except (TypeError, ValueError) as exc:
                self._send_json(
                    {"success": False, "error": str(exc)},
                    status=400,
                )
            except Exception as exc:
                traceback.print_exc()
                self._send_json(
                    {"success": False, "error": str(exc)},
                    status=500,
                )
            return
        if parsed.path == "/api/jobs/submit":
            try:
                result = self.server.manager.submit_random_jobs(
                    seed=body.get("seed", 0),
                )
                self._send_json(result)
            except (TypeError, ValueError) as exc:
                self._send_json(
                    {"success": False, "error": str(exc)},
                    status=400,
                )
            except Exception as exc:
                traceback.print_exc()
                self._send_json(
                    {"success": False, "error": str(exc)},
                    status=500,
                )
            return
        self._send_json({"error": "Not found."}, status=404)

    def _serve_static(self, request_path):
        relative = "index.html" if request_path == "/" else request_path[1:]
        candidate = (WEB_ROOT / relative).resolve()
        try:
            candidate.relative_to(WEB_ROOT.resolve())
        except ValueError:
            self.send_error(403)
            return

        if not candidate.is_file():
            self.send_error(404)
            return

        content_type = mimetypes.guess_type(candidate.name)[0]
        if content_type is None:
            content_type = "application/octet-stream"
        content = candidate.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", f"{content_type}; charset=utf-8")
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def _read_json_body(self):
        content_length = int(self.headers.get("Content-Length", "0"))
        if content_length == 0:
            return {}
        return json.loads(self.rfile.read(content_length))

    def _send_json(self, payload, status=200):
        content = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def log_message(self, message, *args):
        return


def create_dashboard_server(host, port, manager):
    server = ThreadingHTTPServer(
        (host, int(port)),
        DashboardRequestHandler,
    )
    server.manager = manager
    thread = threading.Thread(
        target=server.serve_forever,
        name="dashboard-server",
        daemon=True,
    )
    thread.start()
    return server, thread


def serve_dashboard(
    config_path,
    host,
    port,
    speed=None,
    display_percent=None,
    real_time_step=None,
    realtime=None,
):
    """Run the dashboard until interrupted; simulations start from the UI."""
    config = load_simulator_config(config_path)
    visualization = config.get("visualization", {})
    host = host or visualization.get("host", "127.0.0.1")
    port = int(port or visualization.get("port", 8000))
    speed = (
        visualization.get("speed", 5.0)
        if speed is None
        else speed
    )
    display_percent = (
        visualization.get("display_percent", 100)
        if display_percent is None
        else display_percent
    )
    manager = SimulationManager(
        config_path=config_path,
        speed=speed,
        display_percent=display_percent,
        real_time_step=real_time_step,
        realtime=realtime,
    )
    server, thread = create_dashboard_server(host, port, manager)
    display_host = host
    if host in {"0.0.0.0", "::"}:
        try:
            probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            try:
                probe.connect(("8.8.8.8", 80))
                display_host = probe.getsockname()[0]
            finally:
                probe.close()
        except OSError:
            display_host = "127.0.0.1"
    print(f"WEB_DASHBOARD=http://{display_host}:{port}", flush=True)
    try:
        manager.preload_scheduler()
        thread.join()
    except KeyboardInterrupt:
        pass
    finally:
        server.shutdown()
        server.server_close()
    return manager


def parse_arguments():
    parser = argparse.ArgumentParser(
        description="Launch the production simulator visualization."
    )
    parser.add_argument("--host", default=None)
    parser.add_argument("--port", type=int, default=None)
    parser.add_argument("--config", default=str(DEFAULT_CONFIG_PATH))
    parser.add_argument(
        "--speed",
        type=float,
        default=None,
        help="Visualization speed; defaults to visualization.speed.",
    )
    return parser.parse_args()


def main():
    args = parse_arguments()
    serve_dashboard(
        config_path=args.config,
        host=args.host,
        port=args.port,
        speed=args.speed,
    )


if __name__ == "__main__":
    main()

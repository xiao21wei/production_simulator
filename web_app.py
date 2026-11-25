import argparse
import csv
import json
import mimetypes
import random
import socket
import tempfile
import threading
import traceback
from dataclasses import asdict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from simulator.config import DEFAULT_CONFIG_PATH, load_simulator_config
from simulator.anomaly import (
    MACHINE_ANOMALY_DEFAULT_DURATIONS,
    MACHINE_ANOMALY_DURATION_RANGES,
    MachineAnomalyType,
    validate_machine_anomaly_duration,
)
from simulator.construction import (
    CONSTRUCTION_METHODS,
    ConstructionError,
    construct_schedule as run_construction,
)
from simulator.detection_data import MachineDetectionDataProvider
from simulator.dataset import (
    list_dataset_sources,
    load_model_additional_text,
)
from simulator.event import (
    MachineAnomalyEvent,
    OrderCancelEvent,
    OrderInsertEvent,
)
from simulator.run_log import SimulationRunLogger
from simulator.simulator import Simulator


PROJECT_ROOT = Path(__file__).resolve().parent
WEB_ROOT = PROJECT_ROOT / "web"
HLS_TEST_ROOT = PROJECT_ROOT / "HLS_test"
AUTO_MACHINE_ANOMALY_INTERVAL = 50
MACHINE_ANOMALY_DRL_NUM_SAMPLES = 1
REOPTIMIZATION_ANIMATION_TIMEOUT = 15.0
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
    "greedy": "greedy",
    "fastest": "greedy",
    "builtin": "greedy",
    "drl": "drl",
    "mofjsp": "drl",
    "hls": "hls",
    "influence_aware": "construction",
    "influenceaware": "construction",
    "influenceawareconstruct": "construction",
    "construction": "construction",
}
REOPTIMIZATION_COMMAND_CONFIG_FIELDS = {
    "greedy": set(),
    "drl": {"num_samples", "seed"},
    "hls": {"seed", *HLS_OPTION_FIELDS},
    "construction": {"method"},
}
EVENT_FIELDS = (
    "job_id",
    "job_ids",
    "order_id",
    "order_ids",
    "order_source",
    "job_count",
    "operation_id",
    "from_stage",
    "to_stage",
    "stage_id",
    "batch_window",
    "job_ready_times",
    "historical",
    "transport_start",
    "transport_end",
    "machine_id",
    "anomaly_type",
    "anomaly_started_at",
    "duration",
    "machine_status",
    "required_materials",
    "replenishment_materials",
    "added_materials",
    "shortage_materials",
    "available_materials",
    "replenishment_event_id",
    "consumed_materials",
    "lead_time",
    "materials_before_recovery",
    "target_materials",
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
    if hasattr(event, "operation_id"):
        try:
            task = simulator.jobs[event.job_id].tasks[
                event.operation_id
            ]
            event_data["stage_id"] = task.stage_id
            event_data["stage_operation_id"] = (
                task.stage_operation_id
            )
        except (AttributeError, IndexError, TypeError):
            pass

    return event_data


def serialize_plan(planned_operations):
    return [asdict(operation) for operation in planned_operations]


def load_material_catalog(dataset_root):
    path = Path(dataset_root) / "material_master.csv"
    if not path.is_file():
        return {}
    catalog = {}
    with path.open(newline="", encoding="utf-8") as source:
        for row in csv.DictReader(source):
            material_id = row.get("material_id")
            if material_id:
                catalog[material_id] = {
                    "material_name": row.get("material_name", ""),
                    "unit": row.get("unit", ""),
                    "category": row.get("category", ""),
                }
    return catalog


def serialize_job_states(simulator):
    job_states = []
    for job in simulator.jobs:
        all_completed = all(
            task.status == "completed" for task in job.tasks
        )
        if job.is_canceled:
            status = "canceled"
        elif all_completed:
            status = "completed"
        else:
            status = "processing"

        processing_tasks = [
            task
            for task in job.tasks
            if task.status == "processing" and task.actual_end is None
        ]
        completed_count = sum(
            task.status == "completed" for task in job.tasks
        )
        stage_ids = []
        for task in job.tasks:
            stage_id = getattr(task, "stage_id", 1)
            if stage_id not in stage_ids:
                stage_ids.append(stage_id)
        current_stage = stage_ids[-1] if stage_ids else 1
        if not all_completed and not job.is_canceled:
            unfinished_task = next(
                (
                    task
                    for task in job.tasks
                    if task.status != "completed"
                ),
                None,
            )
            if unfinished_task is not None:
                current_stage = getattr(
                    unfinished_task,
                    "stage_id",
                    1,
                )
        current_stage_tasks = [
            task
            for task in job.tasks
            if getattr(task, "stage_id", 1) == current_stage
        ]
        job_states.append(
            {
                "job_id": job.job_id,
                "status": status,
                "operation_count": job.operation_count,
                "completed_operations": completed_count,
                "current_operations": [
                    {
                        "operation_id": task.operation_id,
                        "stage_id": getattr(task, "stage_id", 1),
                        "stage_operation_id": getattr(
                            task,
                            "stage_operation_id",
                            task.operation_id,
                        ),
                        "machine_id": task.assigned_machine,
                    }
                    for task in processing_tasks
                ],
                "canceled_at": job.canceled_at,
                "completion_time": job.completion_time,
                "priority": job.priority,
                "current_stage": current_stage,
                "stage_count": len(stage_ids),
                "stage_operation_count": len(current_stage_tasks),
                "stage_completed_operations": sum(
                    task.status == "completed"
                    for task in current_stage_tasks
                ),
            }
        )
    return sorted(job_states, key=lambda item: item["job_id"])


def serialize_order_batches(simulator, job_states):
    """Serialize submitted Job batches as timestamp-named orders."""
    states_by_job_id = {
        state["job_id"]: state for state in job_states
    }
    order_batches = []
    for order_batch in getattr(simulator, "order_batches", []):
        batch_job_states = [
            states_by_job_id[job_id]
            for job_id in order_batch.job_ids
            if job_id in states_by_job_id
        ]
        status_counts = {
            status: sum(
                state["status"] == status
                for state in batch_job_states
            )
            for status in ("processing", "completed", "canceled")
        }
        if (
            batch_job_states
            and status_counts["canceled"] == len(batch_job_states)
        ):
            status = "canceled"
        elif (
            batch_job_states
            and status_counts["completed"] == len(batch_job_states)
        ):
            status = "completed"
        elif status_counts["processing"] > 0:
            status = "processing"
        else:
            status = "mixed"
        canceled_times = [
            state["canceled_at"]
            for state in batch_job_states
            if state["canceled_at"] is not None
        ]
        canceled_at = order_batch.canceled_at
        if canceled_at is None and status == "canceled" and canceled_times:
            canceled_at = max(canceled_times)
        order_batches.append(
            {
                "order_id": order_batch.order_id,
                "submitted_at": order_batch.submitted_at,
                "source": order_batch.source,
                "job_ids": list(order_batch.job_ids),
                "job_count": len(order_batch.job_ids),
                "status": status,
                "status_counts": status_counts,
                "canceled_at": canceled_at,
            }
        )
    return order_batches


class DashboardState:
    def __init__(
        self,
        display_percent=100,
        speed=5.0,
        anomaly_handling_enabled=False,
    ):
        self.lock = threading.RLock()
        self.status = "idle"
        self.generation = 0
        self.events = []
        self.plan = []
        self.current_time = 0
        self.makespan = 0
        self.speed = float(speed)
        self.horizon = 100
        self.finished_jobs = 0
        self.total_jobs = 0
        self.canceled_jobs = 0
        self.canceled_orders = []
        self.order_batches = []
        self.job_states = []
        self.machine_states = []
        self.processes = []
        self.process_plans = {}
        self.process_machine_states = {}
        self.detection_process_ids = set()
        self.material_catalog = {}
        self.objectives = {}
        self.selected_dataset = None
        self.error = None
        self.plan_revision = 0
        self.plan_structure_signature = None
        self.display_percent = float(display_percent)
        self.auto_job_submission_enabled = False
        self.auto_job_submission_triggered = False
        self.auto_job_submission_count = 0
        self.auto_job_submission_threshold = None
        self.auto_machine_anomaly_enabled = False
        self.anomaly_handling_enabled = bool(
            anomaly_handling_enabled
        )
        self.auto_machine_anomaly_count = 0
        self.next_auto_machine_anomaly_time = None
        self.last_auto_machine_anomaly = None

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
            self.canceled_jobs = 0
            self.canceled_orders = []
            self.order_batches = []
            self.job_states = []
            self.machine_states = []
            self.processes = []
            self.process_plans = {}
            self.process_machine_states = {}
            self.objectives = {}
            self.selected_dataset = None
            self.error = None
            self.plan_revision = 0
            self.plan_structure_signature = None
            self.auto_job_submission_triggered = False
            self.auto_job_submission_count = 0
            self.auto_job_submission_threshold = None
            self.auto_machine_anomaly_count = 0
            self.next_auto_machine_anomaly_time = None
            self.last_auto_machine_anomaly = None

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

    def stop(self, simulator):
        with self.lock:
            self.status = "stopped"
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
                "canceled_jobs": self.canceled_jobs,
                "canceled_orders": list(self.canceled_orders),
                "order_batches": list(self.order_batches),
                "job_states": list(self.job_states),
                "machine_states": self.machine_states,
                "processes": list(self.processes),
                "process_plans": self.process_plans,
                "process_machine_states": self.process_machine_states,
                "material_catalog": self.material_catalog,
                "objectives": self.objectives,
                "selected_dataset": self.selected_dataset,
                "error": self.error,
                "auto_job_submission": {
                    "enabled": self.auto_job_submission_enabled,
                    "triggered": self.auto_job_submission_triggered,
                    "count": self.auto_job_submission_count,
                    "threshold": self.auto_job_submission_threshold,
                },
                "auto_machine_anomaly": {
                    "enabled": self.auto_machine_anomaly_enabled,
                    "interval": AUTO_MACHINE_ANOMALY_INTERVAL,
                    "count": self.auto_machine_anomaly_count,
                    "next_time": self.next_auto_machine_anomaly_time,
                    "last": self.last_auto_machine_anomaly,
                },
                "anomaly_handling": {
                    "enabled": self.anomaly_handling_enabled,
                },
            }

    def _update_simulator(self, simulator):
        self.current_time = simulator.curr_time
        self.makespan = simulator.makespan
        serialized_plan = serialize_plan(
            simulator.planned_operations
        )
        self.plan = serialized_plan
        structure_signature = tuple(
            (
                operation.get("job_id"),
                operation.get("operation_id"),
                operation.get("machine_id"),
                operation.get("stage_id"),
            )
            for operation in serialized_plan
        )
        if structure_signature != self.plan_structure_signature:
            self.plan_structure_signature = structure_signature
            self.plan_revision += 1
        self.finished_jobs = len(simulator.finished_queue)
        self.total_jobs = len(simulator.jobs)
        self.job_states = serialize_job_states(simulator)
        self.order_batches = serialize_order_batches(
            simulator,
            self.job_states,
        )
        self.canceled_jobs = sum(
            state["status"] == "canceled"
            for state in self.job_states
        )
        self.canceled_orders = [
            {
                "job_id": order.job_id,
                "priority": order.priority,
                "submit_time": order.submit_time,
                "canceled_at": order.canceled_at,
            }
            for order in simulator.canceled_orders
        ]
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
                "anomaly_type": machine.anomaly_type,
                "anomaly_started_at": machine.anomaly_started_at,
                "recovery_time": machine.recovery_time,
                "performance_factor": machine.performance_factor,
                "materials": dict(
                    getattr(machine, "materials", {}) or {}
                ),
                "stage_id": getattr(machine, "stage_id", 1),
                "local_id": getattr(
                    machine,
                    "local_machine_id",
                    machine.machine_id + 1,
                ),
            }
            for machine in simulator.machines
        ]
        process_definitions = getattr(
            simulator,
            "process_definitions",
            [],
        )
        if process_definitions:
            self.processes = []
            self.process_plans = {}
            self.process_machine_states = {}
            for process in process_definitions:
                stage_id = int(process["id"])
                machine_ids = set(
                    range(
                        int(process["machine_offset"]),
                        int(process["machine_offset"])
                        + int(process["machine_count"]),
                    )
                )
                process_job_count = sum(
                    state["current_stage"] == stage_id
                    for state in self.job_states
                    if state["status"] == "processing"
                )
                self.processes.append(
                    {
                        **process,
                        "detection_available": (
                            int(process["id"])
                            in getattr(
                                self,
                                "detection_process_ids",
                                set(),
                            )
                        ),
                        "active_job_count": process_job_count,
                    }
                )
                self.process_plans[str(stage_id)] = [
                    operation
                    for operation in self.plan
                    if int(operation.get("stage_id") or 0) == stage_id
                ]
                self.process_machine_states[str(stage_id)] = [
                    machine
                    for machine in self.machine_states
                    if machine["id"] in machine_ids
                ]
        else:
            self.processes = []
            self.process_plans = {}
            self.process_machine_states = {}
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
        influence_aware_executable=None,
        anomaly_handling_enabled=None,
        log_dir=None,
    ):
        self.config_path = Path(config_path).resolve()
        config = load_simulator_config(self.config_path)
        self.speed = float(speed)
        self.real_time_step = real_time_step
        self.realtime = realtime
        configured_anomaly_handling = config.get(
            "anomaly_handling",
            {},
        ).get("enabled", False)
        self.anomaly_handling_enabled = (
            configured_anomaly_handling
            if anomaly_handling_enabled is None
            else bool(anomaly_handling_enabled)
        )
        self.state = DashboardState(
            display_percent,
            speed=self.speed,
            anomaly_handling_enabled=self.anomaly_handling_enabled,
        )
        self.simulator = None
        self.selected_source = None
        self.thread = None
        self.start_lock = threading.Lock()
        self.mutation_lock = threading.RLock()
        self.scheduler_lock = threading.Lock()
        self.scheduler_factory = scheduler_factory
        self.hls_scheduler_factory = hls_scheduler_factory
        self.influence_aware_executable = influence_aware_executable
        self._scheduler = None
        self._hls_scheduler = None
        self.pending_reoptimization_animation = None
        self.reoptimization_animation_timer = None
        self.reoptimization_animation_sequence = 0
        self.auto_job_submission_enabled = False
        self.auto_job_submission_triggered = False
        self.auto_job_submission_count = 0
        self.auto_machine_anomaly_enabled = False
        self.auto_machine_anomaly_count = 0
        self.next_auto_machine_anomaly_time = None
        self.last_auto_machine_anomaly = None
        self._prediction_alarm_generation = None
        self._prediction_alarm_timestamps = set()
        detection_config = config.get("detection_data", {})
        detection_provider_options = {
            "timeout": detection_config.get("timeout", 10),
            "history_points": detection_config.get(
                "history_points",
                60,
            ),
            "poll_interval_ms": detection_config.get(
                "poll_interval_ms",
                1000,
            ),
            "prediction_interval": detection_config.get(
                "prediction_interval",
                5,
            ),
        }
        process_base_urls = detection_config.get(
            "process_base_urls",
        ) or {
            1: detection_config.get(
                "base_url",
                "http://127.0.0.1:8068",
            )
        }
        process_protocols = detection_config.get(
            "process_protocols",
            {},
        )
        self.detection_data_by_process = {
            int(process_id): MachineDetectionDataProvider(
                base_url=base_url,
                protocol=process_protocols.get(
                    str(process_id),
                    "legacy",
                ),
                **detection_provider_options,
            )
            for process_id, base_url in process_base_urls.items()
        }
        self.detection_process_ids = set(
            self.detection_data_by_process
        )
        self.detection_data = self.detection_data_by_process.get(1)
        self.state.detection_process_ids = set(
            self.detection_process_ids
        )
        self.run_logger = None
        self.dataset_root = (
            self.config_path.parent / config["paths"]["dataset_root"]
        ).resolve()
        self.state.material_catalog = load_material_catalog(
            self.dataset_root
        )
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
            if self.reoptimization_animation_timer is not None:
                self.reoptimization_animation_timer.cancel()
            self.reoptimization_animation_timer = None
            self.pending_reoptimization_animation = None
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

    def _current_event_timestamp(self):
        return max(
            self.simulator.curr_time,
            self.simulator.clock.current_simulation_time,
            self.simulator.pending_event_timestamp
            or self.simulator.curr_time,
        )

    def detection_data_for_process(self, process_id=1):
        try:
            process_id = int(process_id)
        except (TypeError, ValueError) as exc:
            raise ValueError("process_id must be an integer.") from exc
        if process_id == 1 and self.detection_data is not None:
            return self.detection_data
        provider = self.detection_data_by_process.get(process_id)
        if provider is None:
            raise ValueError(
                "Detection data source is not configured for "
                f"process_id={process_id}."
            )
        return provider

    def _dispatch_current_event(self, event):
        handled = self.simulator.dispatchEventImmediately(event)
        if handled is False:
            raise RuntimeError(
                f"Event {type(event).__name__} was rejected."
            )
        return event

    def _defer_resume_for_reoptimization_animation(
        self,
        reoptimization,
        wait_for_animation,
    ):
        """Keep the simulator paused until the queue movement finishes."""
        moved_operations = list(
            reoptimization.get("moved_operations", [])
        )
        if not wait_for_animation or not moved_operations:
            with self.state.lock:
                self.state.status = "running"
                self.state._update_simulator(self.simulator)
            self.simulator.resume()
            return {
                "animation_required": False,
                "animation_id": None,
                "animation_moves": [],
            }

        self.reoptimization_animation_sequence += 1
        animation_id = self.reoptimization_animation_sequence
        animation_moves = [
            {
                "task_id": operation.get("task_id"),
                "job_id": operation.get("job_id"),
                "operation_id": operation.get("operation_id"),
                "from_machine_id": operation.get("old_machine_id"),
                "from_queue_machine_id": operation.get(
                    "from_queue_machine_id",
                    operation.get("old_machine_id"),
                ),
                "from_queue_index": operation.get(
                    "from_queue_index",
                    0,
                ),
                "current_position_machine_id": operation.get(
                    "current_position_machine_id"
                ),
                "to_machine_id": operation.get("new_machine_id"),
                "to_queue_machine_id": operation.get(
                    "to_queue_machine_id",
                    operation.get("new_machine_id"),
                ),
                "to_queue_index": operation.get(
                    "to_queue_index",
                    0,
                ),
                "start_time": operation.get("start_time"),
                "transport_time": operation.get(
                    "transport_time",
                    0,
                ),
                "waiting_time": operation.get("waiting_time", 0),
            }
            for operation in moved_operations
        ]
        self.pending_reoptimization_animation = {
            "animation_id": animation_id,
            "moves": animation_moves,
        }
        with self.state.lock:
            self.state.status = "animating"
            self.state._update_simulator(self.simulator)

        timer = threading.Timer(
            REOPTIMIZATION_ANIMATION_TIMEOUT,
            self.complete_reoptimization_animation,
            args=(animation_id,),
        )
        timer.daemon = True
        self.reoptimization_animation_timer = timer
        timer.start()
        return {
            "animation_required": True,
            "animation_id": animation_id,
            "animation_moves": animation_moves,
            "animation_timeout_seconds": (
                REOPTIMIZATION_ANIMATION_TIMEOUT
            ),
        }

    def complete_reoptimization_animation(self, animation_id=None):
        """Resume simulation after the frontend finishes queue animation."""
        with self.mutation_lock:
            pending = self.pending_reoptimization_animation
            if pending is None:
                return {
                    "success": False,
                    "error": "No reoptimization animation is pending.",
                }
            if (
                animation_id is not None
                and int(animation_id) != int(pending["animation_id"])
            ):
                return {
                    "success": False,
                    "error": "Unknown reoptimization animation ID.",
                }

            if self.reoptimization_animation_timer is not None:
                self.reoptimization_animation_timer.cancel()
            self.reoptimization_animation_timer = None
            self.pending_reoptimization_animation = None
            with self.state.lock:
                if (
                    self.state.status != "animating"
                    or self.simulator.stop_event.is_set()
                ):
                    return {
                        "success": False,
                        "error": (
                            "Simulation is no longer waiting for the "
                            "reoptimization animation."
                        ),
                    }
                self.simulator.resume()
                self.state.status = "running"
                self.state._update_simulator(self.simulator)
            return {
                "success": True,
                "animation_id": pending["animation_id"],
                "resumed": True,
                "status": "running",
            }

    def set_paused(self, paused):
        if not isinstance(paused, bool):
            raise ValueError("paused must be a boolean.")
        with self.mutation_lock:
            with self.state.lock:
                if self.simulator is None:
                    raise ValueError("Simulation has not been started.")
                if paused:
                    if self.state.status == "paused":
                        return {
                            "success": True,
                            "paused": True,
                            "status": self.state.status,
                        }
                    if self.state.status != "running":
                        raise ValueError(
                            "Simulation must be running to pause."
                        )
                    self.simulator.pause()
                    self.state.status = "paused"
                else:
                    if self.state.status == "running":
                        return {
                            "success": True,
                            "paused": False,
                            "status": self.state.status,
                        }
                    if self.state.status != "paused":
                        raise ValueError(
                            "Simulation must be paused to resume."
                        )
                    self.simulator.resume()
                    self.state.status = "running"
                return {
                    "success": True,
                    "paused": self.state.status == "paused",
                    "status": self.state.status,
                }

    def stop(self):
        """Stop the active simulation and preserve its partial state."""
        with self.state.lock:
            if self.simulator is None:
                raise ValueError("Simulation has not been started.")
            if self.state.status in {"idle", "finished", "stopped"}:
                return {
                    "success": True,
                    "status": self.state.status,
                    "stopped": self.state.status == "stopped",
                }
            if self.state.status not in {
                "running",
                "paused",
                "reoptimizing",
                "animating",
            }:
                raise ValueError(
                    "Simulation must be active to stop."
                )
            if self.reoptimization_animation_timer is not None:
                self.reoptimization_animation_timer.cancel()
            self.reoptimization_animation_timer = None
            self.pending_reoptimization_animation = None
            self.state.status = "stopping"
            self.simulator.stop()

        thread = self.thread
        if (
            thread is not None
            and thread.is_alive()
            and thread is not threading.current_thread()
        ):
            thread.join(timeout=5)
        with self.state.lock:
            if self.simulator is not None:
                self.state.stop(self.simulator)
            return {
                "success": True,
                "status": self.state.status,
                "stopped": True,
            }

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
                    "dataset_delivery_cost_file": (
                        self.selected_source.get(
                            "delivery_cost_file"
                        )
                    ),
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
                process_sources=self.selected_source.get("processes"),
                process_chain=True,
            )
            self.simulator.event_lock = self.mutation_lock
            self.simulator.machine_recovery_reoptimizer = (
                self._reoptimize_after_machine_recovery
            )
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
            self.auto_machine_anomaly_count = 0
            self.last_auto_machine_anomaly = None
            self.next_auto_machine_anomaly_time = (
                AUTO_MACHINE_ANOMALY_INTERVAL
                if self.auto_machine_anomaly_enabled
                else None
            )
            self.state.auto_machine_anomaly_enabled = (
                self.auto_machine_anomaly_enabled
            )
            self.state.auto_machine_anomaly_count = 0
            self.state.next_auto_machine_anomaly_time = (
                self.next_auto_machine_anomaly_time
            )
            self.state.last_auto_machine_anomaly = None

            self.state.set_running(self.simulator)
            original_handle_event = self.simulator.handleEvent

            def handle_and_publish(event):
                with self.mutation_lock:
                    handled = original_handle_event(event)
                    if handled is False:
                        return
                    for materialized_event in getattr(
                        event,
                        "materialized_events",
                        (),
                    ):
                        self.state.record_event(
                            materialized_event,
                            self.simulator,
                        )
                        self.run_logger.record_event(
                            materialized_event,
                            self.simulator,
                        )
                    self.state.record_event(event, self.simulator)
                    self.run_logger.record_event(event, self.simulator)
                    self._maybe_auto_submit_jobs()
                    self._maybe_auto_insert_machine_anomaly()

            self.simulator.handleEvent = handle_and_publish
            completed = self.simulator.run()
            self.run_logger.finish(self.simulator)
            if completed:
                self.state.finish(self.simulator)
            else:
                self.state.stop(self.simulator)
        except Exception as exc:
            traceback.print_exc()
            self.state.fail(exc)
            if self.run_logger is not None:
                self.run_logger.fail(exc)

    def _request_drl_assignments(
        self,
        num_samples=1,
        seed=0,
        excluded_machines=None,
        process_id=1,
    ):
        """Return DRL-scheduled machine assignments for unfinished work."""
        if self.selected_source is None:
            raise ValueError("No dataset has been selected.")
        process_id = int(process_id)
        process_source = next(
            (
                source
                for source in self.selected_source.get(
                    "processes",
                    [],
                )
                if int(source["id"]) == process_id
            ),
            None,
        )
        source = process_source or self.selected_source
        scheduler = self._get_scheduler()
        raw_text = Path(source["raw_file"]).read_text(encoding="utf-8")
        additional_text = load_model_additional_text(
            source["raw_file"],
            source["additional_file"],
            source.get("delivery_cost_file"),
        )
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
            (
                row["job_id"],
                next(
                    task.operation_id
                    for task in self.simulator.jobs[
                        row["job_id"]
                    ].tasks
                    if (
                        task.stage_id == process_id
                        and task.stage_operation_id
                        == row["operation_index"]
                    )
                ),
            ): int(row["machine_id"])
            + int(source.get("machine_offset", 0))
            for row in model_result["schedule"]
        }
        assignments = self._completeUnfinishedAssignments(
            assignments,
            excluded_machines=excluded_machines,
            stage_ids={process_id},
        )
        return model_result, assignments

    def construct_schedule(
        self,
        dataset_id=None,
        method="InfluenceAwareConstruct",
        process_id=1,
    ):
        """Run one initial construction method without changing simulation."""
        source = (
            self.datasets_by_id.get(dataset_id)
            if dataset_id
            else self.selected_source
        )
        if dataset_id and source is None:
            raise ValueError(f"Unknown dataset ID: {dataset_id}")
        if source is None:
            source = self.datasets_by_id[self.default_dataset_id]

        try:
            process_id = int(process_id)
        except (TypeError, ValueError) as exc:
            raise ValueError("process_id must be an integer.") from exc
        process = next(
            (
                item
                for item in source.get("processes", [])
                if int(item["id"]) == process_id
            ),
            None,
        )
        if process is None:
            if process_id != 1:
                raise ValueError(f"Unknown process_id: {process_id}")
            process = source

        with self.scheduler_lock:
            result = run_construction(
                raw_file=process["raw_file"],
                additional_file=process["additional_file"],
                delivery_cost_file=process.get(
                    "delivery_cost_file"
                ),
                dataset_root=self.dataset_root,
                process_id=process_id,
                method=method,
                executable=self.influence_aware_executable,
            )
        return {
            **result,
            "dataset_id": source["id"],
            "process_id": process_id,
            "api": {
                "method": result.get("method"),
                "dataset_id": source["id"],
                "process_id": process_id,
            },
        }

    def construction_methods(self):
        """Return the construction methods exposed by the simulator API."""
        return {
            "default_method": "InfluenceAwareConstruct",
            "methods": list(CONSTRUCTION_METHODS),
        }

    def test_construction_model(
        self,
        dataset_id=None,
        method="InfluenceAwareConstruct",
        process_id=1,
    ):
        """Run one construction method without changing the active schedule."""
        result = self.construct_schedule(
            dataset_id=dataset_id,
            method=method,
            process_id=process_id,
        )
        return {
            "success": True,
            "test_type": "construction",
            "dataset_id": result["dataset_id"],
            "process_id": result["process_id"],
            "method": result["method"],
            "result": result,
        }

    def reoptimize(
        self,
        num_samples=1,
        seed=0,
        process_id=1,
        wait_for_animation=False,
    ):
        """Use the mofjsp model to reassign all unfinished operations."""
        with self.mutation_lock:
            with self.state.lock:
                if self.simulator is None:
                    raise ValueError("Simulation has not been started.")
                if self.state.status != "running":
                    raise ValueError("Simulation must be running to reoptimize.")
                self.state.status = "reoptimizing"

            self.simulator.pause()
            try:
                model_result, assignments = (
                    self._request_drl_assignments(
                        num_samples=num_samples,
                        seed=seed,
                        process_id=process_id,
                    )
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
                        stage_ids={int(process_id)},
                    )
                )
                with self.state.lock:
                    self.state.plan = serialize_plan(
                        self.simulator.planned_operations
                    )
                    self.state.plan_revision += 1
                    self.state._update_simulator(self.simulator)
            except Exception as exc:
                with self.state.lock:
                    self.state.status = "running"
                self.simulator.resume()
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

            animation_state = (
                self._defer_resume_for_reoptimization_animation(
                    reoptimization,
                    wait_for_animation,
                )
            )
            response = {
                "success": True,
                "model": model_result.get("model"),
                "num_samples": model_result.get("num_samples"),
                "model_objectives": model_result.get("objectives"),
                "process_ids": [int(process_id)],
                **reoptimization,
                **animation_state,
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

    def hls_reoptimize(
        self,
        seed=0,
        process_id=1,
        wait_for_animation=False,
        **hls_options,
    ):
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
                process_id = int(process_id)
                process_source = next(
                    (
                        source
                        for source in self.selected_source.get(
                            "processes",
                            [],
                        )
                        if int(source["id"]) == process_id
                    ),
                    None,
                )
                source = process_source or self.selected_source
                self.state.status = "reoptimizing"

            self.simulator.pause()
            try:
                request = {
                    "raw_lines": Path(source["raw_file"]).read_text(
                        encoding="utf-8"
                    ),
                    "additional_lines": load_model_additional_text(
                        source["raw_file"],
                        source["additional_file"],
                        source.get("delivery_cost_file"),
                    ),
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
                unfinished_key_map = {
                    (
                        job.job_id,
                        task.stage_operation_id,
                    ): task.operation_id
                    for job in self.simulator.jobs
                    for task in job.tasks
                    if (
                        task.status in {"pending", "scheduled"}
                        and task.stage_id == process_id
                    )
                }
                assignments = {
                    (
                        row["job_id"],
                        unfinished_key_map[
                            (
                                row["job_id"],
                                row["operation_index"],
                            )
                        ],
                    ): int(row["machine_id"])
                    + int(source.get("machine_offset", 0))
                    for row in model_result["schedule"]
                    if (
                        row["job_id"],
                        row["operation_index"],
                    )
                    in unfinished_key_map
                }
                assignments = self._completeUnfinishedAssignments(
                    assignments,
                    stage_ids={process_id},
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
                        stage_ids={process_id},
                    )
                )
                with self.state.lock:
                    self.state.plan = serialize_plan(
                        self.simulator.planned_operations
                    )
                    self.state.plan_revision += 1
                    self.state._update_simulator(self.simulator)
            except Exception as exc:
                with self.state.lock:
                    self.state.status = "running"
                self.simulator.resume()
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

            animation_state = (
                self._defer_resume_for_reoptimization_animation(
                    reoptimization,
                    wait_for_animation,
                )
            )
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
                "process_ids": [process_id],
                "hls_assignment_count": len(assignments),
                "additional_data_used": model_result.get(
                    "additional_data_used",
                    False,
                ),
                **reoptimization,
                **animation_state,
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

    def construction_reoptimize(
        self,
        method="InfluenceAwareConstruct",
        process_id=1,
        wait_for_animation=False,
    ):
        """Apply construction-method machine assignments to unfinished work."""
        with self.mutation_lock:
            with self.state.lock:
                if self.simulator is None:
                    raise ValueError("Simulation has not been started.")
                if self.state.status != "running":
                    raise ValueError(
                        "Simulation must be running to reoptimize."
                    )
                process_id = int(process_id)
                source = self.selected_source
                if source is None:
                    raise ValueError("No dataset has been selected.")
                process_source = next(
                    (
                        item
                        for item in source.get("processes", [])
                        if int(item["id"]) == process_id
                    ),
                    None,
                )
                if process_source is None:
                    if process_id != 1:
                        raise ValueError(
                            f"Unknown process_id: {process_id}"
                        )
                    process_source = source
                self.state.status = "reoptimizing"

            self.simulator.pause()
            try:
                model_result = self.construct_schedule(
                    dataset_id=source["id"],
                    process_id=process_id,
                    method=method,
                )
                schedule_operations = (
                    model_result.get("schedule", {}).get(
                        "operations",
                        [],
                    )
                )
                unfinished_key_map = {
                    (
                        job.job_id,
                        task.stage_operation_id,
                    ): task.operation_id
                    for job in self.simulator.jobs
                    for task in job.tasks
                    if (
                        task.status in {"pending", "scheduled"}
                        and task.stage_id == process_id
                    )
                }
                assignments = {}
                for row in schedule_operations:
                    stage_key = (
                        int(row["job_id"]),
                        int(row["operation_id"]),
                    )
                    operation_id = unfinished_key_map.get(stage_key)
                    if operation_id is None:
                        continue
                    assignments[(stage_key[0], operation_id)] = (
                        int(row["machine_id"])
                        + int(process_source.get("machine_offset", 0))
                    )
                assignments = self._completeUnfinishedAssignments(
                    assignments,
                    stage_ids={process_id},
                )
                reoptimization = (
                    self.simulator.reoptimizeUnfinishedOperations(
                        assignments,
                        current_time=self._current_event_timestamp(),
                        stage_ids={process_id},
                    )
                )
                with self.state.lock:
                    self.state.plan = serialize_plan(
                        self.simulator.planned_operations
                    )
                    self.state.plan_revision += 1
                    self.state._update_simulator(self.simulator)
            except Exception as exc:
                with self.state.lock:
                    self.state.status = "running"
                self.simulator.resume()
                if self.run_logger is not None:
                    self.run_logger.record_reoptimization(
                        {
                            "optimizer": "construction",
                            "method": str(method),
                            "process_id": process_id,
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

            animation_state = (
                self._defer_resume_for_reoptimization_animation(
                    reoptimization,
                    wait_for_animation,
                )
            )
            response = {
                "success": True,
                "optimizer": "construction",
                "construction_method": model_result.get(
                    "method",
                    method,
                ),
                "construction_objectives": model_result.get(
                    "objectives",
                    {},
                ),
                "construction_objective_breakdown": (
                    model_result.get("objective_breakdown", {})
                ),
                "construction_schedule_times_used": False,
                "transport_time_recalculated": True,
                "assignment_scope": (
                    "pending_and_scheduled_operations"
                ),
                "process_ids": [process_id],
                "construction_assignment_count": len(assignments),
                **reoptimization,
                **animation_state,
            }
            if self.run_logger is not None:
                self.run_logger.record_reoptimization(
                    {
                        "optimizer": "construction",
                        "method": response["construction_method"],
                        "process_id": process_id,
                        "simulation_time": self.simulator.curr_time,
                    },
                    response,
                    self.simulator,
                )
            return response

    def greedy_reoptimize(
        self,
        process_id=1,
        wait_for_animation=False,
    ):
        """Use the built-in fastest-available-machine heuristic."""
        with self.mutation_lock:
            with self.state.lock:
                if self.simulator is None:
                    raise ValueError("Simulation has not been started.")
                if self.state.status != "running":
                    raise ValueError(
                        "Simulation must be running to reoptimize."
                    )
                process_id = int(process_id)
                self.state.status = "reoptimizing"

            self.simulator.pause()
            try:
                now = max(
                    self.simulator.curr_time,
                    self.simulator.clock.current_simulation_time,
                    self.simulator.pending_event_timestamp
                    or self.simulator.curr_time,
                )
                reoptimization = (
                    self.simulator._greedyRescheduleUnfinished(
                        now,
                        stage_ids={process_id},
                    )
                )
                with self.state.lock:
                    self.state.plan = serialize_plan(
                        self.simulator.planned_operations
                    )
                    self.state.plan_revision += 1
                    self.state._update_simulator(self.simulator)
            except Exception as exc:
                with self.state.lock:
                    self.state.status = "running"
                self.simulator.resume()
                if self.run_logger is not None:
                    self.run_logger.record_reoptimization(
                        {
                            "optimizer": "greedy",
                            "process_id": process_id,
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

            animation_state = (
                self._defer_resume_for_reoptimization_animation(
                    reoptimization,
                    wait_for_animation,
                )
            )
            response = {
                "success": True,
                "optimizer": "greedy",
                "algorithm": "fastest_available_machine",
                "assignment_scope": "pending_and_scheduled_operations",
                "transport_time_recalculated": True,
                "process_ids": [process_id],
                **reoptimization,
                **animation_state,
            }
            if self.run_logger is not None:
                self.run_logger.record_reoptimization(
                    {
                        "optimizer": "greedy",
                        "process_id": process_id,
                        "simulation_time": self.simulator.curr_time,
                    },
                    response,
                    self.simulator,
                )
            return response

    def test_hls_model(
        self,
        dataset_id=None,
        seed=0,
        **hls_options,
    ):
        """Run HLS model inference without changing the active schedule."""
        source = (
            self.datasets_by_id.get(dataset_id)
            if dataset_id
            else self.selected_source
        )
        if source is None:
            source = self.datasets_by_id[self.default_dataset_id]
        request = {
            "raw_lines": Path(source["raw_file"]).read_text(
                encoding="utf-8"
            ),
            "additional_lines": load_model_additional_text(
                source["raw_file"],
                source["additional_file"],
                source.get("delivery_cost_file"),
            ),
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
        with self.scheduler_lock:
            model_result = scheduler.predict(request)
        return {
            "success": True,
            "test_type": "hls",
            "dataset_id": source["id"],
            "parameters": {
                "seed": int(seed),
                **{
                    key: hls_options[key]
                    for key in HLS_OPTION_FIELDS
                    if key in hls_options
                },
            },
            "result": model_result,
        }

    def test_anomaly_model(
        self,
        process_id=1,
        t=85,
        machine_count=None,
        machine_id=None,
    ):
        """Run anomaly prediction without injecting an anomaly event."""
        source = self.selected_source or self.datasets_by_id[
            self.default_dataset_id
        ]
        process_id = int(process_id)
        process_definition = next(
            (
                process
                for process in source.get("processes", [])
                if int(process["id"]) == process_id
            ),
            None,
        )
        if process_definition is None:
            if process_id != 1:
                raise ValueError(f"Unknown process_id: {process_id}")
            process_machine_count = int(
                source.get("processes", [{}])[0].get(
                    "machine_count",
                    source.get("processes", [{}])[0].get(
                        "num_machines",
                        source.get("num_machines", 1),
                    ),
                )
            )
        else:
            process_machine_count = int(
                process_definition.get(
                    "machine_count",
                    process_definition.get("num_machines", 1),
                )
            )
        count = (
            process_machine_count
            if machine_count is None
            else int(machine_count)
        )
        if count < 1:
            raise ValueError("machine_count must be positive.")
        provider = self.detection_data_for_process(process_id)
        if machine_id is not None:
            machine_id = int(machine_id)
            if not 0 <= machine_id < count:
                raise ValueError(
                    f"machine_id must be between 0 and {count - 1}."
                )
            if provider.protocol != "legacy":
                raise ValueError(
                    "Detailed model input visualisation is only available "
                    "for the stamping MetroPT detection model."
                )
            return self._test_legacy_anomaly_model(
                source,
                provider,
                process_id,
                count,
                machine_id,
                int(t),
            )
        prediction = provider.predict(
            int(t),
            machine_count=count,
        )
        return {
            "success": True,
            "test_type": "anomaly",
            "dataset_id": source["id"],
            "process_id": process_id,
            "machine_count": count,
            "result": prediction,
        }

    def _test_legacy_anomaly_model(
        self,
        source,
        provider,
        process_id,
        machine_count,
        machine_id,
        t,
    ):
        """Collect one complete model-test bundle for the MetroPT model."""
        metadata = provider.meta()
        prediction = provider.predict_one(machine_id, t)
        horizon = int(prediction.get("prediction_horizon", 20))
        evidence_errors = {}

        def capture(name, loader):
            try:
                return loader()
            except Exception as exc:
                evidence_errors[name] = str(exc)
                return None

        window = capture(
            "window",
            lambda: provider.window(machine_id, t),
        )
        truth = capture(
            "truth",
            lambda: provider.truth(machine_id, t),
        )
        future = capture(
            "future",
            lambda: provider.stream(
                machine_id,
                from_t=t,
                count=horizon,
            ),
        )
        event_payload = capture(
            "events",
            lambda: provider.events(machine_id),
        )

        frames = (future or {}).get("frames", [])
        future_frames = frames[1:] if len(frames) > 1 else frames
        future_fault_count = sum(
            1
            for frame in future_frames
            if int(frame.get("label", 0)) == 1
        )
        future_fault_ratio = (
            future_fault_count / len(future_frames)
            if future_frames
            else 0.0
        )
        events = (event_payload or {}).get("events", [])
        effective_t = int(
            prediction.get("t_effective", t)
        )
        current_event = next(
            (
                event
                for event in events
                if int(event.get("start", 0)) <= effective_t
                <= int(event.get("end", -1))
            ),
            None,
        )
        next_event = next(
            (
                event
                for event in events
                if int(event.get("start", 0)) > effective_t
            ),
            None,
        )
        threshold = float(
            prediction.get(
                "threshold",
                metadata.get("ml", {}).get("threshold", 0),
            )
        )
        probability = float(prediction.get("probability", 0))
        contract = metadata.get("contract", {})
        model_payload = prediction.get("model") or {}
        result = {
            **prediction,
            "machine_count": machine_count,
            "predictions": [prediction],
            "input_parameters": {
                "machine_id": machine_id,
                "t": t,
                "t_effective": effective_t,
                "T": int(
                    (window or {}).get("T", 0)
                    or next(
                        (
                            item.get("T", 0)
                            for item in provider.machines().get(
                                "machines",
                                [],
                            )
                            if int(item.get("machine_id", -1))
                            == machine_id
                        ),
                        0,
                    )
                ),
                "machine_count": machine_count,
                "window_size": int(
                    contract.get("window_size", 0) or 0
                ),
                "prediction_horizon": horizon,
                "decision_threshold": threshold,
            },
            "model": {
                "name": (
                    metadata.get("ml", {}).get("model_name")
                    or "MetroPT CNN-LSTM"
                ),
                "artifact": "metropt_model.pth",
                "protocol": provider.protocol,
                "loaded": bool(model_payload.get("loaded", False)),
                "device": model_payload.get("device"),
                "error": model_payload.get("error"),
                "contract": contract,
                "threshold": threshold,
            },
            "window": window,
            "truth": truth,
            "future": future,
            "events": event_payload,
            "summary": {
                "probability": probability,
                "threshold": threshold,
                "threshold_margin": probability - threshold,
                "is_alarm": bool(prediction.get("is_alarm", False)),
                "truth_label": (
                    int(truth.get("label", 0)) if truth else None
                ),
                "warn": (
                    int(truth.get("warn", 0)) if truth else None
                ),
                "next_fault_t": (
                    truth.get("next_anomaly_t") if truth else None
                ),
                "current_event": current_event,
                "next_event": next_event,
                "next_event_delta": (
                    int(next_event["start"]) - effective_t
                    if next_event
                    else None
                ),
                "event_count": len(events),
                "future_fault_count": future_fault_count,
                "future_point_count": len(future_frames),
                "future_fault_ratio": future_fault_ratio,
            },
            "evidence_errors": evidence_errors,
        }
        return {
            "success": True,
            "test_type": "anomaly",
            "dataset_id": source["id"],
            "process_id": process_id,
            "machine_count": machine_count,
            "machine_id": machine_id,
            "result": result,
        }

    def reoptimize_command(
        self,
        method,
        config=None,
        process_id=1,
        wait_for_animation=False,
    ):
        """Dispatch a Greedy, DRL, or HLS reoptimization command."""
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
            result = self.hls_reoptimize(
                process_id=process_id,
                wait_for_animation=wait_for_animation,
                **normalized_config,
            )
        elif normalized_method == "drl":
            result = self.reoptimize(
                process_id=process_id,
                wait_for_animation=wait_for_animation,
                **normalized_config,
            )
        elif normalized_method == "construction":
            result = self.construction_reoptimize(
                process_id=process_id,
                method=normalized_config.get(
                    "method",
                    "InfluenceAwareConstruct",
                ),
                wait_for_animation=wait_for_animation,
            )
        else:
            result = self.greedy_reoptimize(
                process_id=process_id,
                wait_for_animation=wait_for_animation,
            )
        return {
            **result,
            "optimizer": normalized_method,
            "command_config": normalized_config,
            "process_ids": [int(process_id)],
        }

    def submit_random_jobs(self, seed=0, order_source="manual"):
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
                event = OrderInsertEvent(
                    self.simulator.newEventId(),
                    self._current_event_timestamp(),
                    seed=int(seed),
                    source=order_source,
                )
                self._dispatch_current_event(event)
                result = event.result
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
                "event_id": event.id,
                "event_type": type(event).__name__,
                "event_timestamp": event.timestamp,
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

    def cancel_job(self, job_id):
        """Cancel a Job and publish the updated Job list immediately."""
        with self.mutation_lock:
            with self.state.lock:
                if self.simulator is None:
                    raise ValueError("Simulation has not been started.")
                if self.state.status != "running":
                    raise ValueError(
                        "Simulation must be running to cancel a job."
                    )
                self.state.status = "reoptimizing"

            self.simulator.pause()
            try:
                event = OrderCancelEvent(
                    self.simulator.newEventId(),
                    self._current_event_timestamp(),
                    [job_id],
                    batch=False,
                )
                self._dispatch_current_event(event)
                result = event.result
                with self.state.lock:
                    self.state.plan = serialize_plan(
                        self.simulator.planned_operations
                    )
                    self.state.plan_revision += 1
                    self.state.status = "running"
                    self.state._update_simulator(self.simulator)
                return {
                    **result,
                    "event_id": event.id,
                    "event_type": type(event).__name__,
                    "event_timestamp": event.timestamp,
                }
            except Exception:
                with self.state.lock:
                    self.state.status = "running"
                raise
            finally:
                self.simulator.resume()

    def cancel_jobs(self, job_ids, order_ids=None):
        """Cancel several Jobs and publish one consolidated state update."""
        with self.mutation_lock:
            with self.state.lock:
                if self.simulator is None:
                    raise ValueError("Simulation has not been started.")
                if self.state.status != "running":
                    raise ValueError(
                        "Simulation must be running to cancel jobs."
                    )
                self.state.status = "reoptimizing"

            self.simulator.pause()
            try:
                event = OrderCancelEvent(
                    self.simulator.newEventId(),
                    self._current_event_timestamp(),
                    job_ids,
                    batch=True,
                    order_ids=order_ids,
                )
                self._dispatch_current_event(event)
                result = event.result
                with self.state.lock:
                    self.state.plan = serialize_plan(
                        self.simulator.planned_operations
                    )
                    self.state.plan_revision += 1
                    self.state.status = "running"
                    self.state._update_simulator(self.simulator)
                return {
                    **result,
                    "event_id": event.id,
                    "event_type": type(event).__name__,
                    "event_timestamp": event.timestamp,
                }
            except Exception:
                with self.state.lock:
                    self.state.status = "running"
                raise
            finally:
                self.simulator.resume()

    def cancel_orders(self, order_ids, job_ids=None):
        """Cancel complete order batches and any additionally selected Jobs."""
        if not isinstance(order_ids, list) or not order_ids:
            raise ValueError("order_ids must be a non-empty list.")
        with self.mutation_lock:
            if self.simulator is None:
                raise ValueError("Simulation has not been started.")
            normalized_order_ids, batch_job_ids = (
                self.simulator.orderBatchJobIds(order_ids)
            )
            selected_job_ids = list(batch_job_ids)
            for job_id in job_ids or []:
                normalized_job_id = int(job_id)
                if normalized_job_id not in selected_job_ids:
                    selected_job_ids.append(normalized_job_id)
            return self.cancel_jobs(
                selected_job_ids,
                order_ids=normalized_order_ids,
            )

    def cancel_order(self, job_id):
        """Alias using the order terminology exposed in the API."""
        return self.cancel_job(job_id)

    def handle_machine_anomaly(
        self,
        machine_id,
        anomaly_type,
        duration,
    ):
        """Apply a machine anomaly and reschedule long downtime with DRL."""
        if not self.anomaly_handling_enabled:
            raise ValueError(
                "Machine anomaly handling is disabled by "
                "anomaly_handling.enabled=false."
            )
        from simulator.anomaly import MachineAnomalyType

        anomaly = MachineAnomalyType.normalize(anomaly_type)
        with self.mutation_lock:
            with self.state.lock:
                if self.simulator is None:
                    raise ValueError("Simulation has not been started.")
                if self.state.status != "running":
                    raise ValueError(
                        "Simulation must be running to handle an anomaly."
                    )
                if anomaly == MachineAnomalyType.LONG_FAILURE:
                    self.state.status = "reoptimizing"
            if self.simulator.machine_recovery_reoptimizer is None:
                self.simulator.machine_recovery_reoptimizer = (
                    self._reoptimize_after_machine_recovery
                )

            if anomaly == MachineAnomalyType.LONG_FAILURE:
                self.simulator.pause()
                try:
                    now = max(
                        self.simulator.curr_time,
                        self.simulator.clock.current_simulation_time,
                        self.simulator.pending_event_timestamp
                        or self.simulator.curr_time,
                    )
                    anomaly_event = MachineAnomalyEvent(
                        self.simulator.newEventId(),
                        now,
                        machine_id,
                        anomaly,
                        duration,
                    )
                    self._dispatch_current_event(anomaly_event)
                    anomaly_result = anomaly_event.result
                    self.simulator.deferUnavailableTasks(
                        current_time=now
                    )
                    process_id = self.simulator.machines[
                        int(machine_id)
                    ].stage_id
                    model_result, assignments = (
                        self._request_drl_assignments(
                            num_samples=MACHINE_ANOMALY_DRL_NUM_SAMPLES,
                            seed=int(self.simulator.seed),
                            excluded_machines={int(machine_id)},
                            process_id=process_id,
                        )
                    )
                    reoptimization = (
                        self.simulator.reoptimizeUnfinishedOperations(
                            assignments,
                            current_time=now,
                            excluded_machines={int(machine_id)},
                            stage_ids={process_id},
                        )
                    )
                    with self.state.lock:
                        self.state.plan = serialize_plan(
                            self.simulator.planned_operations
                        )
                        self.state.plan_revision += 1
                        self.state.status = "running"
                        self.state._update_simulator(self.simulator)
                    result = {
                        **anomaly_result,
                        "reschedule_method": "DRL",
                        "optimizer": "drl",
                        "model": model_result.get("model"),
                        "num_samples": model_result.get("num_samples"),
                        "model_objectives": model_result.get(
                            "objectives"
                        ),
                        "event_id": anomaly_event.id,
                        "event_type": type(anomaly_event).__name__,
                        "event_timestamp": anomaly_event.timestamp,
                        "reoptimization": reoptimization,
                    }
                    if self.run_logger is not None:
                        self.run_logger.record_reoptimization(
                            {
                                "optimizer": "machine_anomaly_drl",
                                "machine_id": int(machine_id),
                                "process_id": int(process_id),
                                "anomaly_type": anomaly.value,
                                "simulation_time": now,
                            },
                            result,
                            self.simulator,
                        )
                    return result
                except Exception:
                    with self.state.lock:
                        self.state.status = "running"
                    raise
                finally:
                    self.simulator.resume()

            anomaly_event = MachineAnomalyEvent(
                self.simulator.newEventId(),
                self._current_event_timestamp(),
                machine_id,
                anomaly,
                duration,
            )
            self._dispatch_current_event(anomaly_event)
            result = anomaly_event.result
            with self.state.lock:
                self.state.plan = serialize_plan(
                    self.simulator.planned_operations
                )
                self.state.plan_revision += 1
                self.state.status = "running"
                self.state._update_simulator(self.simulator)
            return {
                **result,
                "reschedule_method": None,
                "event_id": anomaly_event.id,
                "event_type": type(anomaly_event).__name__,
                "event_timestamp": anomaly_event.timestamp,
            }

    def _choose_prediction_anomaly(self, machine_id, prediction_t):
        """Choose a reproducible random anomaly and its default duration."""
        rng = random.Random(
            int(self.simulator.seed)
            + int(prediction_t) * 104729
            + int(machine_id) * 1000003
        )
        anomaly = rng.choice(list(MachineAnomalyType))
        return anomaly, MACHINE_ANOMALY_DEFAULT_DURATIONS[anomaly]

    def handle_prediction_alarms(
        self,
        t,
        predictions,
        process_id=1,
    ):
        """Inject predicted anomalies once for one aligned detection time."""
        if not self.anomaly_handling_enabled:
            return {
                "success": True,
                "t": int(t),
                "process_id": int(process_id),
                "injected_machine_ids": [],
                "injected_events": [],
                "skipped_machines": [],
                "reason": "anomaly_handling_disabled",
            }
        if isinstance(t, bool):
            raise ValueError("t must be an integer.")
        try:
            prediction_t = int(t)
        except (TypeError, ValueError) as exc:
            raise ValueError("t must be an integer.") from exc
        if prediction_t < 0:
            raise ValueError("t must be non-negative.")
        if not isinstance(predictions, list):
            raise ValueError("predictions must be a list.")
        if len(predictions) > 500:
            raise ValueError(
                "predictions must contain at most 500 machines."
            )
        try:
            normalized_process_id = int(process_id)
        except (TypeError, ValueError) as exc:
            raise ValueError("process_id must be an integer.") from exc

        with self.mutation_lock:
            with self.state.lock:
                generation = self.state.generation
                if (
                    self.simulator is None
                    or self.state.status != "running"
                ):
                    return {
                        "success": True,
                        "t": prediction_t,
                        "injected_machine_ids": [],
                        "skipped_machines": [],
                        "reason": "simulation_not_running",
                    }
                if self._prediction_alarm_generation != generation:
                    self._prediction_alarm_generation = generation
                    self._prediction_alarm_timestamps.clear()
                prediction_key = (
                    normalized_process_id,
                    prediction_t,
                )
                if prediction_key in self._prediction_alarm_timestamps:
                    return {
                        "success": True,
                        "t": prediction_t,
                        "injected_machine_ids": [],
                        "skipped_machines": [],
                        "duplicate": True,
                    }
                self._prediction_alarm_timestamps.add(prediction_key)

            process_definitions = getattr(
                self.simulator,
                "process_definitions",
                [],
            )
            process_definition = next(
                (
                    process
                    for process in process_definitions
                    if int(process["id"]) == normalized_process_id
                ),
                None,
            )
            if process_definition is None:
                if normalized_process_id != 1:
                    raise ValueError(
                        f"Unknown process_id: {normalized_process_id}"
                    )
                machine_offset = 0
                process_machine_count = len(self.simulator.machines)
            else:
                machine_offset = int(
                    process_definition["machine_offset"]
                )
                process_machine_count = int(
                    process_definition["machine_count"]
                )

            injected_machine_ids = []
            injected_events = []
            skipped_machines = []
            handled_machine_ids = set()
            for prediction in predictions:
                if (
                    not isinstance(prediction, dict)
                    or not prediction.get("is_alarm", False)
                ):
                    continue
                raw_machine_id = prediction.get("machine_id")
                if isinstance(raw_machine_id, bool):
                    skipped_machines.append(
                        {
                            "machine_id": raw_machine_id,
                            "reason": "invalid_machine_id",
                        }
                    )
                    continue
                try:
                    local_machine_id = int(raw_machine_id)
                except (TypeError, ValueError):
                    skipped_machines.append(
                        {
                            "machine_id": raw_machine_id,
                            "reason": "invalid_machine_id",
                        }
                    )
                    continue
                if not 0 <= local_machine_id < process_machine_count:
                    skipped_machines.append(
                        {
                            "machine_id": local_machine_id,
                            "process_id": normalized_process_id,
                            "reason": "unknown_machine",
                        }
                    )
                    continue
                machine_id = machine_offset + local_machine_id
                if not 0 <= machine_id < len(self.simulator.machines):
                    skipped_machines.append(
                        {
                            "machine_id": machine_id,
                            "process_id": normalized_process_id,
                            "reason": "unknown_machine",
                        }
                    )
                    continue
                if machine_id in handled_machine_ids:
                    continue
                machine = self.simulator.machines[machine_id]
                if (
                    machine.anomaly_type is not None
                    or machine.machine_status
                    in {"failed", "repairing", "degraded"}
                ):
                    skipped_machines.append(
                        {
                            "machine_id": machine_id,
                            "process_id": normalized_process_id,
                            "reason": "active_anomaly",
                        }
                    )
                    continue
                handled_machine_ids.add(machine_id)
                anomaly = None
                duration = None
                prediction_type = prediction.get("anomaly_type")
                if (
                    isinstance(prediction_type, str)
                    and prediction_type != "normal"
                ):
                    try:
                        anomaly = MachineAnomalyType.normalize(
                            prediction_type
                        )
                        duration = validate_machine_anomaly_duration(
                            anomaly,
                            prediction.get(
                                "recommended_duration",
                                MACHINE_ANOMALY_DEFAULT_DURATIONS[
                                    anomaly
                                ],
                            ),
                        )
                    except (TypeError, ValueError):
                        duration = MACHINE_ANOMALY_DEFAULT_DURATIONS[
                            anomaly
                        ] if anomaly is not None else None
                if anomaly is None:
                    anomaly, duration = self._choose_prediction_anomaly(
                        machine_id,
                        prediction_t,
                    )
                try:
                    result = self.handle_machine_anomaly(
                        machine_id,
                        anomaly.value,
                        duration,
                    )
                except Exception as exc:
                    skipped_machines.append(
                        {
                            "machine_id": machine_id,
                            "reason": str(exc),
                        }
                    )
                    continue
                injected_machine_ids.append(machine_id)
                injected_events.append(
                    {
                        "machine_id": machine_id,
                        "local_machine_id": local_machine_id,
                        "process_id": normalized_process_id,
                        "anomaly_type": anomaly.value,
                        "anomaly_duration": duration,
                        "event_id": result.get("event_id"),
                        "event_type": result.get("event_type"),
                        "event_timestamp": result.get(
                            "event_timestamp"
                        ),
                        "machine_status": result.get("machine_status"),
                        "recovery_time": result.get("recovery_time"),
                    }
                )

            return {
                "success": True,
                "t": prediction_t,
                "process_id": normalized_process_id,
                "injected_machine_ids": injected_machine_ids,
                "injected_events": injected_events,
                "skipped_machines": skipped_machines,
            }

    def _reoptimize_after_machine_recovery(
        self,
        machine_id,
        recovery_time,
    ):
        """Run DRL after a long-failure machine recovers."""
        with self.state.lock:
            self.state.status = "reoptimizing"
        self.simulator.pause()
        try:
            self.simulator.deferUnavailableTasks(
                current_time=recovery_time
            )
            process_id = self.simulator.machines[
                int(machine_id)
            ].stage_id
            model_result, assignments = (
                self._request_drl_assignments(
                    num_samples=MACHINE_ANOMALY_DRL_NUM_SAMPLES,
                    seed=int(self.simulator.seed),
                    process_id=process_id,
                )
            )
            reoptimization = (
                self.simulator.reoptimizeUnfinishedOperations(
                    assignments,
                    current_time=max(
                        self.simulator.curr_time,
                        float(recovery_time),
                    ),
                    stage_ids={process_id},
                )
            )
            with self.state.lock:
                self.state.plan = serialize_plan(
                    self.simulator.planned_operations
                )
                self.state.plan_revision += 1
                self.state.status = "running"
                self.state._update_simulator(self.simulator)
            response = {
                "success": True,
                "reschedule_method": "DRL",
                "optimizer": "drl",
                "model": model_result.get("model"),
                "num_samples": model_result.get("num_samples"),
                "model_objectives": model_result.get("objectives"),
                **reoptimization,
            }
            if self.run_logger is not None:
                self.run_logger.record_reoptimization(
                    {
                        "optimizer": "machine_recovery_drl",
                        "machine_id": int(machine_id),
                        "process_id": int(process_id),
                        "simulation_time": float(recovery_time),
                    },
                    response,
                    self.simulator,
                )
            return response
        except Exception:
            with self.state.lock:
                self.state.status = "running"
            raise
        finally:
            self.simulator.resume()

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

    def _stamping_unfinished_job_count(self):
        """Count non-canceled Jobs that still have unfinished stamping work."""
        if self.simulator is None:
            return 0
        count = 0
        for job in self.simulator.jobs:
            if job.is_canceled:
                continue
            stamping_tasks = [
                task
                for task in job.tasks
                if getattr(task, "stage_id", 1) == 1
            ]
            if any(
                task.status not in {"completed", "canceled"}
                for task in stamping_tasks
            ):
                count += 1
        return count

    def _maybe_auto_submit_jobs(self):
        if (
            not self.auto_job_submission_enabled
            or self.simulator is None
        ):
            return
        threshold = self._auto_job_submission_threshold()
        stamping_job_count = self._stamping_unfinished_job_count()
        if stamping_job_count > threshold:
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
            seed=self.simulator.seed + self.auto_job_submission_count * 1000,
            order_source="auto",
        )

    def set_auto_machine_anomaly(self, enabled):
        if not isinstance(enabled, bool):
            raise ValueError("enabled must be a boolean.")
        if enabled and not self.anomaly_handling_enabled:
            raise ValueError(
                "Machine anomaly handling is disabled by "
                "anomaly_handling.enabled=false."
            )
        with self.mutation_lock:
            self.auto_machine_anomaly_enabled = enabled
            next_time = None
            if (
                enabled
                and self.simulator is not None
                and self.state.status == "running"
            ):
                next_time = (
                    self._current_event_timestamp()
                    + AUTO_MACHINE_ANOMALY_INTERVAL
                )
            self.next_auto_machine_anomaly_time = next_time
            with self.state.lock:
                self.state.auto_machine_anomaly_enabled = enabled
                self.state.next_auto_machine_anomaly_time = next_time
            return {
                "ok": True,
                "auto_machine_anomaly": (
                    self.state.snapshot()["auto_machine_anomaly"]
                ),
            }

    def _maybe_auto_insert_machine_anomaly(self):
        if (
            not self.auto_machine_anomaly_enabled
            or self.simulator is None
            or self.state.status != "running"
        ):
            return

        now = self._current_event_timestamp()
        if self.next_auto_machine_anomaly_time is None:
            self.next_auto_machine_anomaly_time = (
                now + AUTO_MACHINE_ANOMALY_INTERVAL
            )
            with self.state.lock:
                self.state.next_auto_machine_anomaly_time = (
                    self.next_auto_machine_anomaly_time
                )
            return
        if now + 1e-9 < self.next_auto_machine_anomaly_time:
            return

        trigger_time = self.next_auto_machine_anomaly_time
        next_time = trigger_time + AUTO_MACHINE_ANOMALY_INTERVAL
        if next_time <= now + 1e-9:
            next_time = now + AUTO_MACHINE_ANOMALY_INTERVAL
        self.next_auto_machine_anomaly_time = next_time
        candidates = [
            machine
            for machine in self.simulator.machines
            if (
                machine.anomaly_type is None
                and machine.machine_status
                not in {"failed", "repairing", "degraded"}
            )
        ]
        if not candidates:
            with self.state.lock:
                self.state.next_auto_machine_anomaly_time = (
                    self.next_auto_machine_anomaly_time
                )
            return

        rng = random.Random(
            int(self.simulator.seed)
            + self.auto_machine_anomaly_count * 104729
            + int(trigger_time * 1000)
        )
        machine = rng.choice(candidates)
        anomaly = rng.choice(list(MachineAnomalyType))
        minimum, maximum = MACHINE_ANOMALY_DURATION_RANGES[anomaly]
        duration = rng.randint(minimum, maximum)

        self.auto_machine_anomaly_count += 1
        last_anomaly = {
            "triggered_at": now,
            "scheduled_for": trigger_time,
            "machine_id": machine.machine_id,
            "anomaly_type": anomaly.value,
            "duration": duration,
        }
        self.last_auto_machine_anomaly = last_anomaly
        with self.state.lock:
            self.state.auto_machine_anomaly_count = (
                self.auto_machine_anomaly_count
            )
            self.state.next_auto_machine_anomaly_time = (
                self.next_auto_machine_anomaly_time
            )
            self.state.last_auto_machine_anomaly = dict(last_anomaly)

        self.handle_machine_anomaly(
            machine.machine_id,
            anomaly.value,
            duration,
        )

    @staticmethod
    def _normalize_reoptimization_method(method):
        if not isinstance(method, str) or not method.strip():
            raise ValueError(
                "method must be one of: Greedy, DRL, HLS, "
                "InfluenceAwareConstruct."
            )
        normalized_method = REOPTIMIZATION_COMMAND_ALIASES.get(
            method.strip().lower()
        )
        if normalized_method is None:
            raise ValueError(
                "method must be one of: Greedy, DRL, HLS, "
                "InfluenceAwareConstruct."
            )
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

    def _completeUnfinishedAssignments(
        self,
        assignments,
        excluded_machines=None,
        stage_ids=None,
    ):
        """Keep model-compatible assignments and cover dynamically added Jobs."""
        completed = dict(assignments)
        excluded_machines = set(excluded_machines or [])
        scoped_stage_ids = (
            None
            if stage_ids is None
            else {int(stage_id) for stage_id in stage_ids}
        )
        for job in self.simulator.jobs:
            for task in job.tasks:
                if task.status not in {"pending", "scheduled"}:
                    continue
                if (
                    scoped_stage_ids is not None
                    and task.stage_id not in scoped_stage_ids
                ):
                    continue
                key = (job.job_id, task.operation_id)
                if key in self.simulator.deferred_anomaly_tasks:
                    continue
                if key in completed:
                    continue
                if (
                    task.assigned_machine in task.eligible_machines
                    and task.assigned_machine not in excluded_machines
                ):
                    completed[key] = task.assigned_machine
                else:
                    candidates = [
                        machine_id
                        for machine_id in task.eligible_machines
                        if machine_id not in excluded_machines
                    ]
                    if not candidates:
                        raise ValueError(
                            f"No available machine for task {task.task_id}."
                        )
                    completed[key] = min(
                        candidates,
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

    def _current_event_timestamp(self):
        return max(
            self.simulator.curr_time,
            self.simulator.clock.current_simulation_time,
            self.simulator.pending_event_timestamp
            or self.simulator.curr_time,
        )

    def _dispatch_current_event(self, event):
        handled = self.simulator.dispatchEventImmediately(event)
        if handled is False:
            raise RuntimeError(
                f"Event {type(event).__name__} was rejected."
            )
        return event

    def set_paused(self, paused):
        if not isinstance(paused, bool):
            raise ValueError("paused must be a boolean.")
        if self.simulator is None:
            raise ValueError("Simulation has not been started.")
        with self.state.lock:
            if paused:
                self.simulator.pause()
                self.state.status = "paused"
            else:
                self.simulator.resume()
                self.state.status = "running"
        return {
            "success": True,
            "paused": paused,
            "status": self.state.status,
        }

    def stop(self):
        if self.simulator is None:
            raise ValueError("Simulation has not been started.")
        self.simulator.stop()
        with self.state.lock:
            self.state.stop(self.simulator)
        return {
            "success": True,
            "status": self.state.status,
            "stopped": True,
        }

    def cancel_job(self, job_id):
        if self.simulator is None:
            raise ValueError("Simulation has not been started.")
        event = OrderCancelEvent(
            self.simulator.newEventId(),
            self._current_event_timestamp(),
            [job_id],
            batch=False,
        )
        self._dispatch_current_event(event)
        result = {
            **event.result,
            "event_id": event.id,
            "event_type": type(event).__name__,
            "event_timestamp": event.timestamp,
        }
        with self.state.lock:
            self.state.plan = serialize_plan(
                self.simulator.planned_operations
            )
            self.state.plan_revision += 1
            self.state._update_simulator(self.simulator)
        return result

    def cancel_jobs(self, job_ids):
        if self.simulator is None:
            raise ValueError("Simulation has not been started.")
        event = OrderCancelEvent(
            self.simulator.newEventId(),
            self._current_event_timestamp(),
            job_ids,
            batch=True,
        )
        self._dispatch_current_event(event)
        result = {
            **event.result,
            "event_id": event.id,
            "event_type": type(event).__name__,
            "event_timestamp": event.timestamp,
        }
        with self.state.lock:
            self.state.plan = serialize_plan(
                self.simulator.planned_operations
            )
            self.state.plan_revision += 1
            self.state._update_simulator(self.simulator)
        return result


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
                    "processes": [
                        {
                            **process,
                            "detection_available": (
                                int(process["id"])
                                in self.server.manager.detection_process_ids
                            ),
                        }
                        for process in source.get("processes", [])
                    ],
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
        if parsed.path == "/api/construction/methods":
            try:
                self._send_json(
                    self.server.manager.construction_methods()
                )
            except AttributeError:
                self._send_json(
                    {
                        "default_method": "InfluenceAwareConstruct",
                        "methods": list(CONSTRUCTION_METHODS),
                    }
                )
            return
        if parsed.path == "/api/health":
            self._send_json({"ok": True})
            return
        if parsed.path == "/api/detection/meta":
            try:
                query = parse_qs(parsed.query)
                process_id = int(
                    query.get("process_id", ["1"])[0]
                )
                self._send_json(
                    self.server.manager.detection_data_for_process(
                        process_id
                    ).meta()
                )
            except (TypeError, ValueError) as exc:
                self._send_json(
                    {"error": str(exc)},
                    status=400,
                )
            except Exception as exc:
                self._send_json(
                    {"error": str(exc)},
                    status=502,
                )
            return
        if parsed.path == "/api/detection/machines":
            try:
                query = parse_qs(parsed.query)
                process_id = int(
                    query.get("process_id", ["1"])[0]
                )
                self._send_json(
                    self.server.manager.detection_data_for_process(
                        process_id
                    ).machines()
                )
            except (TypeError, ValueError) as exc:
                self._send_json(
                    {"error": str(exc)},
                    status=400,
                )
            except Exception as exc:
                self._send_json(
                    {"error": str(exc)},
                    status=502,
                )
            return
        if parsed.path == "/api/detection/overview":
            try:
                query = parse_qs(parsed.query)
                t = int(query.get("t", ["0"])[0])
                machine_count_value = query.get(
                    "machine_count",
                    [None],
                )[0]
                machine_count = (
                    None
                    if machine_count_value in {None, ""}
                    else int(machine_count_value)
                )
                process_id = int(
                    query.get("process_id", ["1"])[0]
                )
                self._send_json(
                    self.server.manager.detection_data_for_process(
                        process_id
                    ).overview(
                        t,
                        machine_count=machine_count,
                    )
                )
            except (TypeError, ValueError) as exc:
                self._send_json(
                    {"error": str(exc)},
                    status=400,
                )
            except Exception as exc:
                self._send_json(
                    {"error": str(exc)},
                    status=502,
                )
            return
        if parsed.path == "/api/detection/predict":
            try:
                query = parse_qs(parsed.query)
                t = int(query.get("t", ["0"])[0])
                machine_count = int(
                    query.get("machine_count", ["1"])[0]
                )
                process_id = int(
                    query.get("process_id", ["1"])[0]
                )
                prediction = (
                    self.server.manager.detection_data_for_process(
                        process_id
                    ).predict(
                        t,
                        machine_count=machine_count,
                    )
                )
                injection = (
                    self.server.manager.handle_prediction_alarms(
                        prediction["t"],
                        prediction["predictions"],
                        process_id=process_id,
                    )
                )
                self._send_json({**prediction, **injection})
            except (TypeError, ValueError) as exc:
                self._send_json(
                    {"success": False, "error": str(exc)},
                    status=400,
                )
            except Exception as exc:
                self._send_json(
                    {"success": False, "error": str(exc)},
                    status=502,
                )
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
        if parsed.path in {"/api/construction", "/api/construct-initial"}:
            try:
                result = self.server.manager.construct_schedule(
                    dataset_id=body.get("dataset_id"),
                    method=(
                        body.get("method")
                        or body.get("construction_method")
                        or "InfluenceAwareConstruct"
                    ),
                    process_id=body.get("process_id", 1),
                )
                self._send_json(result)
            except (TypeError, ValueError) as exc:
                self._send_json(
                    {"success": False, "error": str(exc)},
                    status=400,
                )
            except FileNotFoundError as exc:
                self._send_json(
                    {"success": False, "error": str(exc)},
                    status=503,
                )
            except ConstructionError as exc:
                self._send_json(
                    {"success": False, "error": str(exc)},
                    status=500,
                )
            except Exception as exc:
                traceback.print_exc()
                self._send_json(
                    {"success": False, "error": str(exc)},
                    status=500,
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
        if parsed.path == "/api/pause":
            try:
                result = self.server.manager.set_paused(
                    body.get("paused")
                )
                self._send_json(result)
            except (TypeError, ValueError) as exc:
                self._send_json(
                    {"success": False, "error": str(exc)},
                    status=400,
                )
            return
        if parsed.path == "/api/stop":
            try:
                self._send_json(self.server.manager.stop())
            except (TypeError, ValueError) as exc:
                self._send_json(
                    {"success": False, "error": str(exc)},
                    status=400,
                )
            except Exception as exc:
                self._send_json(
                    {"success": False, "error": str(exc)},
                    status=500,
                )
            return
        if parsed.path == "/api/anomalies/machine":
            try:
                result = self.server.manager.handle_machine_anomaly(
                    machine_id=body.get("machine_id"),
                    anomaly_type=body.get(
                        "anomaly_type",
                        body.get("type"),
                    ),
                    duration=body.get(
                        "duration",
                        body.get("repair_duration"),
                    ),
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
        if parsed.path == "/api/auto-machine-anomaly":
            try:
                result = self.server.manager.set_auto_machine_anomaly(
                    body.get("enabled")
                )
                self._send_json(result)
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
                    process_id=body.get("process_id", 1),
                    wait_for_animation=bool(
                        body.get("wait_for_animation", False)
                    ),
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
                    process_id=body.get("process_id", 1),
                    wait_for_animation=bool(
                        body.get("wait_for_animation", False)
                    ),
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
        if parsed.path in {
            "/api/construction-reoptimize",
            "/api/influence-aware-reoptimize",
        }:
            try:
                result = self.server.manager.construction_reoptimize(
                    method=(
                        body.get("method")
                        or "InfluenceAwareConstruct"
                    ),
                    process_id=body.get("process_id", 1),
                    wait_for_animation=bool(
                        body.get("wait_for_animation", False)
                    ),
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
        if parsed.path == "/api/reoptimization-animation-complete":
            try:
                result = (
                    self.server.manager.complete_reoptimization_animation(
                        body.get("animation_id")
                    )
                )
                self._send_json(result)
            except (TypeError, ValueError) as exc:
                self._send_json(
                    {"success": False, "error": str(exc)},
                    status=400,
                )
            return
        if parsed.path == "/api/greedy-reoptimize":
            try:
                result = self.server.manager.greedy_reoptimize(
                    process_id=body.get("process_id", 1),
                    wait_for_animation=bool(
                        body.get("wait_for_animation", False)
                    ),
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
                command_options = {
                    "process_id": body.get("process_id", 1),
                }
                if "wait_for_animation" in body:
                    command_options["wait_for_animation"] = bool(
                        body["wait_for_animation"]
                    )
                result = self.server.manager.reoptimize_command(
                    method,
                    config,
                    **command_options,
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
        if parsed.path == "/api/model-test/anomaly":
            try:
                result = self.server.manager.test_anomaly_model(
                    process_id=body.get("process_id", 1),
                    t=body.get("t", 85),
                    machine_id=body.get("machine_id"),
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
                    status=502,
                )
            return
        if parsed.path == "/api/model-test/hls":
            try:
                options = {
                    key: body[key]
                    for key in HLS_OPTION_FIELDS
                    if key in body
                }
                result = self.server.manager.test_hls_model(
                    dataset_id=body.get("dataset_id"),
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
        if parsed.path == "/api/model-test/construction":
            try:
                result = self.server.manager.test_construction_model(
                    dataset_id=body.get("dataset_id"),
                    method=(
                        body.get("method")
                        or "InfluenceAwareConstruct"
                    ),
                    process_id=body.get("process_id", 1),
                )
                self._send_json(result)
            except (TypeError, ValueError, FileNotFoundError) as exc:
                self._send_json(
                    {"success": False, "error": str(exc)},
                    status=400,
                )
            except ConstructionError as exc:
                self._send_json(
                    {"success": False, "error": str(exc)},
                    status=500,
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
        if parsed.path in {"/api/jobs/cancel", "/api/orders/cancel"}:
            try:
                if "order_ids" in body:
                    result = self.server.manager.cancel_orders(
                        body["order_ids"],
                        job_ids=body.get("job_ids"),
                    )
                elif "job_ids" in body:
                    result = self.server.manager.cancel_jobs(
                        body["job_ids"]
                    )
                else:
                    job_id = body.get("job_id", body.get("order_id"))
                    result = self.server.manager.cancel_job(job_id)
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
    display_host = visualization.get("public_host") or host
    if not visualization.get("public_host") and host in {"0.0.0.0", "::"}:
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

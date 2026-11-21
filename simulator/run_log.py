import json
import threading
from datetime import datetime
from pathlib import Path


class SimulationRunLogger:
    """Write the latest simulation run to a structured log directory."""

    JSONL_FILES = (
        "events.jsonl",
        "operations.jsonl",
        "objectives.jsonl",
        "reoptimizations.jsonl",
    )

    def __init__(self, log_root):
        self.log_root = Path(log_root)
        self.latest_dir = self.log_root / "latest"
        self.lock = threading.RLock()
        self.started_at = None

    def start(self, metadata):
        with self.lock:
            self.latest_dir.mkdir(parents=True, exist_ok=True)
            for filename in self.JSONL_FILES:
                (self.latest_dir / filename).write_text(
                    "",
                    encoding="utf-8",
                )
            self.started_at = datetime.now().astimezone().isoformat()
            self._write_json(
                "metadata.json",
                {
                    "started_at": self.started_at,
                    **metadata,
                },
            )
            for filename in ("summary.json", "error.json"):
                stale_path = self.latest_dir / filename
                if stale_path.exists():
                    stale_path.unlink()

    def record_event(self, event, simulator):
        with self.lock:
            event_data = self._event_data(event)
            self._append_jsonl("events.jsonl", event_data)
            self._append_jsonl(
                "objectives.jsonl",
                self._objective_data(event, simulator),
            )
            if type(event).__name__ in {
                "TransportFinishEvent",
                "OperationStartEvent",
                "OperationFinishEvent",
            }:
                self._append_jsonl(
                    "operations.jsonl",
                    self._operation_data(event, simulator),
                )

    def record_reoptimization(
        self,
        request,
        response,
        simulator,
    ):
        with self.lock:
            self._append_jsonl(
                "reoptimizations.jsonl",
                {
                    "logged_at": datetime.now().astimezone().isoformat(),
                    "request": request,
                    "response": response,
                    "objectives_after": dict(simulator.objectives),
                    "processing_operations": [
                        self._task_data(task)
                        for job in simulator.jobs
                        for task in job.tasks
                        if task.status == "processing"
                    ],
                },
            )

    def finish(self, simulator):
        with self.lock:
            jobs = []
            for job in simulator.jobs:
                jobs.append(
                    {
                        "job_id": job.job_id,
                        "operation_count": job.operation_count,
                        "ready_time": job.ready_time,
                        "due_time": job.due_time,
                        "completion_time": job.completion_time,
                        "earliness": job.earliness,
                        "tardiness": job.tardiness,
                        "delivery_penalty": job.delivery_penalty,
                        "processing_energy": job.processing_energy,
                        "transport_energy": job.transport_energy,
                        "status": (
                            "canceled"
                            if job.is_canceled
                            else "completed"
                            if all(
                                task.status == "completed"
                                for task in job.tasks
                            )
                            else "unfinished"
                        ),
                        "tasks": [
                            self._task_data(task) for task in job.tasks
                        ],
                    }
                )
            summary = {
                "started_at": self.started_at,
                "finished_at": datetime.now().astimezone().isoformat(),
                "makespan": simulator.makespan,
                "objectives": dict(simulator.objectives),
                "energy_components": {
                    "processing": simulator.total_processing_energy,
                    "transport": simulator.total_transport_energy,
                    "auxiliary": simulator.total_auxiliary_energy,
                    "total": simulator.total_energy,
                },
                "jobs_completed": len(simulator.finished_queue),
                "jobs_canceled": len(simulator.canceled_orders),
                "jobs_total": len(simulator.jobs),
                "remaining_machine_queue": sum(
                    len(machine.pending_operations)
                    for machine in simulator.machines
                ),
                "remaining_events": len(simulator.event_queue),
                "machines": [
                    {
                        "machine_id": machine.machine_id,
                        "status": machine.machine_status,
                        "ready_time": machine.ready_time,
                        "anomaly_type": machine.anomaly_type,
                        "anomaly_started_at": (
                            machine.anomaly_started_at
                        ),
                        "recovery_time": machine.recovery_time,
                        "performance_factor": (
                            machine.performance_factor
                        ),
                    }
                    for machine in simulator.machines
                ],
                "jobs": jobs,
                "schedule": [
                    {
                        "machine_id": machine_id,
                        "job_id": job_id,
                        "operation_id": operation_id,
                        "start_time": simulator.schedule.start_time[
                            machine_id
                        ][index],
                        "end_time": simulator.schedule.end_time[
                            machine_id
                        ][index],
                    }
                    for machine_id, items in enumerate(
                        simulator.schedule.schedule_items
                    )
                    for index, (job_id, operation_id) in enumerate(items)
                ],
            }
            self._write_json("summary.json", summary)

    def fail(self, error):
        with self.lock:
            self._write_json(
                "error.json",
                {
                    "failed_at": datetime.now().astimezone().isoformat(),
                    "error_type": type(error).__name__,
                    "message": str(error),
                },
            )

    def _event_data(self, event):
        data = {}
        for key, value in vars(event).items():
            if key in {"anomaly", "result"} or value is None:
                continue
            if isinstance(value, (str, int, float, bool, list, dict)):
                data[key] = value
        data["event_type"] = type(event).__name__
        return data

    def _objective_data(self, event, simulator):
        return {
            "recorded_at": datetime.now().astimezone().isoformat(),
            "simulation_time": simulator.curr_time,
            "event_type": type(event).__name__,
            "makespan": simulator.makespan,
            "objectives": dict(simulator.objectives),
            "processing_energy": simulator.total_processing_energy,
            "transport_energy": simulator.total_transport_energy,
            "auxiliary_energy": simulator.total_auxiliary_energy,
            "total_energy": simulator.total_energy,
            "delivery_penalty": simulator.total_penalty,
        }

    def _operation_data(self, event, simulator):
        task = simulator.jobs[event.job_id].tasks[event.operation_id]
        return {
            "recorded_at": datetime.now().astimezone().isoformat(),
            "simulation_time": simulator.curr_time,
            "event_type": type(event).__name__,
            "job_id": event.job_id,
            "operation_id": event.operation_id,
            "machine_id": getattr(event, "machine_id", None),
            "task": self._task_data(task),
        }

    @staticmethod
    def _task_data(task):
        return {
            "task_id": task.task_id,
            "job_id": task.job_id,
            "operation_id": task.operation_id,
            "status": task.status,
            "assigned_machine": task.assigned_machine,
            "eligible_machines": list(task.eligible_machines),
            "planned_start": task.planned_start,
            "planned_end": task.planned_end,
            "actual_start": task.actual_start,
            "actual_end": task.actual_end,
            "source_machine": task.source_machine,
            "transport_start": task.transport_start,
            "transport_end": task.transport_end,
            "transport_time": task.transport_time,
            "transport_energy": task.transport_energy,
            "transport_completed": task.transport_completed,
            "transport_segments": [
                dict(segment) for segment in task.transport_segments
            ],
            "committed_transport_energy": (
                task.committed_transport_energy
            ),
            "total_transport_energy": task.total_transport_energy,
            "current_location_machine": task.current_location_machine,
            "waiting_time": task.waiting_time,
            "ready_not_before": task.ready_not_before,
            "interrupted_at": task.interrupted_at,
            "interrupted_processing_energy": (
                task.interrupted_processing_energy
            ),
            "material_consumption": dict(task.material_consumption),
            "material_consumption_committed": (
                task.material_consumption_committed
            ),
            "processing_time": (
                task.processing_time
                if task.assigned_machine is not None
                else None
            ),
            "processing_energy": (
                task.processing_energy
                if task.assigned_machine is not None
                else None
            ),
        }

    def _append_jsonl(self, filename, payload):
        with (self.latest_dir / filename).open(
            "a",
            encoding="utf-8",
        ) as log_file:
            log_file.write(
                json.dumps(payload, ensure_ascii=False, default=str) + "\n"
            )

    def _write_json(self, filename, payload):
        (self.latest_dir / filename).write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, default=str)
            + "\n",
            encoding="utf-8",
        )

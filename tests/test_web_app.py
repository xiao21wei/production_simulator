import json
import tempfile
import unittest
import urllib.request
from types import SimpleNamespace
from unittest.mock import patch

from simulator.event import OperationStartEvent
from simulator.config import DEFAULT_CONFIG_PATH
from simulator.simulator import Simulator
from system.schedule import PlannedOperation
from web_app import (
    DashboardState,
    SimulationManager,
    create_dashboard_server,
    serialize_event,
    serialize_plan,
)


class WebAppTest(unittest.TestCase):
    def test_drl_scheduler_can_be_preloaded_and_reused(self):
        created = []

        class FakeScheduler:
            def __init__(self):
                created.append(self)

        manager = SimulationManager(
            config_path=DEFAULT_CONFIG_PATH,
            speed=5,
            realtime=False,
            scheduler_factory=FakeScheduler,
        )

        preloaded = manager.preload_scheduler()

        self.assertIs(preloaded, created[0])
        self.assertIs(manager._get_scheduler(), preloaded)
        self.assertEqual(len(created), 1)

    def test_reoptimization_requires_running_simulation(self):
        manager = SimulationManager(
            config_path=DEFAULT_CONFIG_PATH,
            speed=5,
            realtime=False,
        )

        with self.assertRaises(ValueError):
            manager.reoptimize(num_samples=1, seed=0)

    def test_operation_event_contains_animation_data(self):
        simulator = SimpleNamespace(
            jobs=[
                SimpleNamespace(
                    operation_times=[[17.0, 11.0]],
                )
            ]
        )
        event = OperationStartEvent(7, 12, 0, 0, 1)

        payload = serialize_event(event, simulator)

        self.assertEqual(payload["job_id"], 0)
        self.assertEqual(payload["machine_id"], 1)
        self.assertEqual(payload["processing_time"], 11.0)

    def test_display_percent_is_persisted_in_state(self):
        state = DashboardState(display_percent=100)

        state.set_display_percent(150)

        self.assertEqual(state.snapshot()["display_percent"], 150)

    def test_display_percent_range_is_validated(self):
        state = DashboardState()

        with self.assertRaises(ValueError):
            state.set_display_percent(301)

    def test_selected_dataset_starts_simulation(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            manager = SimulationManager(
                config_path=DEFAULT_CONFIG_PATH,
                speed=50,
                realtime=False,
                log_dir=temp_dir,
            )

            started = manager.start(manager.default_dataset_id)
            manager.thread.join(timeout=10)

        self.assertTrue(started)
        self.assertFalse(manager.thread.is_alive())
        self.assertEqual(manager.state.status, "finished")
        self.assertEqual(
            manager.state.selected_dataset["id"],
            manager.default_dataset_id,
        )
        self.assertTrue(
            any(
                operation.get("transport_time", 0) > 0
                for operation in manager.state.plan
            )
        )

    def test_finished_status_is_published_after_logger_finish(self):
        order = []

        class FakeLogger:
            def __init__(self, log_dir):
                self.log_dir = log_dir

            def start(self, metadata):
                return None

            def record_event(self, event, simulator):
                return None

            def record_reoptimization(self, request, response, simulator):
                return None

            def finish(self, simulator):
                order.append("logger_finish")

            def fail(self, error):
                return None

        manager = SimulationManager(
            config_path=DEFAULT_CONFIG_PATH,
            speed=50,
            realtime=False,
        )
        manager.selected_source = manager.datasets_by_id[
            manager.default_dataset_id
        ]
        original_state_finish = manager.state.finish

        def record_state_finish(simulator):
            order.append("state_finish")
            original_state_finish(simulator)

        manager.state.finish = record_state_finish
        with patch("web_app.SimulationRunLogger", FakeLogger):
            manager._run()

        self.assertEqual(order[-2:], ["logger_finish", "state_finish"])
        self.assertEqual(manager.state.status, "finished")

    def test_plan_serializes_transport_fields(self):
        operation = PlannedOperation(
            job_id=2,
            operation_id=3,
            machine_id=4,
            start_time=12,
            end_time=20,
            source_machine=1,
            transport_start=8,
            transport_end=11,
            transport_time=3,
            transport_energy=7,
            waiting_time=1,
        )

        payload = serialize_plan([operation])[0]

        self.assertEqual(payload["source_machine"], 1)
        self.assertEqual(payload["transport_start"], 8)
        self.assertEqual(payload["transport_end"], 11)
        self.assertEqual(payload["transport_energy"], 7)
        self.assertEqual(payload["waiting_time"], 1)

    def test_model_reoptimization_updates_remaining_plan(self):
        simulator = Simulator(realtime=False)
        simulator.log_tag = False
        simulator.init()
        schedule = [
            {
                "job_id": job.job_id,
                "operation_index": task.operation_id,
                "operation_id": task.task_id,
                "machine_id": task.eligible_machines[-1],
            }
            for job in simulator.jobs
            for task in job.tasks
        ]

        class FakeScheduler:
            def predict(self, request):
                return {
                    "model": "fake.pt",
                    "num_samples": request["num_samples"],
                    "objectives": {
                        "makespan": 1,
                        "energy": 1,
                        "penalty": 1,
                    },
                    "schedule": schedule,
                }

        manager = SimulationManager(
            config_path=DEFAULT_CONFIG_PATH,
            speed=5,
            realtime=False,
            scheduler_factory=FakeScheduler,
        )
        manager.simulator = simulator
        manager.selected_source = manager.datasets_by_id[
            manager.default_dataset_id
        ]
        manager.state.prepare(5)
        manager.state.selected_dataset = {
            "id": manager.default_dataset_id,
        }
        manager.state.set_running(simulator)
        lifecycle = []
        simulator.pause = lambda: lifecycle.append("pause")
        simulator.resume = lambda: lifecycle.append("resume")

        result = manager.reoptimize_command(
            "DRL",
            {"num_samples": 1, "seed": 0},
        )

        self.assertTrue(result["success"])
        self.assertEqual(result["optimizer"], "drl")
        self.assertEqual(
            result["command_config"],
            {"num_samples": 1, "seed": 0},
        )
        self.assertEqual(result["model"], "fake.pt")
        self.assertGreater(result["unfinished_task_count"], 0)
        self.assertTrue(manager.state.plan)
        self.assertEqual(lifecycle, ["pause", "resume"])

    def test_hls_reoptimization_uses_only_machine_assignments(self):
        simulator = Simulator(realtime=False)
        simulator.log_tag = False
        simulator.init()
        simulator.updateEventQueue()
        while simulator.event_queue and simulator.event_queue[0].timestamp <= 15:
            event = simulator.event_queue.pop(0)
            simulator.curr_time = event.timestamp
            simulator.handleEvent(event)
            simulator.updateEventQueue()

        processing_before = {
            (job.job_id, task.operation_id): task.assigned_machine
            for job in simulator.jobs
            for task in job.tasks
            if task.status == "processing"
        }
        schedule = [
            {
                "job_id": job.job_id,
                "operation_index": task.operation_id,
                "operation_id": task.task_id,
                "machine_id": task.eligible_machines[-1],
                "start_time": 50_000,
                "end_time": 50_010,
                "processing_time": 10,
            }
            for job in simulator.jobs
            for task in job.tasks
        ]
        requests = []

        class FakeHlsScheduler:
            def predict(self, request):
                requests.append(request)
                return {
                    "success": True,
                    "model": "production_scheduling",
                    "device": "cpu",
                    "objectives": {"makespan": 231},
                    "runtime_seconds": 0.01,
                    "seed": request["seed"],
                    "additional_data_used": False,
                    "additional_data_valid": True,
                    "feasible": True,
                    "schedule": schedule,
                }

        manager = SimulationManager(
            config_path=DEFAULT_CONFIG_PATH,
            speed=5,
            realtime=False,
            hls_scheduler_factory=FakeHlsScheduler,
        )
        manager.simulator = simulator
        manager.selected_source = manager.datasets_by_id[
            manager.default_dataset_id
        ]
        manager.state.prepare(5)
        manager.state.selected_dataset = {
            "id": manager.default_dataset_id,
        }
        manager.state.set_running(simulator)
        lifecycle = []
        simulator.pause = lambda: lifecycle.append("pause")
        simulator.resume = lambda: lifecycle.append("resume")

        result = manager.reoptimize_command(
            "HLS",
            {
                "seed": 17,
                "total_time_seconds": 1,
                "population_size": 8,
            },
        )

        self.assertTrue(result["success"])
        self.assertEqual(result["optimizer"], "hls")
        self.assertFalse(result["hls_schedule_times_used"])
        self.assertTrue(result["transport_time_recalculated"])
        self.assertEqual(result["hls_objectives"], {"makespan": 231})
        self.assertEqual(requests[0]["seed"], 17)
        self.assertEqual(requests[0]["total_time_seconds"], 1)
        self.assertEqual(requests[0]["population_size"], 8)
        self.assertTrue(requests[0]["raw_lines"])
        self.assertTrue(requests[0]["additional_lines"])
        self.assertGreater(result["unfinished_task_count"], 0)
        self.assertEqual(
            result["hls_assignment_count"],
            result["unfinished_task_count"],
        )
        self.assertEqual(lifecycle, ["pause", "resume"])

        processing_after = {
            (job.job_id, task.operation_id): task.assigned_machine
            for job in simulator.jobs
            for task in job.tasks
            if task.status == "processing"
        }
        self.assertEqual(processing_after, processing_before)
        planned_times = {
            operation.start_time
            for operation in simulator.planned_operations
        }
        self.assertNotIn(50_000, planned_times)
        self.assertTrue(
            any(
                operation.transport_time > 0
                for operation in simulator.planned_operations
            )
        )

    def test_hls_reoptimization_http_endpoint(self):
        calls = []

        class FakeManager:
            state = SimpleNamespace()

            def hls_reoptimize(self, seed=0, **options):
                calls.append({"seed": seed, **options})
                return {"success": True, "optimizer": "hls"}

        server, thread = create_dashboard_server(
            "127.0.0.1",
            0,
            FakeManager(),
        )
        try:
            request = urllib.request.Request(
                (
                    "http://127.0.0.1:"
                    f"{server.server_address[1]}/api/hls-reoptimize"
                ),
                data=json.dumps(
                    {
                        "seed": 9,
                        "total_time_seconds": 2,
                        "population_size": 12,
                    }
                ).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(request, timeout=5) as response:
                payload = json.loads(response.read().decode("utf-8"))
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)

        self.assertEqual(payload["optimizer"], "hls")
        self.assertEqual(
            calls,
            [
                {
                    "seed": 9,
                    "total_time_seconds": 2,
                    "population_size": 12,
                }
            ],
        )

    def test_reoptimization_command_http_endpoint(self):
        calls = []

        class FakeManager:
            state = SimpleNamespace()

            def reoptimize_command(self, method, config):
                calls.append({"method": method, "config": config})
                return {
                    "success": True,
                    "optimizer": str(method).lower(),
                }

        server, thread = create_dashboard_server(
            "127.0.0.1",
            0,
            FakeManager(),
        )
        try:
            request = urllib.request.Request(
                (
                    "http://127.0.0.1:"
                    f"{server.server_address[1]}/api/reoptimize-command"
                ),
                data=json.dumps(
                    {
                        "method": "DRL",
                        "config": {
                            "num_samples": 2,
                            "seed": 5,
                        },
                    }
                ).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(request, timeout=5) as response:
                payload = json.loads(response.read().decode("utf-8"))
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)

        self.assertEqual(payload["optimizer"], "drl")
        self.assertEqual(
            calls,
            [
                {
                    "method": "DRL",
                    "config": {"num_samples": 2, "seed": 5},
                }
            ],
        )

    def test_reoptimization_command_validates_method_and_config(self):
        manager = SimulationManager(
            config_path=DEFAULT_CONFIG_PATH,
            speed=5,
            realtime=False,
        )

        with self.assertRaises(ValueError):
            manager.reoptimize_command("unknown", {})
        with self.assertRaises(ValueError):
            manager.reoptimize_command("DRL", {"unsupported": 1})
        with self.assertRaises(ValueError):
            manager.reoptimize_command("HLS", ["invalid"])

    def test_submit_random_job_http_endpoint(self):
        calls = []

        class FakeManager:
            state = SimpleNamespace()

            def submit_random_jobs(self, seed=0):
                calls.append(seed)
                return {
                    "success": True,
                    "optimizer": "dynamic_job_submit",
                    "new_jobs": [{"job_id": 15}],
                }

        server, thread = create_dashboard_server(
            "127.0.0.1",
            0,
            FakeManager(),
        )
        try:
            request = urllib.request.Request(
                (
                    "http://127.0.0.1:"
                    f"{server.server_address[1]}/api/jobs/submit"
                ),
                data=json.dumps({"seed": 12}).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(request, timeout=5) as response:
                payload = json.loads(response.read().decode("utf-8"))
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)

        self.assertEqual(payload["new_jobs"][0]["job_id"], 15)
        self.assertEqual(calls, [12])

    def test_auto_job_submission_http_endpoint(self):
        calls = []
        auto_state = {
            "enabled": True,
            "triggered": False,
            "count": 0,
            "threshold": 5,
        }

        class FakeManager:
            state = SimpleNamespace(
                snapshot=lambda: {
                    "auto_job_submission": auto_state,
                }
            )

            def set_auto_job_submission(self, enabled):
                calls.append(enabled)
                auto_state["enabled"] = enabled

        server, thread = create_dashboard_server(
            "127.0.0.1",
            0,
            FakeManager(),
        )
        try:
            request = urllib.request.Request(
                (
                    "http://127.0.0.1:"
                    f"{server.server_address[1]}/api/auto-job-submission"
                ),
                data=json.dumps({"enabled": True}).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(request, timeout=5) as response:
                payload = json.loads(response.read().decode("utf-8"))
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)

        self.assertTrue(payload["ok"])
        self.assertEqual(calls, [True])
        self.assertEqual(
            payload["auto_job_submission"],
            auto_state,
        )


if __name__ == "__main__":
    unittest.main()

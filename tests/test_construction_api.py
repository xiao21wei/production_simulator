import json
import unittest
import urllib.request
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from simulator.config import DEFAULT_CONFIG_PATH
from simulator.construction import (
    CONSTRUCTION_METHODS,
    construct_schedule,
    normalize_construction_method,
    resolve_construction_paths,
)
from simulator.simulator import Simulator
from web_app import SimulationManager, create_dashboard_server


class ConstructionClientTest(unittest.TestCase):
    def test_normalizes_supported_methods_and_legacy_alias(self):
        for method in CONSTRUCTION_METHODS:
            self.assertEqual(
                normalize_construction_method(method.lower()),
                method,
            )
        self.assertEqual(
            normalize_construction_method("InfluenceAware"),
            "InfluenceAwareConstruct",
        )
        with self.assertRaises(ValueError):
            normalize_construction_method("unknown")

    def test_resolves_process_specific_split_dataset_paths(self):
        paths = resolve_construction_paths(
            instance="fjsp.brandimarte.Mk03.m8j15c5.fjs",
            process_id=3,
        )

        self.assertEqual(Path(paths["raw_file"]).parent.name, "raw2")
        self.assertEqual(
            Path(paths["additional_file"]).parent.name,
            "add2",
        )
        self.assertEqual(
            Path(paths["delivery_cost_file"]).parent.name,
            "delivery_cost",
        )

    @patch("simulator.construction._resolve_executable")
    @patch("simulator.construction.subprocess.run")
    def test_construct_schedule_builds_solver_request(
        self,
        run_mock,
        executable_mock,
    ):
        executable_mock.return_value = Path("/tmp/scheduler")
        run_mock.return_value = SimpleNamespace(
            returncode=0,
            stdout=json.dumps(
                {
                    "success": True,
                    "method": "MOPNR_EET",
                    "objectives": {
                        "makespan": 10,
                        "delivery_cost": 2,
                        "total_energy": 3,
                    },
                    "schedule": {
                        "machine_count": 2,
                        "operation_count": 1,
                        "operations": [],
                    },
                }
            ),
            stderr="",
        )

        result = construct_schedule(
            instance="fjsp.brandimarte.Mk03.m8j15c5.fjs",
            process_id=2,
            method="mopnr_eet",
            executable="/tmp/scheduler",
        )

        command = run_mock.call_args.args[0]
        self.assertEqual(command[:3], [
            "/tmp/scheduler",
            "--construct",
            "MOPNR_EET",
        ])
        self.assertIn("--delivery-cost", command)
        self.assertEqual(result["process_id"], 2)
        self.assertEqual(
            result["request"]["method"],
            "MOPNR_EET",
        )

    def test_simulator_manager_uses_selected_process_paths(self):
        manager = SimulationManager(
            config_path=DEFAULT_CONFIG_PATH,
            speed=2,
            realtime=False,
        )
        fake_result = {
            "success": True,
            "method": "FIFO_SPT",
            "objectives": {
                "makespan": 1,
                "delivery_cost": 0,
                "total_energy": 0,
            },
            "schedule": {
                "machine_count": 1,
                "operation_count": 1,
                "operations": [],
            },
        }
        with patch(
            "web_app.run_construction",
            return_value=fake_result,
        ) as runner:
            result = manager.construct_schedule(
                dataset_id="fjsp.brandimarte.Mk03.m8j15c5",
                process_id=4,
                method="FIFO_SPT",
            )

        request = runner.call_args.kwargs
        self.assertEqual(
            Path(request["raw_file"]).parent.name,
            "raw3",
        )
        self.assertEqual(
            Path(request["additional_file"]).parent.name,
            "add3",
        )
        self.assertEqual(result["process_id"], 4)
        self.assertEqual(
            result["dataset_id"],
            "fjsp.brandimarte.Mk03.m8j15c5",
        )

    def test_construction_method_reoptimizes_unfinished_operations(self):
        simulator = Simulator(realtime=False)
        simulator.log_tag = False
        simulator.init()
        manager = SimulationManager(
            config_path=DEFAULT_CONFIG_PATH,
            speed=5,
            realtime=False,
        )
        manager.simulator = simulator
        manager.selected_source = manager.datasets_by_id[
            manager.default_dataset_id
        ]
        manager.state.prepare(5)
        manager.state.selected_dataset = {
            "id": manager.selected_source["id"],
        }
        manager.state.set_running(simulator)
        operations = [
            {
                "job_id": job.job_id,
                "operation_id": task.operation_id,
                "machine_id": task.eligible_machines[-1],
                "start_time": 0,
                "end_time": 1,
            }
            for job in simulator.jobs
            for task in job.tasks
            if task.status in {"pending", "scheduled"}
        ]
        fake_result = {
            "success": True,
            "method": "FIFO_SPT",
            "objectives": {
                "makespan": 10,
                "delivery_cost": 2,
                "total_energy": 3,
            },
            "objective_breakdown": {
                "processing_time": 8,
                "transport_time": 2,
            },
            "schedule": {
                "machine_count": manager.selected_source[
                    "num_machines"
                ],
                "operation_count": len(operations),
                "operations": operations,
            },
        }
        with patch(
            "web_app.run_construction",
            return_value=fake_result,
        ) as runner:
            result = manager.reoptimize_command(
                "influence_aware",
                {"method": "FIFO_SPT"},
                process_id=1,
            )

        self.assertEqual(
            runner.call_args.kwargs["method"],
            "FIFO_SPT",
        )
        self.assertTrue(result["success"])
        self.assertEqual(result["optimizer"], "construction")
        self.assertEqual(result["construction_method"], "FIFO_SPT")
        self.assertEqual(
            result["construction_objectives"]["makespan"],
            10,
        )
        self.assertGreater(result["construction_assignment_count"], 0)
        self.assertGreater(result["unfinished_task_count"], 0)
        self.assertEqual(manager.state.status, "running")
        self.assertTrue(manager.state.plan)

    def test_reoptimization_animation_defers_resume_until_completion(self):
        simulator = Simulator(realtime=False)
        simulator.log_tag = False
        simulator.init()
        manager = SimulationManager(
            config_path=DEFAULT_CONFIG_PATH,
            speed=5,
            realtime=False,
        )
        manager.simulator = simulator
        manager.selected_source = manager.datasets_by_id[
            manager.default_dataset_id
        ]
        manager.state.prepare(5)
        manager.state.selected_dataset = {
            "id": manager.selected_source["id"],
        }
        manager.state.set_running(simulator)
        operations = [
            {
                "job_id": job.job_id,
                "operation_id": task.operation_id,
                "machine_id": task.eligible_machines[-1],
                "start_time": 0,
                "end_time": 1,
            }
            for job in simulator.jobs
            for task in job.tasks
            if task.status in {"pending", "scheduled"}
        ]
        fake_result = {
            "success": True,
            "method": "FIFO_SPT",
            "objectives": {
                "makespan": 10,
                "delivery_cost": 2,
                "total_energy": 3,
            },
            "objective_breakdown": {
                "processing_time": 8,
                "transport_time": 2,
            },
            "schedule": {
                "machine_count": manager.selected_source[
                    "num_machines"
                ],
                "operation_count": len(operations),
                "operations": operations,
            },
        }
        with patch(
            "web_app.run_construction",
            return_value=fake_result,
        ):
            result = manager.construction_reoptimize(
                method="FIFO_SPT",
                process_id=1,
                wait_for_animation=True,
            )

        self.assertTrue(result["animation_required"])
        self.assertGreater(len(result["animation_moves"]), 0)
        first_move = result["animation_moves"][0]
        self.assertIn("from_queue_machine_id", first_move)
        self.assertIn("from_queue_index", first_move)
        self.assertIn("to_queue_machine_id", first_move)
        self.assertIn("to_queue_index", first_move)
        self.assertEqual(manager.state.status, "animating")
        self.assertIsNotNone(
            manager.pending_reoptimization_animation
        )

        completed = manager.complete_reoptimization_animation(
            result["animation_id"]
        )

        self.assertTrue(completed["success"])
        self.assertEqual(manager.state.status, "running")
        self.assertIsNone(manager.pending_reoptimization_animation)
        self.assertIsNone(manager.reoptimization_animation_timer)

    def test_construction_http_endpoints(self):
        calls = []
        reoptimization_calls = []

        class FakeManager:
            state = SimpleNamespace()

            def construction_methods(self):
                return {
                    "default_method": "InfluenceAwareConstruct",
                    "methods": list(CONSTRUCTION_METHODS),
                }

            def construct_schedule(
                self,
                dataset_id=None,
                method="InfluenceAwareConstruct",
                process_id=1,
            ):
                calls.append((dataset_id, method, process_id))
                return {
                    "success": True,
                    "dataset_id": dataset_id,
                    "method": method,
                    "process_id": process_id,
                    "objectives": {
                        "makespan": 1,
                        "delivery_cost": 0,
                        "total_energy": 0,
                    },
                    "schedule": {
                        "machine_count": 1,
                        "operation_count": 0,
                        "operations": [],
                    },
                }

            def test_construction_model(
                self,
                dataset_id=None,
                method="InfluenceAwareConstruct",
                process_id=1,
            ):
                result = self.construct_schedule(
                    dataset_id=dataset_id,
                    method=method,
                    process_id=process_id,
                )
                return {
                    "success": True,
                    "test_type": "construction",
                    "result": result,
                }

            def construction_reoptimize(
                self,
                method="InfluenceAwareConstruct",
                process_id=1,
                wait_for_animation=False,
            ):
                reoptimization_calls.append((method, process_id))
                return {
                    "success": True,
                    "optimizer": "construction",
                    "construction_method": method,
                    "process_ids": [process_id],
                }

        manager = FakeManager()
        server, thread = create_dashboard_server(
            "127.0.0.1",
            0,
            manager,
        )
        base = f"http://127.0.0.1:{server.server_address[1]}"
        try:
            with urllib.request.urlopen(
                f"{base}/api/construction/methods",
                timeout=5,
            ) as response:
                methods = json.loads(response.read().decode("utf-8"))
            request = urllib.request.Request(
                f"{base}/api/construct-initial",
                data=json.dumps(
                    {
                        "dataset_id": "instance",
                        "construction_method": "MWKR_EET",
                        "process_id": 3,
                    }
                ).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(request, timeout=5) as response:
                result = json.loads(response.read().decode("utf-8"))
            request = urllib.request.Request(
                f"{base}/api/model-test/construction",
                data=json.dumps(
                    {
                        "dataset_id": "instance",
                        "method": "FIFO_EET",
                        "process_id": 2,
                    }
                ).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(request, timeout=5) as response:
                model_result = json.loads(
                    response.read().decode("utf-8")
                )
            request = urllib.request.Request(
                f"{base}/api/influence-aware-reoptimize",
                data=json.dumps(
                    {
                        "method": "InfluenceAwareConstruct",
                        "process_id": 1,
                    }
                ).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(request, timeout=5) as response:
                reoptimization = json.loads(
                    response.read().decode("utf-8")
                )
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)

        self.assertEqual(
            methods["methods"],
            list(CONSTRUCTION_METHODS),
        )
        self.assertTrue(result["success"])
        self.assertTrue(model_result["success"])
        self.assertEqual(model_result["test_type"], "construction")
        self.assertTrue(reoptimization["success"])
        self.assertEqual(
            reoptimization_calls,
            [("InfluenceAwareConstruct", 1)],
        )
        self.assertEqual(
            calls,
            [
                ("instance", "MWKR_EET", 3),
                ("instance", "FIFO_EET", 2),
            ],
        )


if __name__ == "__main__":
    unittest.main()

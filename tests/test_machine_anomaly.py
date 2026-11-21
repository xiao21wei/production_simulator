import json
import math
import unittest
import urllib.request
from types import SimpleNamespace

from simulator.config import DEFAULT_CONFIG_PATH
from simulator.event import (
    MachineRecoveryEvent,
    OperationFinishEvent,
    TransportFinishEvent,
)
from simulator.simulator import Simulator
from web_app import SimulationManager, create_dashboard_server


class MachineAnomalyTest(unittest.TestCase):
    def _processing_simulator(self):
        simulator = Simulator(realtime=False)
        simulator.log_tag = False
        simulator.init()
        simulator.updateEventQueue()
        while simulator.event_queue:
            task = next(
                (
                    task
                    for job in simulator.jobs
                    for task in job.tasks
                    if task.status == "processing"
                ),
                None,
            )
            if task is not None:
                return simulator, task
            event = simulator.event_queue.pop(0)
            simulator.curr_time = event.timestamp
            simulator.handleEvent(event)
            simulator.updateEventQueue()
        self.fail("No processing operation was found.")

    @staticmethod
    def _advance_to(simulator, timestamp):
        simulator.updateEventQueue()
        while (
            simulator.event_queue
            and simulator.event_queue[0].timestamp <= timestamp + 1e-9
        ):
            event = simulator.event_queue.pop(0)
            simulator.curr_time = event.timestamp
            simulator.handleEvent(event)
            simulator.updateEventQueue()

    def test_short_failure_requeues_current_operation_until_recovery(self):
        simulator, task = self._processing_simulator()
        machine_id = task.assigned_machine
        recovery_time = simulator.curr_time + 5
        queued_transports = [
            (
                event.job_id,
                event.operation_id,
                event.machine_id,
                event.timestamp,
            )
            for event in simulator.event_queue
            if (
                isinstance(event, TransportFinishEvent)
                and event.machine_id == machine_id
                and (
                    event.job_id,
                    event.operation_id,
                )
                != (task.job_id, task.operation_id)
            )
        ]

        result = simulator.startMachineAnomaly(
            machine_id,
            "short_failure",
            5,
            current_time=simulator.curr_time,
        )

        machine = simulator.machines[machine_id]
        self.assertEqual(result["machine_status"], "repairing")
        self.assertEqual(machine.machine_status, "repairing")
        self.assertEqual(task.status, "scheduled")
        self.assertIsNone(task.actual_start)
        self.assertEqual(task.assigned_machine, machine_id)
        self.assertEqual(task.ready_not_before, recovery_time)
        self.assertEqual(
            (machine.pending_operations[0].job_id,
             machine.pending_operations[0].operation_id),
            (task.job_id, task.operation_id),
        )
        self.assertTrue(
            any(
                isinstance(event, MachineRecoveryEvent)
                and event.machine_id == machine_id
                for event in simulator.event_queue
            )
        )
        retained_transports = {
            (
                event.job_id,
                event.operation_id,
                event.machine_id,
                event.timestamp,
            )
            for event in simulator.event_queue
            if isinstance(event, TransportFinishEvent)
        }
        self.assertTrue(queued_transports)
        self.assertTrue(
            all(item in retained_transports for item in queued_transports)
        )

        self._advance_to(simulator, recovery_time)

        self.assertEqual(task.status, "processing")
        self.assertEqual(task.actual_start, recovery_time)
        self.assertIsNone(task.ready_not_before)
        self.assertIsNone(machine.anomaly_started_at)

    def test_short_failure_reschedules_future_successor_transport(self):
        simulator, task = self._processing_simulator()
        machine_id = task.assigned_machine
        successor = simulator.jobs[task.job_id].tasks[
            task.operation_id + 1
        ]
        self.assertGreater(successor.transport_time, 0)
        self.assertGreater(
            successor.transport_start,
            simulator.curr_time,
        )

        result = simulator.startMachineAnomaly(
            machine_id,
            "short_failure",
            2,
            current_time=simulator.curr_time,
        )

        self.assertEqual(successor.transport_segments, [])
        self.assertFalse(
            any(
                event.job_id == successor.job_id
                and event.operation_id == successor.operation_id
                for event in simulator.event_queue
                if isinstance(event, TransportFinishEvent)
            )
        )

        self._advance_to(simulator, result["recovery_time"])

        self.assertEqual(task.status, "processing")
        self.assertGreaterEqual(
            successor.transport_start,
            task.planned_end,
        )
        self.assertEqual(len(successor.transport_segments), 1)
        self.assertGreaterEqual(
            successor.transport_segments[0]["transport_start"],
            task.planned_end,
        )

    def test_new_anomaly_replaces_old_recovery_event(self):
        simulator, task = self._processing_simulator()
        machine_id = task.assigned_machine

        simulator.startMachineAnomaly(
            machine_id,
            "degraded",
            10,
            current_time=simulator.curr_time,
        )
        simulator.startMachineAnomaly(
            machine_id,
            "short_failure",
            5,
            current_time=simulator.curr_time,
        )

        recovery_events = [
            event
            for event in simulator.event_queue
            if (
                isinstance(event, MachineRecoveryEvent)
                and event.machine_id == machine_id
            )
        ]
        self.assertEqual(len(recovery_events), 1)
        self.assertEqual(recovery_events[0].anomaly_type, "short_failure")

    def test_machine_anomaly_duration_is_integer_and_type_specific(self):
        simulator, task = self._processing_simulator()
        machine_id = task.assigned_machine

        for anomaly_type, duration in (
            ("short_failure", 2.5),
            ("short_failure", 6),
            ("medium_failure", 4),
            ("long_failure", 14),
            ("degraded", 21),
        ):
            with self.subTest(
                anomaly_type=anomaly_type,
                duration=duration,
            ):
                with self.assertRaises(ValueError):
                    simulator.startMachineAnomaly(
                        machine_id,
                        anomaly_type,
                        duration,
                        current_time=simulator.curr_time,
                    )

    def test_reoptimization_preserves_degraded_finish_time(self):
        simulator, task = self._processing_simulator()
        machine_id = task.assigned_machine
        task.processing_times[machine_id] = 3
        simulator.jobs[task.job_id].operation_times[
            task.operation_id
        ][machine_id] = 3
        nominal_finish = (
            task.actual_start + task.processing_times[machine_id]
        )

        simulator.startMachineAnomaly(
            machine_id,
            "degraded",
            10,
            current_time=simulator.curr_time,
        )
        extended_finish = task.planned_end
        self.assertGreater(extended_finish, nominal_finish)

        assignments = simulator._greedyUnfinishedAssignments()
        simulator.reoptimizeUnfinishedOperations(
            assignments,
            current_time=nominal_finish + 0.5,
        )
        finish_events = [
            event
            for event in simulator.event_queue
            if (
                isinstance(event, OperationFinishEvent)
                and event.job_id == task.job_id
                and event.operation_id == task.operation_id
            )
        ]
        self.assertTrue(finish_events)
        self.assertGreaterEqual(
            min(event.timestamp for event in finish_events),
            extended_finish,
        )

        self._advance_to(simulator, extended_finish)
        self.assertEqual(task.status, "completed")
        self.assertEqual(task.actual_end, extended_finish)

    def test_medium_failure_moves_current_operation_to_other_machine(self):
        simulator, task = self._processing_simulator()
        machine_id = task.assigned_machine
        recovery_time = simulator.curr_time + 5

        result = simulator.startMachineAnomaly(
            machine_id,
            "medium_failure",
            5,
            current_time=simulator.curr_time,
        )

        target_machine = task.assigned_machine
        self.assertEqual(result["machine_status"], "repairing")
        self.assertNotEqual(target_machine, machine_id)
        self.assertEqual(task.status, "scheduled")
        self.assertEqual(task.ready_not_before, recovery_time)
        self.assertEqual(
            (
                simulator.machines[target_machine]
                .pending_operations[0]
                .job_id,
                simulator.machines[target_machine]
                .pending_operations[0]
                .operation_id,
            ),
            (task.job_id, task.operation_id),
        )
        self.assertGreaterEqual(len(task.transport_segments), 1)

        self._advance_to(
            simulator,
            max(recovery_time, task.transport_end or recovery_time),
        )

        self.assertEqual(task.assigned_machine, target_machine)
        self.assertTrue(task.transport_completed)
        self.assertEqual(task.status, "processing")
        self.assertGreaterEqual(task.actual_start, recovery_time)

    def test_degraded_machine_uses_one_and_a_half_processing_time(self):
        simulator, task = self._processing_simulator()
        machine_id = task.assigned_machine
        base_time = task.processing_times[machine_id]
        base_energy = task.processing_energies[machine_id]
        actual_start = task.actual_start
        recovery_time = simulator.curr_time + 10
        degraded_processing_time = math.floor(
            base_time * 1.5
        )

        result = simulator.startMachineAnomaly(
            machine_id,
            "degraded",
            10,
            current_time=simulator.curr_time,
        )

        machine = simulator.machines[machine_id]
        self.assertEqual(result["machine_status"], "degraded")
        self.assertEqual(machine.machine_status, "degraded")
        self.assertEqual(machine.performance_factor, 1.5)
        self.assertEqual(task.status, "processing")
        self.assertEqual(
            task.planned_end,
            actual_start + degraded_processing_time,
        )

        self._advance_to(
            simulator,
            max(recovery_time, task.planned_end),
        )

        self.assertEqual(
            task.actual_end - actual_start,
            degraded_processing_time,
        )
        self.assertEqual(task.processing_energy, base_energy)
        degraded_tasks = [
            item
            for job in simulator.jobs
            for item in job.tasks
            if (
                item.assigned_machine == machine_id
                and item.actual_start is not None
                and item.actual_start < recovery_time
                and item.actual_end is not None
            )
        ]
        self.assertIn(task, degraded_tasks)
        for item in degraded_tasks:
            self.assertEqual(
                item.actual_end - item.actual_start,
                math.floor(
                    item.processing_times[machine_id] * 1.5
                ),
            )
        self.assertNotEqual(machine.machine_status, "degraded")
        self.assertIsNone(machine.anomaly_type)

    def test_long_failure_uses_drl_and_excludes_machine(self):
        simulator, task = self._processing_simulator()
        machine_id = task.assigned_machine
        predict_calls = []

        class FakeScheduler:
            def predict(self, request):
                predict_calls.append(request)
                return {
                    "model": "fake-drl.pt",
                    "num_samples": request["num_samples"],
                    "objectives": {"makespan": 123},
                    "schedule": [],
                }

        manager = SimulationManager(
            config_path=DEFAULT_CONFIG_PATH,
            speed=5,
            realtime=False,
            scheduler_factory=FakeScheduler,
            anomaly_handling_enabled=True,
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

        result = manager.handle_machine_anomaly(
            machine_id,
            "long_failure",
            30,
        )

        self.assertEqual(result["machine_status"], "failed")
        self.assertEqual(result["reschedule_method"], "DRL")
        self.assertEqual(result["optimizer"], "drl")
        self.assertEqual(result["model"], "fake-drl.pt")
        self.assertEqual(result["num_samples"], 1)
        self.assertEqual(result["model_objectives"], {"makespan": 123})
        self.assertTrue(result["requires_reoptimization"])
        self.assertEqual(simulator.machines[machine_id].machine_status, "failed")
        self.assertFalse(
            any(
                item.assigned_machine == machine_id
                for job in simulator.jobs
                for item in job.tasks
                if item.status in {"pending", "scheduled"}
            )
        )
        self.assertFalse(
            simulator.machines[machine_id].pending_operations
        )
        self.assertTrue(
            any(
                isinstance(event, MachineRecoveryEvent)
                and event.machine_id == machine_id
                for event in simulator.event_queue
            )
        )
        self.assertEqual(manager.state.status, "running")
        failed_state = next(
            item
            for item in manager.state.snapshot()["machine_states"]
            if item["id"] == machine_id
        )
        self.assertEqual(failed_state["status"], "failed")
        self.assertEqual(failed_state["anomaly_type"], "long_failure")
        self.assertEqual(
            failed_state["anomaly_started_at"],
            simulator.curr_time,
        )
        self.assertEqual(len(predict_calls), 1)
        self.assertEqual(predict_calls[0]["num_samples"], 1)
        self.assertEqual(
            predict_calls[0]["seed"],
            simulator.seed,
        )

        recovery_event = next(
            event
            for event in simulator.event_queue
            if (
                isinstance(event, MachineRecoveryEvent)
                and event.machine_id == machine_id
            )
        )

        self._advance_to(simulator, result["recovery_time"])

        self.assertEqual(len(predict_calls), 2)
        self.assertEqual(simulator.machines[machine_id].machine_status, "idle")
        self.assertEqual(manager.state.status, "running")
        self.assertEqual(
            recovery_event.result["reschedule_method"],
            "DRL",
        )
        self.assertIsNotNone(
            recovery_event.result["reoptimization"]
        )
        self.assertEqual(
            recovery_event.result["reoptimization"][
                "reschedule_method"
            ],
            "DRL",
        )

    def test_long_failure_defers_single_machine_task_until_recovery(self):
        simulator = Simulator(realtime=False)
        simulator.log_tag = False
        simulator.init()
        simulator.updateEventQueue()
        while simulator.event_queue:
            task = simulator.jobs[8].tasks[0]
            if task.status == "processing":
                break
            event = simulator.event_queue.pop(0)
            simulator.curr_time = event.timestamp
            simulator.handleEvent(event)
            simulator.updateEventQueue()
        self.assertEqual(task.status, "processing")
        self.assertEqual(task.eligible_machines, (0,))

        class FakeScheduler:
            def predict(self, request):
                return {
                    "model": "fake-drl.pt",
                    "num_samples": request["num_samples"],
                    "objectives": {"makespan": 100},
                    "schedule": [],
                }

        manager = SimulationManager(
            config_path=DEFAULT_CONFIG_PATH,
            speed=5,
            realtime=False,
            scheduler_factory=FakeScheduler,
            anomaly_handling_enabled=True,
        )
        manager.simulator = simulator
        manager.selected_source = manager.datasets_by_id[
            manager.default_dataset_id
        ]
        manager.state.prepare(5)
        manager.state.set_running(simulator)

        result = manager.handle_machine_anomaly(
            0,
            "long_failure",
            20,
        )
        key = (task.job_id, task.operation_id)

        self.assertIn(key, simulator.deferred_anomaly_tasks)
        self.assertEqual(task.ready_not_before, result["recovery_time"])
        self.assertNotIn(
            key,
            {
                (operation.job_id, operation.operation_id)
                for operation in simulator.machines[0].pending_operations
            },
        )

        self._advance_to(simulator, result["recovery_time"])

        self.assertNotIn(key, simulator.deferred_anomaly_tasks)
        self.assertIn(task.status, {"scheduled", "processing"})
        self.assertTrue(
            task.status == "processing"
            or any(
                (operation.job_id, operation.operation_id) == key
                for operation in simulator.machines[0].pending_operations
            )
        )

    def test_machine_anomaly_http_endpoint(self):
        calls = []

        class FakeManager:
            state = SimpleNamespace()

            def handle_machine_anomaly(
                self,
                machine_id,
                anomaly_type,
                duration,
            ):
                calls.append(
                    {
                        "machine_id": machine_id,
                        "anomaly_type": anomaly_type,
                        "duration": duration,
                    }
                )
                return {"success": True}

        server, thread = create_dashboard_server(
            "127.0.0.1",
            0,
            FakeManager(),
        )
        try:
            request = urllib.request.Request(
                (
                    "http://127.0.0.1:"
                    f"{server.server_address[1]}/api/anomalies/machine"
                ),
                data=json.dumps(
                    {
                        "machine_id": 3,
                        "anomaly_type": "degraded",
                        "duration": 8,
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

        self.assertTrue(payload["success"])
        self.assertEqual(
            calls,
            [{
                "machine_id": 3,
                "anomaly_type": "degraded",
                "duration": 8,
            }],
        )


if __name__ == "__main__":
    unittest.main()

import json
import tempfile
import unittest
import urllib.request
from pathlib import Path
from types import SimpleNamespace

from simulator.config import DEFAULT_CONFIG_PATH
from simulator.event import TransportFinishEvent
from simulator.simulator import Simulator
from system.order import Order
from web_app import (
    SimulationManager,
    create_dashboard_server,
    serialize_job_states,
)


class JobCancellationTest(unittest.TestCase):
    def _create_simulator(self):
        simulator = Simulator(realtime=False, speed=50)
        simulator.log_tag = False
        simulator.init()
        simulator.updateEventQueue()
        return simulator

    def _advance_to_processing_operation(self, simulator):
        while simulator.event_queue:
            processing_job = next(
                (
                    job
                    for job in simulator.jobs
                    if any(
                        task.status == "processing"
                        for task in job.tasks
                    )
                ),
                None,
            )
            if processing_job is not None:
                return processing_job
            event = simulator.event_queue.pop(0)
            simulator.curr_time = event.timestamp
            simulator.handleEvent(event)
            simulator.updateEventQueue()
        self.fail("Simulation reached an empty event queue without processing.")

    def test_cancel_scheduled_job_removes_all_future_operations(self):
        simulator = self._create_simulator()

        result = simulator.cancelJob(0)

        self.assertTrue(result["success"])
        self.assertEqual(result["removed_operation_count"], 10)
        self.assertEqual(result["processing_operations"], [])
        self.assertEqual(
            [order.job_id for order in simulator.canceled_orders],
            [0],
        )
        self.assertEqual(
            {task.status for task in simulator.jobs[0].tasks},
            {"canceled"},
        )
        self.assertFalse(
            any(
                operation.job_id == 0
                for operation in simulator.planned_operations
            )
        )
        self.assertFalse(
            any(
                operation.job_id == 0
                for machine in simulator.machines
                for operation in machine.pending_operations
            )
        )
        self.assertFalse(
            any(
                getattr(event, "job_id", None) == 0
                for event in simulator.event_queue
            )
        )
        for task in simulator.jobs[0].tasks:
            self.assertEqual(task.status, "canceled")
            self.assertIsNone(task.source_machine)
            self.assertIsNone(task.transport_start)
            self.assertIsNone(task.transport_end)
            self.assertEqual(task.transport_time, 0)
            self.assertEqual(task.transport_energy, 0)
            self.assertFalse(task.transport_completed)

        with tempfile.TemporaryDirectory() as temp_dir:
            simulator.schedule_file = str(
                Path(temp_dir) / "schedule.csv"
            )
            simulator.gantt_file = str(
                Path(temp_dir) / "gantt.txt"
            )
            simulator.run()

        self.assertEqual(
            len(simulator.finished_queue),
            len(simulator.jobs) - 1,
        )
        self.assertEqual(len(simulator.canceled_orders), 1)
        self.assertEqual(simulator.event_queue, [])

    def test_cancel_processing_job_preserves_active_operation(self):
        simulator = self._create_simulator()
        job = self._advance_to_processing_operation(simulator)
        processing_operation = next(
            task.operation_id
            for task in job.tasks
            if task.status == "processing"
        )

        result = simulator.cancelJob(job.job_id)

        self.assertEqual(
            [item["operation_id"] for item in result["processing_operations"]],
            [processing_operation],
        )
        self.assertEqual(
            job.tasks[processing_operation].status,
            "processing",
        )
        self.assertTrue(
            all(
                task.status == "canceled"
                for task in job.tasks[processing_operation + 1:]
            )
        )

        processed_event_types = []
        while simulator.event_queue:
            event = simulator.event_queue.pop(0)
            simulator.curr_time = event.timestamp
            simulator.handleEvent(event)
            simulator.updateEventQueue()
            if getattr(event, "job_id", None) == job.job_id:
                processed_event_types.append(type(event).__name__)

        self.assertEqual(
            job.tasks[processing_operation].status,
            "completed",
        )
        self.assertIn("OperationFinishEvent", processed_event_types)
        self.assertNotIn("JobFinishEvent", processed_event_types)
        self.assertTrue(job.is_canceled)

    def test_cancel_keeps_completed_transport_energy_for_unstarted_operation(self):
        simulator = self._create_simulator()
        transport_task = None

        while simulator.event_queue:
            event = simulator.event_queue.pop(0)
            simulator.curr_time = event.timestamp
            simulator.handleEvent(event)
            simulator.updateEventQueue()
            if not isinstance(event, TransportFinishEvent):
                continue
            task = simulator.jobs[event.job_id].tasks[
                event.operation_id
            ]
            if (
                task.status == "scheduled"
                and task.actual_start is None
                and task.transport_time > 0
            ):
                transport_task = task
                transport_job_id = event.job_id
                break

        self.assertIsNotNone(transport_task)
        self.assertTrue(transport_task.transport_completed)
        completed_transport = {
            "source_machine": transport_task.source_machine,
            "transport_start": transport_task.transport_start,
            "transport_end": transport_task.transport_end,
            "transport_time": transport_task.transport_time,
            "transport_energy": transport_task.transport_energy,
        }

        job = simulator.jobs[transport_job_id]
        result = simulator.cancelJob(transport_job_id)
        removed = next(
            operation
            for operation in result["removed_operations"]
            if operation["operation_id"] == transport_task.operation_id
        )

        self.assertEqual(transport_task.status, "canceled")
        self.assertEqual(
            transport_task.source_machine,
            completed_transport["source_machine"],
        )
        self.assertEqual(
            transport_task.transport_start,
            completed_transport["transport_start"],
        )
        self.assertEqual(
            transport_task.transport_end,
            completed_transport["transport_end"],
        )
        self.assertEqual(
            transport_task.transport_time,
            completed_transport["transport_time"],
        )
        self.assertEqual(
            transport_task.transport_energy,
            completed_transport["transport_energy"],
        )
        self.assertTrue(transport_task.transport_completed)
        self.assertTrue(removed["transport_completed"])
        for field, value in completed_transport.items():
            self.assertEqual(removed[field], value)
        self.assertEqual(
            job.transport_energy,
            sum(task.total_transport_energy for task in job.tasks),
        )
        self.assertGreaterEqual(
            job.transport_energy,
            transport_task.transport_energy,
        )
        self.assertFalse(
            any(
                getattr(event, "job_id", None) == transport_job_id
                for event in simulator.event_queue
            )
        )

    def test_cancel_lets_in_progress_transport_finish_and_counts_energy(self):
        simulator = self._create_simulator()
        transport_task = None

        while simulator.event_queue:
            for job in simulator.jobs:
                for task in job.tasks:
                    if (
                        task.status == "scheduled"
                        and task.actual_start is None
                        and not task.transport_completed
                        and task.transport_start is not None
                        and task.transport_end is not None
                        and task.transport_start <= simulator.curr_time
                        and task.transport_end > simulator.curr_time
                    ):
                        transport_task = task
                        break
                if transport_task is not None:
                    break
            if transport_task is not None:
                break
            event = simulator.event_queue.pop(0)
            simulator.curr_time = event.timestamp
            simulator.handleEvent(event)
            simulator.updateEventQueue()

        self.assertIsNotNone(transport_task)
        job = simulator.jobs[transport_task.job_id]
        operation_key = (
            transport_task.job_id,
            transport_task.operation_id,
        )
        simulator.cancelJob(transport_task.job_id)

        self.assertEqual(transport_task.status, "canceled")
        self.assertFalse(transport_task.transport_completed)
        self.assertGreater(transport_task.transport_energy, 0)
        self.assertTrue(
            any(
                isinstance(event, TransportFinishEvent)
                and (event.job_id, event.operation_id) == operation_key
                for event in simulator.event_queue
            )
        )

        while simulator.event_queue:
            event = simulator.event_queue.pop(0)
            simulator.curr_time = event.timestamp
            simulator.handleEvent(event)
            simulator.updateEventQueue()
            if (
                isinstance(event, TransportFinishEvent)
                and (event.job_id, event.operation_id) == operation_key
            ):
                break

        self.assertTrue(transport_task.transport_completed)
        self.assertGreaterEqual(
            job.transport_energy,
            transport_task.transport_energy,
        )

    def test_cancel_triggered_reoptimization_chains_in_progress_transport(self):
        simulator = self._create_simulator()
        transport_task = None

        while simulator.event_queue:
            for job in simulator.jobs:
                for task in job.tasks:
                    if (
                        task.status == "scheduled"
                        and task.actual_start is None
                        and not task.transport_completed
                        and task.transport_start is not None
                        and task.transport_end is not None
                        and task.transport_start <= simulator.curr_time
                        and task.transport_end > simulator.curr_time
                    ):
                        transport_task = task
                        break
                if transport_task is not None:
                    break
            if transport_task is not None:
                break
            event = simulator.event_queue.pop(0)
            simulator.curr_time = event.timestamp
            simulator.handleEvent(event)
            simulator.updateEventQueue()

        self.assertIsNotNone(transport_task)
        old_target = transport_task.assigned_machine
        old_source = transport_task.source_machine
        first_end = transport_task.transport_end
        new_target = next(
            machine_id
            for machine_id in transport_task.eligible_machines
            if machine_id != old_target
        )
        expected_second_time = simulator.transport_time[
            old_target
        ][new_target]
        expected_second_energy = simulator.transport_energy[
            old_target
        ][new_target]
        original_assignments = simulator._greedyUnfinishedAssignments

        def force_transport_task_to_new_machine():
            assignments = original_assignments()
            assignments[
                (transport_task.job_id, transport_task.operation_id)
            ] = new_target
            return assignments

        simulator._greedyUnfinishedAssignments = (
            force_transport_task_to_new_machine
        )
        canceled_job_id = next(
            job.job_id
            for job in simulator.jobs
            if job.job_id != transport_task.job_id
        )
        simulator.cancelJob(canceled_job_id)

        self.assertEqual(transport_task.assigned_machine, new_target)
        self.assertEqual(len(transport_task.transport_segments), 2)
        first_segment, second_segment = transport_task.transport_segments
        self.assertEqual(first_segment["source_machine"], old_source)
        self.assertEqual(first_segment["target_machine"], old_target)
        self.assertEqual(first_segment["transport_end"], first_end)
        self.assertFalse(first_segment["completed"])
        self.assertEqual(second_segment["source_machine"], old_target)
        self.assertEqual(second_segment["target_machine"], new_target)
        self.assertEqual(second_segment["transport_start"], first_end)
        self.assertEqual(
            second_segment["transport_time"],
            expected_second_time,
        )
        self.assertEqual(
            second_segment["transport_energy"],
            expected_second_energy,
        )
        self.assertEqual(
            second_segment["transport_end"],
            first_end + expected_second_time,
        )
        self.assertGreaterEqual(
            transport_task.planned_start,
            second_segment["transport_end"],
        )

    def test_reoptimization_does_not_restore_canceled_job(self):
        simulator = self._create_simulator()
        simulator.cancelJob(0)
        assignments = {
            (job.job_id, task.operation_id): task.assigned_machine
            for job in simulator.jobs
            if not job.is_canceled
            for task in job.tasks
            if task.status in {"pending", "scheduled"}
        }

        result = simulator.reoptimizeUnfinishedOperations(
            assignments,
            current_time=0,
        )

        self.assertGreater(result["unfinished_task_count"], 0)
        self.assertEqual(
            {task.status for task in simulator.jobs[0].tasks},
            {"canceled"},
        )
        self.assertFalse(
            any(
                operation.job_id == 0
                for operation in simulator.planned_operations
            )
        )
        self.assertFalse(
            any(
                getattr(event, "job_id", None) == 0
                for event in simulator.event_queue
            )
        )

    def test_cancel_multiple_jobs_in_one_batch(self):
        simulator = self._create_simulator()

        result = simulator.cancelJobs([0, 1])

        self.assertTrue(result["success"])
        self.assertEqual(result["newly_canceled_job_ids"], [0, 1])
        self.assertEqual(result["already_canceled_job_ids"], [])
        self.assertEqual(result["removed_operation_count"], 20)
        self.assertTrue(result["greedy_reschedule"]["applied"])
        self.assertEqual(
            [order.job_id for order in simulator.canceled_orders],
            [0, 1],
        )
        for job_id in (0, 1):
            self.assertTrue(simulator.jobs[job_id].is_canceled)
            self.assertEqual(
                {task.status for task in simulator.jobs[job_id].tasks},
                {"canceled"},
            )
        self.assertFalse(
            any(
                getattr(event, "job_id", None) in {0, 1}
                for event in simulator.event_queue
            )
        )

    def test_cancel_rebuilds_remaining_schedule_without_queue_gaps(self):
        simulator = self._create_simulator()

        result = simulator.cancelJob(0)

        self.assertTrue(result["greedy_reschedule"]["applied"])
        active_tasks = [
            task
            for job in simulator.jobs
            if not job.is_canceled
            for task in job.tasks
            if task.status in {"pending", "scheduled"}
        ]
        self.assertEqual(
            result["greedy_reschedule"]["unfinished_task_count"],
            len(active_tasks),
        )
        for task in active_tasks:
            expected_machine = min(
                task.eligible_machines,
                key=lambda machine_id: (
                    task.processing_times[machine_id],
                    machine_id,
                ),
            )
            self.assertEqual(task.assigned_machine, expected_machine)

        for machine in simulator.machines:
            previous_end = simulator.curr_time
            for operation in machine.pending_operations:
                task = simulator.jobs[operation.job_id].tasks[
                    operation.operation_id
                ]
                release_time = (
                    max(simulator.curr_time, simulator.jobs[task.job_id].ready_time)
                    if task.operation_id == 0
                    else max(
                        simulator.curr_time,
                        task.transport_end
                        or (
                            simulator.jobs[task.job_id]
                            .tasks[task.operation_id - 1]
                            .planned_end
                            + task.transport_time
                        ),
                    )
                )
                self.assertEqual(
                    operation.start_time,
                    max(release_time, previous_end),
                )
                previous_end = operation.end_time

    def test_batch_cancel_accepts_processing_and_completed_jobs(self):
        simulator = self._create_simulator()
        completed_job = simulator.jobs[2]
        for task in completed_job.tasks:
            task.status = "completed"
            task.actual_end = simulator.curr_time
        completed_job.completion_time = simulator.curr_time
        simulator.finished_queue.append(
            Order(2, completed_job.priority, completed_job.ready_time)
        )

        result = simulator.cancelJobs([0, 2])

        self.assertEqual(result["newly_canceled_job_ids"], [0, 2])
        self.assertEqual(result["removed_operation_count"], 10)
        self.assertTrue(simulator.jobs[0].is_canceled)
        self.assertTrue(completed_job.is_canceled)
        self.assertEqual(
            {task.status for task in completed_job.tasks},
            {"completed"},
        )
        self.assertTrue(
            all(
                task.actual_end is not None
                for task in completed_job.tasks
            )
        )
        self.assertFalse(
            any(order.job_id == 2 for order in simulator.finished_queue)
        )
        self.assertEqual(
            sum(
                operation.job_id == 2
                for operation in simulator.planned_operations
            ),
            completed_job.operation_count,
        )
        self.assertEqual(
            [order.job_id for order in simulator.canceled_orders],
            [0, 2],
        )

    def test_manager_publishes_all_three_job_states(self):
        simulator = self._create_simulator()
        manager = SimulationManager(
            config_path=DEFAULT_CONFIG_PATH,
            speed=50,
            realtime=False,
        )
        manager.simulator = simulator
        manager.state.prepare(50)
        manager.state.set_running(simulator)
        simulator.cancelJob(1)
        for task in simulator.jobs[2].tasks:
            task.status = "completed"
            task.actual_end = simulator.curr_time
        simulator.jobs[2].completion_time = simulator.curr_time

        manager.cancel_job(0)
        snapshot = manager.state.snapshot()
        states = {
            state["job_id"]: state["status"]
            for state in snapshot["job_states"]
        }

        self.assertEqual(states[0], "canceled")
        self.assertEqual(states[1], "canceled")
        self.assertEqual(states[2], "completed")
        self.assertEqual(states[3], "processing")
        self.assertEqual(snapshot["canceled_jobs"], 2)
        self.assertEqual(
            [order["job_id"] for order in snapshot["canceled_orders"]],
            [1, 0],
        )
        self.assertEqual(
            [state["job_id"] for state in snapshot["job_states"]],
            sorted(states),
        )
        self.assertEqual(
            serialize_job_states(simulator),
            snapshot["job_states"],
        )
        self.assertFalse(
            any(
                operation["job_id"] == 0
                for operation in snapshot["plan"]
            )
        )

    def test_job_completed_status_requires_all_operations_completed(self):
        simulator = self._create_simulator()
        job = simulator.jobs[0]
        simulator.finished_queue.append(
            Order(job.job_id, job.priority, job.ready_time)
        )

        processing_state = next(
            state
            for state in serialize_job_states(simulator)
            if state["job_id"] == job.job_id
        )
        self.assertEqual(processing_state["status"], "processing")

        for task in job.tasks:
            task.status = "completed"
        completed_state = next(
            state
            for state in serialize_job_states(simulator)
            if state["job_id"] == job.job_id
        )
        self.assertEqual(completed_state["status"], "completed")

    def test_finish_publishes_current_plan_without_canceled_operations(self):
        simulator = self._create_simulator()
        manager = SimulationManager(
            config_path=DEFAULT_CONFIG_PATH,
            speed=50,
            realtime=False,
        )
        manager.simulator = simulator
        manager.state.prepare(50)
        manager.state.set_running(simulator)

        manager.cancel_jobs([0, 1])
        with tempfile.TemporaryDirectory() as temp_dir:
            simulator.schedule_file = str(
                Path(temp_dir) / "schedule.csv"
            )
            simulator.gantt_file = str(
                Path(temp_dir) / "gantt.txt"
            )
            simulator.run()
        manager.state.finish(simulator)
        snapshot = manager.state.snapshot()

        self.assertEqual(snapshot["status"], "finished")
        self.assertFalse(
            any(
                operation["job_id"] in {0, 1}
                for operation in snapshot["plan"]
            )
        )
        self.assertFalse(
            any(
                operation["start_time"] > snapshot["current_time"]
                for operation in snapshot["plan"]
            )
        )
        self.assertTrue(
            all(
                machine["pending"] == 0
                for machine in snapshot["machine_states"]
            )
        )

    def test_cancel_job_http_endpoint(self):
        calls = []

        class FakeManager:
            state = SimpleNamespace()

            def cancel_job(self, job_id):
                calls.append(job_id)
                return {
                    "success": True,
                    "job_id": job_id,
                    "status": "canceled",
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
                    f"{server.server_address[1]}/api/orders/cancel"
                ),
                data=json.dumps({"order_id": 7}).encode("utf-8"),
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
        self.assertEqual(payload["job_id"], 7)
        self.assertEqual(calls, [7])

    def test_batch_cancel_http_endpoint(self):
        calls = []

        class FakeManager:
            state = SimpleNamespace()

            def cancel_jobs(self, job_ids):
                calls.append(job_ids)
                return {
                    "success": True,
                    "job_ids": job_ids,
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
                    f"{server.server_address[1]}/api/jobs/cancel"
                ),
                data=json.dumps({"job_ids": [2, 4]}).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(request, timeout=5) as response:
                payload = json.loads(response.read().decode("utf-8"))
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)

        self.assertEqual(payload["job_ids"], [2, 4])
        self.assertEqual(calls, [[2, 4]])

    def test_order_batch_cancel_updates_all_jobs_and_order_status(self):
        simulator = self._create_simulator()
        manager = SimulationManager(
            config_path=DEFAULT_CONFIG_PATH,
            speed=50,
            realtime=False,
        )
        manager.simulator = simulator
        manager.state.prepare(50)
        manager.state.set_running(simulator)

        result = manager.cancel_orders(["T+0"])

        self.assertEqual(result["order_ids"], ["T+0"])
        self.assertTrue(
            all(job.is_canceled for job in simulator.jobs)
        )
        self.assertIsNotNone(simulator.order_batches[0].canceled_at)
        order_state = manager.state.snapshot()["order_batches"][0]
        self.assertEqual(order_state["status"], "canceled")
        self.assertEqual(
            order_state["status_counts"]["canceled"],
            len(simulator.jobs),
        )

    def test_order_batch_cancel_http_endpoint(self):
        calls = []

        class FakeManager:
            state = SimpleNamespace()

            def cancel_orders(self, order_ids, job_ids=None):
                calls.append((order_ids, job_ids))
                return {
                    "success": True,
                    "order_ids": order_ids,
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
                    f"{server.server_address[1]}/api/orders/cancel"
                ),
                data=json.dumps({
                    "order_ids": ["T+20", "T+40"],
                    "job_ids": [15, 16],
                }).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(request, timeout=5) as response:
                payload = json.loads(response.read().decode("utf-8"))
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)

        self.assertEqual(
            payload["order_ids"],
            ["T+20", "T+40"],
        )
        self.assertEqual(
            calls,
            [(["T+20", "T+40"], [15, 16])],
        )


if __name__ == "__main__":
    unittest.main()

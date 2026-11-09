import tempfile
import unittest
from pathlib import Path

from simulator.event import (
    JobFinishEvent,
    OperationFinishEvent,
    OperationStartEvent,
    TransportFinishEvent,
)
from simulator.simulator import Simulator


class OperationSchedulingTest(unittest.TestCase):
    def test_initial_schedule_consumes_job_queue(self):
        simulator = Simulator(realtime=False)
        simulator.log_tag = False
        observed = {}
        original_generate_plan = simulator.generatePlan

        def inspect_queues_then_generate():
            observed["job_queue"] = [
                (order.job_id, order.priority, order.submit_time)
                for order in simulator.job_queue
            ]
            observed["processing_queue"] = list(
                simulator.processing_queue
            )
            original_generate_plan()

        simulator.generatePlan = inspect_queues_then_generate
        simulator.init()

        self.assertEqual(
            observed["job_queue"],
            [
                (job.job_id, job.priority, job.ready_time)
                for job in simulator.jobs
            ],
        )
        self.assertEqual(observed["processing_queue"], [])
        self.assertEqual(simulator.job_queue, [])
        self.assertEqual(
            [order.job_id for order in simulator.processing_queue],
            [job.job_id for job in simulator.jobs],
        )
        self.assertEqual(simulator.finished_queue, [])
        self.assertTrue(
            all(
                task.status == "scheduled"
                for job in simulator.jobs
                for task in job.tasks
            )
        )

    def test_initialization_builds_complete_machine_queues(self):
        simulator = self._create_simulator()
        expected_count = sum(job.operation_count for job in simulator.jobs)

        self.assertEqual(len(simulator.planned_operations), expected_count)
        self.assertEqual(
            sum(len(machine.pending_operations) for machine in simulator.machines),
            expected_count,
        )
        self.assertGreater(len(simulator.event_queue), 0)
        self.assertTrue(
            all(
                isinstance(
                    event,
                    (OperationStartEvent, TransportFinishEvent),
                )
                for event in simulator.event_queue
            )
        )

        for machine in simulator.machines:
            queue = machine.pending_operations
            self.assertEqual(
                queue,
                sorted(queue, key=lambda operation: operation.start_time),
            )
            for previous, current in zip(queue, queue[1:]):
                self.assertGreaterEqual(
                    current.start_time,
                    previous.end_time,
                )

    def test_successor_priority_uses_transport_release_time(self):
        simulator = self._create_simulator()

        job9_first = simulator.jobs[9].tasks[0]
        job7_second = simulator.jobs[7].tasks[1]

        self.assertEqual(
            job9_first.planned_start,
            simulator.jobs[9].ready_time,
        )
        self.assertGreaterEqual(
            job7_second.planned_start,
            simulator.jobs[7].tasks[0].planned_end
            + simulator.transport_time[
                simulator.jobs[7].tasks[0].assigned_machine
            ][job7_second.assigned_machine],
        )

    def test_machine_queues_run_all_operations_once(self):
        simulator = self._create_simulator()
        processed_event_types = set()
        original_handle_event = simulator.handleEvent

        def collect_event_types(event):
            processed_event_types.add(type(event).__name__)
            original_handle_event(event)

        simulator.handleEvent = collect_event_types
        expected_operations = {
            (job.job_id, operation_id)
            for job in simulator.jobs
            for operation_id in range(job.operation_count)
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            simulator.schedule_file = str(Path(temp_dir) / "schedule.csv")
            simulator.gantt_file = str(Path(temp_dir) / "gantt.txt")
            simulator.run()

        scheduled_operations = []
        operation_times = {}
        for machine_id, items in enumerate(simulator.schedule.schedule_items):
            starts = simulator.schedule.start_time[machine_id]
            ends = simulator.schedule.end_time[machine_id]
            for item, start_time, end_time in zip(items, starts, ends):
                scheduled_operations.append(item)
                operation_times[item] = (start_time, end_time)
                self.assertLess(start_time, end_time)
            for index in range(1, len(items)):
                self.assertGreaterEqual(
                    starts[index],
                    ends[index - 1],
                )

        for job in simulator.jobs:
            first_task = job.tasks[0]
            self.assertGreaterEqual(
                first_task.planned_start,
                job.ready_time,
            )
            self.assertIsNone(first_task.transport_start)
            self.assertEqual(
                first_task.waiting_time,
                first_task.planned_start - job.ready_time,
            )
            for operation_id in range(1, job.operation_count):
                previous_end = operation_times[(job.job_id, operation_id - 1)][1]
                current_start = operation_times[(job.job_id, operation_id)][0]
                self.assertGreaterEqual(current_start, previous_end)
                previous_task = job.tasks[operation_id - 1]
                current_task = job.tasks[operation_id]
                expected_transport = simulator.transport_time[
                    previous_task.assigned_machine
                ][current_task.assigned_machine]
                self.assertEqual(
                    current_task.transport_time,
                    expected_transport,
                )
                self.assertEqual(
                    current_task.transport_start,
                    previous_task.planned_end,
                )
                self.assertEqual(
                    current_task.transport_end,
                    current_task.transport_start
                    + current_task.transport_time,
                )
                self.assertGreaterEqual(
                    current_task.planned_start,
                    current_task.transport_end,
                )
                self.assertEqual(
                    current_task.waiting_time,
                    current_task.planned_start
                    - current_task.transport_end,
                )

        self.assertEqual(len(scheduled_operations), len(expected_operations))
        self.assertEqual(set(scheduled_operations), expected_operations)
        self.assertEqual(len(simulator.finished_queue), len(simulator.jobs))
        self.assertNotIn("OperationScheduleEvent", processed_event_types)
        self.assertEqual(
            sum(
                1
                for job in simulator.jobs
                for task in job.tasks
                if task.status == "completed"
            ),
            len(expected_operations),
        )
        self.assertEqual(simulator.objectives["makespan"], simulator.makespan)
        self.assertEqual(
            simulator.transport_adjusted_makespan,
            max(
                task.actual_end
                for job in simulator.jobs
                for task in job.tasks
            ),
        )
        self.assertEqual(
            simulator.makespan,
            simulator.transport_adjusted_makespan,
        )
        self.assertGreater(simulator.objectives["energy"], 0)
        self.assertGreaterEqual(simulator.objectives["penalty"], 0)
        recomputed_processing_energy = sum(
            job.operation_energy[
                task.operation_id
            ][task.assigned_machine]
            for job in simulator.jobs
            for task in job.tasks
        )
        recomputed_transport_energy = sum(
            simulator.transport_energy[
                previous.assigned_machine
            ][current.assigned_machine]
            for job in simulator.jobs
            for previous, current in zip(job.tasks, job.tasks[1:])
        )
        recomputed_energy = (
            recomputed_processing_energy
            + recomputed_transport_energy
            + simulator.auxiliary_energy * simulator.makespan
        )
        recomputed_penalty = sum(
            job.weight * (
                job.earliness_penalty * max(
                    job.due_time - job.completion_time,
                    0,
                )
                + job.tardiness_penalty * max(
                    job.completion_time - job.due_time,
                    0,
                )
            )
            for job in simulator.jobs
        )
        self.assertEqual(simulator.total_processing_energy, recomputed_processing_energy)
        self.assertEqual(simulator.total_transport_energy, recomputed_transport_energy)
        self.assertEqual(simulator.total_energy, recomputed_energy)
        self.assertEqual(simulator.total_penalty, recomputed_penalty)
        self.assertEqual(
            sum(len(machine.pending_operations) for machine in simulator.machines),
            0,
        )

    def test_replanning_rebuilds_complete_queues(self):
        simulator = self._create_simulator()
        simulator.curr_time = 100

        simulator.replanRemainingOperations()

        self.assertEqual(
            sum(
                len(machine.pending_operations)
                for machine in simulator.machines
            ),
            sum(job.operation_count for job in simulator.jobs),
        )
        start_events = [
            event
            for event in simulator.event_queue
            if isinstance(event, OperationStartEvent)
        ]
        self.assertEqual(
            len(start_events),
            sum(
                bool(machine.pending_operations)
                for machine in simulator.machines
            ),
        )

    def test_external_reassignment_preserves_processing_and_replans_rest(self):
        simulator = self._create_simulator()
        simulator.updateEventQueue()
        while simulator.event_queue and simulator.curr_time < 50:
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
        assignments = {}
        for job in simulator.jobs:
            for task in job.tasks:
                if task.status in {"pending", "scheduled"}:
                    assignments[(job.job_id, task.operation_id)] = (
                        task.eligible_machines[-1]
                    )

        result = simulator.reoptimizeUnfinishedOperations(
            assignments,
            current_time=simulator.curr_time,
        )

        processing_after = {
            (job.job_id, task.operation_id): task.assigned_machine
            for job in simulator.jobs
            for task in job.tasks
            if task.status == "processing"
        }
        self.assertEqual(processing_before, processing_after)
        self.assertEqual(
            result["unfinished_task_count"],
            len(assignments),
        )
        for job in simulator.jobs:
            for task in job.tasks:
                if (job.job_id, task.operation_id) in assignments:
                    self.assertEqual(
                        task.assigned_machine,
                        assignments[(job.job_id, task.operation_id)],
                    )
                    if (
                        task.transport_start is not None
                        and task.transport_start < simulator.curr_time
                    ):
                        self.assertTrue(task.transport_completed)
        self.assertGreaterEqual(result["transport_time_added"], 0)
        self.assertGreaterEqual(result["transport_energy_added"], 0)
        pending_keys = {
            (operation.job_id, operation.operation_id)
            for machine in simulator.machines
            for operation in machine.pending_operations
        }
        self.assertEqual(
            pending_keys,
            {
                key
                for key, task in (
                    ((job.job_id, task.operation_id), task)
                    for job in simulator.jobs
                    for task in job.tasks
                )
                if task.status == "scheduled"
            },
        )
        self.assertTrue(
            pending_keys.isdisjoint(processing_before.keys())
        )
        start_events = [
            event
            for event in simulator.event_queue
            if isinstance(event, OperationStartEvent)
        ]
        self.assertEqual(
            len(start_events),
            len({
                (event.job_id, event.operation_id)
                for event in start_events
            }),
        )
        event_timestamps = [
            event.timestamp for event in simulator.event_queue
        ]
        self.assertEqual(event_timestamps, sorted(event_timestamps))

    def test_reoptimization_preserves_completed_transport_to_same_machine(self):
        simulator = self._create_simulator()
        self._advance_until(simulator, 13)
        job_id, operation_id = 2, 2
        task = simulator.jobs[job_id].tasks[operation_id]
        self.assertEqual(task.status, "scheduled")
        self.assertTrue(task.transport_completed)
        self.assertGreater(task.transport_energy, 0)
        old_assigned_machine = task.assigned_machine
        old_transport = (
            task.source_machine,
            task.transport_start,
            task.transport_end,
            task.transport_time,
            task.transport_energy,
        )
        assignments = {
            (job.job_id, item.operation_id): item.eligible_machines[-1]
            for job in simulator.jobs
            for item in job.tasks
            if item.status in {"pending", "scheduled"}
        }
        assignments[(job_id, operation_id)] = old_assigned_machine

        simulator.reoptimizeUnfinishedOperations(
            assignments,
            current_time=simulator.curr_time,
        )

        self.assertEqual(task.assigned_machine, old_assigned_machine)
        self.assertTrue(task.transport_completed)
        self.assertEqual(
            (
                task.source_machine,
                task.transport_start,
                task.transport_end,
                task.transport_time,
                task.transport_energy,
            ),
            old_transport,
        )
        self.assertEqual(
            task.current_location_machine,
            old_assigned_machine,
        )
        self.assertFalse(
            any(
                isinstance(event, TransportFinishEvent)
                and (event.job_id, event.operation_id)
                == (job_id, operation_id)
                for event in simulator.event_queue
            )
        )

    def test_reassigned_predecessor_invalidates_completed_transport_state(self):
        simulator = self._create_simulator()
        predecessor = simulator.jobs[13].tasks[8]
        successor = simulator.jobs[13].tasks[9]
        assignments = {
            (job.job_id, task.operation_id): task.assigned_machine
            for job in simulator.jobs
            for task in job.tasks
        }
        assignments[(13, 8)] = 1
        assignments[(13, 9)] = 0

        simulator.reoptimizeUnfinishedOperations(
            assignments,
            current_time=simulator.curr_time,
        )

        self.assertEqual(predecessor.status, "scheduled")
        self.assertEqual(successor.source_machine, 1)
        self.assertEqual(
            successor.transport_time,
            simulator.transport_time[1][0],
        )
        self.assertFalse(successor.transport_completed)
        self.assertEqual(
            successor.current_location_machine,
            predecessor.assigned_machine,
        )
        self.assertGreaterEqual(
            successor.planned_start,
            predecessor.planned_end,
        )

    def test_reoptimization_reroutes_from_current_machine_and_keeps_energy(self):
        simulator = self._create_simulator()
        self._advance_until(simulator, 13)
        job_id, operation_id = 2, 2
        task = simulator.jobs[job_id].tasks[operation_id]
        old_machine = task.assigned_machine
        old_transport_energy = task.transport_energy
        new_machine = next(
            machine_id
            for machine_id in task.eligible_machines
            if machine_id != old_machine
        )
        expected_transport_time = simulator.transport_time[
            old_machine
        ][new_machine]
        expected_new_energy = simulator.transport_energy[
            old_machine
        ][new_machine]
        assignments = {
            (job.job_id, item.operation_id): item.eligible_machines[-1]
            for job in simulator.jobs
            for item in job.tasks
            if item.status in {"pending", "scheduled"}
        }
        assignments[(job_id, operation_id)] = new_machine

        simulator.reoptimizeUnfinishedOperations(
            assignments,
            current_time=simulator.curr_time,
        )

        self.assertEqual(task.assigned_machine, new_machine)
        self.assertEqual(task.source_machine, old_machine)
        self.assertEqual(
            task.committed_transport_energy,
            old_transport_energy,
        )
        self.assertEqual(
            task.transport_start,
            simulator.curr_time,
        )
        self.assertEqual(
            task.transport_time,
            expected_transport_time,
        )
        self.assertEqual(
            task.transport_energy,
            expected_new_energy,
        )
        self.assertEqual(
            task.transport_end,
            simulator.curr_time + expected_transport_time,
        )
        self.assertEqual(
            task.current_location_machine,
            old_machine,
        )
        self.assertFalse(task.transport_completed)
        planned = next(
            operation
            for operation in simulator.planned_operations
            if (operation.job_id, operation.operation_id)
            == (job_id, operation_id)
        )
        self.assertEqual(planned.machine_id, new_machine)
        self.assertEqual(planned.source_machine, old_machine)
        self.assertEqual(planned.transport_start, simulator.curr_time)
        self.assertEqual(
            planned.transport_end,
            simulator.curr_time + expected_transport_time,
        )

        self._run_to_completion(simulator)
        expected_total_transport_energy = sum(
            item.total_transport_energy
            for job in simulator.jobs
            for item in job.tasks
        )
        self.assertEqual(
            simulator.total_transport_energy,
            expected_total_transport_energy,
        )
        self.assertEqual(
            task.total_transport_energy,
            old_transport_energy + expected_new_energy,
        )
        self.assertEqual(task.current_location_machine, new_machine)

    def test_reoptimization_restores_processing_before_downstream_work(self):
        simulator = self._create_simulator()
        self._advance_until(simulator, 20)
        processing_before = {
            (job.job_id, task.operation_id): {
                "machine_id": task.assigned_machine,
                "actual_start": task.actual_start,
                "expected_end": (
                    task.actual_start
                    + task.processing_times[task.assigned_machine]
                ),
            }
            for job in simulator.jobs
            for task in job.tasks
            if task.status == "processing"
        }
        self.assertTrue(processing_before)

        old_transport_event_ids = {
            event.id
            for event in simulator.event_queue
            if isinstance(event, TransportFinishEvent)
        }
        assignments = {
            (job.job_id, task.operation_id): task.eligible_machines[-1]
            for job in simulator.jobs
            for task in job.tasks
            if task.status in {"pending", "scheduled"}
        }

        simulator.reoptimizeUnfinishedOperations(
            assignments,
            current_time=simulator.curr_time,
        )

        current_transport_event_ids = {
            event.id
            for event in simulator.event_queue
            if isinstance(event, TransportFinishEvent)
        }
        self.assertTrue(
            current_transport_event_ids.isdisjoint(old_transport_event_ids)
        )

        processing_finish_events = {}
        for event in simulator.event_queue:
            if (
                isinstance(event, OperationFinishEvent)
                and (event.job_id, event.operation_id)
                in processing_before
            ):
                processing_finish_events[
                    (event.job_id, event.operation_id)
                ] = event
        self.assertEqual(
            set(processing_finish_events),
            set(processing_before),
        )

        planned_keys = {
            (operation.job_id, operation.operation_id)
            for operation in simulator.planned_operations
        }
        for key, before in processing_before.items():
            job_id, operation_id = key
            task = simulator.jobs[job_id].tasks[operation_id]
            self.assertIn(key, planned_keys)
            self.assertEqual(task.status, "processing")
            self.assertEqual(task.assigned_machine, before["machine_id"])
            self.assertEqual(task.actual_start, before["actual_start"])
            finish_event = processing_finish_events[key]
            self.assertEqual(
                finish_event.machine_id,
                before["machine_id"],
            )
            self.assertEqual(
                finish_event.timestamp,
                before["expected_end"],
            )

            first_queued = simulator.machines[
                before["machine_id"]
            ].nextPendingOperation()
            if first_queued is not None:
                self.assertGreaterEqual(
                    first_queued.start_time,
                    before["expected_end"],
                )

            if operation_id + 1 >= simulator.jobs[job_id].operation_count:
                continue
            successor = simulator.jobs[job_id].tasks[
                operation_id + 1
            ]
            self.assertGreaterEqual(
                successor.planned_start,
                before["expected_end"]
                + simulator.transport_time[
                    before["machine_id"]
                ][successor.assigned_machine],
            )

        handled_events = []
        original_handle_event = simulator.handleEvent

        def record_event(event):
            handled_events.append(event)
            original_handle_event(event)

        simulator.handleEvent = record_event
        with tempfile.TemporaryDirectory() as temp_dir:
            simulator.schedule_file = str(Path(temp_dir) / "schedule.csv")
            simulator.gantt_file = str(Path(temp_dir) / "gantt.txt")
            simulator.run()

        event_positions = {
            (
                type(event).__name__,
                getattr(event, "job_id", None),
                getattr(event, "operation_id", None),
            ): index
            for index, event in enumerate(handled_events)
        }
        for job_id, operation_id in processing_before:
            if operation_id + 1 >= simulator.jobs[job_id].operation_count:
                continue
            finish_position = event_positions[
                ("OperationFinishEvent", job_id, operation_id)
            ]
            successor_start_position = event_positions[
                ("OperationStartEvent", job_id, operation_id + 1)
            ]
            self.assertLess(finish_position, successor_start_position)

        self.assertEqual(
            len(simulator.finished_queue),
            len(simulator.jobs),
        )
        self.assertEqual(simulator.curr_time, simulator.makespan)
        self.assertFalse(simulator.event_queue)

    def test_stale_transport_event_does_not_extend_simulation_clock(self):
        simulator = self._create_simulator()
        self._advance_until(simulator, 20)
        completed_task = next(
            task
            for job in simulator.jobs
            for task in job.tasks
            if task.status == "completed"
        )
        stale_event = TransportFinishEvent(
            simulator.newEventId(),
            10_000,
            completed_task.job_id,
            completed_task.operation_id,
            completed_task.assigned_machine,
        )
        simulator.addEvent(stale_event)
        handled_event_ids = set()
        original_handle_event = simulator.handleEvent

        def record_event(event):
            handled_event_ids.add(event.id)
            original_handle_event(event)

        simulator.handleEvent = record_event
        with tempfile.TemporaryDirectory() as temp_dir:
            simulator.schedule_file = str(Path(temp_dir) / "schedule.csv")
            simulator.gantt_file = str(Path(temp_dir) / "gantt.txt")
            simulator.run()

        self.assertNotIn(stale_event.id, handled_event_ids)
        self.assertEqual(simulator.curr_time, simulator.makespan)
        self.assertFalse(simulator.event_queue)

    def test_objectives_update_immediately_during_execution(self):
        simulator = self._create_simulator()
        simulator.updateEventQueue()
        saw_transport_energy = False
        saw_processing_energy = False
        saw_delivery_penalty = False

        while simulator.event_queue:
            event = simulator.event_queue.pop(0)
            simulator.curr_time = event.timestamp
            simulator.handleEvent(event)
            simulator.updateEventQueue()

            if isinstance(event, TransportFinishEvent):
                task = simulator.jobs[event.job_id].tasks[
                    event.operation_id
                ]
                if task.transport_energy > 0:
                    self.assertTrue(task.transport_completed)
                    self.assertGreaterEqual(
                        simulator.total_transport_energy,
                        task.transport_energy,
                    )
                    saw_transport_energy = True

            if simulator.total_processing_energy > 0:
                saw_processing_energy = True

            if isinstance(event, JobFinishEvent):
                completed_jobs = {
                    job.job_id
                    for job in simulator.jobs
                    if all(
                        task.status == "completed"
                        for task in job.tasks
                    )
                }
                expected_penalty = sum(
                    simulator.jobs[job_id].delivery_penalty
                    for job_id in completed_jobs
                )
                self.assertEqual(
                    simulator.total_penalty,
                    expected_penalty,
                )
                saw_delivery_penalty = True

        self.assertTrue(saw_transport_energy)
        self.assertTrue(saw_processing_energy)
        self.assertTrue(saw_delivery_penalty)

    @staticmethod
    def _create_simulator():
        simulator = Simulator(realtime=False)
        simulator.log_tag = False
        simulator.init()
        return simulator

    @staticmethod
    def _advance_until(simulator, timestamp):
        simulator.updateEventQueue()
        while (
            simulator.event_queue
            and simulator.event_queue[0].timestamp <= timestamp
        ):
            event = simulator.event_queue.pop(0)
            simulator.curr_time = event.timestamp
            simulator.handleEvent(event)
            simulator.updateEventQueue()

    @staticmethod
    def _run_to_completion(simulator):
        with tempfile.TemporaryDirectory() as temp_dir:
            simulator.schedule_file = str(Path(temp_dir) / "schedule.csv")
            simulator.gantt_file = str(Path(temp_dir) / "gantt.txt")
            simulator.run()


if __name__ == "__main__":
    unittest.main()

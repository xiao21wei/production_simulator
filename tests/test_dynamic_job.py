import tempfile
import unittest
from pathlib import Path

from simulator.config import DEFAULT_CONFIG_PATH
from simulator.job_generator import generate_random_job
from simulator.simulator import Simulator
from web_app import SimulationManager


class DynamicJobTest(unittest.TestCase):
    def test_random_job_uses_create_instance_ranges(self):
        simulator = self._create_simulator()
        job = generate_random_job(
            simulator.jobs,
            len(simulator.machines),
            current_time=50,
            seed=7,
        )

        self.assertEqual(job.job_id, len(simulator.jobs))
        self.assertEqual(job.operation_count, 10)
        self.assertTrue(1 <= job.weight <= 5)
        self.assertTrue(50 <= job.ready_time <= 70)
        self.assertGreaterEqual(job.due_time, job.ready_time)
        self.assertTrue(1 <= job.earliness_cost <= 10)
        self.assertTrue(1 <= job.tardiness_cost <= 10)
        self.assertEqual(
            len(job.tasks),
            job.operation_count,
        )
        for task in job.tasks:
            self.assertTrue(task.eligible_machines)
            for machine_id in task.eligible_machines:
                self.assertTrue(
                    1
                    <= task.processing_times[machine_id]
                    <= 19
                )
                self.assertTrue(
                    4
                    <= task.processing_energies[machine_id]
                    <= 15
                )

        machine_count = len(simulator.machines)
        self.assertEqual(len(job.transport_time_matrix), machine_count)
        self.assertEqual(len(job.transport_energy_matrix), machine_count)
        for source in range(machine_count):
            self.assertEqual(job.transport_time_matrix[source][source], 0)
            self.assertEqual(job.transport_energy_matrix[source][source], 0)
            for target in range(source + 1, machine_count):
                self.assertEqual(
                    job.transport_time_matrix[source][target],
                    job.transport_time_matrix[target][source],
                )
                self.assertEqual(
                    job.transport_energy_matrix[source][target],
                    job.transport_energy_matrix[target][source],
                )
                self.assertTrue(
                    1 <= job.transport_time_matrix[source][target] <= 3
                )
                self.assertTrue(
                    1 <= job.transport_energy_matrix[source][target] <= 4
                )

    def test_submit_job_replans_queued_and_pending_operations(self):
        simulator = self._create_simulator()
        simulator.updateEventQueue()
        self._advance_to(simulator, 20)
        processing_before = {
            (job.job_id, task.operation_id): (
                task.assigned_machine,
                task.actual_start,
            )
            for job in simulator.jobs
            for task in job.tasks
            if task.status == "processing"
        }
        manager = SimulationManager(
            config_path=DEFAULT_CONFIG_PATH,
            speed=2,
            realtime=False,
        )
        manager.simulator = simulator
        manager.selected_source = manager.datasets_by_id[
            manager.default_dataset_id
        ]
        manager.state.prepare(2)
        manager.state.selected_dataset = {
            "id": manager.default_dataset_id,
        }
        manager.state.set_running(simulator)
        lifecycle = []
        simulator.pause = lambda: lifecycle.append("pause")
        simulator.resume = lambda: lifecycle.append("resume")

        original_reoptimize = simulator.reoptimizeUnfinishedOperations
        observed = {}

        def inspect_and_reoptimize(assignments, current_time=None):
            observed["queued_job_ids"] = [
                order.job_id for order in simulator.job_queue
            ]
            observed["processing_count"] = len(
                simulator.processing_queue
            )
            return original_reoptimize(
                assignments,
                current_time=current_time,
            )

        simulator.reoptimizeUnfinishedOperations = inspect_and_reoptimize
        result = manager.submit_random_jobs(seed=7)

        new_jobs = result["new_jobs"]
        self.assertEqual(result["initial_job_count"], 15)
        self.assertEqual(result["submitted_job_count"], 7)
        self.assertEqual(len(new_jobs), 7)
        self.assertEqual(
            observed["queued_job_ids"],
            [job["job_id"] for job in new_jobs],
        )
        self.assertEqual(
            observed["processing_count"],
            result["initial_job_count"],
        )
        self.assertFalse(simulator.job_queue)
        self.assertEqual(
            {order.job_id for order in simulator.processing_queue},
            {job.job_id for job in simulator.jobs},
        )
        processing_after = {
            (job.job_id, task.operation_id): (
                task.assigned_machine,
                task.actual_start,
            )
            for job in simulator.jobs
            for task in job.tasks
            if task.status == "processing"
        }
        self.assertEqual(processing_after, processing_before)
        self.assertEqual(lifecycle, ["pause", "resume"])
        self.assertGreater(
            result["unfinished_task_count"],
            sum(job["operation_count"] for job in new_jobs),
        )
        self.assertEqual(
            manager.state.total_jobs,
            len(simulator.jobs),
        )

        for job_data in new_jobs:
            new_job = simulator.jobs[job_data["job_id"]]
            for operation_id, task in enumerate(new_job.tasks):
                self.assertIn(
                    task.status,
                    {"scheduled", "processing", "completed"},
                )
                self.assertIsNotNone(task.assigned_machine)
                if operation_id > 0:
                    predecessor = new_job.tasks[operation_id - 1]
                    self.assertEqual(
                        task.transport_time,
                        new_job.transport_time_matrix[
                            predecessor.assigned_machine
                        ][task.assigned_machine],
                    )
                    self.assertEqual(
                        task.transport_energy,
                        new_job.transport_energy_matrix[
                            predecessor.assigned_machine
                        ][task.assigned_machine],
                    )

        with tempfile.TemporaryDirectory() as temp_dir:
            simulator.schedule_file = str(
                Path(temp_dir) / "schedule.csv"
            )
            simulator.gantt_file = str(Path(temp_dir) / "gantt.txt")
            simulator.run()

        self.assertEqual(
            len(simulator.finished_queue),
            len(simulator.jobs),
        )
        self.assertEqual(simulator.curr_time, simulator.makespan)
        self.assertFalse(simulator.event_queue)

    def test_auto_submit_repeats_until_disabled(self):
        simulator = self._create_simulator()
        simulator.updateEventQueue()
        manager = SimulationManager(
            config_path=DEFAULT_CONFIG_PATH,
            speed=50,
            realtime=False,
        )
        manager.simulator = simulator
        manager.selected_source = manager.datasets_by_id[
            manager.default_dataset_id
        ]
        manager.state.prepare(50)
        manager.state.selected_dataset = {
            "id": manager.default_dataset_id,
        }
        manager.state.set_running(simulator)
        manager.set_auto_job_submission(True)

        for _ in range(3000):
            if manager.auto_job_submission_count >= 2:
                break
            if not simulator.event_queue:
                break
            event = simulator.event_queue.pop(0)
            simulator.curr_time = event.timestamp
            simulator.handleEvent(event)
            simulator.updateEventQueue()
            manager._maybe_auto_submit_jobs()

        self.assertEqual(
            manager.state.auto_job_submission_threshold,
            5,
        )
        self.assertEqual(manager.auto_job_submission_count, 2)
        self.assertEqual(
            manager.state.auto_job_submission_count,
            2,
        )
        self.assertEqual(len(simulator.jobs), 29)
        self.assertEqual(manager.state.total_jobs, 29)

        manager.set_auto_job_submission(False)
        for _ in range(3000):
            remaining = len(simulator.jobs) - len(
                simulator.finished_queue
            )
            if remaining <= 5 or not simulator.event_queue:
                break
            event = simulator.event_queue.pop(0)
            simulator.curr_time = event.timestamp
            simulator.handleEvent(event)
            simulator.updateEventQueue()
            manager._maybe_auto_submit_jobs()

        self.assertEqual(len(simulator.jobs), 29)
        self.assertEqual(
            manager.auto_job_submission_count,
            2,
        )

    @staticmethod
    def _create_simulator():
        simulator = Simulator(realtime=False)
        simulator.log_tag = False
        simulator.init()
        return simulator

    @staticmethod
    def _advance_to(simulator, timestamp):
        simulator.updateEventQueue()
        while (
            simulator.event_queue
            and simulator.event_queue[0].timestamp <= timestamp
        ):
            event = simulator.event_queue.pop(0)
            simulator.curr_time = event.timestamp
            simulator.handleEvent(event)
            simulator.updateEventQueue()


if __name__ == "__main__":
    unittest.main()

import json
import unittest
from pathlib import Path

from simulator.config import DEFAULT_CONFIG_PATH, load_simulator_config
from simulator.dataset import list_dataset_sources
from simulator.event import (
    JobFinishEvent,
    ProcessStageBatchScheduleEvent,
    ProcessStageFinishEvent,
    TransportFinishEvent,
)
from simulator.simulator import Simulator
from web_app import SimulationManager


class ProcessChainSimulatorTest(unittest.TestCase):
    def setUp(self):
        config = load_simulator_config(DEFAULT_CONFIG_PATH)
        sources = list_dataset_sources(
            config["paths"]["dataset_root"],
            config["paths"]["input_file"],
        )
        self.source = next(
            source for source in sources if source["is_default"]
        )
        self.simulator = Simulator(realtime=False)
        self.simulator.log_tag = False
        self.simulator.init(
            file_path=self.source["raw_file"],
            additional_file_path=self.source["additional_file"],
            process_sources=self.source["processes"],
            process_chain=True,
        )

    def _advance_to_first_stage_finish(self, job_id=0):
        while self.simulator.event_queue:
            event = self.simulator.event_queue.pop(0)
            self.simulator.curr_time = event.timestamp
            self.simulator.handleEvent(event)
            self.simulator.updateEventQueue()
            if (
                isinstance(event, ProcessStageFinishEvent)
                and event.job_id == job_id
            ):
                return event
        self.fail("No process-stage finish event was generated.")

    def _advance_to_stage_batch(self, stage_id=2, job_id=None):
        while self.simulator.event_queue:
            event = self.simulator.event_queue.pop(0)
            self.simulator.curr_time = event.timestamp
            self.simulator.handleEvent(event)
            self.simulator.updateEventQueue()
            if (
                isinstance(event, ProcessStageBatchScheduleEvent)
                and event.stage_id == stage_id
                and (
                    job_id is None
                    or job_id in event.job_ids
                )
            ):
                return event
        self.fail("No process-stage batch schedule event was generated.")

    def _advance_to_first_stage_release(self, job_id=0):
        self._advance_to_first_stage_finish(job_id)
        return self._advance_to_stage_batch(2, job_id)

    def test_four_processes_are_loaded_into_one_job_route(self):
        self.assertEqual(
            [item["name"] for item in self.source["processes"]],
            ["冲压", "焊装", "涂装", "总装"],
        )
        self.assertEqual(len(self.simulator.process_datasets), 4)
        machine_counts = [
            dataset.num_machines
            for _, dataset in sorted(self.simulator.process_datasets.items())
        ]
        self.assertEqual(machine_counts, [8, 6, 5, 7])
        self.assertEqual(len(self.simulator.machines), sum(machine_counts))
        self.assertEqual(
            [
                item["machine_count"]
                for item in self.simulator.process_definitions
            ],
            machine_counts,
        )
        self.assertEqual(
            [
                item["detection_start_t"]
                for item in self.simulator.process_definitions
            ],
            [0, 1800, 3600, 5400],
        )
        job = self.simulator.jobs[0]
        stage_operation_counts = {
            stage_id: sum(
                task.stage_id == stage_id
                for task in job.tasks
            )
            for stage_id in range(1, 5)
        }
        self.assertEqual(
            stage_operation_counts,
            {1: 10, 2: 6, 3: 6, 4: 8},
        )
        self.assertEqual(job.operation_count, sum(stage_operation_counts.values()))
        self.assertEqual(
            sorted({task.stage_id for task in job.tasks}),
            [1, 2, 3, 4],
        )
        self.assertEqual(
            {
                task.stage_id
                for task in job.tasks
                if task.status != "blocked"
            },
            {1},
        )
        stage_starts = {
            task.stage_id: task
            for task in job.tasks
            if task.stage_operation_id == 0
        }
        self.assertEqual(sorted(stage_starts), [1, 2, 3, 4])
        self.assertEqual(
            {
                operation.stage_id
                for operation in self.simulator.planned_operations
            },
            {1},
        )

    def test_material_inventory_and_consumption_are_loaded(self):
        for process in self.source["processes"]:
            process_id = process["id"]
            inventory = json.loads(
                Path(process["material_inventory_file"]).read_text(
                    encoding="utf-8"
                )
            )
            consumption = json.loads(
                Path(process["material_consumption_file"]).read_text(
                    encoding="utf-8"
                )
            )
            for machine_record in inventory["machines"]:
                global_machine_id = (
                    process["machine_offset"]
                    + machine_record["machine_id"]
                    - 1
                )
                expected_materials = {
                    item["material_id"]: item["quantity"]
                    for item in machine_record["materials"]
                }
                self.assertEqual(
                    self.simulator.machines[global_machine_id].materials,
                    expected_materials,
                )

            for job_record in consumption["jobs"]:
                job = self.simulator.jobs[job_record["job_id"]]
                loaded = job.material_consumption[process_id]
                if process_id == 1:
                    expected_job_materials = {
                        item["material_id"]: item["quantity"]
                        for item in job_record["materials"]
                    }
                    self.assertEqual(
                        loaded["job_materials"],
                        expected_job_materials,
                    )
                    self.assertEqual(loaded["tasks"], {})
                    continue
                for task_record in job_record["tasks"]:
                    expected_task_materials = {
                        item["material_id"]: item["quantity"]
                        for item in task_record["materials"]
                    }
                    task = next(
                        task
                        for task in job.tasks
                        if (
                            task.stage_id == process_id
                            and task.stage_operation_id
                            == task_record["stage_operation_id"]
                        )
                    )
                    self.assertEqual(
                        task.material_consumption,
                        expected_task_materials,
                    )
                    self.assertEqual(
                        loaded["tasks"][
                            task_record["stage_operation_id"]
                        ],
                        expected_task_materials,
                    )

    def test_stage_finish_releases_next_process_lazily(self):
        job = self.simulator.jobs[0]
        stage_finish_event = self._advance_to_first_stage_finish(
            job.job_id
        )
        self.assertEqual(stage_finish_event.from_stage, 1)
        self.assertEqual(stage_finish_event.to_stage, 2)
        self.assertEqual(
            job.tasks[stage_finish_event.result[
                "released_operation_id"
            ]].status,
            "blocked",
        )
        self.assertFalse(
            any(
                operation.job_id == job.job_id
                and operation.stage_id == 2
                for operation in self.simulator.planned_operations
            )
        )

        batch_event = self._advance_to_stage_batch(2, job.job_id)
        self.assertIn(job.job_id, batch_event.job_ids)
        self.assertEqual(
            batch_event.timestamp,
            stage_finish_event.result["batch_scheduled_for"],
        )

        predecessor = job.tasks[stage_finish_event.result[
            "released_operation_id"
        ] - 1]
        first_stage2 = job.tasks[
            stage_finish_event.result["released_operation_id"]
        ]
        planned = next(
            operation
            for operation in self.simulator.planned_operations
            if (
                operation.job_id == job.job_id
                and operation.operation_id
                == first_stage2.operation_id
            )
        )
        self.assertEqual(len(first_stage2.transport_segments), 1)
        segment = first_stage2.transport_segments[0]
        self.assertTrue(segment["completed"])
        self.assertEqual(segment["transport_time"], 2)
        self.assertEqual(planned.transport_time, 2)
        self.assertEqual(planned.transport_segments, [segment])
        self.assertEqual(planned.source_machine, predecessor.assigned_machine)
        self.assertGreaterEqual(
            planned.start_time,
            predecessor.actual_end + 2,
        )
        historical_event = next(
            event
            for event in batch_event.materialized_events
            if (
                isinstance(event, TransportFinishEvent)
                and event.job_id == job.job_id
                and event.operation_id == first_stage2.operation_id
            )
        )
        self.assertTrue(historical_event.historical)
        self.assertEqual(
            historical_event.timestamp,
            first_stage2.transport_end,
        )
        self.assertEqual(
            historical_event.transport_start,
            first_stage2.transport_start,
        )

    def test_nearby_stage_finishes_share_one_schedule_batch(self):
        self.simulator.process_stage_batch_window = 1000.0

        batch_event = self._advance_to_stage_batch(2)

        self.assertGreaterEqual(batch_event.job_count, 2)
        self.assertEqual(
            batch_event.job_count,
            len(batch_event.job_ids),
        )
        self.assertGreater(
            batch_event.result["planned_operation_count"],
            batch_event.job_count,
        )
        self.assertEqual(
            {
                operation.job_id
                for operation in self.simulator.planned_operations
                if operation.stage_id == 2
            },
            set(batch_event.job_ids),
        )

    def test_process_batches_apply_to_all_following_processes(self):
        self.simulator.process_stage_batch_window = 20.0
        multi_job_stages = set()

        while self.simulator.event_queue and multi_job_stages != {2, 3, 4}:
            event = self.simulator.event_queue.pop(0)
            self.simulator.curr_time = event.timestamp
            self.simulator.handleEvent(event)
            self.simulator.updateEventQueue()
            if (
                isinstance(event, ProcessStageBatchScheduleEvent)
                and event.job_count > 1
            ):
                multi_job_stages.add(event.stage_id)

        self.assertEqual(multi_job_stages, {2, 3, 4})

    def test_reoptimization_scope_keeps_other_process_queues(self):
        self._advance_to_first_stage_release(0)
        scoped_stage = 2
        scoped_machine_ids = {
            machine.machine_id
            for machine in self.simulator.machines
            if machine.stage_id == scoped_stage
        }

        def queue_snapshot(machine_ids):
            return {
                machine_id: [
                    (
                        operation.job_id,
                        operation.operation_id,
                        operation.start_time,
                        operation.end_time,
                    )
                    for operation in self.simulator.machines[
                        machine_id
                    ].pending_operations
                ]
                for machine_id in sorted(machine_ids)
            }

        other_machine_ids = {
            machine.machine_id
            for machine in self.simulator.machines
            if machine.stage_id != scoped_stage
        }
        before = queue_snapshot(other_machine_ids)
        unrelated_finish_event = JobFinishEvent(
            self.simulator.newEventId(),
            self.simulator.curr_time + 100,
            1,
        )
        self.simulator.event_queue.append(unrelated_finish_event)
        assignments = self.simulator._greedyUnfinishedAssignments(
            stage_ids={scoped_stage}
        )

        result = self.simulator.reoptimizeUnfinishedOperations(
            assignments,
            current_time=self.simulator.curr_time,
            stage_ids={scoped_stage},
        )

        self.assertEqual(
            queue_snapshot(other_machine_ids),
            before,
        )
        self.assertIn(
            unrelated_finish_event,
            self.simulator.event_queue,
        )
        self.assertEqual(result["process_ids"], [scoped_stage])
        self.assertTrue(
            all(
                machine_id in scoped_machine_ids
                for machine_id in assignments.values()
            )
        )

    def test_drl_reoptimization_uses_selected_process_dataset(self):
        self._advance_to_first_stage_release(0)
        process = next(
            item
            for item in self.source["processes"]
            if item["id"] == 2
        )
        offset = process["machine_offset"]
        requests = []
        schedule = []
        for job in self.simulator.jobs:
            for task in job.tasks:
                if (
                    task.stage_id != 2
                    or task.status not in {"pending", "scheduled"}
                ):
                    continue
                global_machine_id = min(task.eligible_machines)
                schedule.append(
                    {
                        "job_id": job.job_id,
                        "operation_index": task.stage_operation_id,
                        "machine_id": global_machine_id - offset,
                    }
                )

        class FakeScheduler:
            def predict(self, request):
                requests.append(request)
                return {
                    "model": "fake-stage2.pt",
                    "num_samples": request["num_samples"],
                    "objectives": {"makespan": 100},
                    "schedule": schedule,
                }

        manager = SimulationManager(
            DEFAULT_CONFIG_PATH,
            speed=2,
            realtime=False,
            scheduler_factory=FakeScheduler,
        )
        manager.simulator = self.simulator
        manager.selected_source = self.source
        manager.state.prepare(2)
        manager.state.set_running(self.simulator)

        result = manager.reoptimize(
            process_id=2,
            num_samples=1,
            seed=3,
        )

        self.assertEqual(result["process_ids"], [2])
        self.assertEqual(len(requests), 1)
        self.assertEqual(
            requests[0]["raw_lines"].splitlines()[0].split()[1],
            str(process["num_machines"]),
        )

    def test_hls_reoptimization_uses_selected_process_dataset(self):
        self._advance_to_first_stage_release(0)
        process = next(
            item
            for item in self.source["processes"]
            if item["id"] == 2
        )
        offset = process["machine_offset"]
        schedule = []
        for job in self.simulator.jobs:
            for task in job.tasks:
                if (
                    task.stage_id != 2
                    or task.status not in {"pending", "scheduled"}
                ):
                    continue
                global_machine_id = min(task.eligible_machines)
                schedule.append(
                    {
                        "job_id": job.job_id,
                        "operation_index": task.stage_operation_id,
                        "machine_id": global_machine_id - offset,
                    }
                )
        requests = []

        class FakeHlsScheduler:
            def predict(self, request):
                requests.append(request)
                return {
                    "model": "fake-stage2-hls",
                    "objectives": {"makespan": 100},
                    "runtime_seconds": 0.01,
                    "seed": request["seed"],
                    "additional_data_used": False,
                    "schedule": schedule,
                }

        other_machine_ids = {
            machine.machine_id
            for machine in self.simulator.machines
            if machine.stage_id != 2
        }
        queues_before = {
            machine_id: list(
                self.simulator.machines[machine_id].pending_operations
            )
            for machine_id in other_machine_ids
        }
        manager = SimulationManager(
            DEFAULT_CONFIG_PATH,
            speed=2,
            realtime=False,
            hls_scheduler_factory=FakeHlsScheduler,
        )
        manager.simulator = self.simulator
        manager.selected_source = self.source
        manager.state.prepare(2)
        manager.state.set_running(self.simulator)

        result = manager.hls_reoptimize(
            process_id=2,
            seed=3,
        )

        self.assertEqual(result["process_ids"], [2])
        self.assertEqual(len(requests), 1)
        self.assertEqual(
            requests[0]["raw_lines"].splitlines()[0].split()[1],
            str(process["num_machines"]),
        )
        scoped_tasks = [
            task
            for job in self.simulator.jobs
            for task in job.tasks
            if (
                task.stage_id == 2
                and task.status in {"pending", "scheduled"}
            )
        ]
        self.assertTrue(scoped_tasks)
        self.assertTrue(
            all(
                offset
                <= task.assigned_machine
                < offset + process["num_machines"]
                for task in scoped_tasks
            )
        )
        self.assertEqual(
            {
                machine_id: self.simulator.machines[
                    machine_id
                ].pending_operations
                for machine_id in other_machine_ids
            },
            queues_before,
        )

    def test_process_prediction_maps_local_machine_to_global_pool(self):
        manager = SimulationManager(
            DEFAULT_CONFIG_PATH,
            speed=2,
            realtime=False,
            anomaly_handling_enabled=True,
        )
        manager.simulator = self.simulator
        manager.selected_source = self.source
        manager.state.prepare(2)
        manager.state.set_running(self.simulator)

        result = manager.handle_prediction_alarms(
            1800,
            [{"machine_id": 0, "is_alarm": True}],
            process_id=2,
        )

        self.assertEqual(result["injected_machine_ids"], [8])
        self.assertEqual(
            self.simulator.machines[8].stage_id,
            2,
        )
        self.assertEqual(
            self.simulator.machines[8].local_machine_id,
            1,
        )

    def test_dynamic_job_keeps_all_four_processes(self):
        result = self.simulator.submitRandomJobsAndReoptimize(
            current_time=20,
            seed=7,
            order_source="manual",
        )
        new_job = self.simulator.jobs[result["new_jobs"][-1]["job_id"]]

        self.assertEqual(len(result["new_jobs"]), 7)
        self.assertEqual(
            sorted({task.stage_id for task in new_job.tasks}),
            [1, 2, 3, 4],
        )
        self.assertEqual(
            new_job.operation_count,
            self.simulator.jobs[0].operation_count,
        )
        self.assertEqual(
            set(new_job.material_consumption),
            {1, 2, 3, 4},
        )
        self.assertTrue(
            all(
                isinstance(task.material_consumption, dict)
                for task in new_job.tasks
            )
        )

    def test_runtime_status_does_not_change_plan_revision(self):
        manager = SimulationManager(
            DEFAULT_CONFIG_PATH,
            speed=2,
            realtime=False,
        )
        manager.simulator = self.simulator
        manager.selected_source = self.source
        manager.state.prepare(2)
        manager.state.set_running(self.simulator)
        initial_revision = manager.state.plan_revision
        first_task = self.simulator.jobs[0].tasks[0]

        first_task.status = "completed"
        manager.state._update_simulator(self.simulator)
        self.assertEqual(
            manager.state.plan_revision,
            initial_revision,
        )

        first_plan = next(
            operation
            for operation in self.simulator.planned_operations
            if (
                operation.job_id == first_task.job_id
                and operation.operation_id
                == first_task.operation_id
            )
        )
        first_plan.machine_id += 1
        manager.state._update_simulator(self.simulator)
        self.assertGreater(
            manager.state.plan_revision,
            initial_revision,
        )


if __name__ == "__main__":
    unittest.main()

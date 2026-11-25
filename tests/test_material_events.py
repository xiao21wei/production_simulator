import tempfile
import unittest
from pathlib import Path

from simulator.config import DEFAULT_CONFIG_PATH, load_simulator_config
from simulator.dataset import list_dataset_sources
from simulator.event import (
    EventType,
    MaterialRecoveryEvent,
    MaterialReplenishmentEvent,
    OperationStartEvent,
)
from simulator.simulator import Simulator
from web_app import serialize_event


class MaterialEventTest(unittest.TestCase):
    @staticmethod
    def _simulator():
        simulator = Simulator(realtime=False)
        simulator.log_tag = False
        simulator.init()
        simulator.updateEventQueue()
        return simulator

    @staticmethod
    def _event_for_task(simulator, event_type, job_id, operation_id):
        return next(
            event
            for event in simulator.event_queue
            if (
                isinstance(event, event_type)
                and event.job_id == job_id
                and event.operation_id == operation_id
            )
        )

    def test_shortage_replenishes_and_recovers_before_operation_start(self):
        simulator = self._simulator()
        start_event = next(
            event
            for event in simulator.event_queue
            if (
                isinstance(event, OperationStartEvent)
                and simulator._operationMaterialRequirements(
                    event.job_id,
                    event.operation_id,
                )
            )
        )
        simulator.event_queue.remove(start_event)
        task = simulator.jobs[start_event.job_id].tasks[
            start_event.operation_id
        ]
        machine = simulator.machines[start_event.machine_id]
        requirements = simulator._operationMaterialRequirements(
            start_event.job_id,
            start_event.operation_id,
        )
        for material_id, required in requirements.items():
            machine.materials[material_id] = required / 2

        simulator.curr_time = start_event.timestamp
        self.assertTrue(simulator.handleEvent(start_event))
        self.assertEqual(task.status, "scheduled")
        self.assertIsNone(task.actual_start)

        simulator.updateEventQueue()
        replenishment_event = self._event_for_task(
            simulator,
            MaterialReplenishmentEvent,
            start_event.job_id,
            start_event.operation_id,
        )
        recovery_event = self._event_for_task(
            simulator,
            MaterialRecoveryEvent,
            start_event.job_id,
            start_event.operation_id,
        )
        self.assertEqual(
            replenishment_event.getEventType(),
            EventType.MATERIAL_REPLENISHMENT,
        )
        self.assertEqual(
            recovery_event.getEventType(),
            EventType.MATERIAL_RECOVERY,
        )
        self.assertLess(
            simulator.event_queue.index(replenishment_event),
            simulator.event_queue.index(recovery_event),
        )
        self.assertEqual(
            simulator.material_replenishment_lead_time,
            20.0,
        )
        self.assertEqual(
            simulator.material_replenishment_target_factor,
            3.0,
        )
        self.assertEqual(
            recovery_event.timestamp,
            replenishment_event.timestamp
            + simulator.material_replenishment_lead_time,
        )

        simulator.event_queue.remove(replenishment_event)
        self.assertTrue(
            simulator.handleEvent(replenishment_event)
        )
        for material_id, required in requirements.items():
            self.assertAlmostEqual(
                machine.materials[material_id],
                required / 2,
            )
        self.assertEqual(replenishment_event.added_materials, {})
        self.assertEqual(task.status, "scheduled")
        self.assertFalse(
            any(
                isinstance(event, OperationStartEvent)
                and event.job_id == start_event.job_id
                and event.operation_id == start_event.operation_id
                for event in simulator.event_queue
            )
        )

        simulator.event_queue.remove(recovery_event)
        simulator.curr_time = recovery_event.timestamp
        self.assertTrue(simulator.handleEvent(recovery_event))
        for material_id, required in requirements.items():
            self.assertGreaterEqual(
                machine.materials[material_id] + 1e-9,
                required,
            )
            self.assertAlmostEqual(
                replenishment_event.replenishment_materials[
                    material_id
                ],
                required * 2.5,
            )
            self.assertAlmostEqual(
                replenishment_event.target_materials[material_id],
                required * 3.0,
            )
        self.assertTrue(recovery_event.added_materials)
        simulator.updateEventQueue()
        released_start = self._event_for_task(
            simulator,
            OperationStartEvent,
            start_event.job_id,
            start_event.operation_id,
        )
        self.assertGreater(released_start.id, recovery_event.id)
        simulator.event_queue.remove(released_start)
        simulator.curr_time = released_start.timestamp
        self.assertTrue(simulator.handleEvent(released_start))

        self.assertEqual(task.status, "processing")
        self.assertTrue(task.material_consumption_committed)
        for material_id, required in requirements.items():
            self.assertAlmostEqual(
                machine.materials[material_id],
                required * 2.0,
            )

        replenishment_data = serialize_event(
            replenishment_event,
            simulator,
        )
        self.assertIn(
            "replenishment_materials",
            replenishment_data,
        )
        self.assertEqual(
            replenishment_data["type"],
            "MaterialReplenishmentEvent",
        )
        self.assertEqual(replenishment_data["lead_time"], 20.0)
        recovery_data = serialize_event(
            recovery_event,
            simulator,
        )
        self.assertEqual(
            recovery_data["replenishment_event_id"],
            replenishment_event.id,
        )

    def test_all_four_processes_have_start_material_requirements(self):
        config = load_simulator_config(DEFAULT_CONFIG_PATH)
        sources = list_dataset_sources(
            config["paths"]["dataset_root"],
            config["paths"]["input_file"],
        )
        source = next(item for item in sources if item["is_default"])
        simulator = Simulator(realtime=False)
        simulator.log_tag = False
        simulator.init(
            file_path=source["raw_file"],
            additional_file_path=source["additional_file"],
            process_sources=source["processes"],
            process_chain=True,
        )

        requirements_by_stage = {}
        for job in simulator.jobs:
            for task in job.tasks:
                requirements = (
                    simulator._operationMaterialRequirements(
                        job.job_id,
                        task.operation_id,
                    )
                )
                if requirements:
                    requirements_by_stage.setdefault(
                        task.stage_id,
                        requirements,
                    )

        self.assertEqual(
            set(requirements_by_stage),
            {1, 2, 3, 4},
        )
        for requirements in requirements_by_stage.values():
            self.assertTrue(requirements)
            self.assertTrue(
                all(quantity > 0 for quantity in requirements.values())
            )

    def test_all_four_processes_execute_material_event_chain(self):
        project_root = Path(__file__).resolve().parents[1]
        source_name = "fjsp.brandimarte.Mk03.m8j15c5.fjs"
        process_directories = (
            ("raw", "add"),
            ("raw1", "add1"),
            ("raw2", "add2"),
            ("raw3", "add3"),
        )
        for raw_dir, add_dir in process_directories:
            with self.subTest(raw_dir=raw_dir):
                simulator = Simulator(realtime=False)
                simulator.log_tag = False
                simulator.init(
                    file_path=project_root / "datasets" / raw_dir
                    / source_name,
                    additional_file_path=project_root / "datasets"
                    / add_dir / source_name,
                )
                simulator.updateEventQueue()
                target_task = None
                requirements = None
                for job in simulator.jobs:
                    for task in job.tasks:
                        task_requirements = (
                            simulator._operationMaterialRequirements(
                                job.job_id,
                                task.operation_id,
                            )
                        )
                        if (
                            task_requirements
                            and task.assigned_machine is not None
                        ):
                            target_task = task
                            requirements = task_requirements
                            break
                    if target_task is not None:
                        break
                self.assertIsNotNone(target_task)
                machine = simulator.machines[
                    target_task.assigned_machine
                ]
                for material_id in requirements:
                    machine.materials[material_id] = 0.0

                processed = []
                while simulator.event_queue:
                    event = simulator.event_queue.pop(0)
                    simulator.curr_time = event.timestamp
                    handled = simulator.handleEvent(event)
                    simulator.updateEventQueue()
                    if handled is not False:
                        processed.append(event)
                    if target_task.status == "processing":
                        break

                self.assertEqual(target_task.status, "processing")
                material_events = [
                    event
                    for event in processed
                    if isinstance(
                        event,
                        (
                            MaterialReplenishmentEvent,
                            MaterialRecoveryEvent,
                        ),
                    )
                ]
                self.assertTrue(
                    any(
                        isinstance(
                            event,
                            MaterialReplenishmentEvent,
                        )
                        for event in material_events
                    )
                )
                self.assertTrue(
                    any(
                        isinstance(event, MaterialRecoveryEvent)
                        for event in material_events
                    )
                )
                self.assertTrue(
                    target_task.material_consumption_committed
                )

    def test_replenishment_tops_up_all_materials_to_threshold(self):
        project_root = Path(__file__).resolve().parents[1]
        source_name = "fjsp.brandimarte.Mk03.m8j15c5.fjs"
        simulator = Simulator(realtime=False)
        simulator.log_tag = False
        simulator.init(
            file_path=(
                project_root / "datasets" / "raw3" / source_name
            ),
            additional_file_path=(
                project_root / "datasets" / "add3" / source_name
            ),
        )
        simulator.updateEventQueue()
        start_event = next(
            event
            for event in simulator.event_queue
            if (
                isinstance(event, OperationStartEvent)
                and len(
                    simulator._operationMaterialRequirements(
                        event.job_id,
                        event.operation_id,
                    )
                ) >= 2
            )
        )
        simulator.event_queue.remove(start_event)
        requirements = simulator._operationMaterialRequirements(
            start_event.job_id,
            start_event.operation_id,
        )
        machine = simulator.machines[start_event.machine_id]
        for material_id, required in requirements.items():
            machine.materials[material_id] = required
        first_material_id = next(iter(requirements))
        machine.materials[first_material_id] = (
            requirements[first_material_id] * 0.5
        )

        simulator.curr_time = start_event.timestamp
        self.assertTrue(simulator.handleEvent(start_event))
        simulator.updateEventQueue()
        replenishment_event = self._event_for_task(
            simulator,
            MaterialReplenishmentEvent,
            start_event.job_id,
            start_event.operation_id,
        )

        for material_id, required in requirements.items():
            self.assertAlmostEqual(
                replenishment_event.target_materials[material_id],
                required * 3.0,
            )
            expected_replenishment = (
                required * 2.5
                if material_id == first_material_id
                else required * 2.0
            )
            self.assertAlmostEqual(
                replenishment_event.replenishment_materials[
                    material_id
                ],
                expected_replenishment,
            )

    def test_initial_jobs_avoid_frequent_anomalies_but_added_jobs_do_not(self):
        config = load_simulator_config(DEFAULT_CONFIG_PATH)
        source = next(
            item
            for item in list_dataset_sources(
                config["paths"]["dataset_root"],
                config["paths"]["input_file"],
            )
            if item["is_default"]
        )

        def count_anomalies(add_jobs):
            simulator = Simulator(realtime=False)
            simulator.log_tag = False
            simulator.init(
                file_path=source["raw_file"],
                additional_file_path=source["additional_file"],
                process_sources=source["processes"],
                process_chain=True,
            )
            added_jobs = 0
            if add_jobs:
                result = simulator.submitRandomJobsAndReoptimize(
                    current_time=0,
                    seed=7,
                    order_source="manual",
                )
                added_jobs = len(result["new_jobs"])

            count = 0
            original_handle_event = simulator.handleEvent

            def handle_and_count(event):
                nonlocal count
                handled = original_handle_event(event)
                if (
                    isinstance(event, MaterialReplenishmentEvent)
                    and handled is not False
                ):
                    count += 1
                return handled

            simulator.handleEvent = handle_and_count
            with tempfile.TemporaryDirectory() as temp_dir:
                simulator.schedule_file = str(
                    Path(temp_dir) / "schedule.csv"
                )
                simulator.gantt_file = str(
                    Path(temp_dir) / "gantt.txt"
                )
                self.assertTrue(simulator.run())
            return added_jobs, count

        baseline_added, baseline_anomalies = count_anomalies(False)
        dynamic_added, dynamic_anomalies = count_anomalies(True)

        self.assertEqual(baseline_added, 0)
        self.assertEqual(baseline_anomalies, 0)
        self.assertGreater(dynamic_added, 0)
        self.assertGreaterEqual(dynamic_anomalies, 15)


if __name__ == "__main__":
    unittest.main()

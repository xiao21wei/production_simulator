import json
import math
import unittest

from datasets.generate_followup_processes import (
    MATERIAL_CONFIG_ROOT,
    MATERIAL_CONSUMPTION_ROOT,
    MATERIAL_RESERVE_FACTOR,
    MATERIALS,
    PROCESS_SPECS,
    ROOT,
    STAGE_MATERIALS,
    process_filename,
    render_delivery_file,
    render_material_config,
    render_material_consumption,
    render_stage1_file,
    render_stage_pair,
    stage_machine_count,
)
from simulator.dataset import load_multi_objective_dataset


class FollowupProcessDatasetTest(unittest.TestCase):
    source_name = "fjsp.brandimarte.Mk03.m8j15c5.fjs"

    def test_generated_processes_are_loadable_and_reproducible(self):
        raw_path = ROOT / "raw" / self.source_name
        stage1 = render_stage1_file(raw_path)
        self.assertEqual(
            (ROOT / "add" / self.source_name).read_text(encoding="utf-8"),
            stage1["add_text"],
        )

        stage_sources = [stage1["source"]]
        for spec in PROCESS_SPECS:
            with self.subTest(process=spec.process_name):
                result = render_stage_pair(
                    stage1["source"],
                    spec,
                    self.source_name,
                )
                stage_sources.append(result["source"])
                raw_output = (
                    ROOT / f"raw{spec.directory}" / self.source_name
                )
                add_output = (
                    ROOT / f"add{spec.directory}" / self.source_name
                )
                self.assertEqual(
                    raw_output.read_text(encoding="utf-8"),
                    result["raw_text"],
                )
                self.assertEqual(
                    add_output.read_text(encoding="utf-8"),
                    result["add_text"],
                )
                self.assertEqual(
                    result["metadata"]["num_machines"],
                    stage_machine_count(spec, stage1["source"]),
                )
                expected_tasks = len(spec.tasks)
                self.assertTrue(
                    all(
                        len(job["raw_tasks"]) == expected_tasks
                        for job in result["jobs"]
                    )
                )
                for job in result["jobs"]:
                    self.assertEqual(
                        sum(
                            task["base_processing_time"]
                            for task in job["tasks"]
                        ),
                        job["target_processing_time"],
                    )
                    self.assertEqual(
                        sum(
                            task["base_processing_energy"]
                            for task in job["tasks"]
                        ),
                        job["target_processing_energy"],
                    )
                    for task in job["tasks"]:
                        self.assertGreaterEqual(
                            len(task["machine_options"]),
                            1,
                        )
                        for option in task["machine_options"]:
                            self.assertGreater(
                                option["processing_time"],
                                0,
                            )
                            self.assertGreaterEqual(
                                option["processing_energy"],
                                0,
                            )

                dataset = load_multi_objective_dataset(
                    raw_output,
                    add_output,
                    ROOT / "delivery_cost" / self.source_name,
                )
                self.assertEqual(
                    dataset.num_jobs,
                    stage1["metadata"]["num_jobs"],
                )
                self.assertEqual(
                    dataset.num_machines,
                    result["metadata"]["num_machines"],
                )
                self.assertTrue(
                    all(
                        len(task.eligible_machines) >= 1
                        for job in dataset.jobs
                        for task in job.tasks
                    )
                )

        self.assertEqual(
            (ROOT / "delivery_cost" / self.source_name).read_text(
                encoding="utf-8"
            ),
            render_delivery_file(self.source_name, stage_sources),
        )

    def test_energy_and_material_configs_cover_every_instance_machine(self):
        raw_path = ROOT / "raw" / self.source_name
        stage1 = render_stage1_file(raw_path)
        base_source = stage1["source"]
        stages = [(1, "冲压", stage1)]
        stages.extend(
            (
                spec.process_id,
                spec.process_name,
                render_stage_pair(base_source, spec, self.source_name),
            )
            for spec in PROCESS_SPECS
        )
        config_name = process_filename(self.source_name)

        for process_id, process_name, result in stages:
            with self.subTest(
                process=process_name,
                config=config_name,
            ):
                energy_path = (
                    ROOT
                    / "process_generation_configs"
                    / f"process_{process_id}"
                    / config_name
                )
                energy = json.loads(
                    energy_path.read_text(encoding="utf-8")
                )
                self.assertEqual(
                    energy["instance"],
                    self.source_name,
                )
                self.assertEqual(
                    energy["num_machines"],
                    result["metadata"]["num_machines"],
                )
                self.assertEqual(
                    len(energy["jobs"]),
                    result["metadata"]["num_jobs"],
                )
                self.assertEqual(
                    energy["transport_energy"],
                    result["transport_energy"],
                )
                for job in energy["jobs"]:
                    for task in job["tasks"]:
                        self.assertNotIn("materials", task)

                material_path = (
                    MATERIAL_CONFIG_ROOT
                    / f"process_{process_id}"
                    / config_name
                )
                material = json.loads(
                    material_path.read_text(encoding="utf-8")
                )
                self.assertEqual(
                    len(material["machines"]),
                    result["metadata"]["num_machines"],
                )
                expected_materials = set(STAGE_MATERIALS[process_id])
                for machine in material["machines"]:
                    configured = {
                        item["material_id"]
                        for item in machine["materials"]
                    }
                    self.assertEqual(configured, expected_materials)
                    for item in machine["materials"]:
                        self.assertEqual(
                            set(item),
                            {"material_id", "quantity"},
                        )
                        self.assertGreaterEqual(
                            item["quantity"],
                            0,
                        )

                consumption_path = (
                    MATERIAL_CONSUMPTION_ROOT
                    / f"process_{process_id}"
                    / config_name
                )
                consumption = json.loads(
                    consumption_path.read_text(encoding="utf-8")
                )
                expected_by_machine = {
                    machine_id: {
                        material_id: 0.0
                        for material_id in STAGE_MATERIALS[process_id]
                    }
                    for machine_id in range(
                        1,
                        result["metadata"]["num_machines"] + 1,
                    )
                }
                for job in result["jobs"]:
                    for task in job["tasks"]:
                        machine_ids = {
                            int(option["machine_id"])
                            for option in task["machine_options"]
                        }
                        for item in task["materials"]:
                            for machine_id in machine_ids:
                                expected_by_machine[machine_id][
                                    item["material_id"]
                                ] += item["quantity"]
                for machine in material["machines"]:
                    actual = {
                        item["material_id"]: item["quantity"]
                        for item in machine["materials"]
                    }
                    for material_id, quantity in (
                        expected_by_machine[machine["machine_id"]].items()
                    ):
                        resolution = (
                            1.0
                            if MATERIALS[material_id][1]
                            in {"piece", "set"}
                            else 0.1
                        )
                        expected = (
                            math.ceil(
                                quantity
                                * MATERIAL_RESERVE_FACTOR
                                / resolution
                                - 1e-9
                            )
                            * resolution
                        )
                        self.assertAlmostEqual(
                            actual[material_id],
                            expected,
                        )
                self.assertEqual(
                    set(consumption),
                    {"instance", "process_id", "jobs"},
                )
                self.assertEqual(
                    len(consumption["jobs"]),
                    result["metadata"]["num_jobs"],
                )
                for job in consumption["jobs"]:
                    if process_id == 1:
                        self.assertEqual(
                            set(job),
                            {"job_id", "materials"},
                        )
                        for item in job["materials"]:
                            self.assertEqual(
                                set(item),
                                {"material_id", "quantity"},
                            )
                    else:
                        self.assertEqual(
                            set(job),
                            {"job_id", "tasks"},
                        )
                        self.assertEqual(
                            len(job["tasks"]),
                            len(
                                result["jobs"][job["job_id"]]["tasks"]
                            ),
                        )
                        for task in job["tasks"]:
                            self.assertEqual(
                                set(task),
                                {"stage_operation_id", "materials"},
                            )
                            for item in task["materials"]:
                                self.assertEqual(
                                    set(item),
                                    {"material_id", "quantity"},
                                )

    def test_machine_inventory_follows_eligible_task_demand(self):
        jobs = [
            {
                "job_id": 0,
                "tasks": [
                    {
                        "stage_operation_id": 2,
                        "machine_options": [
                            {"machine_id": 1},
                        ],
                        "materials": [
                            {
                                "material_id": "M2_WELD_WIRE",
                                "quantity": 2.0,
                            }
                        ],
                    },
                    {
                        "stage_operation_id": 3,
                        "machine_options": [
                            {"machine_id": 1},
                            {"machine_id": 2},
                        ],
                        "materials": [
                            {
                                "material_id": (
                                    "M2_STRUCTURAL_ADHESIVE"
                                ),
                                "quantity": 4.0,
                            }
                        ],
                    },
                ],
            }
        ]
        consumption = render_material_consumption(
            "unit-test.fjs",
            2,
            jobs,
        )
        config = render_material_config(
            "unit-test.fjs",
            2,
            2,
            consumption,
            jobs,
        )
        machine_materials = [
            {
                item["material_id"]: item["quantity"]
                for item in machine["materials"]
            }
            for machine in config["machines"]
        ]

        self.assertEqual(
            machine_materials[0]["M2_WELD_WIRE"],
            2.4,
        )
        self.assertEqual(
            machine_materials[1]["M2_WELD_WIRE"],
            0.0,
        )
        self.assertEqual(
            machine_materials[0]["M2_STRUCTURAL_ADHESIVE"],
            4.8,
        )
        self.assertEqual(
            machine_materials[1]["M2_STRUCTURAL_ADHESIVE"],
            4.8,
        )


if __name__ == "__main__":
    unittest.main()

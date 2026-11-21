import tempfile
import unittest
from pathlib import Path

from simulator.config import load_simulator_config
from simulator.dataset import (
    DatasetValidationError,
    get_dataset_source,
    list_dataset_sources,
    load_model_additional_text,
    load_multi_objective_dataset,
)


class MultiObjectiveDatasetTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        config = load_simulator_config()
        cls.raw_path = Path(config["paths"]["input_file"])
        cls.additional_path = Path(config["paths"]["additional_file"])
        cls.delivery_path = (
            Path("datasets")
            / "delivery_cost"
            / cls.raw_path.name
        )
        cls.dataset = load_multi_objective_dataset(
            cls.raw_path,
            cls.additional_path,
        )

    def test_default_dataset_shape_and_fields(self):
        dataset = self.dataset

        self.assertEqual(dataset.num_jobs, 15)
        self.assertEqual(dataset.num_machines, 8)
        self.assertEqual(dataset.num_operations, 150)
        self.assertEqual(
            sum(len(job.tasks) for job in dataset.jobs),
            150,
        )

        first_job = dataset.jobs[0]
        self.assertIn(first_job.weight, range(1, 6))
        self.assertIn(first_job.ready_time, range(0, 21))
        self.assertGreater(first_job.due_time, first_job.ready_time)
        self.assertIn(first_job.earliness_cost, range(1, 11))
        self.assertIn(first_job.tardiness_cost, range(1, 11))
        self.assertEqual(first_job.release_time, first_job.ready_time)
        self.assertEqual(first_job.due_date, first_job.due_time)
        self.assertEqual(
            dataset.delivery_cost_path,
            self.delivery_path,
        )

    def test_tasks_contain_machine_time_and_energy_fields(self):
        for job in self.dataset.jobs:
            for operation_id, task in enumerate(job.tasks):
                self.assertEqual(task.task_id, sum(
                    previous.operation_count
                    for previous in self.dataset.jobs[:job.job_id]
                ) + operation_id)
                self.assertEqual(task.job_id, job.job_id)
                self.assertEqual(task.operation_id, operation_id)
                self.assertTrue(task.processing_times)
                self.assertEqual(
                    set(task.processing_times),
                    set(task.processing_energies),
                )
                self.assertEqual(
                    task.eligible_machines,
                    tuple(sorted(task.processing_times)),
                )

        first_task = self.dataset.jobs[0].tasks[0]
        self.assertIsNone(first_task.predecessor_id)
        self.assertEqual(first_task.successor_id, 1)

    def test_transport_matrices_are_complete_and_symmetric(self):
        for matrix in (
            self.dataset.transport_time,
            self.dataset.transport_energy,
        ):
            self.assertEqual(len(matrix), self.dataset.num_machines)
            for row_index, row in enumerate(matrix):
                self.assertEqual(len(row), self.dataset.num_machines)
                self.assertEqual(row[row_index], 0)
                for column_index, value in enumerate(row):
                    self.assertEqual(
                        value,
                        matrix[column_index][row_index],
                    )

    def test_delivery_fields_are_merged_for_model_input(self):
        merged = load_model_additional_text(
            self.raw_path,
            self.additional_path,
            self.delivery_path,
        )
        lines = [line for line in merged.splitlines() if line.strip()]
        add_lines = [
            line
            for line in self.additional_path.read_text(
                encoding="utf-8"
            ).splitlines()
            if line.strip()
        ]
        delivery_lines = [
            line
            for line in self.delivery_path.read_text(
                encoding="utf-8"
            ).splitlines()
            if line.strip() and not line.startswith("#")
        ]

        self.assertEqual(
            len(lines),
            len(add_lines) + len(delivery_lines),
        )
        self.assertEqual(
            lines[self.dataset.num_jobs:self.dataset.num_jobs * 2],
            delivery_lines,
        )

    def test_missing_additional_file_is_rejected(self):
        with self.assertRaises(DatasetValidationError):
            load_multi_objective_dataset(
                self.raw_path,
                Path("datasets/add/not-found.fjs"),
            )

    def test_missing_delivery_cost_file_is_rejected(self):
        with self.assertRaises(DatasetValidationError):
            load_multi_objective_dataset(
                self.raw_path,
                self.additional_path,
                Path("datasets/delivery_cost/not-found.fjs"),
            )

    def test_machine_mismatch_is_rejected(self):
        lines = self.additional_path.read_text("utf-8").splitlines()
        tokens = lines[0].split()
        tokens[1] = "99"
        lines[0] = " ".join(tokens)

        with tempfile.TemporaryDirectory() as temp_dir:
            invalid_path = Path(temp_dir) / "invalid.fjs"
            invalid_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

            with self.assertRaises(DatasetValidationError):
                load_multi_objective_dataset(self.raw_path, invalid_path)

    def test_incomplete_transport_section_is_rejected(self):
        lines = self.additional_path.read_text("utf-8").splitlines()

        with tempfile.TemporaryDirectory() as temp_dir:
            invalid_path = Path(temp_dir) / "invalid.fjs"
            invalid_path.write_text(
                "\n".join(lines[:-1]) + "\n",
                encoding="utf-8",
            )

            with self.assertRaises(DatasetValidationError):
                load_multi_objective_dataset(self.raw_path, invalid_path)

    def test_dataset_catalog_lists_complete_pairs(self):
        config = load_simulator_config()
        sources = list_dataset_sources(
            config["paths"]["dataset_root"],
            self.raw_path,
        )

        dataset_root = Path(config["paths"]["dataset_root"])
        raw_names = {
            path.name for path in (dataset_root / "raw").glob("*.fjs")
        }
        add_names = {
            path.name for path in (dataset_root / "add").glob("*.fjs")
        }
        delivery_names = {
            path.name
            for path in (
                dataset_root
                / "delivery_cost"
            ).glob("*.fjs")
        }
        self.assertEqual(len(sources), len(raw_names & add_names))
        self.assertEqual(
            len(sources),
            len(raw_names & add_names & delivery_names),
        )
        self.assertGreater(len(sources), 0)
        default_sources = [
            source for source in sources if source["is_default"]
        ]
        self.assertEqual(len(default_sources), 1)
        self.assertEqual(
            default_sources[0]["id"],
            self.raw_path.stem,
        )
        self.assertTrue(
            default_sources[0]["delivery_cost_file"].endswith(
                "delivery_cost/"
                + self.raw_path.name
            )
        )

    def test_dataset_catalog_lookup_rejects_unknown_id(self):
        config = load_simulator_config()

        with self.assertRaises(DatasetValidationError):
            get_dataset_source(
                config["paths"]["dataset_root"],
                "not-a-real-dataset",
            )


if __name__ == "__main__":
    unittest.main()

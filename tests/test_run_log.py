import json
import tempfile
import unittest
from pathlib import Path

from simulator.run_log import SimulationRunLogger
from simulator.simulator import Simulator


class SimulationRunLoggerTest(unittest.TestCase):
    def test_latest_run_log_contains_complete_records(self):
        simulator = Simulator(realtime=False)
        simulator.log_tag = False
        simulator.init()
        simulator.updateEventQueue()

        with tempfile.TemporaryDirectory() as temp_dir:
            logger = SimulationRunLogger(temp_dir)
            logger.start(
                {
                    "dataset": {"id": simulator.dataset.raw_path.stem},
                    "speed": 10,
                }
            )
            while simulator.event_queue:
                event = simulator.event_queue.pop(0)
                simulator.curr_time = event.timestamp
                simulator.handleEvent(event)
                simulator.updateEventQueue()
                logger.record_event(event, simulator)
            simulator.calculateObjectives()
            logger.record_reoptimization(
                {"num_samples": 1, "seed": 0},
                {"success": True, "moved_operation_count": 0},
                simulator,
            )
            logger.finish(simulator)

            latest_dir = Path(temp_dir) / "latest"
            expected_files = {
                "metadata.json",
                "summary.json",
                "events.jsonl",
                "operations.jsonl",
                "objectives.jsonl",
                "reoptimizations.jsonl",
            }
            self.assertEqual(
                {path.name for path in latest_dir.iterdir()},
                expected_files,
            )

            summary = json.loads(
                (latest_dir / "summary.json").read_text(encoding="utf-8")
            )
            self.assertEqual(
                summary["jobs_completed"],
                len(simulator.jobs),
            )
            self.assertEqual(
                summary["objectives"],
                simulator.objectives,
            )
            for filename in SimulationRunLogger.JSONL_FILES:
                self.assertGreater(
                    (latest_dir / filename).stat().st_size,
                    0,
                )

            event_rows = [
                json.loads(line)
                for line in (latest_dir / "events.jsonl")
                .read_text(encoding="utf-8")
                .splitlines()
            ]
            self.assertGreater(len(event_rows), 0)
            self.assertIn(
                "OperationFinishEvent",
                {row["event_type"] for row in event_rows},
            )


if __name__ == "__main__":
    unittest.main()

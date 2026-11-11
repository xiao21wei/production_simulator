import unittest
from unittest.mock import patch

from simulator.anomaly import MachineAnomalyType
from simulator.config import DEFAULT_CONFIG_PATH
from simulator.simulator import Simulator
from web_app import SimulationManager


class AutoMachineAnomalyTest(unittest.TestCase):
    def _manager(self):
        simulator = Simulator(realtime=False)
        simulator.log_tag = False
        simulator.init()
        simulator.updateEventQueue()
        manager = SimulationManager(
            config_path=DEFAULT_CONFIG_PATH,
            speed=10,
            realtime=False,
        )
        manager.simulator = simulator
        manager.selected_source = manager.datasets_by_id[
            manager.default_dataset_id
        ]
        manager.state.prepare(10)
        manager.state.selected_dataset = {
            "id": manager.default_dataset_id,
        }
        manager.state.set_running(simulator)
        return simulator, manager

    def test_auto_machine_anomaly_triggers_every_40_steps(self):
        simulator, manager = self._manager()
        simulator.machines[0].machine_status = "failed"
        simulator.machines[0].anomaly_type = "long_failure"
        calls = []
        manager.handle_machine_anomaly = (
            lambda machine_id, anomaly_type, duration: calls.append(
                (machine_id, anomaly_type, duration)
            )
        )

        result = manager.set_auto_machine_anomaly(True)

        self.assertTrue(result["auto_machine_anomaly"]["enabled"])
        self.assertEqual(
            manager.next_auto_machine_anomaly_time,
            40,
        )
        simulator.curr_time = 39
        manager._maybe_auto_insert_machine_anomaly()
        self.assertEqual(calls, [])

        def choose(values):
            first = values[0]
            if hasattr(first, "machine_id"):
                return first
            return MachineAnomalyType.SHORT_FAILURE

        with patch("web_app.random.Random") as random_cls:
            random_cls.return_value.choice.side_effect = choose
            random_cls.return_value.randint.return_value = 5

            simulator.curr_time = 40
            manager._maybe_auto_insert_machine_anomaly()
            self.assertEqual(len(calls), 1)
            self.assertNotEqual(calls[0][0], 0)
            self.assertEqual(calls[0][1], "short_failure")
            self.assertEqual(calls[0][2], 5)
            self.assertEqual(
                manager.next_auto_machine_anomaly_time,
                80,
            )

            simulator.curr_time = 79
            manager._maybe_auto_insert_machine_anomaly()
            self.assertEqual(len(calls), 1)
            simulator.curr_time = 80
            manager._maybe_auto_insert_machine_anomaly()
            self.assertEqual(len(calls), 2)

        self.assertEqual(manager.auto_machine_anomaly_count, 2)
        state = manager.state.snapshot()["auto_machine_anomaly"]
        self.assertEqual(state["count"], 2)
        self.assertEqual(state["next_time"], 120)
        self.assertEqual(state["last"]["duration"], 5)

        manager.set_auto_machine_anomaly(False)
        simulator.curr_time = 160
        manager._maybe_auto_insert_machine_anomaly()
        self.assertEqual(len(calls), 2)
        self.assertIsNone(manager.next_auto_machine_anomaly_time)


if __name__ == "__main__":
    unittest.main()

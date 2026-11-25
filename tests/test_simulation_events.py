import unittest

from simulator.config import DEFAULT_CONFIG_PATH
from simulator.event import (
    EventType,
    MachineAnomalyEvent,
    MachineRecoveryEvent,
    OrderCancelEvent,
    OrderInsertEvent,
    ProcessStageBatchScheduleEvent,
)
from simulator.simulator import Simulator
from web_app import SimulationManager, serialize_event


class SimulationEventTest(unittest.TestCase):
    def _manager(self):
        simulator = Simulator(realtime=False)
        simulator.log_tag = False
        simulator.init()
        simulator.updateEventQueue()
        manager = SimulationManager(
            config_path=DEFAULT_CONFIG_PATH,
            speed=5,
            realtime=False,
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
        processed = []
        original_handle_event = simulator.handleEvent

        def collect(event):
            processed.append(event)
            handled = original_handle_event(event)
            if handled is not False:
                manager.state.record_event(event, simulator)
            return handled

        simulator.handleEvent = collect
        return simulator, manager, processed

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

    def test_order_insert_is_dispatched_as_event(self):
        simulator, manager, processed = self._manager()

        result = manager.submit_random_jobs(seed=17)

        insert_event = next(
            event
            for event in processed
            if isinstance(event, OrderInsertEvent)
        )
        self.assertEqual(insert_event.getEventType(), EventType.ORDER_INSERT)
        self.assertEqual(insert_event.seed, 17)
        self.assertEqual(insert_event.job_count, 7)
        self.assertEqual(
            insert_event.job_ids,
            [job["job_id"] for job in result["new_jobs"]],
        )
        self.assertEqual(result["event_id"], insert_event.id)
        self.assertEqual(result["event_type"], "OrderInsertEvent")
        event_data = serialize_event(insert_event, simulator)
        self.assertEqual(event_data["type"], "OrderInsertEvent")
        self.assertEqual(event_data["job_count"], 7)
        self.assertEqual(event_data["job_ids"], insert_event.job_ids)
        self.assertEqual(
            len(simulator.jobs),
            simulator.initial_job_count + 7,
        )
        self.assertIn(
            "OrderInsertEvent",
            {
                event["type"]
                for event in manager.state.snapshot()["events"]
            },
        )

    def test_order_cancel_is_dispatched_as_event(self):
        simulator, manager, processed = self._manager()

        result = manager.cancel_jobs([0, 1])

        cancel_event = next(
            event
            for event in processed
            if isinstance(event, OrderCancelEvent)
        )
        self.assertEqual(cancel_event.getEventType(), EventType.ORDER_CANCEL)
        self.assertEqual(cancel_event.job_ids, [0, 1])
        self.assertTrue(cancel_event.batch)
        self.assertEqual(result["event_id"], cancel_event.id)
        self.assertEqual(result["event_type"], "OrderCancelEvent")
        self.assertTrue(simulator.jobs[0].is_canceled)
        self.assertTrue(simulator.jobs[1].is_canceled)
        self.assertIn(
            "OrderCancelEvent",
            {
                event["type"]
                for event in manager.state.snapshot()["events"]
            },
        )

    def test_machine_anomaly_and_recovery_are_events(self):
        simulator, manager, processed = self._manager()
        simulator.updateEventQueue()
        while simulator.event_queue:
            event = simulator.event_queue.pop(0)
            simulator.curr_time = event.timestamp
            simulator.handleEvent(event)
            simulator.updateEventQueue()
            if any(
                task.status == "processing"
                for job in simulator.jobs
                for task in job.tasks
            ):
                break
        task = next(
            task
            for job in simulator.jobs
            for task in job.tasks
            if task.status == "processing"
        )
        machine_id = task.assigned_machine

        result = manager.handle_machine_anomaly(
            machine_id,
            "short_failure",
            10,
        )

        anomaly_event = next(
            event
            for event in processed
            if isinstance(event, MachineAnomalyEvent)
        )
        self.assertEqual(
            anomaly_event.getEventType(),
            EventType.MACHINE_ANOMALY,
        )
        self.assertEqual(anomaly_event.machine_id, machine_id)
        self.assertEqual(anomaly_event.duration, 10)
        self.assertEqual(result["event_id"], anomaly_event.id)
        event_data = serialize_event(anomaly_event, simulator)
        self.assertEqual(event_data["machine_id"], machine_id)
        self.assertEqual(event_data["duration"], 10)
        self.assertEqual(event_data["machine_status"], "repairing")
        recovery_event = next(
            event
            for event in simulator.event_queue
            if isinstance(event, MachineRecoveryEvent)
            and event.machine_id == machine_id
        )
        self.assertEqual(
            recovery_event.getEventType(),
            EventType.MACHINE_RECOVERY,
        )
        self.assertEqual(
            recovery_event.anomaly_started_at,
            anomaly_event.timestamp,
        )
        self.assertIn(
            "MachineAnomalyEvent",
            {
                event["type"]
                for event in manager.state.snapshot()["events"]
            },
        )

        self._advance_to(simulator, recovery_event.timestamp)

        processed_recovery = next(
            event
            for event in processed
            if isinstance(event, MachineRecoveryEvent)
            and event.machine_id == machine_id
        )
        self.assertIsNotNone(processed_recovery.result)
        self.assertTrue(processed_recovery.result["success"])
        self.assertEqual(
            processed_recovery.machine_status,
            processed_recovery.result["machine_status"],
        )
        self.assertIn(
            processed_recovery.machine_status,
            {"idle", "scheduled", "busy"},
        )
        self.assertIn(
            "MachineRecoveryEvent",
            {
                event["type"]
                for event in manager.state.snapshot()["events"]
            },
        )

    def test_process_stage_batch_event_serialization(self):
        simulator, _, _ = self._manager()
        event = ProcessStageBatchScheduleEvent(
            simulator.newEventId(),
            25,
            2,
            10,
        )
        event.add_job(0, 18)
        event.add_job(1, 20)
        event.result = {
            "stage_id": 2,
            "job_ids": [0, 1],
            "job_count": 2,
            "planned_operation_count": 12,
        }

        self.assertEqual(
            event.getEventType(),
            EventType.PROCESS_STAGE_BATCH_SCHEDULE,
        )
        event_data = serialize_event(event, simulator)
        self.assertEqual(
            event_data["type"],
            "ProcessStageBatchScheduleEvent",
        )
        self.assertEqual(event_data["stage_id"], 2)
        self.assertEqual(event_data["batch_window"], 10)
        self.assertEqual(event_data["job_ids"], [0, 1])
        self.assertEqual(
            event_data["job_ready_times"],
            {0: 18.0, 1: 20.0},
        )


if __name__ == "__main__":
    unittest.main()

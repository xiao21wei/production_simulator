import json
import tempfile
import time
import unittest
import urllib.request
from types import SimpleNamespace
from unittest.mock import patch

from simulator.anomaly import (
    MACHINE_ANOMALY_DEFAULT_DURATIONS,
    MachineAnomalyType,
)
from simulator.event import MachineRecoveryEvent, OperationStartEvent
from simulator.config import DEFAULT_CONFIG_PATH
from simulator.simulator import Simulator
from system.schedule import PlannedOperation
from web_app import (
    DashboardState,
    SimulationManager,
    create_dashboard_server,
    serialize_event,
    serialize_plan,
)


class WebAppTest(unittest.TestCase):
    def test_initial_dashboard_speed_uses_configured_speed(self):
        manager = SimulationManager(
            config_path=DEFAULT_CONFIG_PATH,
            speed=2,
            realtime=False,
        )

        self.assertEqual(manager.state.snapshot()["speed"], 2)

    def test_anomaly_handling_is_disabled_by_default(self):
        manager = SimulationManager(
            config_path=DEFAULT_CONFIG_PATH,
            speed=2,
            realtime=False,
        )

        snapshot = manager.state.snapshot()
        result = manager.handle_prediction_alarms(
            5,
            [{"machine_id": 0, "is_alarm": True}],
        )

        self.assertFalse(snapshot["anomaly_handling"]["enabled"])
        self.assertEqual(
            result["reason"],
            "anomaly_handling_disabled",
        )
        with self.assertRaises(ValueError):
            manager.handle_machine_anomaly(0, "short_failure", 3)
        with self.assertRaises(ValueError):
            manager.set_auto_machine_anomaly(True)

    def test_detection_proxy_endpoints(self):
        prediction_calls = []

        class FakeDetectionData:
            def meta(self):
                return {
                    "history_points": 60,
                    "poll_interval_ms": 1000,
                    "selected_features": [{"name": "TP2"}],
                }

            def machines(self):
                return {"machines": [{"machine_id": 0, "T": 100}]}

            def overview(self, t, machine_count=None):
                return {
                    "t": t,
                    "machine_count": machine_count,
                    "prediction_horizon": 20,
                    "machines": [{
                        "machine_id": 0,
                        "T": 100,
                        "t_effective": t,
                        "label": 0,
                        "warn": 0,
                        "values": {"TP2": 1.5},
                    }],
                }

            def predict(self, t, machine_count=1):
                prediction_calls.append((t, machine_count))
                return {
                    "t": t,
                    "prediction_interval": 5,
                    "predictions": [{
                        "machine_id": 0,
                        "t": t,
                        "is_alarm": True,
                    }],
                }

        alarm_calls = []

        class FakeManager:
            state = SimpleNamespace()

            def __init__(self):
                self.detection_data = FakeDetectionData()

            def handle_prediction_alarms(
                self,
                t,
                predictions,
                process_id=1,
            ):
                alarm_calls.append(
                    (t, predictions, process_id)
                )
                return {
                    "success": True,
                    "t": t,
                    "process_id": process_id,
                    "injected_machine_ids": [0],
                }

        manager = FakeManager()
        server, thread = create_dashboard_server(
            "127.0.0.1",
            0,
            manager,
        )
        base = f"http://127.0.0.1:{server.server_address[1]}"
        try:
            with urllib.request.urlopen(
                f"{base}/api/detection/meta",
                timeout=5,
            ) as response:
                meta = json.loads(response.read().decode("utf-8"))
            with urllib.request.urlopen(
                f"{base}/api/detection/machines",
                timeout=5,
            ) as response:
                machines = json.loads(response.read().decode("utf-8"))
            with urllib.request.urlopen(
                f"{base}/api/detection/overview?t=87&machine_count=3",
                timeout=5,
            ) as response:
                overview = json.loads(response.read().decode("utf-8"))
            with urllib.request.urlopen(
                (
                    f"{base}/api/detection/predict"
                    "?t=85&machine_count=3"
                ),
                timeout=5,
            ) as response:
                prediction = json.loads(
                    response.read().decode("utf-8")
                )
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)

        self.assertEqual(meta["poll_interval_ms"], 1000)
        self.assertEqual(machines["machines"][0]["machine_id"], 0)
        self.assertEqual(overview["t"], 87)
        self.assertEqual(overview["machine_count"], 3)
        self.assertEqual(overview["machines"][0]["values"]["TP2"], 1.5)
        self.assertEqual(prediction["t"], 85)
        self.assertEqual(prediction["injected_machine_ids"], [0])
        self.assertEqual(prediction_calls, [(85, 3)])
        self.assertEqual(alarm_calls[0][0], 85)
        self.assertTrue(alarm_calls[0][1][0]["is_alarm"])
        self.assertEqual(alarm_calls[0][2], 1)

    def test_dashboard_contains_anomaly_list_and_injection_control(self):
        manager = SimpleNamespace(state=SimpleNamespace())
        server, thread = create_dashboard_server(
            "127.0.0.1",
            0,
            manager,
        )
        try:
            with urllib.request.urlopen(
                f"http://127.0.0.1:{server.server_address[1]}/",
                timeout=5,
            ) as response:
                html = response.read().decode("utf-8")
            with urllib.request.urlopen(
                (
                    "http://127.0.0.1:"
                    f"{server.server_address[1]}/app.js"
                ),
                timeout=5,
            ) as response:
                javascript = response.read().decode("utf-8")
            with urllib.request.urlopen(
                (
                    "http://127.0.0.1:"
                    f"{server.server_address[1]}/styles.css"
                ),
                timeout=5,
            ) as response:
                stylesheet = response.read().decode("utf-8")
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)

        self.assertIn("异常列表", html)
        self.assertIn(
            "<title>生产调度实时监控</title>",
            html,
        )
        self.assertNotIn(
            "<title>生产调度实时仿真</title>",
            html,
        )
        self.assertIn(
            "Production Scheduling Real-time Monitoring",
            html,
        )
        self.assertNotIn(
            "Production Scheduling Digital Twin",
            html,
        )
        self.assertIn("工序调度", html)
        self.assertIn("设备状态看板", html)
        self.assertIn('id="schedule-tab"', html)
        self.assertIn('id="machine-board-tab"', html)
        self.assertIn('id="process-tabs"', html)
        self.assertNotIn('id="schedule-process-tabs"', html)
        self.assertNotIn('id="machine-board-process-tabs"', html)
        self.assertLess(
            html.index('id="process-tabs"'),
            html.index('id="schedule-tab"'),
        )
        self.assertIn('id="machine-card-grid"', html)
        self.assertIn('/vendor/echarts.min.js', html)
        self.assertIn('id="order-list"', html)
        self.assertIn('id="order-count"', html)
        self.assertIn('id="order-list-panel"', html)
        self.assertIn('id="job-list-panel"', html)
        self.assertIn('id="cancel-order-options"', html)
        self.assertIn('<option value="1">1x</option>', html)
        self.assertIn('<option value="2" selected>2x</option>', html)
        self.assertIn('<option value="5">5x</option>', html)
        self.assertNotIn('<option value="10">10x</option>', html)
        self.assertIn('id="stop-button"', html)
        self.assertIn('id="insert-anomaly-button"', html)
        self.assertIn('id="auto-machine-anomaly"', html)
        self.assertIn('id="anomaly-type-select"', html)
        self.assertIn("短故障（1–5，默认 3）", html)
        self.assertIn("中等故障（5–15，默认 10）", html)
        self.assertIn("长故障（15–45，默认 30）", html)
        self.assertIn("降额运行（10–20，默认 15）", html)
        self.assertIn('id="anomaly-duration-hint"', html)
        self.assertIn('id="anomaly-duration"', html)
        self.assertIn('step="1"', html)
        self.assertIn("OrderInsertEvent", javascript)
        self.assertIn("OrderCancelEvent", javascript)
        self.assertIn("MachineAnomalyEvent", javascript)
        self.assertIn("MachineRecoveryEvent", javascript)
        self.assertIn(
            "option.textContent = `M${machine.local_id ?? machine.id}`",
            javascript,
        )
        self.assertIn("app.planRevision !== snapshot.plan_revision", javascript)
        self.assertIn("TIMELINE_REBUILD_EVENT_TYPES", javascript)
        self.assertIn(
            "function snapshotRequiresTimelineRebuild",
            javascript,
        )
        self.assertIn(
            "const timelineRebuildRequired =\n"
            "    snapshotRequiresTimelineRebuild(snapshot);",
            javascript,
        )
        self.assertIn("Number.isInteger(duration)", javascript)
        self.assertIn("/api/auto-machine-anomaly", javascript)
        self.assertIn("syncAnomalyHandling", javascript)
        self.assertIn("renderMachineDetectionBoard", javascript)
        self.assertIn('id="material-board-tab"', html)
        self.assertIn('id="material-board-view"', html)
        self.assertIn("物料库存看板", html)
        self.assertIn("renderMaterialInventoryBoard", javascript)
        self.assertIn("function createMaterialInventoryCard", javascript)
        self.assertIn(
            'MaterialReplenishmentEvent: "物料异常 · 补料"',
            javascript,
        )
        self.assertIn(
            'MaterialRecoveryEvent: "物料异常 · 恢复"',
            javascript,
        )
        self.assertIn(
            '"MaterialReplenishmentEvent",\n'
            '  "MaterialRecoveryEvent",\n'
            "]);",
            javascript,
        )
        self.assertIn("function formatMaterialEventMap", javascript)
        self.assertIn('row.classList.add("material-event")', javascript)
        self.assertIn(".event-row.material-event .event-dot", stylesheet)
        self.assertIn('setDashboardTab("material-board")', javascript)
        self.assertIn(
            'root.style.setProperty("--board-scale", String(scale))',
            javascript,
        )
        self.assertIn(
            "--board-scale: 1;",
            stylesheet,
        )
        self.assertIn(
            "height: calc(190px * var(--board-scale));",
            stylesheet,
        )
        self.assertIn(
            "minmax(calc(300px * var(--board-scale)), 1fr)",
            stylesheet,
        )
        self.assertIn(
            ".process-navigation-row .process-tab {\n"
            "  padding: 8px 14px;\n"
            "  font-size: 14px;\n"
            "}",
            stylesheet,
        )
        self.assertIn(
            ".view-tab {\n"
            "  padding: 9px 14px;\n"
            "  border-color: transparent;\n"
            "  background: transparent;\n"
            "  color: var(--muted);\n"
            "  font-size: 17px;\n"
            "  font-weight: 700;\n"
            "}",
            stylesheet,
        )
        self.assertIn("renderProcessTabs", javascript)
        self.assertIn(
            'processTabs: document.querySelector("#process-tabs")',
            javascript,
        )
        self.assertIn(
            "syncDetectionWithSimulation(app.status)",
            javascript,
        )
        self.assertIn("renderActiveProcessSchedule", javascript)
        self.assertIn("process_id=${app.detectionProcessId || 1}", javascript)
        self.assertIn(
            "process_id: Number(app.activeProcessId)",
            javascript,
        )
        self.assertIn("renderOrderBatches", javascript)
        self.assertIn("createOrderCard", javascript)
        for job_group_label in (
            "冲压中",
            "焊装中",
            "涂装中",
            "总装中",
            "已完成",
            "已取消",
        ):
            self.assertIn(f'label: "{job_group_label}"', javascript)
        self.assertIn("function jobGroupKey", javascript)
        self.assertNotIn("waiting-segment", javascript)
        self.assertIn("function operationDisplayName", javascript)
        self.assertIn(
            "bar.textContent = operationDisplayName(operation)",
            javascript,
        )
        self.assertIn(
            "chip.textContent = operationDisplayName(operation)",
            javascript,
        )
        self.assertIn("transportPlanSignature", javascript)
        self.assertIn("syncTransportPlan(activePlan)", javascript)
        self.assertIn(
            "renderPendingQueues(plan, app.serverTime, true)",
            javascript,
        )
        self.assertIn(
            "for (const operation of plan || []) {\n"
            "    if (TIMELINE_OPERATION_STATUSES.has(operation.status)) {\n"
            "      ensureBar(operation);\n"
            "    }\n"
            "  }\n"
            "  syncTransportPlan(plan);",
            javascript,
        )
        self.assertIn(
            'const TIMELINE_OPERATION_STATUSES = new Set([\n'
            '  "processing",\n'
            '  "completed",\n'
            "]);",
            javascript,
        )
        self.assertIn(
            "renderNow - app.lastPendingQueueRenderAt < 450",
            javascript,
        )
        self.assertNotIn(
            "chip.textContent = `J${operation.job_id}-O${operation.operation_id}`",
            javascript,
        )
        self.assertIn("cancel-order-checkbox", javascript)
        self.assertIn("selectedCancelOrderIds", javascript)
        self.assertIn("order_ids: orderIds", javascript)
        self.assertIn('setDashboardTab("machine-board")', javascript)
        self.assertIn("initializeMachineDetection", javascript)
        self.assertIn("pollDetectionOverview", javascript)
        self.assertIn("syncDetectionWithSimulation", javascript)
        self.assertIn("pauseDetectionPolling", javascript)
        self.assertIn("clearDetectionStream", javascript)
        self.assertIn(
            "Math.round(Number(app.speed || 1))",
            javascript,
        )
        self.assertIn("/api/detection/overview", javascript)
        self.assertIn("/api/detection/predict", javascript)
        self.assertIn("maybeRequestDetectionPrediction", javascript)
        self.assertIn(
            "numericTimestamp % interval !== 0",
            javascript,
        )
        self.assertIn(
            "maybeRequestDetectionPrediction(payload.t)",
            javascript,
        )
        self.assertIn("machine_count=", javascript)
        self.assertNotIn("/api/v1/stream", javascript)
        self.assertNotIn(
            "app.detectionMachines.length === 0",
            javascript,
        )
        self.assertIn("normalizedSeries", javascript)
        self.assertIn("animationDurationUpdate: 320", javascript)
        self.assertIn("visibleSlotLabels", javascript)
        self.assertIn("/api/stop", javascript)

    def test_prediction_alarms_inject_only_healthy_machines_once(self):
        manager = SimulationManager(
            config_path=DEFAULT_CONFIG_PATH,
            speed=2,
            realtime=False,
            anomaly_handling_enabled=True,
        )
        manager.simulator = SimpleNamespace(
            seed=42,
            machines=[
                SimpleNamespace(
                    machine_id=0,
                    machine_status="idle",
                    anomaly_type=None,
                ),
                SimpleNamespace(
                    machine_id=1,
                    machine_status="repairing",
                    anomaly_type="short_failure",
                ),
            ],
        )
        manager.state.status = "running"
        manager.state.generation = 1
        calls = []

        def inject(machine_id, anomaly_type, duration):
            calls.append((machine_id, anomaly_type, duration))
            machine = manager.simulator.machines[machine_id]
            machine.machine_status = "repairing"
            machine.anomaly_type = anomaly_type
            return {
                "machine_id": machine_id,
                "machine_status": "repairing",
                "event_id": machine_id + 10,
                "event_type": "MachineAnomalyEvent",
                "event_timestamp": 85,
                "recovery_time": 88,
            }

        manager.handle_machine_anomaly = inject
        predictions = [
            {"machine_id": 0, "is_alarm": True},
            {"machine_id": 0, "is_alarm": True},
            {"machine_id": 1, "is_alarm": True},
            {"machine_id": 9, "is_alarm": True},
            {"machine_id": 1, "is_alarm": False},
        ]

        first = manager.handle_prediction_alarms(85, predictions)
        second = manager.handle_prediction_alarms(85, predictions)

        selections = {
            manager._choose_prediction_anomaly(machine_id, 85)[0]
            for machine_id in range(8)
        }
        expected_anomaly, expected_duration = (
            manager._choose_prediction_anomaly(0, 85)
        )
        self.assertEqual(first["injected_machine_ids"], [0])
        self.assertEqual(
            calls,
            [(0, expected_anomaly.value, expected_duration)],
        )
        self.assertEqual(
            expected_duration,
            MACHINE_ANOMALY_DEFAULT_DURATIONS[expected_anomaly],
        )
        self.assertEqual(selections, set(MachineAnomalyType))
        self.assertEqual(
            first["injected_events"][0]["anomaly_type"],
            expected_anomaly.value,
        )
        self.assertTrue(second["duplicate"])
        self.assertEqual(len(calls), 1)
        self.assertEqual(
            {
                item["reason"]
                for item in first["skipped_machines"]
            },
            {"active_anomaly", "unknown_machine"},
        )

    def test_prediction_alarm_updates_real_machine_and_creates_events(self):
        simulator = Simulator(realtime=False)
        simulator.log_tag = False
        simulator.init()
        manager = SimulationManager(
            config_path=DEFAULT_CONFIG_PATH,
            speed=2,
            realtime=False,
            anomaly_handling_enabled=True,
        )
        manager.simulator = simulator
        manager.state.prepare(2)
        manager.state.selected_dataset = {
            "id": manager.default_dataset_id,
        }
        manager.state.set_running(simulator)

        expected_anomaly, expected_duration = (
            manager._choose_prediction_anomaly(0, 85)
        )
        result = manager.handle_prediction_alarms(
            85,
            [{"machine_id": 0, "is_alarm": True}],
        )

        machine = simulator.machines[0]
        self.assertEqual(result["injected_machine_ids"], [0])
        self.assertEqual(machine.anomaly_type, expected_anomaly.value)
        self.assertEqual(
            machine.recovery_time,
            machine.anomaly_started_at + expected_duration,
        )
        self.assertTrue(
            any(
                isinstance(event, MachineRecoveryEvent)
                and event.machine_id == 0
                for event in simulator.event_queue
            )
        )
        machine_state = next(
            state
            for state in manager.state.snapshot()["machine_states"]
            if state["id"] == 0
        )
        self.assertEqual(machine_state["status"], machine.machine_status)
        self.assertEqual(
            machine_state["anomaly_type"],
            expected_anomaly.value,
        )
        self.assertIn("materials", machine_state)
        self.assertTrue(machine_state["materials"])
        snapshot = manager.state.snapshot()
        self.assertTrue(snapshot["material_catalog"])

    def test_drl_scheduler_can_be_preloaded_and_reused(self):
        created = []

        class FakeScheduler:
            def __init__(self):
                created.append(self)

        manager = SimulationManager(
            config_path=DEFAULT_CONFIG_PATH,
            speed=5,
            realtime=False,
            scheduler_factory=FakeScheduler,
        )

        preloaded = manager.preload_scheduler()

        self.assertIs(preloaded, created[0])
        self.assertIs(manager._get_scheduler(), preloaded)
        self.assertEqual(len(created), 1)

    def test_reoptimization_requires_running_simulation(self):
        manager = SimulationManager(
            config_path=DEFAULT_CONFIG_PATH,
            speed=5,
            realtime=False,
        )

        with self.assertRaises(ValueError):
            manager.reoptimize(num_samples=1, seed=0)

    def test_operation_event_contains_animation_data(self):
        simulator = SimpleNamespace(
            jobs=[
                SimpleNamespace(
                    operation_times=[[17.0, 11.0]],
                )
            ]
        )
        event = OperationStartEvent(7, 12, 0, 0, 1)

        payload = serialize_event(event, simulator)

        self.assertEqual(payload["job_id"], 0)
        self.assertEqual(payload["machine_id"], 1)
        self.assertEqual(payload["processing_time"], 11.0)

    def test_display_percent_is_persisted_in_state(self):
        state = DashboardState(display_percent=100)

        state.set_display_percent(150)

        self.assertEqual(state.snapshot()["display_percent"], 150)

    def test_display_percent_range_is_validated(self):
        state = DashboardState()

        with self.assertRaises(ValueError):
            state.set_display_percent(301)

    def test_selected_dataset_starts_simulation(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            manager = SimulationManager(
                config_path=DEFAULT_CONFIG_PATH,
                speed=50,
                realtime=False,
                log_dir=temp_dir,
            )
            started = manager.start(manager.default_dataset_id)
            manager.thread.join(timeout=30)

        self.assertTrue(started)
        self.assertFalse(manager.thread.is_alive())
        self.assertEqual(manager.state.status, "finished")
        self.assertEqual(
            manager.state.selected_dataset["id"],
            manager.default_dataset_id,
        )
        self.assertTrue(
            any(
                operation.get("transport_time", 0) > 0
                for operation in manager.state.plan
            )
        )

    def test_stop_terminates_active_simulation_thread(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            manager = SimulationManager(
                config_path=DEFAULT_CONFIG_PATH,
                speed=1,
                realtime=True,
                log_dir=temp_dir,
            )
            self.assertTrue(manager.start(manager.default_dataset_id))
            deadline = time.monotonic() + 10
            while (
                manager.state.status != "running"
                and time.monotonic() < deadline
            ):
                time.sleep(0.01)
            self.assertEqual(manager.state.status, "running")

            result = manager.stop()

            self.assertEqual(result["status"], "stopped")
            self.assertFalse(manager.thread.is_alive())
            self.assertTrue(manager.simulator.stop_event.is_set())

    def test_finished_status_is_published_after_logger_finish(self):
        order = []

        class FakeLogger:
            def __init__(self, log_dir):
                self.log_dir = log_dir

            def start(self, metadata):
                return None

            def record_event(self, event, simulator):
                return None

            def record_reoptimization(self, request, response, simulator):
                return None

            def finish(self, simulator):
                order.append("logger_finish")

            def fail(self, error):
                return None

        manager = SimulationManager(
            config_path=DEFAULT_CONFIG_PATH,
            speed=50,
            realtime=False,
        )
        manager.selected_source = manager.datasets_by_id[
            manager.default_dataset_id
        ]
        original_state_finish = manager.state.finish

        def record_state_finish(simulator):
            order.append("state_finish")
            original_state_finish(simulator)

        manager.state.finish = record_state_finish
        with patch("web_app.SimulationRunLogger", FakeLogger):
            manager._run()

        self.assertEqual(order[-2:], ["logger_finish", "state_finish"])
        self.assertEqual(manager.state.status, "finished")

    def test_plan_serializes_transport_fields(self):
        operation = PlannedOperation(
            job_id=2,
            operation_id=3,
            machine_id=4,
            start_time=12,
            end_time=20,
            source_machine=1,
            transport_start=8,
            transport_end=11,
            transport_time=3,
            transport_energy=7,
            transport_segments=[
                {
                    "source_machine": 1,
                    "target_machine": 4,
                    "transport_start": 8,
                    "transport_end": 11,
                    "transport_time": 3,
                    "transport_energy": 7,
                    "completed": False,
                }
            ],
            waiting_time=1,
        )

        payload = serialize_plan([operation])[0]

        self.assertEqual(payload["source_machine"], 1)
        self.assertEqual(payload["transport_start"], 8)
        self.assertEqual(payload["transport_end"], 11)
        self.assertEqual(payload["transport_energy"], 7)
        self.assertEqual(payload["transport_segments"][0]["target_machine"], 4)
        self.assertEqual(payload["waiting_time"], 1)
        self.assertEqual(payload["status"], "scheduled")

    def test_model_reoptimization_updates_remaining_plan(self):
        simulator = Simulator(realtime=False)
        simulator.log_tag = False
        simulator.init()
        schedule = [
            {
                "job_id": job.job_id,
                "operation_index": task.operation_id,
                "operation_id": task.task_id,
                "machine_id": task.eligible_machines[-1],
            }
            for job in simulator.jobs
            for task in job.tasks
        ]

        class FakeScheduler:
            def predict(self, request):
                return {
                    "model": "fake.pt",
                    "num_samples": request["num_samples"],
                    "objectives": {
                        "makespan": 1,
                        "energy": 1,
                        "penalty": 1,
                    },
                    "schedule": schedule,
                }

        manager = SimulationManager(
            config_path=DEFAULT_CONFIG_PATH,
            speed=5,
            realtime=False,
            scheduler_factory=FakeScheduler,
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
        lifecycle = []
        simulator.pause = lambda: lifecycle.append("pause")
        simulator.resume = lambda: lifecycle.append("resume")

        result = manager.reoptimize_command(
            "DRL",
            {"num_samples": 1, "seed": 0},
        )

        self.assertTrue(result["success"])
        self.assertEqual(result["optimizer"], "drl")
        self.assertEqual(
            result["command_config"],
            {"num_samples": 1, "seed": 0},
        )
        self.assertEqual(result["model"], "fake.pt")
        self.assertGreater(result["unfinished_task_count"], 0)
        self.assertTrue(manager.state.plan)
        self.assertEqual(lifecycle, ["pause", "resume"])

    def test_hls_reoptimization_uses_only_machine_assignments(self):
        simulator = Simulator(realtime=False)
        simulator.log_tag = False
        simulator.init()
        simulator.updateEventQueue()
        while simulator.event_queue and simulator.event_queue[0].timestamp <= 15:
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
        schedule = [
            {
                "job_id": job.job_id,
                "operation_index": task.operation_id,
                "operation_id": task.task_id,
                "machine_id": task.eligible_machines[-1],
                "start_time": 50_000,
                "end_time": 50_010,
                "processing_time": 10,
            }
            for job in simulator.jobs
            for task in job.tasks
        ]
        requests = []

        class FakeHlsScheduler:
            def predict(self, request):
                requests.append(request)
                return {
                    "success": True,
                    "model": "production_scheduling",
                    "device": "cpu",
                    "objectives": {"makespan": 231},
                    "runtime_seconds": 0.01,
                    "seed": request["seed"],
                    "additional_data_used": False,
                    "additional_data_valid": True,
                    "feasible": True,
                    "schedule": schedule,
                }

        manager = SimulationManager(
            config_path=DEFAULT_CONFIG_PATH,
            speed=5,
            realtime=False,
            hls_scheduler_factory=FakeHlsScheduler,
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
        lifecycle = []
        simulator.pause = lambda: lifecycle.append("pause")
        simulator.resume = lambda: lifecycle.append("resume")

        result = manager.reoptimize_command(
            "HLS",
            {
                "seed": 17,
                "total_time_seconds": 1,
                "population_size": 8,
            },
        )

        self.assertTrue(result["success"])
        self.assertEqual(result["optimizer"], "hls")
        self.assertFalse(result["hls_schedule_times_used"])
        self.assertTrue(result["transport_time_recalculated"])
        self.assertEqual(result["hls_objectives"], {"makespan": 231})
        self.assertEqual(requests[0]["seed"], 17)
        self.assertEqual(requests[0]["total_time_seconds"], 1)
        self.assertEqual(requests[0]["population_size"], 8)
        self.assertTrue(requests[0]["raw_lines"])
        self.assertTrue(requests[0]["additional_lines"])
        self.assertGreater(result["unfinished_task_count"], 0)
        self.assertEqual(
            result["hls_assignment_count"],
            result["unfinished_task_count"],
        )
        self.assertEqual(lifecycle, ["pause", "resume"])

        processing_after = {
            (job.job_id, task.operation_id): task.assigned_machine
            for job in simulator.jobs
            for task in job.tasks
            if task.status == "processing"
        }
        self.assertEqual(processing_after, processing_before)
        planned_times = {
            operation.start_time
            for operation in simulator.planned_operations
        }
        self.assertNotIn(50_000, planned_times)
        self.assertTrue(
            any(
                operation.transport_time > 0
                for operation in simulator.planned_operations
            )
        )

    def test_hls_reoptimization_http_endpoint(self):
        calls = []

        class FakeManager:
            state = SimpleNamespace()

            def hls_reoptimize(
                self,
                seed=0,
                process_id=1,
                **options,
            ):
                calls.append(
                    {
                        "seed": seed,
                        "process_id": process_id,
                        **options,
                    }
                )
                return {"success": True, "optimizer": "hls"}

        server, thread = create_dashboard_server(
            "127.0.0.1",
            0,
            FakeManager(),
        )
        try:
            request = urllib.request.Request(
                (
                    "http://127.0.0.1:"
                    f"{server.server_address[1]}/api/hls-reoptimize"
                ),
                data=json.dumps(
                    {
                        "seed": 9,
                        "process_id": 3,
                        "total_time_seconds": 2,
                        "population_size": 12,
                    }
                ).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(request, timeout=5) as response:
                payload = json.loads(response.read().decode("utf-8"))
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)

        self.assertEqual(payload["optimizer"], "hls")
        self.assertEqual(
            calls,
            [
                {
                    "seed": 9,
                    "process_id": 3,
                    "total_time_seconds": 2,
                    "population_size": 12,
                }
            ],
        )

    def test_reoptimization_command_http_endpoint(self):
        calls = []

        class FakeManager:
            state = SimpleNamespace()

            def reoptimize_command(
                self,
                method,
                config,
                process_id=1,
            ):
                calls.append(
                    {
                        "method": method,
                        "config": config,
                        "process_id": process_id,
                    }
                )
                return {
                    "success": True,
                    "optimizer": str(method).lower(),
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
                    f"{server.server_address[1]}/api/reoptimize-command"
                ),
                data=json.dumps(
                    {
                        "method": "DRL",
                        "process_id": 2,
                        "config": {
                            "num_samples": 2,
                            "seed": 5,
                        },
                    }
                ).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(request, timeout=5) as response:
                payload = json.loads(response.read().decode("utf-8"))
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)

        self.assertEqual(payload["optimizer"], "drl")
        self.assertEqual(
            calls,
            [
                {
                    "method": "DRL",
                    "config": {"num_samples": 2, "seed": 5},
                    "process_id": 2,
                }
            ],
        )

    def test_reoptimization_command_validates_method_and_config(self):
        manager = SimulationManager(
            config_path=DEFAULT_CONFIG_PATH,
            speed=5,
            realtime=False,
        )

        with self.assertRaises(ValueError):
            manager.reoptimize_command("unknown", {})
        with self.assertRaises(ValueError):
            manager.reoptimize_command("DRL", {"unsupported": 1})
        with self.assertRaises(ValueError):
            manager.reoptimize_command("HLS", ["invalid"])

    def test_submit_random_job_http_endpoint(self):
        calls = []

        class FakeManager:
            state = SimpleNamespace()

            def submit_random_jobs(self, seed=0):
                calls.append(seed)
                return {
                    "success": True,
                    "optimizer": "dynamic_job_submit",
                    "new_jobs": [{"job_id": 15}],
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
                    f"{server.server_address[1]}/api/jobs/submit"
                ),
                data=json.dumps({"seed": 12}).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(request, timeout=5) as response:
                payload = json.loads(response.read().decode("utf-8"))
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)

        self.assertEqual(payload["new_jobs"][0]["job_id"], 15)
        self.assertEqual(calls, [12])

    def test_auto_job_submission_http_endpoint(self):
        calls = []
        auto_state = {
            "enabled": True,
            "triggered": False,
            "count": 0,
            "threshold": 5,
        }

        class FakeManager:
            state = SimpleNamespace(
                snapshot=lambda: {
                    "auto_job_submission": auto_state,
                }
            )

            def set_auto_job_submission(self, enabled):
                calls.append(enabled)
                auto_state["enabled"] = enabled

        server, thread = create_dashboard_server(
            "127.0.0.1",
            0,
            FakeManager(),
        )
        try:
            request = urllib.request.Request(
                (
                    "http://127.0.0.1:"
                    f"{server.server_address[1]}/api/auto-job-submission"
                ),
                data=json.dumps({"enabled": True}).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(request, timeout=5) as response:
                payload = json.loads(response.read().decode("utf-8"))
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)

        self.assertTrue(payload["ok"])
        self.assertEqual(calls, [True])
        self.assertEqual(
            payload["auto_job_submission"],
            auto_state,
        )

    def test_auto_machine_anomaly_http_endpoint(self):
        calls = []
        auto_state = {
            "enabled": True,
            "interval": 40,
            "count": 0,
            "next_time": 40,
            "last": None,
        }

        class FakeManager:
            def set_auto_machine_anomaly(self, enabled):
                calls.append(enabled)
                auto_state["enabled"] = enabled
                return {
                    "ok": True,
                    "auto_machine_anomaly": auto_state,
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
                    f"{server.server_address[1]}/api/auto-machine-anomaly"
                ),
                data=json.dumps({"enabled": True}).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(request, timeout=5) as response:
                payload = json.loads(response.read().decode("utf-8"))
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)

        self.assertTrue(payload["ok"])
        self.assertEqual(calls, [True])
        self.assertEqual(
            payload["auto_machine_anomaly"],
            auto_state,
        )

    def test_pause_and_resume_running_simulation(self):
        calls = []

        class FakeSimulator:
            def pause(self):
                calls.append("pause")

            def resume(self):
                calls.append("resume")

        manager = SimulationManager(
            config_path=DEFAULT_CONFIG_PATH,
            speed=5,
            realtime=False,
        )
        manager.simulator = FakeSimulator()
        manager.state.status = "running"

        paused = manager.set_paused(True)
        resumed = manager.set_paused(False)

        self.assertTrue(paused["paused"])
        self.assertEqual(paused["status"], "paused")
        self.assertFalse(resumed["paused"])
        self.assertEqual(resumed["status"], "running")
        self.assertEqual(calls, ["pause", "resume"])

    def test_pause_http_endpoint(self):
        calls = []

        class FakeManager:
            state = SimpleNamespace()

            def set_paused(self, paused):
                calls.append(paused)
                return {
                    "success": True,
                    "paused": paused,
                    "status": "paused" if paused else "running",
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
                    f"{server.server_address[1]}/api/pause"
                ),
                data=json.dumps({"paused": True}).encode("utf-8"),
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
        self.assertTrue(payload["paused"])
        self.assertEqual(calls, [True])

    def test_stop_http_endpoint(self):
        calls = []

        class FakeManager:
            def stop(self):
                calls.append(True)
                return {
                    "success": True,
                    "status": "stopped",
                    "stopped": True,
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
                    f"{server.server_address[1]}/api/stop"
                ),
                data=b"{}",
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
        self.assertEqual(payload["status"], "stopped")
        self.assertEqual(calls, [True])


if __name__ == "__main__":
    unittest.main()

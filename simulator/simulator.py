from system.job import Job, Task
from system.machine import Machine
from system.schedule import PlannedOperation, Schedule
from system.order import Order, OrderBatch
from simulator.event import *
from simulator.anomaly import (
    DEGRADED_PROCESSING_FACTOR,
    MachineAnomalyType,
    validate_machine_anomaly_duration,
)
from simulator.clock import SimulationClock
from simulator.config import DEFAULT_CONFIG_PATH, load_simulator_config
from simulator.dataset import (
    infer_process_id,
    infer_process_material_paths,
    load_multi_objective_dataset,
    load_process_material_data,
)
from simulator.job_generator import generate_random_job
import copy
import random
import time
import math
import heapq
import threading
from pathlib import Path

EVENT_QUEUE_PRIORITIES = {
    ScheduleEvent: 0,
    OrderInsertEvent: 1,
    OrderCancelEvent: 1,
    MachineAnomalyEvent: 1,
    JobSubmitEvent: 1,
    JobStartEvent: 2,
    TransportFinishEvent: 3,
    MachineRecoveryEvent: 3,
    MaterialReplenishmentEvent: 3,
    OperationStartEvent: 4,
    MaterialRecoveryEvent: 4,
    OperationFinishEvent: 5,
    ProcessStageFinishEvent: 6,
    ProcessStageBatchScheduleEvent: 7,
    JobFinishEvent: 8,
}
PROCESS_INTERSTAGE_TIME = {
    2: 2,
    3: 4,
    4: 3,
}
PROCESS_INTERSTAGE_ENERGY = {
    2: 3,
    3: 5,
    4: 4,
}
DEFAULT_MATERIAL_REPLENISHMENT_LEAD_TIME = 5.0
DEFAULT_MATERIAL_REPLENISHMENT_TARGET_FACTOR = 3.0


class Simulator:
    def __init__(
        self,
        real_time_step=None,
        speed=None,
        realtime=None,
        config_path=None,
    ):
        """
        初始化仿真器。

        参数:
            real_time_step: 覆盖配置文件中每个仿真步对应的现实时间（秒）
            speed: 覆盖配置文件中的仿真倍速
            realtime: 覆盖配置文件中的现实时间等待开关
            config_path: JSON 配置文件路径，默认使用项目根目录配置
        """
        self.config_path = Path(config_path or DEFAULT_CONFIG_PATH).expanduser()
        if not self.config_path.is_absolute():
            self.config_path = Path.cwd() / self.config_path
        self.config = load_simulator_config(self.config_path)
        self.config_dir = self.config_path.parent

        self.event_queue = []
        self.event_lock = threading.RLock()
        self.resume_event = threading.Event()
        self.resume_event.set()
        self.stop_event = threading.Event()
        self.machine_recovery_reoptimizer = None
        self.pending_event_timestamp = None
        self.curr_event_id = -1
        self.curr_time = 0

        self.jobs = []
        self.initial_job_count = 0
        self.machines = []
        self.process_definitions = []
        self.process_datasets = {}

        self.job_queue = []
        self.processing_queue = []
        self.finished_queue = []
        self.order_batches = []
        self.canceled_orders = []
        self.deferred_anomaly_tasks = {}
        self.pending_material_recoveries = {}
        self.scheduled_operations = []
        self.completed_operations = set()

        self.schedule = None
        self.makespan = 0
        self.total_processing_energy = 0
        self.total_transport_energy = 0
        self.total_auxiliary_energy = 0
        self.total_energy = 0
        self.total_penalty = 0
        self.transport_adjusted_makespan = 0
        self.objectives = {
            "makespan": 0,
            "energy": 0,
            "penalty": 0,
        }

        simulation_config = self.config["simulation"]
        path_config = self.config["paths"]

        self.log_tag = simulation_config["log_tag"]
        self.input_file = self._resolve_config_path(path_config["input_file"])
        self.additional_file = self._resolve_config_path(
            path_config["additional_file"]
        )
        self.schedule_file = self._resolve_config_path(
            path_config["schedule_file"]
        )
        self.gantt_file = self._resolve_config_path(path_config["gantt_file"])

        # 引入多目标优化相关参数
        self.seed = simulation_config["seed"]
        self.due_time_factor = simulation_config["due_time_factor"]
        self.auxiliary_energy = simulation_config["auxiliary_energy"]
        self.process_stage_batch_window = float(
            simulation_config.get("process_stage_batch_window", 10.0)
        )
        self.material_replenishment_lead_time = float(
            simulation_config.get(
                "material_replenishment_lead_time",
                DEFAULT_MATERIAL_REPLENISHMENT_LEAD_TIME,
            )
        )
        self.material_replenishment_target_factor = float(
            simulation_config.get(
                "material_replenishment_target_factor",
                DEFAULT_MATERIAL_REPLENISHMENT_TARGET_FACTOR,
            )
        )

        # 时钟设置：现实时间步与仿真时间步通过倍速关联
        time_config = self.config["time"]
        self.clock = SimulationClock(
            real_time_step=(
                time_config["real_time_step"]
                if real_time_step is None
                else real_time_step
            ),
            speed=time_config["speed"] if speed is None else speed,
            realtime=(
                time_config["realtime"] if realtime is None else realtime
            ),
        )
        self.clock.set_pause_event(self.resume_event)

    def _resolve_config_path(self, value):
        path = Path(value).expanduser()
        if not path.is_absolute():
            path = self.config_dir / path
        return str(path)

    def set_speed(self, speed):
        """运行时修改倍速，并从当前仿真时刻重新校准现实时钟。"""
        self.speed = speed

    @property
    def real_time_step(self):
        return self.clock.real_time_step

    @real_time_step.setter
    def real_time_step(self, value):
        self.clock.real_time_step = value

    @property
    def speed(self):
        return self.clock.speed

    @speed.setter
    def speed(self, value):
        self.clock.speed = value

    @property
    def simulation_time_step(self):
        return self.clock.simulation_time_step

    @property
    def realtime(self):
        return self.clock.realtime

    @realtime.setter
    def realtime(self, value):
        self.clock.realtime = value

    def _wait_until(self, simulation_timestamp):
        """等待到指定仿真时刻，使事件推进速度符合配置倍速。"""
        if self.stop_event.is_set():
            return False
        if not self.realtime:
            self.clock.wait_until(simulation_timestamp)
            return not self.stop_event.is_set()

        while self.clock.current_simulation_time < simulation_timestamp:
            if self.stop_event.is_set():
                return False
            chunk_end = min(
                simulation_timestamp,
                self.clock.current_simulation_time
                + max(0.001, self.speed * 0.05),
            )
            self.clock.wait_until(chunk_end)
            with self.event_lock:
                if (
                    not self.event_queue
                    or self.event_queue[0].timestamp != simulation_timestamp
                ):
                    return False
        return True

    def pause(self):
        self.clock.pause()

    def resume(self):
        self.clock.resume()

    def stop(self):
        """Stop event processing and unblock the simulation runner."""
        self.stop_event.set()
        self.clock.resume()
        self.clock.stop()

    @staticmethod
    def _transition_time(source_stage, target_stage):
        if source_stage == target_stage:
            return 0
        first = min(source_stage, target_stage)
        last = max(source_stage, target_stage)
        return sum(
            PROCESS_INTERSTAGE_TIME[stage]
            for stage in range(first + 1, last + 1)
        )

    @staticmethod
    def _transition_energy(source_stage, target_stage):
        if source_stage == target_stage:
            return 0
        first = min(source_stage, target_stage)
        last = max(source_stage, target_stage)
        return sum(
            PROCESS_INTERSTAGE_ENERGY[stage]
            for stage in range(first + 1, last + 1)
        )

    @staticmethod
    def _load_source_material_data(source, dataset):
        inventory_path = source.get("material_inventory_file")
        consumption_path = source.get("material_consumption_file")
        if inventory_path is None or consumption_path is None:
            inferred_inventory, inferred_consumption = (
                infer_process_material_paths(source["additional_file"])
            )
            inventory_path = inventory_path or inferred_inventory
            consumption_path = consumption_path or inferred_consumption
        return load_process_material_data(
            inventory_path,
            consumption_path,
            int(source["id"]),
            dataset.num_jobs,
            dataset.num_machines,
            operation_counts=[
                job.operation_count for job in dataset.jobs
            ],
        )

    def _init_process_chain(self, process_sources):
        ordered_sources = sorted(
            process_sources,
            key=lambda source: int(source["id"]),
        )
        stage_datasets = []
        for source in ordered_sources:
            stage_datasets.append(
                load_multi_objective_dataset(
                    source["raw_file"],
                    source["additional_file"],
                    source.get("delivery_cost_file"),
                )
            )
        stage_material_data = [
            self._load_source_material_data(source, dataset)
            for source, dataset in zip(ordered_sources, stage_datasets)
        ]
        if not stage_datasets:
            raise ValueError("No process datasets are available.")
        job_count = stage_datasets[0].num_jobs
        if any(
            dataset.num_jobs != job_count
            for dataset in stage_datasets[1:]
        ):
            raise ValueError(
                "All process datasets must contain the same Job count."
            )

        machine_offsets = {}
        total_machines = 0
        for source, dataset in zip(ordered_sources, stage_datasets):
            stage_id = int(source["id"])
            machine_offsets[stage_id] = total_machines
            total_machines += dataset.num_machines

        transport_time = [
            [0.0] * total_machines for _ in range(total_machines)
        ]
        transport_energy = [
            [0.0] * total_machines for _ in range(total_machines)
        ]
        for source, dataset in zip(ordered_sources, stage_datasets):
            stage_id = int(source["id"])
            offset = machine_offsets[stage_id]
            for row_index, row in enumerate(dataset.transport_time):
                for column_index, value in enumerate(row):
                    transport_time[offset + row_index][
                        offset + column_index
                    ] = value
            for row_index, row in enumerate(dataset.transport_energy):
                for column_index, value in enumerate(row):
                    transport_energy[offset + row_index][
                        offset + column_index
                    ] = value
        for source_stage, source_dataset in zip(
            ordered_sources,
            stage_datasets,
        ):
            for target_stage, target_dataset in zip(
                ordered_sources,
                stage_datasets,
            ):
                source_id = int(source_stage["id"])
                target_id = int(target_stage["id"])
                if source_id == target_id:
                    continue
                source_offset = machine_offsets[source_id]
                target_offset = machine_offsets[target_id]
                time_value = self._transition_time(
                    source_id,
                    target_id,
                )
                energy_value = self._transition_energy(
                    source_id,
                    target_id,
                )
                for source_machine in range(source_dataset.num_machines):
                    for target_machine in range(
                        target_dataset.num_machines
                    ):
                        transport_time[
                            source_offset + source_machine
                        ][target_offset + target_machine] = time_value
                        transport_energy[
                            source_offset + source_machine
                        ][target_offset + target_machine] = energy_value

        merged_jobs = []
        global_task_id = 0
        for job_index in range(job_count):
            base_job = stage_datasets[0].jobs[job_index]
            base_job.material_consumption = {}
            merged_tasks = []
            operation_times = []
            operation_energy = []
            global_operation_id = 0
            for source, dataset, material_data in zip(
                ordered_sources,
                stage_datasets,
                stage_material_data,
            ):
                stage_id = int(source["id"])
                offset = machine_offsets[stage_id]
                stage_job = dataset.jobs[job_index]
                stage_job_materials = dict(
                    material_data.job_consumption.get(job_index, {})
                )
                stage_task_materials = material_data.task_consumption.get(
                    job_index,
                    {},
                )
                base_job.material_consumption[stage_id] = {
                    "job_materials": stage_job_materials,
                    "tasks": {
                        operation_id: dict(materials)
                        for operation_id, materials
                        in stage_task_materials.items()
                    },
                }
                for stage_task in stage_job.tasks:
                    processing_times = {
                        offset + machine_id: value
                        for machine_id, value in (
                            stage_task.processing_times.items()
                        )
                    }
                    processing_energies = {
                        offset + machine_id: value
                        for machine_id, value in (
                            stage_task.processing_energies.items()
                        )
                    }
                    task = Task(
                        task_id=global_task_id,
                        job_id=job_index,
                        operation_id=global_operation_id,
                        processing_times=processing_times,
                        processing_energies=processing_energies,
                        predecessor_id=(
                            global_task_id - 1
                            if global_operation_id > 0
                            else None
                        ),
                        stage_id=stage_id,
                        stage_operation_id=(
                            stage_task.operation_id
                        ),
                        material_consumption=(
                            stage_task_materials.get(
                                stage_task.operation_id,
                                {},
                            )
                        ),
                    )
                    merged_tasks.append(task)
                    operation_times.append(
                        [float("inf") for _ in range(total_machines)]
                    )
                    operation_energy.append(
                        [float("inf") for _ in range(total_machines)]
                    )
                    time_row = processing_times
                    energy_row = processing_energies
                    for machine_id, value in time_row.items():
                        operation_times[global_operation_id][
                            machine_id
                        ] = value
                    for machine_id, value in energy_row.items():
                        operation_energy[global_operation_id][
                            machine_id
                        ] = value
                    global_task_id += 1
                    global_operation_id += 1
            for operation_index in range(len(merged_tasks) - 1):
                merged_tasks[operation_index].successor_id = (
                    merged_tasks[operation_index + 1].task_id
                )
            for task in merged_tasks:
                if task.stage_id > 1:
                    task.status = "blocked"
            base_job.operation_count = len(merged_tasks)
            base_job.tasks = merged_tasks
            base_job.operation_times = operation_times
            base_job.operation_energy = operation_energy
            base_job.transport_time_matrix = transport_time
            base_job.transport_energy_matrix = transport_energy
            merged_jobs.append(base_job)

        self.dataset = stage_datasets[0]
        self.process_datasets = {
            int(source["id"]): dataset
            for source, dataset in zip(
                ordered_sources,
                stage_datasets,
            )
        }
        self.jobs = merged_jobs
        self.initial_job_count = len(merged_jobs)
        self.transport_time = transport_time
        self.transport_energy = transport_energy
        self.machines = []
        for source, dataset, material_data in zip(
            ordered_sources,
            stage_datasets,
            stage_material_data,
        ):
            stage_id = int(source["id"])
            offset = machine_offsets[stage_id]
            for local_machine_id in range(dataset.num_machines):
                global_machine_id = offset + local_machine_id
                machine = Machine(
                    global_machine_id,
                    "idle",
                    0,
                    transport_time[global_machine_id],
                    transport_energy[global_machine_id],
                    stage_id=stage_id,
                    local_machine_id=local_machine_id + 1,
                    materials=material_data.inventory.get(
                        local_machine_id + 1,
                        {},
                    ),
                )
                self.machines.append(machine)
        self.process_definitions = [
            {
                "id": int(source["id"]),
                "name": source["name"],
                "machine_count": dataset.num_machines,
                "machine_offset": machine_offsets[int(source["id"])],
                "detection_start_t": int(
                    source.get("detection_start_t", 0)
                ),
            }
            for source, dataset in zip(
                ordered_sources,
                stage_datasets,
            )
        ]
        items = [[] for _ in range(total_machines)]
        start = [[] for _ in range(total_machines)]
        end = [[] for _ in range(total_machines)]
        self.scheduled_operations = [
            [] for _ in range(total_machines)
        ]
        self.schedule = Schedule(
            0,
            total_machines,
            items,
            start,
            end,
        )
        self.order_batches = []
        self.registerOrderBatch(
            [job.job_id for job in self.jobs],
            0.0,
            source="initial",
        )
        self.job_queue = [
            Order(job.job_id, job.priority, job.ready_time)
            for job in self.jobs
        ]
        self.processing_queue = []
        self.finished_queue = []
        self.canceled_orders = []
        self.deferred_anomaly_tasks = {}
        self.handleScheduleEvent(ScheduleEvent(self.newEventId(), 0))

    def init(
        self,
        file_path=None,
        additional_file_path=None,
        process_sources=None,
        process_chain=False,
    ):
        """读取多目标优化数据，初始化工件、任务和机器。"""
        raw_path = Path(file_path or self.input_file)
        if additional_file_path is not None:
            additional_path = Path(additional_file_path)
        elif file_path is not None and raw_path.parent.name == "raw":
            additional_path = raw_path.parent.parent / "add" / raw_path.name
        else:
            additional_path = Path(self.additional_file)

        if process_chain and process_sources:
            self._init_process_chain(process_sources)
            return

        dataset = load_multi_objective_dataset(raw_path, additional_path)
        self.dataset = dataset
        self.jobs = list(dataset.jobs)
        self.initial_job_count = len(self.jobs)
        machine_count = dataset.num_machines
        self.transport_time = dataset.transport_time
        self.transport_energy = dataset.transport_energy
        process_id = infer_process_id(additional_path) or 1
        material_data = self._load_source_material_data(
            {
                "id": process_id,
                "additional_file": str(additional_path),
            },
            dataset,
        )
        for job in self.jobs:
            job.material_consumption = {}
            if process_id == 1:
                job.material_consumption[1] = {
                    "job_materials": dict(
                        material_data.job_consumption.get(
                            job.job_id,
                            {},
                        )
                    ),
                    "tasks": {},
                }
                continue
            task_materials = material_data.task_consumption.get(
                job.job_id,
                {},
            )
            job.material_consumption[process_id] = {
                "job_materials": {},
                "tasks": {
                    operation_id: dict(materials)
                    for operation_id, materials
                    in task_materials.items()
                },
            }
            for task in job.tasks:
                task.material_consumption = dict(
                    task_materials.get(task.operation_id, {})
                )

        self.machines = []
        for machine_id in range(machine_count):
            self.machines.append(
                Machine(
                    machine_id,
                    "idle",
                    0,
                    dataset.transport_time[machine_id],
                    dataset.transport_energy[machine_id],
                    stage_id=process_id,
                    local_machine_id=machine_id + 1,
                    materials=material_data.inventory.get(
                        machine_id + 1,
                        {},
                    ),
                )
            )

        # 初始化调度相关的数据结构
        items = [[] for _ in range(machine_count)]
        start = [[] for _ in range(machine_count)]
        end = [[] for _ in range(machine_count)]
        
        # 初始化每台机器的调度工序列表
        self.scheduled_operations = [[] for _ in range(machine_count)]
        
        # 初始化调度对象
        self.schedule = Schedule(0, machine_count, items, start, end)

        # 初始数据源中的所有 Job 属于同一个初始订单。
        self.order_batches = []
        self.registerOrderBatch(
            [job.job_id for job in self.jobs],
            0.0,
            source="initial",
        )

        # 初始化时为所有 Job 创建 Order，等待初始 ScheduleEvent 调度
        self.job_queue = [
            Order(job.job_id, job.priority, job.ready_time)
            for job in self.jobs
        ]
        self.processing_queue = []
        self.finished_queue = []
        self.canceled_orders = []
        self.deferred_anomaly_tasks = {}

        # 初始 ScheduleEvent 从 job_queue 获取作业，生成完整机器队列
        self.handleScheduleEvent(ScheduleEvent(self.newEventId(), 0))

    @staticmethod
    def _orderTimestampLabel(timestamp):
        numeric_timestamp = float(timestamp)
        if numeric_timestamp.is_integer():
            return str(int(numeric_timestamp))
        return f"{numeric_timestamp:g}"

    def registerOrderBatch(self, job_ids, submitted_at, source="manual"):
        """Register one submitted Job batch as a timestamp-named order."""
        submitted_at = float(submitted_at)
        existing_ids = {
            order_batch.order_id for order_batch in self.order_batches
        }
        base_id = f"T+{self._orderTimestampLabel(submitted_at)}"
        order_id = base_id
        duplicate_index = 2
        while order_id in existing_ids:
            order_id = f"{base_id}#{duplicate_index}"
            duplicate_index += 1
        order_batch = OrderBatch(
            order_id,
            submitted_at,
            job_ids,
            source=source,
        )
        self.order_batches.append(order_batch)
        return order_batch

    def orderBatchJobIds(self, order_ids):
        """Resolve order IDs to their complete, de-duplicated Job sets."""
        normalized_order_ids = []
        for order_id in order_ids:
            normalized_order_id = str(order_id)
            if normalized_order_id not in normalized_order_ids:
                normalized_order_ids.append(normalized_order_id)
        batches_by_id = {
            order_batch.order_id: order_batch
            for order_batch in self.order_batches
        }
        unknown_order_ids = [
            order_id
            for order_id in normalized_order_ids
            if order_id not in batches_by_id
        ]
        if unknown_order_ids:
            raise ValueError(
                "Unknown order_ids: " + ", ".join(unknown_order_ids)
            )
        job_ids = []
        for order_id in normalized_order_ids:
            for job_id in batches_by_id[order_id].job_ids:
                if job_id not in job_ids:
                    job_ids.append(job_id)
        return normalized_order_ids, job_ids

    def _markCanceledOrderBatches(self, order_ids, canceled_at):
        normalized_ids = set(str(order_id) for order_id in order_ids)
        for order_batch in self.order_batches:
            if order_batch.order_id not in normalized_ids:
                continue
            if all(
                self.jobs[job_id].is_canceled
                for job_id in order_batch.job_ids
            ):
                order_batch.canceled_at = float(canceled_at)

    def run(self):
        start_time = time.monotonic()
        self.clock.start(self.curr_time)
        self.updateEventQueue()

        if self.log_tag:
            print(
                "Simulation clock: "
                f"real_time_step={self.real_time_step:g}s, "
                f"speed={self.speed:g}x, "
                f"simulation_time_step={self.simulation_time_step:g}"
            )

        try:
            recovery_attempts = 0
            while not self.stop_event.is_set():
                self._drainEventQueue()
                if self.stop_event.is_set():
                    break
                if not self._recoverUnscheduledOperations():
                    break
                recovery_attempts += 1
                if recovery_attempts > 10:
                    break
        finally:
            self.pending_event_timestamp = None
            self.clock.stop()

        if self.stop_event.is_set():
            self.calculateObjectives()
            return False
        self._validateSimulationCompletion()
        if self.log_tag:
            print(f"\nSimulation finished at time {self.makespan}.")
        elapsed_real_time = time.monotonic() - start_time
        if self.log_tag:
            print(f"Total simulation time: {elapsed_real_time:.2f} seconds.")
        self.calculateObjectives()
        self.schedule.printItems(self.schedule_file, self.gantt_file, self.machines)
        self.schedule.testSchedule()
        return True

    def _drainEventQueue(self):
        while self.event_queue:
            with self.event_lock:
                self._discardStaleTransportEvents()
                if not self.event_queue:
                    break
                target_timestamp = self.event_queue[0].timestamp
                self.pending_event_timestamp = target_timestamp

            if not self._wait_until(target_timestamp):
                if self.stop_event.is_set():
                    self.pending_event_timestamp = None
                    return
                continue

            with self.event_lock:
                self._discardStaleTransportEvents()
                if not self.event_queue:
                    self.pending_event_timestamp = None
                    break
                event = self.event_queue[0]
                if event.timestamp != target_timestamp:
                    continue
                if event.timestamp < self.curr_time:
                    self.event_queue.pop(0)
                    self.printEvent(event)
                    print(
                        "Warning: Event "
                        f"{event.id} has a timestamp earlier than "
                        f"the current time ({event.timestamp} < "
                        f"{self.curr_time}). Skipping."
                    )
                    self.pending_event_timestamp = None
                    continue
                self.event_queue.pop(0)
                self.curr_time = event.timestamp
                self.handleEvent(event)
                self.updateEventQueue()
                self.pending_event_timestamp = None

    def _recoverUnscheduledOperations(self):
        unfinished = [
            task
            for job in self.jobs
            if not job.is_canceled
            for task in job.tasks
            if task.status in {"pending", "scheduled", "processing"}
        ]
        if not unfinished:
            return False
        assignments = self._greedyUnfinishedAssignments()
        has_processing = any(
            task.status == "processing" for task in unfinished
        )
        if not assignments and not has_processing:
            return False
        if self.log_tag:
            print(
                "Rebuilding unfinished schedule after event queue "
                f"became empty: {len(unfinished)} operations."
            )
        self.reoptimizeUnfinishedOperations(
            assignments,
            current_time=max(
                self.curr_time,
                self.clock.current_simulation_time,
            ),
        )
        return bool(self.event_queue)

    def _validateSimulationCompletion(self):
        unfinished = [
            {
                "job_id": job.job_id,
                "operation_id": task.operation_id,
                "status": task.status,
                "machine_id": task.assigned_machine,
            }
            for job in self.jobs
            for task in job.tasks
            if task.status in {"pending", "scheduled", "processing"}
        ]
        if not unfinished:
            return
        preview = ", ".join(
            f"{item['job_id']}-{item['operation_id']}"
            f"({item['status']})"
            for item in unfinished[:12]
        )
        raise RuntimeError(
            "Simulation event queue is empty but unfinished operations "
            f"remain: count={len(unfinished)}, operations={preview}."
        )

    def printEvent(self, event):
        print()
        print(f"Event ID: {event.id}")
        print(f"Timestamp: {event.timestamp}")
        print(f"event type: {type(event).__name__}")
        if isinstance(event, JobStartEvent):
            print(f"Job Start: Job ID {event.job_id}")
        elif isinstance(event, JobFinishEvent):
            print(f"Job Finish: Job ID {event.job_id}")
        elif isinstance(event, TransportFinishEvent):
            print(
                "Transport Finish: "
                f"Job ID {event.job_id}, Operation ID {event.operation_id}, "
                f"Machine ID {event.machine_id}"
            )
        elif isinstance(event, OperationStartEvent):
            print(f"Operation Start: Job ID {event.job_id}, Operation ID {event.operation_id}, Machine ID {event.machine_id}")
        elif isinstance(event, OperationFinishEvent):
            print(f"Operation Finish: Job ID {event.job_id}, Operation ID {event.operation_id}, Machine ID {event.machine_id}")
        elif isinstance(event, OrderInsertEvent):
            print(
                "Order Inserted: "
                f"Job IDs {event.job_ids or 'pending'}, "
                f"Seed {event.seed}"
            )
        elif isinstance(event, OrderCancelEvent):
            print(f"Orders Canceled: Job IDs {event.job_ids}")
        elif isinstance(event, MachineAnomalyEvent):
            print(
                "Machine Anomaly: "
                f"Machine ID {event.machine_id}, "
                f"Type {event.anomaly_type}, "
                f"Duration {event.duration}"
            )
        elif isinstance(event, MachineRecoveryEvent):
            print(
                "Machine Recovery: "
                f"Machine ID {event.machine_id}, "
                f"Type {event.anomaly_type}"
            )
        elif isinstance(event, MaterialReplenishmentEvent):
            print(
                "Material Replenishment: "
                f"Machine ID {event.machine_id}, "
                f"Job ID {event.job_id}, "
                f"Operation ID {event.operation_id}, "
                f"Materials {event.replenishment_materials}"
            )
        elif isinstance(event, MaterialRecoveryEvent):
            print(
                "Material Recovery: "
                f"Machine ID {event.machine_id}, "
                f"Job ID {event.job_id}, "
                f"Operation ID {event.operation_id}"
            )
        # elif isinstance(event, OrderAddEvent):
        #     print(f"Order Added: Job ID {event.job_id}, Priority {event.priority}")
        # elif isinstance(event, OrderDeleteEvent):
        #     print(f"Order Deleted: Job ID {event.job_id}")
        # elif isinstance(event, OrderUpdateEvent):
        #     print(f"Order Updated: Job ID {event.job_id}, New Priority {event.new_priority}")
        # elif isinstance(event, OperationTimeUpdateEvent):
        #     print(f"Operation Time Updated: Job ID {event.job_id}, Operation ID {event.operation_id}, Machine ID {event.machine_id}, New Time {event.new_time}")
        print()

    def addEvent(self, event):
        self.event_queue.append(event)

    def dispatchEventImmediately(self, event):
        """Process an externally triggered event at the current simulation time."""
        with self.event_lock:
            event.timestamp = max(
                float(event.timestamp),
                float(self.curr_time),
            )
            self.event_queue.append(event)
            self.updateEventQueue()
            try:
                self.event_queue.remove(event)
                self.curr_time = max(self.curr_time, event.timestamp)
                return self.handleEvent(event)
            finally:
                self.updateEventQueue()

    def scheduleTransportFinishEvents(
        self,
        planned_operations,
        after_time=0,
    ):
        for operation in planned_operations:
            task = self.jobs[operation.job_id].tasks[
                operation.operation_id
            ]
            if task.transport_segments:
                for segment in task.transport_segments:
                    if (
                        segment["completed"]
                        or segment["transport_time"] <= 0
                        or segment["transport_end"] is None
                        or segment["transport_end"] < after_time
                    ):
                        continue
                    self.addEvent(
                        TransportFinishEvent(
                            self.newEventId(),
                            segment["transport_end"],
                            operation.job_id,
                            operation.operation_id,
                            segment["target_machine"],
                        )
                    )
                continue
            if (
                operation.transport_time <= 0
                or operation.transport_end is None
                or operation.transport_end < after_time
            ):
                continue
            if task.transport_completed:
                continue
            self.addEvent(
                TransportFinishEvent(
                    self.newEventId(),
                    operation.transport_end,
                    operation.job_id,
                    operation.operation_id,
                    operation.machine_id,
                )
            )

    def _isCurrentTransportFinishEvent(self, event):
        """Return whether a transport event still matches the active task plan."""
        try:
            task = self.jobs[event.job_id].tasks[event.operation_id]
        except (IndexError, TypeError):
            return False

        if task.status not in {"pending", "scheduled", "canceled"}:
            return False
        if task.actual_start is not None:
            return False
        predecessor_end = None
        if event.operation_id > 0:
            predecessor = self.jobs[event.job_id].tasks[
                event.operation_id - 1
            ]
            if (
                predecessor.status != "completed"
                or predecessor.actual_end is None
            ):
                return False
            predecessor_end = predecessor.actual_end
        if task.transport_segments:
            current_segment = next(
                (
                    segment
                    for segment in task.transport_segments
                    if (
                        not segment["completed"]
                        and segment["target_machine"] == event.machine_id
                        and segment["transport_end"] is not None
                        and math.isclose(
                            float(event.timestamp),
                            float(segment["transport_end"]),
                            rel_tol=0,
                            abs_tol=1e-9,
                        )
                    )
                ),
                None,
            )
            if current_segment is None:
                return False
            return (
                predecessor_end is None
                or current_segment["transport_start"] is not None
                and current_segment["transport_start"]
                >= predecessor_end - 1e-9
            )
        return (
            predecessor_end is None
            or task.transport_start is not None
            and task.transport_start >= predecessor_end - 1e-9
        ) and (
            not task.transport_completed
            and task.assigned_machine == event.machine_id
            and task.transport_end is not None
            and math.isclose(
                float(event.timestamp),
                float(task.transport_end),
                rel_tol=0,
                abs_tol=1e-9,
            )
        )

    def _discardStaleTransportEvents(self):
        """Remove obsolete transport events before they can advance sim time."""
        while (
            self.event_queue
            and isinstance(self.event_queue[0], TransportFinishEvent)
            and not self._isCurrentTransportFinishEvent(
                self.event_queue[0]
            )
        ):
            stale_event = self.event_queue.pop(0)
            if self.log_tag:
                print(
                    "Discarding stale transport event "
                    f"{stale_event.id} for job {stale_event.job_id}, "
                    f"operation {stale_event.operation_id}, "
                    f"machine {stale_event.machine_id} at "
                    f"time {stale_event.timestamp}."
                )

    def clearMachineScheduleQueue(self, machine_id):
        self.machines[machine_id].clearPendingOperations()
        self.scheduled_operations[machine_id] = []

    def cancelJob(self, job_id, current_time=None, reschedule=True):
        """
        Cancel a Job while preserving any operation already being processed.

        All future operations of the Job are marked canceled and removed from
        machine queues, plans and pending events. The active operation keeps
        its finish event so it can complete normally.
        """
        if isinstance(job_id, bool):
            raise ValueError("job_id must be an integer.")
        try:
            job_id = int(job_id)
        except (TypeError, ValueError) as exc:
            raise ValueError("job_id must be an integer.") from exc
        if not 0 <= job_id < len(self.jobs):
            raise ValueError(f"Unknown job_id: {job_id}")

        job = self.jobs[job_id]
        if job.is_canceled:
            return {
                "success": True,
                "job_id": job_id,
                "status": "canceled",
                "already_canceled": True,
                "canceled_at": job.canceled_at,
                "removed_operation_count": 0,
                "removed_operations": [],
                "processing_operations": [
                    self._taskCancellationData(task)
                    for task in job.tasks
                    if (
                        task.status == "processing"
                        and task.actual_end is None
                    )
                ],
                "canceled_job_ids": [
                    order.job_id for order in self.canceled_orders
                ],
                "greedy_reschedule": {
                    "applied": False,
                    "unfinished_task_count": 0,
                    "moved_operation_count": 0,
                    "transport_time_added": 0,
                    "transport_energy_added": 0,
                },
            }

        now = max(
            float(self.curr_time),
            float(self.clock.current_simulation_time),
        )
        if current_time is not None:
            now = max(now, float(current_time))

        processing_tasks = [
            task
            for task in job.tasks
            if task.status == "processing" and task.actual_end is None
        ]
        preserved_operation_keys = {
            (job_id, task.operation_id) for task in processing_tasks
        }
        removed_tasks = [
            task
            for task in job.tasks
            if task.status not in {"processing", "completed"}
        ]
        removed_operation_keys = {
            (job_id, task.operation_id) for task in removed_tasks
        }
        transport_started_keys = {
            (job_id, task.operation_id)
            for task in removed_tasks
            if (
                task.operation_id > 0
                and (
                    task.transport_completed
                    or (
                        task.transport_start is not None
                        and task.transport_start <= now + 1e-9
                    )
                )
            )
        }
        transport_in_progress_keys = {
            (job_id, task.operation_id)
            for task in removed_tasks
            if (
                (job_id, task.operation_id) in transport_started_keys
                and not task.transport_completed
                and task.transport_end is not None
                and task.transport_end >= now - 1e-9
            )
        }
        removed_operations = [
            self._taskCancellationData(task) for task in removed_tasks
        ]

        order = None
        for queue in (
            self.job_queue,
            self.processing_queue,
            self.finished_queue,
        ):
            for existing_order in list(queue):
                if existing_order.job_id == job_id:
                    if order is None:
                        order = existing_order
                    queue.remove(existing_order)
        if order is None:
            order = Order(job_id, job.priority, job.ready_time)
        order.status = "canceled"
        order.canceled_at = now
        self.canceled_orders.append(order)

        job.canceled_at = now
        for task in removed_tasks:
            task.status = "canceled"
            task.waiting_time = 0
            operation_key = (job_id, task.operation_id)
            if operation_key in transport_started_keys:
                if (
                    task.transport_end is not None
                    and task.transport_end <= now + 1e-9
                ):
                    task.transport_completed = True
                    task.current_location_machine = (
                        task.assigned_machine
                    )
                continue

            task.source_machine = None
            task.transport_start = None
            task.transport_end = None
            task.transport_time = 0
            task.transport_energy = 0
            task.transport_completed = False
            task.committed_transport_energy = 0
            task.transport_segments = []
            task.current_location_machine = None

        self.planned_operations = [
            operation
            for operation in self.planned_operations
            if (
                operation.job_id,
                operation.operation_id,
            ) not in removed_operation_keys
        ]
        for machine_id, machine in enumerate(self.machines):
            machine.pending_operations = [
                operation
                for operation in machine.pending_operations
                if operation.job_id != job_id
            ]
            self.scheduled_operations[machine_id] = [
                item
                for item in self.scheduled_operations[machine_id]
                if item[0] != job_id
            ]

        def keep_event(event):
            if isinstance(
                event,
                (
                    JobSubmitEvent,
                    JobStartEvent,
                    JobFinishEvent,
                ),
            ):
                return event.job_id != job_id
            if isinstance(
                event,
                (
                    TransportFinishEvent,
                    OperationStartEvent,
                    OperationFinishEvent,
                    MaterialReplenishmentEvent,
                    MaterialRecoveryEvent,
                ),
            ):
                operation_key = (event.job_id, event.operation_id)
                if operation_key in preserved_operation_keys:
                    return isinstance(event, OperationFinishEvent)
                if (
                    operation_key in transport_in_progress_keys
                    and isinstance(event, TransportFinishEvent)
                ):
                    return True
                return event.job_id != job_id
            return True

        self.event_queue = [
            event for event in self.event_queue if keep_event(event)
        ]

        for machine_id, machine in enumerate(self.machines):
            processing = [
                task
                for job_item in self.jobs
                for task in job_item.tasks
                if (
                    task.status == "processing"
                    and task.actual_end is None
                    and task.assigned_machine == machine_id
                )
            ]
            first_operation = machine.nextPendingOperation()
            if processing:
                machine.machine_status = "busy"
                machine.ready_time = max(
                    now,
                    max(self._taskEffectiveEnd(task) for task in processing),
                    *(
                        [operation.end_time for operation in machine.pending_operations]
                        or [now]
                    ),
                )
                continue
            if first_operation is None:
                machine.machine_status = "idle"
                machine.ready_time = now
                continue

            machine.machine_status = "scheduled"
            machine.ready_time = max(
                now,
                max(
                    operation.end_time
                    for operation in machine.pending_operations
                ),
            )
            start_time = max(now, first_operation.start_time)
            existing_start = next(
                (
                    event
                    for event in self.event_queue
                    if (
                        isinstance(event, OperationStartEvent)
                        and event.job_id == first_operation.job_id
                        and event.operation_id
                        == first_operation.operation_id
                        and event.machine_id == first_operation.machine_id
                    )
                ),
                None,
            )
            if existing_start is None:
                self.addEvent(
                    OperationStartEvent(
                        self.newEventId(),
                        start_time,
                        first_operation.job_id,
                        first_operation.operation_id,
                        first_operation.machine_id,
                    )
                )
            elif existing_start.timestamp < now:
                existing_start.timestamp = now

        self.updateEventQueue()
        self.refreshRealtimeObjectives()
        greedy_reschedule = (
            self._greedyRescheduleUnfinished(now)
            if reschedule
            else {
                "applied": False,
                "unfinished_task_count": 0,
                "moved_operation_count": 0,
                "transport_time_added": 0,
                "transport_energy_added": 0,
            }
        )
        processing_operations = [
            self._taskCancellationData(task)
            for task in processing_tasks
        ]
        result = {
            "success": True,
            "job_id": job_id,
            "status": "canceled",
            "already_canceled": False,
            "canceled_at": now,
            "removed_operation_count": len(removed_operations),
            "removed_operations": removed_operations,
            "processing_operations": processing_operations,
            "canceled_job_ids": [
                canceled.job_id for canceled in self.canceled_orders
            ],
            "greedy_reschedule": greedy_reschedule,
        }
        if self.log_tag:
            print(
                f"Canceled job {job_id} at time {now}; "
                f"removed {len(removed_operations)} operations, "
                f"preserved {len(processing_operations)} processing operations."
            )
        return result

    def cancelJobs(self, job_ids, current_time=None):
        """Cancel multiple Jobs under one prevalidated batch operation."""
        if not isinstance(job_ids, (list, tuple)):
            raise ValueError("job_ids must be a list of integers.")
        if not job_ids:
            raise ValueError("job_ids must not be empty.")

        normalized_ids = []
        for job_id in job_ids:
            if isinstance(job_id, bool):
                raise ValueError("job_ids must contain only integers.")
            try:
                normalized_id = int(job_id)
            except (TypeError, ValueError) as exc:
                raise ValueError(
                    "job_ids must contain only integers."
                ) from exc
            if not 0 <= normalized_id < len(self.jobs):
                raise ValueError(f"Unknown job_id: {normalized_id}")
            normalized_ids.append(normalized_id)
        if len(set(normalized_ids)) != len(normalized_ids):
            raise ValueError("job_ids must not contain duplicates.")

        now = max(
            float(self.curr_time),
            float(self.clock.current_simulation_time),
        )
        if current_time is not None:
            now = max(now, float(current_time))

        already_canceled_ids = [
            job_id
            for job_id in normalized_ids
            if self.jobs[job_id].is_canceled
        ]
        results = [
            self.cancelJob(
                job_id,
                current_time=now,
                reschedule=False,
            )
            for job_id in normalized_ids
            if job_id not in already_canceled_ids
        ]
        removed_operations = [
            operation
            for result in results
            for operation in result["removed_operations"]
        ]
        processing_operations = [
            operation
            for result in results
            for operation in result["processing_operations"]
        ]
        newly_canceled_ids = [
            result["job_id"] for result in results
        ]
        greedy_reschedule = (
            self._greedyRescheduleUnfinished(now)
            if results
            else {
                "applied": False,
                "unfinished_task_count": 0,
                "moved_operation_count": 0,
                "transport_time_added": 0,
                "transport_energy_added": 0,
            }
        )
        return {
            "success": True,
            "job_ids": normalized_ids,
            "newly_canceled_job_ids": newly_canceled_ids,
            "already_canceled_job_ids": already_canceled_ids,
            "removed_operation_count": len(removed_operations),
            "removed_operations": removed_operations,
            "processing_operations": processing_operations,
            "canceled_job_ids": [
                order.job_id for order in self.canceled_orders
            ],
            "greedy_reschedule": greedy_reschedule,
        }

    @staticmethod
    def _taskCancellationData(task):
        return {
            "task_id": task.task_id,
            "job_id": task.job_id,
            "operation_id": task.operation_id,
            "status": task.status,
            "machine_id": task.assigned_machine,
            "planned_start": task.planned_start,
            "planned_end": task.planned_end,
            "actual_start": task.actual_start,
            "actual_end": task.actual_end,
            "source_machine": task.source_machine,
            "transport_start": task.transport_start,
            "transport_end": task.transport_end,
            "transport_time": task.transport_time,
            "transport_energy": task.transport_energy,
            "transport_completed": task.transport_completed,
            "transport_segments": [
                dict(segment) for segment in task.transport_segments
            ],
            "committed_transport_energy": (
                task.committed_transport_energy
            ),
        }

    def startMachineAnomaly(
        self,
        machine_id,
        anomaly_type,
        duration,
        current_time=None,
    ):
        """Apply a machine anomaly and prepare the affected operations."""
        anomaly = MachineAnomalyType.normalize(anomaly_type)
        try:
            machine_id = int(machine_id)
        except (TypeError, ValueError) as exc:
            raise ValueError("machine_id must be an integer.") from exc
        if not 0 <= machine_id < len(self.machines):
            raise ValueError(f"Unknown machine_id: {machine_id}")
        duration = validate_machine_anomaly_duration(
            anomaly,
            duration,
        )

        now = max(
            float(self.curr_time),
            float(self.clock.current_simulation_time),
        )
        if current_time is not None:
            now = max(now, float(current_time))
        recovery_time = now + duration
        machine = self.machines[machine_id]
        if machine.machine_status in {"failed", "repairing"}:
            raise ValueError(
                f"Machine {machine_id} already has an active anomaly."
            )
        # A machine may receive another anomaly while it is degraded. Remove
        # the old recovery event so it cannot clear the newer anomaly state.
        self.event_queue = [
            event
            for event in self.event_queue
            if not (
                isinstance(event, MachineRecoveryEvent)
                and event.machine_id == machine_id
            )
        ]

        current_tasks = [
            task
            for job in self.jobs
            for task in job.tasks
            if (
                task.status == "processing"
                and task.actual_end is None
                and task.assigned_machine == machine_id
            )
        ]
        affected = []
        if anomaly != MachineAnomalyType.DEGRADED:
            for task in current_tasks:
                affected.append(self._interruptTask(task, now))
        else:
            affected = [
                {
                    "task_id": task.task_id,
                    "job_id": task.job_id,
                    "operation_id": task.operation_id,
                    "machine_id": machine_id,
                    "actual_start": task.actual_start,
                }
                for task in current_tasks
            ]

        if anomaly == MachineAnomalyType.DEGRADED:
            machine.machine_status = "degraded"
            machine.anomaly_type = anomaly.value
            machine.anomaly_started_at = now
            machine.recovery_time = recovery_time
            machine.performance_factor = DEGRADED_PROCESSING_FACTOR
            for task in current_tasks:
                self._extendDegradedOperation(
                    task,
                    machine_id,
                    recovery_time,
                )
        elif anomaly == MachineAnomalyType.LONG_FAILURE:
            machine.machine_status = "failed"
            machine.anomaly_type = anomaly.value
            machine.anomaly_started_at = now
            machine.recovery_time = recovery_time
            machine.performance_factor = 1.0
            self.deferUnavailableTasks(current_time=now)
        else:
            machine.machine_status = "repairing"
            machine.anomaly_type = anomaly.value
            machine.anomaly_started_at = now
            machine.recovery_time = recovery_time
            machine.performance_factor = 1.0

        self._removeMachinePendingEvents(
            machine_id,
            remove_starts=(
                anomaly != MachineAnomalyType.DEGRADED
            ),
            # Queued operations may already be in transit to this machine.
            # Their transport events must survive the downtime; otherwise the
            # operation can remain scheduled forever without a wake-up event.
            remove_transports=False,
        )
        if anomaly == MachineAnomalyType.DEGRADED:
            for task in current_tasks:
                self._ensureDegradedFinishEvent(task, now)
        elif anomaly in {
            MachineAnomalyType.SHORT_FAILURE,
            MachineAnomalyType.MEDIUM_FAILURE,
        }:
            for task in current_tasks:
                target_machine = machine_id
                if anomaly == MachineAnomalyType.MEDIUM_FAILURE:
                    candidates = [
                        candidate
                        for candidate in task.eligible_machines
                        if (
                            candidate != machine_id
                            and self.machines[candidate].machine_status
                            not in {"failed", "repairing"}
                        )
                    ]
                    if candidates:
                        target_machine = min(
                            candidates,
                            key=lambda candidate: (
                                task.processing_times[candidate],
                                candidate,
                            ),
                        )
                self._requeueInterruptedTask(
                    task,
                    machine_id,
                    target_machine,
                    now,
                    recovery_time,
                )

        self.addEvent(
            MachineRecoveryEvent(
                self.newEventId(),
                recovery_time,
                machine_id,
                anomaly.value,
                anomaly_started_at=now,
            )
        )
        self.updateEventQueue()
        self.refreshRealtimeObjectives()
        return {
            "success": True,
            "machine_id": machine_id,
            "anomaly_type": anomaly.value,
            "machine_status": machine.machine_status,
            "anomaly_started_at": now,
            "recovery_time": recovery_time,
            "processing_time_factor": (
                DEGRADED_PROCESSING_FACTOR
                if anomaly == MachineAnomalyType.DEGRADED
                else 1.0
            ),
            "affected_operations": affected,
            "requires_reoptimization": (
                anomaly == MachineAnomalyType.LONG_FAILURE
            ),
        }

    def deferUnavailableTasks(self, current_time=None):
        """Defer unfinished tasks that have no currently available machine."""
        now = max(
            float(self.curr_time),
            float(self.clock.current_simulation_time),
        )
        if current_time is not None:
            now = max(now, float(current_time))
        unavailable = {
            machine.machine_id
            for machine in self.machines
            if machine.machine_status in {"failed", "repairing"}
        }
        deferred = []
        for job in self.jobs:
            if job.is_canceled:
                continue
            for task in job.tasks:
                key = (job.job_id, task.operation_id)
                if (
                    task.status not in {"pending", "scheduled"}
                    or key in self.deferred_anomaly_tasks
                ):
                    continue
                if any(
                    candidate not in unavailable
                    for candidate in task.eligible_machines
                ):
                    continue
                fallback_machine = min(
                    task.eligible_machines,
                    key=lambda candidate: (
                        self.machines[candidate].recovery_time
                        or float("inf"),
                        candidate,
                    ),
                )
                recovery_time = (
                    self.machines[fallback_machine].recovery_time
                    or now
                )
                self.deferred_anomaly_tasks[key] = fallback_machine
                task.ready_not_before = max(now, recovery_time)
                deferred.append(key)
        return deferred

    def _interruptTask(self, task, interrupted_at):
        assigned_machine = task.assigned_machine
        interrupted_energy = 0.0
        if task.actual_start is not None and assigned_machine is not None:
            processing_time = task.processing_times[assigned_machine]
            elapsed = min(
                max(0.0, interrupted_at - task.actual_start),
                processing_time,
            )
            interrupted_energy = (
                task.processing_energies[assigned_machine]
                * elapsed
                / processing_time
                if processing_time > 0
                else 0.0
            )
        task.interrupted_processing_energy += interrupted_energy
        self._removeScheduleEntry(task.job_id, task.operation_id)
        task.status = "scheduled"
        task.actual_start = None
        task.actual_end = None
        task.interrupted_at = interrupted_at
        task.current_location_machine = assigned_machine
        self._clearUnstartedSuccessorTransport(
            task,
            interrupted_at,
        )
        return {
            "task_id": task.task_id,
            "job_id": task.job_id,
            "operation_id": task.operation_id,
            "machine_id": assigned_machine,
            "interrupted_at": interrupted_at,
            "interrupted_processing_energy": interrupted_energy,
        }

    def _clearUnstartedSuccessorTransport(self, task, interrupted_at):
        """Discard a successor transport that has not started yet."""
        job = self.jobs[task.job_id]
        successor_id = task.operation_id + 1
        if successor_id >= job.operation_count:
            return
        successor = job.tasks[successor_id]
        if (
            successor.actual_start is not None
            or successor.transport_completed
            or successor.transport_start is None
            or successor.transport_start <= interrupted_at + 1e-9
        ):
            return

        self.event_queue = [
            event
            for event in self.event_queue
            if not (
                isinstance(event, TransportFinishEvent)
                and event.job_id == task.job_id
                and event.operation_id == successor_id
            )
        ]
        successor.source_machine = task.assigned_machine
        successor.transport_start = None
        successor.transport_end = None
        successor.transport_time = 0
        successor.transport_energy = 0
        successor.transport_completed = False
        successor.transport_segments = []
        successor.current_location_machine = task.assigned_machine

        planned = next(
            (
                operation
                for operation in self.planned_operations
                if (
                    operation.job_id == task.job_id
                    and operation.operation_id == successor_id
                )
            ),
            None,
        )
        if planned is not None:
            planned.source_machine = task.assigned_machine
            planned.transport_start = None
            planned.transport_end = None
            planned.transport_time = 0
            planned.transport_energy = 0
            planned.transport_segments = []

    def _removeScheduleEntry(self, job_id, operation_id):
        key = (job_id, operation_id)
        for machine_id, items in enumerate(self.schedule.schedule_items):
            while key in items:
                index = items.index(key)
                items.pop(index)
                self.schedule.start_time[machine_id].pop(index)
                self.schedule.end_time[machine_id].pop(index)

    def _removeMachinePendingEvents(
        self,
        machine_id,
        remove_starts=True,
        remove_transports=True,
        remove_finishes=True,
    ):
        self.event_queue = [
            event
            for event in self.event_queue
            if not (
                remove_finishes
                and
                isinstance(event, OperationFinishEvent)
                and event.machine_id == machine_id
            )
            and not (
                remove_transports
                and isinstance(event, TransportFinishEvent)
                and event.machine_id == machine_id
            )
            and not (
                remove_starts
                and isinstance(
                    event,
                    (
                        OperationStartEvent,
                        MaterialReplenishmentEvent,
                        MaterialRecoveryEvent,
                    ),
                )
                and event.machine_id == machine_id
            )
        ]

    @staticmethod
    def _taskProcessingEnergy(task):
        completed = (
            task.processing_energy
            if (
                task.actual_end is not None
                and task.assigned_machine is not None
            )
            else 0
        )
        return completed + task.interrupted_processing_energy

    def _extendDegradedOperation(
        self,
        task,
        machine_id,
        recovery_time,
    ):
        processing_time = math.floor(
            task.processing_times[machine_id]
            * DEGRADED_PROCESSING_FACTOR
        )
        finish_time = task.actual_start + processing_time
        task.planned_end = finish_time
        planned = next(
            (
                operation
                for operation in self.planned_operations
                if (
                    operation.job_id == task.job_id
                    and operation.operation_id == task.operation_id
                )
            ),
            None,
        )
        if planned is not None:
            planned.end_time = finish_time
        self.machines[machine_id].ready_time = max(
            self.machines[machine_id].ready_time,
            finish_time,
        )
        key = (task.job_id, task.operation_id)
        for schedule_items, start_times, end_times in zip(
            self.schedule.schedule_items,
            self.schedule.start_time,
            self.schedule.end_time,
        ):
            if key in schedule_items:
                index = schedule_items.index(key)
                end_times[index] = finish_time
                break

    def _ensureDegradedFinishEvent(self, task, now):
        self.event_queue = [
            event
            for event in self.event_queue
            if not (
                isinstance(event, OperationFinishEvent)
                and event.job_id == task.job_id
                and event.operation_id == task.operation_id
            )
        ]
        self.addEvent(
            OperationFinishEvent(
                self.newEventId(),
                max(now, task.planned_end),
                task.job_id,
                task.operation_id,
                task.assigned_machine,
            )
        )

    def _requeueInterruptedTask(
        self,
        task,
        original_machine,
        target_machine,
        now,
        recovery_time,
    ):
        task.assigned_machine = target_machine
        task.ready_not_before = recovery_time
        task.planned_start = max(recovery_time, now)
        task.planned_end = (
            task.planned_start + task.processing_times[target_machine]
        )
        machine = self.machines[target_machine]
        planned = next(
            (
                operation
                for operation in self.planned_operations
                if (
                    operation.job_id == task.job_id
                    and operation.operation_id == task.operation_id
                )
            ),
            None,
        )
        for machine_item in self.machines:
            machine_item.pending_operations = [
                operation
                for operation in machine_item.pending_operations
                if not (
                    operation.job_id == task.job_id
                    and operation.operation_id == task.operation_id
                )
            ]
        if planned is None:
            planned = PlannedOperation(
                job_id=task.job_id,
                operation_id=task.operation_id,
                machine_id=target_machine,
                start_time=task.planned_start,
                end_time=task.planned_end,
            )
            self.planned_operations.append(planned)
        planned.machine_id = target_machine
        planned.start_time = task.planned_start
        planned.end_time = task.planned_end
        planned.status = "scheduled"
        machine.pending_operations.insert(0, planned)
        self.scheduled_operations[target_machine].insert(
            0,
            [task.job_id, task.operation_id],
        )

        if target_machine != original_machine:
            transport_time = self._jobTransportTime(
                task.job_id,
                original_machine,
                target_machine,
            )
            transport_energy = self._jobTransportEnergy(
                task.job_id,
                original_machine,
                target_machine,
            )
            segment = {
                "source_machine": original_machine,
                "target_machine": target_machine,
                "transport_start": now,
                "transport_end": now + transport_time,
                "transport_time": transport_time,
                "transport_energy": transport_energy,
                "completed": transport_time == 0,
            }
            task.transport_segments.append(segment)
            task.source_machine = original_machine
            task.transport_start = segment["transport_start"]
            task.transport_end = segment["transport_end"]
            task.transport_time = transport_time
            task.transport_energy = transport_energy
            task.transport_completed = segment["completed"]
            task.current_location_machine = (
                target_machine if segment["completed"] else original_machine
            )
            planned.source_machine = original_machine
            planned.transport_start = segment["transport_start"]
            planned.transport_end = segment["transport_end"]
            planned.transport_time = transport_time
            planned.transport_energy = transport_energy
            planned.transport_segments = [
                dict(item) for item in task.transport_segments
            ]
            if transport_time > 0:
                self.addEvent(
                    TransportFinishEvent(
                        self.newEventId(),
                        segment["transport_end"],
                        task.job_id,
                        task.operation_id,
                        target_machine,
                    )
                )
            self._removeMachinePendingEvents(
                target_machine,
                remove_starts=True,
                remove_transports=False,
                remove_finishes=False,
            )
        else:
            task.current_location_machine = target_machine
            task.transport_completed = True

    def handleMachineRecoveryEvent(self, event):
        machine = self.machines[event.machine_id]
        machine.machine_status = "idle"
        machine.anomaly_type = None
        machine.anomaly_started_at = None
        machine.recovery_time = None
        machine.performance_factor = 1.0
        self._enqueueDeferredAnomalyTasks(
            event.machine_id,
            event.timestamp,
        )

        released_tasks = [
            task
            for job in self.jobs
            for task in job.tasks
            if (
                task.status == "scheduled"
                and task.ready_not_before is not None
                and task.ready_not_before <= event.timestamp + 1e-9
            )
        ]
        for task in released_tasks:
            task.ready_not_before = None
        for machine_id in {
            task.assigned_machine
            for task in released_tasks
            if task.assigned_machine is not None
        } | {event.machine_id}:
            self._startReadyOperationIfPossible(
                machine_id,
                event.timestamp,
            )
        if any(
            task.status == "processing"
            and task.actual_end is None
            and task.assigned_machine == event.machine_id
            for job in self.jobs
            for task in job.tasks
        ):
            machine.machine_status = "busy"
        elif machine.pending_operations:
            machine.machine_status = "scheduled"
        else:
            machine.machine_status = "idle"
        recovery_reoptimization = None
        if (
            event.anomaly_type
            == MachineAnomalyType.LONG_FAILURE.value
            and self.machine_recovery_reoptimizer is not None
        ):
            recovery_reoptimization = self.machine_recovery_reoptimizer(
                event.machine_id,
                event.timestamp,
            )
        self.refreshRealtimeObjectives()
        recovery_reschedule_method = None
        if (
            event.anomaly_type
            == MachineAnomalyType.LONG_FAILURE.value
            and recovery_reoptimization is not None
        ):
            recovery_reschedule_method = (
                recovery_reoptimization.get("reschedule_method")
                if isinstance(recovery_reoptimization, dict)
                else None
            )
        event.machine_status = machine.machine_status
        event.result = {
            "success": True,
            "machine_id": event.machine_id,
            "machine_status": machine.machine_status,
            "anomaly_type": event.anomaly_type,
            "recovered_at": event.timestamp,
            "reschedule_method": recovery_reschedule_method,
            "reoptimization": recovery_reoptimization,
        }
        return True

    def _generate_process_chain_job(
        self,
        existing_jobs,
        current_time,
        seed,
        template_jobs,
    ):
        """Generate one dynamic Job with the complete four-process route."""
        rng = random.Random(int(seed))
        template = rng.choice(list(template_jobs))
        job_id = max(
            (job.job_id for job in existing_jobs),
            default=-1,
        ) + 1
        next_task_id = max(
            (
                task.task_id
                for job in existing_jobs
                for task in job.tasks
            ),
            default=-1,
        ) + 1
        tasks = []
        operation_times = []
        operation_energy = []
        for template_task in template.tasks:
            processing_times = {}
            processing_energies = {}
            for machine_id, template_time in (
                template_task.processing_times.items()
            ):
                low = max(1, int(template_time * 0.9))
                high = max(low, int(template_time * 1.1))
                processing_times[machine_id] = rng.randint(low, high)
                processing_energies[machine_id] = rng.randint(4, 15)
            task = Task(
                task_id=next_task_id + len(tasks),
                job_id=job_id,
                operation_id=len(tasks),
                processing_times=processing_times,
                processing_energies=processing_energies,
                predecessor_id=(
                    next_task_id + len(tasks) - 1
                    if tasks
                    else None
                ),
                stage_id=template_task.stage_id,
                stage_operation_id=template_task.stage_operation_id,
                material_consumption=copy.deepcopy(
                    template_task.material_consumption
                ),
            )
            if task.stage_id > 1:
                task.status = "blocked"
            tasks.append(task)
            operation_times.append([
                processing_times.get(machine_id, float("inf"))
                for machine_id in range(len(self.machines))
            ])
            operation_energy.append([
                processing_energies.get(machine_id, float("inf"))
                for machine_id in range(len(self.machines))
            ])
        for index in range(len(tasks) - 1):
            tasks[index].successor_id = tasks[index + 1].task_id
        ready_time = float(current_time) + rng.randint(0, 20)
        due_duration = max(
            1,
            float(template.due_time) - float(template.ready_time),
        )
        return Job(
            job_id=job_id,
            operation_count=len(tasks),
            operation_times=operation_times,
            operation_energy=operation_energy,
            ready_time=ready_time,
            due_time=ready_time + due_duration,
            earliness_cost=rng.randint(1, 10),
            tardiness_cost=rng.randint(1, 10),
            weight=rng.randint(1, 5),
            tasks=tasks,
            priority=0,
            transport_time_matrix=self.transport_time,
            transport_energy_matrix=self.transport_energy,
            material_consumption=copy.deepcopy(
                template.material_consumption
            ),
        )

    def _enqueueDeferredAnomalyTasks(self, machine_id, recovery_time):
        deferred_keys = [
            key
            for key, target_machine in self.deferred_anomaly_tasks.items()
            if target_machine == machine_id
        ]
        if not deferred_keys:
            return
        machine = self.machines[machine_id]
        for key in deferred_keys:
            job_id, operation_id = key
            task = self.jobs[job_id].tasks[operation_id]
            task.status = "scheduled"
            task.assigned_machine = machine_id
            task.ready_not_before = recovery_time
            task.planned_start = recovery_time
            task.planned_end = (
                recovery_time + task.processing_times[machine_id]
            )
            task.current_location_machine = machine_id
            planned = next(
                (
                    operation
                    for operation in self.planned_operations
                    if (
                        operation.job_id == job_id
                        and operation.operation_id == operation_id
                    )
                ),
                None,
            )
            if planned is None:
                planned = PlannedOperation(
                    job_id=job_id,
                    operation_id=operation_id,
                    machine_id=machine_id,
                    start_time=task.planned_start,
                    end_time=task.planned_end,
                )
                self.planned_operations.append(planned)
            else:
                planned.machine_id = machine_id
                planned.start_time = task.planned_start
                planned.end_time = task.planned_end
                planned.status = "scheduled"
            self.assignTaskPlan(task, planned)
            machine.pending_operations.append(planned)
            self.scheduled_operations[machine_id].append(
                [job_id, operation_id]
            )
            del self.deferred_anomaly_tasks[key]
        machine.pending_operations.sort(
            key=lambda operation: (
                operation.start_time,
                -self.jobs[operation.job_id].priority,
                operation.job_id,
                operation.operation_id,
            )
        )
        self.scheduled_operations[machine_id] = [
            [operation.job_id, operation.operation_id]
            for operation in machine.pending_operations
        ]

    def replanRemainingOperations(self):
        """取消未完成工序事件，并从当前时刻重建全部剩余机器队列。"""
        operation_event_types = (
            JobSubmitEvent,
            JobStartEvent,
            JobFinishEvent,
            TransportFinishEvent,
            OperationStartEvent,
            OperationFinishEvent,
            MaterialReplenishmentEvent,
            MaterialRecoveryEvent,
        )
        self.event_queue = [
            event
            for event in self.event_queue
            if not isinstance(event, operation_event_types)
        ]
        self.pending_material_recoveries.clear()

        for machine_id, machine in enumerate(self.machines):
            machine.clearPendingOperations()
            self.scheduled_operations[machine_id] = []
            machine.ready_time = self.curr_time

        for machine_id in range(len(self.machines)):
            kept_operations = []
            for item, start_time, end_time in zip(
                self.schedule.schedule_items[machine_id],
                self.schedule.start_time[machine_id],
                self.schedule.end_time[machine_id],
            ):
                if item in self.completed_operations:
                    kept_operations.append((item, start_time, end_time))
            self.schedule.schedule_items[machine_id] = [
                item for item, _, _ in kept_operations
            ]
            self.schedule.start_time[machine_id] = [
                start_time for _, start_time, _ in kept_operations
            ]
            self.schedule.end_time[machine_id] = [
                end_time for _, _, end_time in kept_operations
            ]

        self.processing_queue = []
        self.finished_queue = []
        self.planned_operations = []
        operation_queue = []

        for job in self.jobs:
            if job.is_canceled:
                continue
            for task in job.tasks:
                if (job.job_id, task.operation_id) not in self.completed_operations:
                    task.status = "pending"
                    task.assigned_machine = None
                    task.planned_start = None
                    task.planned_end = None
                    task.actual_start = None
                    task.actual_end = None
                    task.source_machine = None
                    task.transport_start = None
                    task.transport_end = None
                    task.transport_time = 0
                    task.transport_energy = 0
                    task.transport_completed = False
                    task.committed_transport_energy = 0
                    task.transport_segments = []
                    task.current_location_machine = None
                    task.waiting_time = 0

        for job in self.jobs:
            if job.is_canceled:
                continue
            next_operation_id = 0
            while (
                job.job_id,
                next_operation_id,
            ) in self.completed_operations:
                next_operation_id += 1

            if next_operation_id >= job.operation_count:
                self.finished_queue.append(
                    Order(job.job_id, 0, job.ready_time)
                )
                continue

            initial_release_time = max(
                self.curr_time,
                job.ready_time if next_operation_id == 0 else 0,
            )
            initial_machine_id = self.placeOperation(
                job.job_id,
                next_operation_id,
            )
            initial_queue_release = self.operationReleaseTime(
                job.job_id,
                next_operation_id,
                initial_machine_id,
                initial_release_time,
            )[0]
            self.processing_queue.append(
                Order(job.job_id, 0, job.ready_time)
            )
            heapq.heappush(
                operation_queue,
                (
                    initial_queue_release,
                    0,
                    job.job_id,
                    next_operation_id,
                    initial_release_time,
                ),
            )

        while operation_queue:
            (
                _queue_release_time,
                neg_priority,
                job_id,
                operation_id,
                release_time,
            ) = heapq.heappop(operation_queue)
            job = self.jobs[job_id]
            machine_id = self.placeOperation(job_id, operation_id)
            if machine_id == -1:
                continue

            machine = self.machines[machine_id]
            (
                release_time,
                inbound_transport,
                inbound_energy,
                transport_start,
                transport_end,
            ) = (
                self.operationReleaseTime(
                    job_id,
                    operation_id,
                    machine_id,
                    release_time,
                )
            )
            start_time = max(release_time, machine.ready_time)
            end_time = (
                start_time
                + job.operation_times[operation_id][machine_id]
            )
            planned_operation = PlannedOperation(
                job_id=job_id,
                operation_id=operation_id,
                machine_id=machine_id,
                start_time=start_time,
                end_time=end_time,
            )
            machine.enqueueOperation(planned_operation)
            machine.ready_time = end_time
            task = job.tasks[operation_id]
            task.status = "scheduled"
            task.assigned_machine = machine_id
            task.planned_start = start_time
            task.planned_end = end_time
            task.source_machine = (
                job.tasks[operation_id - 1].assigned_machine
                if operation_id > 0
                else None
            )
            task.transport_time = inbound_transport
            task.transport_energy = inbound_energy
            task.transport_start = transport_start
            task.transport_end = transport_end
            task.transport_completed = self._inboundTransportCompleted(
                job_id,
                operation_id,
                inbound_transport,
            )
            task.current_location_machine = (
                task.source_machine
                if task.source_machine is not None
                and not task.transport_completed
                else machine_id
            )
            self.assignTaskPlan(task, planned_operation)
            self.scheduled_operations[machine_id].append(
                [job_id, operation_id]
            )
            self.planned_operations.append(planned_operation)

            next_operation_id = operation_id + 1
            if (
                next_operation_id < job.operation_count
                and job.tasks[next_operation_id].status != "blocked"
            ):
                next_machine_id = self.placeOperation(
                    job_id,
                    next_operation_id,
                )
                next_release_time = self.operationReleaseTime(
                    job_id,
                    next_operation_id,
                    next_machine_id,
                    end_time,
                )[0]
                heapq.heappush(
                    operation_queue,
                    (
                        next_release_time,
                        neg_priority,
                        job_id,
                        next_operation_id,
                        end_time,
                    ),
                )

        for machine in self.machines:
            first_operation = machine.nextPendingOperation()
            if first_operation is not None:
                self.addEvent(
                    OperationStartEvent(
                        self.newEventId(),
                        first_operation.start_time,
                        first_operation.job_id,
                        first_operation.operation_id,
                        first_operation.machine_id,
                    )
                )
        self.scheduleTransportFinishEvents(
            self.planned_operations,
            after_time=self.curr_time,
        )

    def calculateObjectives(self):
        """Recalculate all objectives from the current task states."""
        return self.refreshRealtimeObjectives()

    def refreshRealtimeObjectives(self):
        """Incrementally mirror energy and delivery metrics to Web clients."""
        total_processing_energy = 0
        total_transport_energy = 0
        total_penalty = 0
        completion_times = []

        for job in self.jobs:
            job.processing_energy = sum(
                self._taskProcessingEnergy(task)
                for task in job.tasks
            )
            job.transport_energy = sum(
                task.total_transport_energy
                for task in job.tasks
            )

            completed_times = [
                task.actual_end
                for task in job.tasks
                if task.actual_end is not None
            ]
            all_completed = (
                len(completed_times) == job.operation_count
                and not job.is_canceled
            )
            job.completion_time = (
                max(completed_times) if all_completed else None
            )
            if job.completion_time is not None:
                completion_times.append(job.completion_time)
                job.earliness = max(
                    job.due_time - job.completion_time,
                    0,
                )
                job.tardiness = max(
                    job.completion_time - job.due_time,
                    0,
                )
            else:
                job.earliness = 0
                job.tardiness = 0

            total_processing_energy += job.processing_energy
            total_transport_energy += job.transport_energy
            total_penalty += (
                job.delivery_penalty
                if job.completion_time is not None
                else 0
            )

        self.makespan = max(completion_times, default=0)
        self.transport_adjusted_makespan = self.makespan
        self.total_processing_energy = total_processing_energy
        self.total_transport_energy = total_transport_energy
        self.total_auxiliary_energy = (
            self.auxiliary_energy * self.curr_time
        )
        self.total_energy = (
            self.total_processing_energy
            + self.total_transport_energy
            + self.total_auxiliary_energy
        )
        self.total_penalty = total_penalty
        self.objectives = {
            "makespan": self.makespan,
            "energy": self.total_energy,
            "penalty": self.total_penalty,
        }
        return self.objectives

    def _process_scope(self, stage_ids=None):
        available_stage_ids = {
            int(process["id"])
            for process in self.process_definitions
        } or {1}
        if stage_ids is None:
            return available_stage_ids, set(range(len(self.machines)))
        normalized_stage_ids = {
            int(stage_id) for stage_id in stage_ids
        }
        unknown_stage_ids = (
            normalized_stage_ids - available_stage_ids
        )
        if unknown_stage_ids:
            raise ValueError(
                "Unknown process_id: "
                + ", ".join(
                    str(stage_id)
                    for stage_id in sorted(unknown_stage_ids)
                )
            )
        machine_ids = {
            machine.machine_id
            for machine in self.machines
            if getattr(machine, "stage_id", 1)
            in normalized_stage_ids
        }
        return normalized_stage_ids, machine_ids

    def _greedyUnfinishedAssignments(
        self,
        excluded_machines=None,
        stage_ids=None,
    ):
        """Assign each unfinished operation to its fastest available machine."""
        scoped_stage_ids, _ = self._process_scope(stage_ids)
        unavailable_machines = {
            machine.machine_id
            for machine in self.machines
            if machine.machine_status in {"failed", "repairing"}
        }
        unavailable_machines.update(
            int(machine_id)
            for machine_id in (excluded_machines or [])
        )
        assignments = {}
        for job in self.jobs:
            if job.is_canceled:
                continue
            for task in job.tasks:
                key = (job.job_id, task.operation_id)
                if (
                    task.status not in {"pending", "scheduled"}
                    or task.stage_id not in scoped_stage_ids
                    or key in self.deferred_anomaly_tasks
                ):
                    continue
                candidates = [
                    machine_id
                    for machine_id in task.eligible_machines
                    if machine_id not in unavailable_machines
                ]
                if not candidates:
                    continue
                assignments[key] = min(
                    candidates,
                    key=lambda machine_id: (
                        task.processing_times[machine_id],
                        machine_id,
                    ),
                )
        return assignments

    def _greedyRescheduleUnfinished(self, current_time, stage_ids=None):
        """Rebuild unfinished work with the built-in greedy assignment."""
        if stage_ids is None:
            assignments = self._greedyUnfinishedAssignments()
        else:
            assignments = self._greedyUnfinishedAssignments(
                stage_ids=stage_ids,
            )
        if not assignments:
            self.refreshRealtimeObjectives()
            return {
                "applied": False,
                "unfinished_task_count": 0,
                "moved_operation_count": 0,
                "transport_time_added": 0,
                "transport_energy_added": 0,
            }

        result = self.reoptimizeUnfinishedOperations(
            assignments,
            current_time=current_time,
            stage_ids=stage_ids,
        )
        return {
            "applied": True,
            "unfinished_task_count": result["unfinished_task_count"],
            "moved_operation_count": result["moved_operation_count"],
            "transport_time_added": result["transport_time_added"],
            "transport_energy_added": result["transport_energy_added"],
        }

    def reoptimizeUnfinishedOperations(
        self,
        machine_assignments,
        current_time=None,
        excluded_machines=None,
        stage_ids=None,
    ):
        """
        使用外部模型给出的机器分配重建未加工工序队列。

        已完成和正在加工的任务保持原机器与时间；未开始任务使用新机器分配，
        并根据工件的实际所在机器重新计算机器可用时间、运输时间和运输能耗。
        已到达新目标机器的运输不会重复生成。
        """
        now = self.curr_time if current_time is None else float(current_time)
        scoped_stage_ids, scoped_machine_ids = self._process_scope(
            stage_ids
        )
        assignments = {}
        for key, machine_id in machine_assignments.items():
            key = tuple(key)
            if key in self.deferred_anomaly_tasks:
                continue
            task = self.jobs[key[0]].tasks[key[1]]
            if (
                task.status not in {"pending", "scheduled"}
                or task.stage_id not in scoped_stage_ids
            ):
                continue
            assignments[key] = int(machine_id)
        unavailable_machines = {
            machine.machine_id
            for machine in self.machines
            if machine.machine_status in {"failed", "repairing"}
        }
        unavailable_machines.update(
            int(machine_id)
            for machine_id in (excluded_machines or [])
        )
        for key, machine_id in list(assignments.items()):
            task = self.jobs[key[0]].tasks[key[1]]
            if machine_id not in unavailable_machines:
                continue
            candidates = [
                candidate
                for candidate in task.eligible_machines
                if candidate not in unavailable_machines
            ]
            if not candidates:
                raise ValueError(
                    f"No available machine for task {task.task_id}."
                )
            assignments[key] = min(
                candidates,
                key=lambda candidate: (
                    task.processing_times[candidate],
                    candidate,
                ),
            )
        old_machines = {
            (job.job_id, task.operation_id): task.assigned_machine
            for job in self.jobs
            for task in job.tasks
        }
        old_transport_states = {
            (job.job_id, task.operation_id): {
                "assigned_machine": task.assigned_machine,
                "source_machine": task.source_machine,
                "current_location_machine": self._taskCurrentLocation(
                    task
                ),
                "transport_completed": task.transport_completed,
                "transport_start": task.transport_start,
                "transport_end": task.transport_end,
                "transport_time": task.transport_time,
                "transport_energy": task.transport_energy,
                "transport_segments": [
                    dict(segment)
                    for segment in task.transport_segments
                ],
                "committed_transport_energy": (
                    task.committed_transport_energy
                ),
            }
            for job in self.jobs
            for task in job.tasks
        }
        processing_tasks = [
            task
            for job in self.jobs
            for task in job.tasks
            if (
                task.status == "processing"
                and task.actual_end is None
                and task.stage_id in scoped_stage_ids
            )
        ]
        effective_ends = {
            (job.job_id, task.operation_id): self._taskEffectiveEnd(task)
            for job in self.jobs
            for task in job.tasks
        }

        unfinished_tasks = [
            (job.job_id, task)
            for job in self.jobs
            if not job.is_canceled
            for task in job.tasks
            if task.status in {"pending", "scheduled"}
            and task.stage_id in scoped_stage_ids
            and (job.job_id, task.operation_id)
            not in self.deferred_anomaly_tasks
        ]
        missing_assignments = [
            (job_id, task.operation_id)
            for job_id, task in unfinished_tasks
            if (job_id, task.operation_id) not in assignments
        ]
        if missing_assignments:
            raise ValueError(
                "Missing machine assignments for unfinished tasks: "
                + ", ".join(
                    f"{job_id}-{operation_id}"
                    for job_id, operation_id in missing_assignments[:10]
                )
            )

        for machine_id, machine in enumerate(self.machines):
            if machine_id not in scoped_machine_ids:
                continue
            anomaly_status = (
                machine.machine_status
                if machine.machine_status
                in {"failed", "repairing", "degraded"}
                else None
            )
            machine.clearPendingOperations()
            machine.ready_time = now
            machine.machine_status = anomaly_status or "idle"
            self.scheduled_operations[machine_id] = []

        for task in processing_tasks:
            expected_end = effective_ends[(task.job_id, task.operation_id)]
            machine = self.machines[task.assigned_machine]
            machine.ready_time = max(
                machine.ready_time,
                expected_end,
            )
            if machine.machine_status not in {
                "failed",
                "repairing",
                "degraded",
            }:
                machine.machine_status = "busy"

        obsolete_event_types = (
            OperationStartEvent,
            OperationFinishEvent,
            TransportFinishEvent,
            MaterialReplenishmentEvent,
            MaterialRecoveryEvent,
        )
        active_canceled_transport_keys = {
            (job.job_id, task.operation_id)
            for job in self.jobs
            if job.is_canceled
            for task in job.tasks
            if (
                task.status == "canceled"
                and task.actual_start is None
                and not task.transport_completed
                and task.transport_start is not None
                and task.transport_start <= now + 1e-9
                and task.transport_end is not None
                and task.transport_end >= now - 1e-9
            )
        }
        kept_events = []
        for event in self.event_queue:
            if (
                isinstance(event, TransportFinishEvent)
                and (event.job_id, event.operation_id)
                in active_canceled_transport_keys
            ):
                kept_events.append(event)
                continue
            if isinstance(event, obsolete_event_types):
                try:
                    event_task = self.jobs[event.job_id].tasks[
                        event.operation_id
                    ]
                except (AttributeError, IndexError, TypeError):
                    event_task = None
                if (
                    event_task is not None
                    and event_task.stage_id in scoped_stage_ids
                ):
                    continue
            kept_events.append(event)
        self.event_queue = kept_events

        for task in processing_tasks:
            self.addEvent(
                OperationFinishEvent(
                    self.newEventId(),
                    effective_ends[(task.job_id, task.operation_id)],
                    task.job_id,
                    task.operation_id,
                    task.assigned_machine,
                )
            )

        for job_id, task in unfinished_tasks:
            previous_transport = old_transport_states[
                (job_id, task.operation_id)
            ]
            task.status = "pending"
            task.assigned_machine = None
            task.planned_start = None
            task.planned_end = None
            task.actual_start = None
            task.actual_end = None
            task.source_machine = None
            task.transport_start = None
            task.transport_end = None
            task.transport_time = 0
            task.transport_energy = 0
            task.transport_completed = False
            task.committed_transport_energy = previous_transport[
                "committed_transport_energy"
            ]
            task.transport_segments = []
            task.current_location_machine = previous_transport[
                "current_location_machine"
            ]
            task.waiting_time = 0

        operation_queue = []
        for job in self.jobs:
            if job.is_canceled:
                continue
            next_task = next(
                (
                    task
                    for task in job.tasks
                    if (
                        task.stage_id in scoped_stage_ids
                        and task.status
                        not in {"completed", "processing", "blocked"}
                    )
                ),
                None,
            )
            if next_task is None:
                continue
            next_operation_id = next_task.operation_id
            if (
                job.job_id,
                next_operation_id,
            ) in self.deferred_anomaly_tasks:
                continue

            if next_operation_id == 0:
                release_time = max(now, job.ready_time)
            else:
                predecessor_end = effective_ends[
                    (job.job_id, next_operation_id - 1)
                ]
                release_time = max(now, predecessor_end or now)
            heapq.heappush(
                operation_queue,
                (
                    self._reoptimizationReleaseEstimate(
                        job.job_id,
                        next_operation_id,
                        assignments[
                            (job.job_id, next_operation_id)
                        ],
                        release_time,
                        old_transport_states[
                            (job.job_id, next_operation_id)
                        ],
                        now,
                    ),
                    0,
                    job.job_id,
                    next_operation_id,
                    release_time,
                ),
            )

        preserved_plans = [
            operation
            for operation in self.planned_operations
            if operation.stage_id not in scoped_stage_ids
        ]
        scoped_existing_plans = [
            self._plannedOperationFromTask(task)
            for job in self.jobs
            for task in job.tasks
            if (
                task.stage_id in scoped_stage_ids
                and task.status in {"completed", "processing"}
            )
        ]
        self.planned_operations = (
            preserved_plans + scoped_existing_plans
        )
        moved_operations = []
        transport_time_added = 0
        transport_energy_added = 0

        finished_job_ids = {
            order.job_id for order in self.finished_queue
        }
        queued_job_finish_ids = {
            event.job_id
            for event in self.event_queue
            if isinstance(event, JobFinishEvent)
        }
        for job in self.jobs:
            if (
                not job.is_canceled
                and
                all(task.status == "completed" for task in job.tasks)
                and job.job_id not in finished_job_ids
                and job.job_id not in queued_job_finish_ids
            ):
                completion_time = max(
                    task.actual_end
                    for task in job.tasks
                    if task.actual_end is not None
                )
                self.addEvent(
                    JobFinishEvent(
                        self.newEventId(),
                        max(now, completion_time),
                        job.job_id,
                    )
                )

        while operation_queue:
            (
                _queue_release_time,
                _,
                job_id,
                operation_id,
                release_time,
            ) = heapq.heappop(operation_queue)
            job = self.jobs[job_id]
            task = job.tasks[operation_id]
            machine_id = assignments[(job_id, operation_id)]
            if not 0 <= machine_id < len(self.machines):
                raise ValueError(
                    f"Invalid machine {machine_id} for task {job.tasks[operation_id].task_id}"
                )
            if machine_id not in task.eligible_machines:
                raise ValueError(
                    f"Task {task.task_id} cannot run on machine {machine_id}"
                )

            machine = self.machines[machine_id]
            previous_transport = old_transport_states[
                (job_id, operation_id)
            ]
            transport_start = None
            transport_end = None
            transport_segments = []
            added_transport_time = 0
            added_transport_energy = 0
            predecessor = (
                job.tasks[operation_id - 1]
                if operation_id > 0
                else None
            )
            predecessor_end = (
                predecessor.actual_end
                if (
                    predecessor is not None
                    and predecessor.actual_end is not None
                )
                else self._taskEffectiveEnd(predecessor)
                if predecessor is not None
                else None
            )
            previous_segments = [
                dict(segment)
                for segment in previous_transport[
                    "transport_segments"
                ]
            ]
            previous_chain = previous_segments
            if (
                not previous_chain
                and previous_transport["transport_start"] is not None
                and previous_transport["transport_end"] is not None
            ):
                previous_chain = [{
                    "source_machine": previous_transport[
                        "source_machine"
                    ],
                    "target_machine": previous_transport[
                        "assigned_machine"
                    ],
                    "transport_start": previous_transport[
                        "transport_start"
                    ],
                    "transport_end": previous_transport[
                        "transport_end"
                    ],
                    "transport_time": previous_transport[
                        "transport_time"
                    ],
                    "transport_energy": previous_transport[
                        "transport_energy"
                    ],
                    "completed": previous_transport[
                        "transport_completed"
                    ],
                }]
            previous_transport_valid = (
                operation_id == 0
                or self._transportChainMatchesPredecessor(
                    job_id,
                    previous_chain,
                    predecessor,
                )
            )

            if operation_id == 0:
                source_machine = None
                inbound_transport = 0
                inbound_energy = 0
                release_time = max(release_time, now, job.ready_time)
                current_location = machine_id
                transport_completed = True
            elif (
                previous_transport_valid
                and
                previous_transport["transport_completed"]
                and previous_transport["current_location_machine"]
                == machine_id
            ):
                source_machine = previous_transport["source_machine"]
                inbound_transport = previous_transport["transport_time"]
                inbound_energy = previous_transport["transport_energy"]
                transport_start = previous_transport["transport_start"]
                transport_end = previous_transport["transport_end"]
                if transport_end is not None:
                    release_time = max(release_time, transport_end)
                current_location = machine_id
                transport_completed = True
                transport_segments = [
                    dict(segment)
                    for segment in previous_transport[
                        "transport_segments"
                    ]
                ]
            else:
                previous_segments = (
                    previous_segments
                    if previous_transport_valid
                    else []
                )
                active_segment = next(
                    (
                        segment
                        for segment in previous_segments
                        if not segment["completed"]
                    ),
                    None,
                )
                legacy_in_progress = (
                    previous_transport_valid
                    and
                    not previous_transport["transport_completed"]
                    and previous_transport["transport_start"] is not None
                    and previous_transport["transport_end"] is not None
                    and previous_transport["transport_start"]
                    <= now + 1e-9
                    and previous_transport["transport_end"]
                    > now + 1e-9
                )
                if active_segment is None and legacy_in_progress:
                    active_segment = {
                        "source_machine": previous_transport[
                            "source_machine"
                        ],
                        "target_machine": previous_transport[
                            "assigned_machine"
                        ],
                        "transport_start": previous_transport[
                            "transport_start"
                        ],
                        "transport_end": previous_transport[
                            "transport_end"
                        ],
                        "transport_time": previous_transport[
                            "transport_time"
                        ],
                        "transport_energy": previous_transport[
                            "transport_energy"
                        ],
                        "completed": False,
                    }

                if active_segment is not None:
                    completed_segments = [
                        dict(segment)
                        for segment in previous_segments
                        if segment["completed"]
                    ]
                    current_segment = dict(active_segment)
                    transport_segments = [
                        *completed_segments,
                        current_segment,
                    ]
                    source_machine = current_segment[
                        "source_machine"
                    ]
                    inbound_transport = current_segment[
                        "transport_time"
                    ]
                    inbound_energy = current_segment[
                        "transport_energy"
                    ]
                    transport_start = current_segment[
                        "transport_start"
                    ]
                    transport_end = current_segment[
                        "transport_end"
                    ]
                    release_time = max(release_time, transport_end)
                    current_location = source_machine

                    if current_segment["target_machine"] != machine_id:
                        second_transport_time = self._jobTransportTime(
                            job_id,
                            current_segment["target_machine"],
                            machine_id,
                        )
                        second_transport_energy = (
                            self._jobTransportEnergy(
                                job_id,
                                current_segment["target_machine"],
                                machine_id,
                            )
                        )
                        second_segment = {
                            "source_machine": current_segment[
                                "target_machine"
                            ],
                            "target_machine": machine_id,
                            "transport_start": current_segment[
                                "transport_end"
                            ],
                            "transport_end": (
                                current_segment["transport_end"]
                                + second_transport_time
                            ),
                            "transport_time": second_transport_time,
                            "transport_energy": second_transport_energy,
                            "completed": False,
                        }
                        transport_segments.append(second_segment)
                        release_time = second_segment["transport_end"]
                        added_transport_time = second_transport_time
                        added_transport_energy = second_transport_energy
                    transport_completed = False
                else:
                    if (
                        previous_transport_valid
                        and previous_transport["transport_completed"]
                    ):
                        source_machine = previous_transport[
                            "current_location_machine"
                        ]
                        if previous_segments:
                            transport_segments = previous_segments
                        else:
                            task.committed_transport_energy += (
                                previous_transport[
                                    "transport_energy"
                                ]
                            )
                    else:
                        source_machine = predecessor.assigned_machine

                    transport_available_time = (
                        max(now, release_time)
                        if (
                            previous_transport_valid
                            and previous_transport[
                                "transport_completed"
                            ]
                        )
                        else (
                            predecessor_end
                            if predecessor_end is not None
                            else max(now, release_time)
                        )
                    )
                    if (
                        source_machine is None
                        or source_machine == machine_id
                    ):
                        inbound_transport = 0
                        inbound_energy = 0
                        release_time = transport_available_time
                        current_location = machine_id
                        transport_completed = (
                            self._inboundTransportCompleted(
                                job_id,
                                operation_id,
                                0,
                            )
                        )
                    else:
                        inbound_transport = self._jobTransportTime(
                            job_id,
                            source_machine,
                            machine_id,
                        )
                        inbound_energy = self._jobTransportEnergy(
                            job_id,
                            source_machine,
                            machine_id,
                        )
                        transport_start = transport_available_time
                        transport_end = (
                            transport_start + inbound_transport
                        )
                        release_time = transport_end
                        current_location = source_machine
                        transport_segment = {
                            "source_machine": source_machine,
                            "target_machine": machine_id,
                            "transport_start": transport_start,
                            "transport_end": transport_end,
                            "transport_time": inbound_transport,
                            "transport_energy": inbound_energy,
                            "completed": False,
                        }
                        if transport_end <= now + 1e-9:
                            transport_segment["completed"] = True
                            transport_completed = True
                            current_location = machine_id
                            release_time = transport_end
                        else:
                            release_time = transport_end
                            current_location = source_machine
                            transport_completed = (
                                self._inboundTransportCompleted(
                                    job_id,
                                    operation_id,
                                    inbound_transport,
                                )
                            )
                        transport_segments.append(
                            transport_segment
                        )
                        added_transport_time = inbound_transport
                        added_transport_energy = inbound_energy

            start_time = max(release_time, machine.ready_time)
            end_time = start_time + task.processing_times[machine_id]
            planned = PlannedOperation(
                job_id=job_id,
                operation_id=operation_id,
                machine_id=machine_id,
                start_time=start_time,
                end_time=end_time,
                transport_segments=[
                    dict(segment)
                    for segment in transport_segments
                ],
            )

            task.status = "scheduled"
            task.assigned_machine = machine_id
            task.planned_start = start_time
            task.planned_end = end_time
            task.source_machine = source_machine
            task.transport_time = inbound_transport
            task.transport_energy = inbound_energy
            task.transport_start = transport_start
            task.transport_end = transport_end
            task.transport_completed = transport_completed
            task.transport_segments = [
                dict(segment) for segment in transport_segments
            ]
            if task.transport_completed:
                current_location = machine_id
            task.current_location_machine = current_location
            self.assignTaskPlan(task, planned)
            machine.enqueueOperation(planned)
            machine.ready_time = end_time
            self.scheduled_operations[machine_id].append(
                [job_id, operation_id]
            )
            self.planned_operations.append(planned)
            transport_time_added += added_transport_time
            transport_energy_added += added_transport_energy

            if old_machines[(job_id, operation_id)] != machine_id:
                moved_operations.append(
                    {
                        "task_id": task.task_id,
                        "job_id": job_id,
                        "operation_id": operation_id,
                        "old_machine_id": old_machines[
                            (job_id, operation_id)
                        ],
                        "current_position_machine_id": task.source_machine,
                        "new_machine_id": machine_id,
                        "transport_time": sum(
                            segment["transport_time"]
                            for segment in transport_segments
                        ),
                        "transport_energy": sum(
                            segment["transport_energy"]
                            for segment in transport_segments
                        ),
                        "transport_start": task.transport_start,
                        "transport_end": task.transport_end,
                        "start_time": start_time,
                        "waiting_time": task.waiting_time,
                    }
                )

            if (
                operation_id + 1 < job.operation_count
                and (
                    job_id,
                    operation_id + 1,
                ) not in self.deferred_anomaly_tasks
                and job.tasks[operation_id + 1].status
                in {"pending", "scheduled"}
                and (job_id, operation_id + 1) in assignments
            ):
                next_operation_id = operation_id + 1
                next_machine_id = assignments[
                    (job_id, next_operation_id)
                ]
                next_release_time = self._reoptimizationReleaseEstimate(
                    job_id,
                    next_operation_id,
                    next_machine_id,
                    end_time,
                    old_transport_states[
                        (job_id, next_operation_id)
                    ],
                    now,
                )
                heapq.heappush(
                    operation_queue,
                    (
                        next_release_time,
                        0,
                        job_id,
                        next_operation_id,
                        end_time,
                    ),
                )

        processing_machine_ids = {
            task.assigned_machine for task in processing_tasks
        }
        for machine_id, machine in enumerate(self.machines):
            if machine_id not in scoped_machine_ids:
                continue
            first_operation = machine.nextPendingOperation()
            if (
                first_operation is not None
                and machine_id not in processing_machine_ids
            ):
                self.addEvent(
                    OperationStartEvent(
                        self.newEventId(),
                        first_operation.start_time,
                        first_operation.job_id,
                        first_operation.operation_id,
                        first_operation.machine_id,
                    )
                )

        self.planned_operations.sort(
            key=lambda operation: (
                operation.start_time,
                operation.machine_id,
                operation.job_id,
                operation.operation_id,
            )
        )
        self.scheduleTransportFinishEvents(
            [
                operation
                for operation in self.planned_operations
                if operation.stage_id in scoped_stage_ids
            ],
            after_time=now,
        )
        self.updateEventQueue()
        self.refreshRealtimeObjectives()
        return {
            "reoptimized_at": now,
            "unfinished_task_count": len(unfinished_tasks),
            "moved_operation_count": len(moved_operations),
            "moved_operations": moved_operations,
            "processing_operations": [
                {
                    "task_id": task.task_id,
                    "job_id": task.job_id,
                    "operation_id": task.operation_id,
                    "machine_id": task.assigned_machine,
                    "actual_start": task.actual_start,
                    "expected_end": effective_ends[
                        (task.job_id, task.operation_id)
                    ],
                }
                for task in processing_tasks
            ],
            "transport_time_added": transport_time_added,
            "transport_energy_added": transport_energy_added,
            "process_ids": sorted(scoped_stage_ids),
        }

    def submitRandomJobsAndReoptimize(
        self,
        current_time=None,
        seed=0,
        order_source="manual",
    ):
        """
        Add a batch of generated Jobs and reschedule all unfinished work.

        Processing tasks keep their current machine and finish event. Every
        unfinished task, including all tasks of Jobs currently in job_queue,
        is assigned again and inserted into the rebuilt machine queues.
        """
        now = self.curr_time if current_time is None else float(current_time)
        initial_jobs = list(self.jobs[:self.initial_job_count])
        job_count = max(3, self.initial_job_count // 2)
        new_jobs = []
        for index in range(job_count):
            if self.process_definitions:
                job = self._generate_process_chain_job(
                    self.jobs,
                    now,
                    int(seed) + index,
                    template_jobs=initial_jobs,
                )
            else:
                job = generate_random_job(
                    self.jobs,
                    len(self.machines),
                    now,
                    int(seed) + index,
                    template_jobs=initial_jobs,
                )
            self.jobs.append(job)
            self.job_queue.append(
                Order(job.job_id, job.priority, now)
            )
            new_jobs.append(job)

        order_batch = self.registerOrderBatch(
            [job.job_id for job in new_jobs],
            now,
            source=order_source,
        )
        assignments = self._greedyUnfinishedAssignments()
        reoptimization = self.reoptimizeUnfinishedOperations(
            assignments,
            current_time=now,
        )

        queued_orders = list(self.job_queue)
        processing_job_ids = {
            existing_order.job_id
            for existing_order in self.processing_queue
        }
        self.processing_queue.extend(
            queued_order
            for queued_order in queued_orders
            if queued_order.job_id not in processing_job_ids
        )
        self.job_queue.clear()

        reoptimization.update(
            {
                "new_jobs": [{
                    "job_id": job.job_id,
                    "operation_count": job.operation_count,
                    "weight": job.weight,
                    "ready_time": job.ready_time,
                    "due_time": job.due_time,
                    "earliness_cost": job.earliness_cost,
                    "tardiness_cost": job.tardiness_cost,
                    "processing_options": [
                        {
                            "operation_id": task.operation_id,
                            "machines": dict(task.processing_times),
                            "energies": dict(task.processing_energies),
                        }
                        for task in job.tasks
                    ],
                    "transport_time": job.transport_time_matrix,
                    "transport_energy": job.transport_energy_matrix,
                } for job in new_jobs],
                "submitted_job_count": len(new_jobs),
                "order_id": order_batch.order_id,
                "order_source": order_batch.source,
                "order_job_ids": list(order_batch.job_ids),
                "initial_job_count": self.initial_job_count,
                "queued_job_count": len(queued_orders),
                "processing_queue_size": len(self.processing_queue),
                "rescheduling_scope": (
                    "queued_jobs_and_all_unfinished_machine_operations"
                ),
            }
        )
        return reoptimization

    def _taskCurrentLocation(self, task):
        """Return the real machine where the job is currently located."""
        if task.current_location_machine is not None:
            return task.current_location_machine
        if task.actual_start is not None or task.transport_completed:
            return task.assigned_machine
        return task.source_machine

    def _reoptimizationReleaseEstimate(
        self,
        job_id,
        operation_id,
        machine_id,
        fallback_time,
        previous_transport,
        now,
    ):
        """Estimate when an unfinished task can enter its target machine."""
        job = self.jobs[job_id]
        if operation_id == 0:
            return max(fallback_time, now, job.ready_time)

        if previous_transport["transport_completed"]:
            previous_location = previous_transport[
                "current_location_machine"
            ]
            if previous_location == machine_id:
                transport_end = previous_transport["transport_end"]
                return max(
                    fallback_time,
                    now,
                    transport_end or fallback_time,
                )
            if previous_location is None:
                previous_location = job.tasks[
                    operation_id - 1
                ].assigned_machine
            if (
                previous_location is not None
                and previous_location != machine_id
            ):
                return (
                    max(fallback_time, now)
                    + self._jobTransportTime(
                        job_id,
                        previous_location,
                        machine_id,
                    )
                )
            return max(fallback_time, now)

        return self.operationReleaseTime(
            job_id,
            operation_id,
            machine_id,
            fallback_time,
        )[0]

    def _taskEffectiveEnd(self, task):
        if task.actual_end is not None:
            return task.actual_end
        if task.actual_start is not None and task.assigned_machine is not None:
            nominal_end = (
                task.actual_start
                + task.processing_times[task.assigned_machine]
            )
            if task.planned_end is None:
                return nominal_end
            # Machine degradation can extend an active operation without
            # changing its nominal processing time. Reoptimization must keep
            # the extended finish, otherwise it recreates a finish event in
            # the past and the operation can remain processing forever.
            return max(nominal_end, task.planned_end)
        return task.planned_end

    @staticmethod
    def _plannedOperationFromTask(task):
        return PlannedOperation(
            job_id=task.job_id,
            operation_id=task.operation_id,
            machine_id=task.assigned_machine,
            start_time=task.actual_start or task.planned_start,
            end_time=task.actual_end or task.planned_end,
            source_machine=task.source_machine,
            transport_start=task.transport_start,
            transport_end=task.transport_end,
            transport_time=task.transport_time,
            transport_energy=task.transport_energy,
            transport_segments=[
                dict(segment) for segment in task.transport_segments
            ],
            waiting_time=task.waiting_time,
            status=task.status,
            stage_id=task.stage_id,
            stage_operation_id=task.stage_operation_id,
        )

    def updateEventQueue(self):
        self.event_queue.sort(
            key=lambda event: (
                event.timestamp,
                EVENT_QUEUE_PRIORITIES.get(type(event), 99),
                event.id,
            )
        )

    def newEventId(self):
        self.curr_event_id += 1
        return self.curr_event_id
    
    def submitJob(self, job_id, priority, timestamp):
        """提交一个新的作业"""
        event = JobSubmitEvent(self.newEventId(), timestamp, job_id, priority)
        self.addEvent(event)

    def handleEvent(self, event):
        """处理事件"""
        if isinstance(event, ScheduleEvent):
            self.handleScheduleEvent(event)
        elif isinstance(event, OrderInsertEvent):
            return self.handleOrderInsertEvent(event)
        elif isinstance(event, OrderCancelEvent):
            return self.handleOrderCancelEvent(event)
        elif isinstance(event, MachineAnomalyEvent):
            return self.handleMachineAnomalyEvent(event)
        elif isinstance(event, JobSubmitEvent):
            self.handleJobSubmitEvent(event)
        elif isinstance(event, JobStartEvent):
            self.handleJobStartEvent(event)
        elif isinstance(event, JobFinishEvent):
            self.handleJobFinishEvent(event)
        elif isinstance(event, TransportFinishEvent):
            self.handleTransportFinishEvent(event)
        elif isinstance(event, OperationStartEvent):
            return self.handleOperationStartEvent(event)
        elif isinstance(event, OperationFinishEvent):
            self.handleOperationFinishEvent(event)
        elif isinstance(event, ProcessStageFinishEvent):
            return self.handleProcessStageFinishEvent(event)
        elif isinstance(event, ProcessStageBatchScheduleEvent):
            return self.handleProcessStageBatchScheduleEvent(event)
        elif isinstance(event, MachineRecoveryEvent):
            self.handleMachineRecoveryEvent(event)
        elif isinstance(event, MaterialReplenishmentEvent):
            return self.handleMaterialReplenishmentEvent(event)
        elif isinstance(event, MaterialRecoveryEvent):
            return self.handleMaterialRecoveryEvent(event)
        else:
            print(f"Error: Unknown event type {type(event)} with ID {event.id}.")
            return False
        return True

    def handleOrderInsertEvent(self, event):
        if self.log_tag:
            print(
                f"Inserting orders at time {event.timestamp} "
                f"with seed {event.seed}."
            )
        result = self.submitRandomJobsAndReoptimize(
            current_time=event.timestamp,
            seed=event.seed,
            order_source=event.order_source,
        )
        event.order_id = result.get("order_id")
        event.job_ids = [
            job["job_id"] for job in result.get("new_jobs", [])
        ]
        event.job_count = len(event.job_ids)
        event.result = result
        return True

    def handleOrderCancelEvent(self, event):
        if self.log_tag:
            print(
                f"Canceling orders {event.job_ids} "
                f"at time {event.timestamp}."
            )
        if event.batch:
            result = self.cancelJobs(
                event.job_ids,
                current_time=event.timestamp,
            )
        else:
            result = self.cancelJob(
                event.job_ids[0],
                current_time=event.timestamp,
            )
        if event.order_ids:
            self._markCanceledOrderBatches(
                event.order_ids,
                event.timestamp,
            )
            result["order_ids"] = list(event.order_ids)
        event.result = result
        return True

    def handleMachineAnomalyEvent(self, event):
        if self.log_tag:
            print(
                "Applying machine anomaly "
                f"{event.anomaly_type} to machine {event.machine_id} "
                f"at time {event.timestamp}."
            )
        result = self.startMachineAnomaly(
            event.machine_id,
            event.anomaly_type,
            event.duration,
            current_time=event.timestamp,
        )
        event.machine_status = result["machine_status"]
        event.result = result
        return True

    def handleScheduleEvent(self, event):
        """调度当前 job_queue 中的作业，并生成完整机器队列。"""
        if self.log_tag:
            print(f"Generating complete schedule at time {event.timestamp}")

        self.generatePlan()

    def generatePlan(self):
        """
        按作业先后约束生成完整调度计划。

        每个作业仅把当前可调度的下一道工序放入规划队列，工序分配到机器后，
        再把同一作业的后续工序加入规划队列。这样既保证同一作业的工序顺序，
        也能让不同作业的工序在机器之间交错排队。
        """
        queued_orders = list(self.job_queue)
        queued_job_ids = {
            order.job_id for order in queued_orders
        }
        if len(queued_job_ids) != len(queued_orders):
            raise RuntimeError(
                "job_queue contains duplicate job IDs."
            )
        self.processing_queue = []
        self.finished_queue = []
        self.completed_operations = set()
        self.planned_operations = []
        self.pending_material_recoveries.clear()

        for job in self.jobs:
            if job.job_id not in queued_job_ids:
                continue
            job.completion_time = None
            job.earliness = 0
            job.tardiness = 0
            job.processing_energy = 0
            job.transport_energy = 0
            for task in job.tasks:
                task.status = (
                    "blocked"
                    if task.stage_id > 1
                    else "pending"
                )
                task.assigned_machine = None
                task.planned_start = None
                task.planned_end = None
                task.actual_start = None
                task.actual_end = None
                task.source_machine = None
                task.transport_start = None
                task.transport_end = None
                task.transport_time = 0
                task.transport_energy = 0
                task.transport_completed = False
                task.committed_transport_energy = 0
                task.transport_segments = []
                task.current_location_machine = None
                task.waiting_time = 0
                task.material_consumption_committed = False

        for machine in self.machines:
            machine.clearPendingOperations()
            machine.machine_status = "idle"
            machine.ready_time = 0

        self.scheduled_operations = [
            [] for _ in range(len(self.machines))
        ]

        operation_queue = []
        for order in queued_orders:
            job = self.jobs[order.job_id]
            heapq.heappush(
                operation_queue,
                (
                    job.ready_time,
                    -order.priority,
                    job.job_id,
                    0,
                    job.ready_time,
                ),
            )

        while operation_queue:
            (
                _queue_release_time,
                neg_priority,
                job_id,
                operation_id,
                release_time,
            ) = heapq.heappop(operation_queue)
            job = self.jobs[job_id]
            machine_id = self.placeOperation(job_id, operation_id)
            if machine_id == -1:
                raise RuntimeError(
                    f"No available machine for job {job_id} "
                    f"operation {operation_id}."
                )

            machine = self.machines[machine_id]
            (
                release_time,
                inbound_transport,
                inbound_energy,
                transport_start,
                transport_end,
            ) = (
                self.operationReleaseTime(
                    job_id,
                    operation_id,
                    machine_id,
                    release_time,
                )
            )
            start_time = max(release_time, machine.ready_time)
            processing_time = job.operation_times[operation_id][machine_id]
            if not math.isfinite(processing_time):
                raise RuntimeError(
                    f"Invalid processing time for job {job_id} "
                    f"operation {operation_id} on machine {machine_id}."
                )

            end_time = start_time + processing_time
            transport_segments = []
            if (
                operation_id > 0
                and inbound_transport > 0
                and transport_start is not None
                and transport_end is not None
            ):
                transport_segments.append(
                    {
                        "source_machine": job.tasks[
                            operation_id - 1
                        ].assigned_machine,
                        "target_machine": machine_id,
                        "transport_start": transport_start,
                        "transport_end": transport_end,
                        "transport_time": inbound_transport,
                        "transport_energy": inbound_energy,
                        "completed": False,
                    }
                )
            planned_operation = PlannedOperation(
                job_id=job_id,
                operation_id=operation_id,
                machine_id=machine_id,
                start_time=start_time,
                end_time=end_time,
                transport_segments=[
                    dict(segment)
                    for segment in transport_segments
                ],
            )
            machine.enqueueOperation(planned_operation)
            machine.ready_time = end_time
            task = job.tasks[operation_id]
            task.status = "scheduled"
            task.assigned_machine = machine_id
            task.planned_start = start_time
            task.planned_end = end_time
            task.source_machine = (
                job.tasks[operation_id - 1].assigned_machine
                if operation_id > 0
                else None
            )
            task.transport_time = inbound_transport
            task.transport_energy = inbound_energy
            task.transport_start = transport_start
            task.transport_end = transport_end
            task.transport_segments = [
                dict(segment) for segment in transport_segments
            ]
            task.transport_completed = self._inboundTransportCompleted(
                job_id,
                operation_id,
                inbound_transport,
            )
            task.current_location_machine = (
                task.source_machine
                if task.source_machine is not None
                and not task.transport_completed
                else machine_id
            )
            self.assignTaskPlan(task, planned_operation)
            self.scheduled_operations[machine_id].append(
                [job_id, operation_id]
            )
            self.planned_operations.append(planned_operation)

            next_operation_id = operation_id + 1
            if (
                next_operation_id < job.operation_count
                and job.tasks[next_operation_id].status != "blocked"
            ):
                next_machine_id = self.placeOperation(
                    job_id,
                    next_operation_id,
                )
                next_release_time = self.operationReleaseTime(
                    job_id,
                    next_operation_id,
                    next_machine_id,
                    end_time,
                )[0]
                heapq.heappush(
                    operation_queue,
                    (
                        next_release_time,
                        neg_priority,
                        job_id,
                        next_operation_id,
                        end_time,
                    ),
                )

        for machine in self.machines:
            first_operation = machine.nextPendingOperation()
            if first_operation is not None:
                self.addEvent(
                    OperationStartEvent(
                        self.newEventId(),
                        first_operation.start_time,
                        first_operation.job_id,
                        first_operation.operation_id,
                        first_operation.machine_id,
                    )
                )
        self.scheduleTransportFinishEvents(
            self.planned_operations,
            after_time=self.curr_time,
        )

        self.processing_queue.extend(queued_orders)
        self.job_queue.clear()

    def handleJobSubmitEvent(self, event):
        if self.log_tag:
            print(f"Job {event.job_id} submitted at time {event.timestamp} with priority {event.priority}")
        if self.jobs[event.job_id].is_canceled:
            return
        self.job_queue.append(Order(event.job_id, event.priority, event.timestamp))
        self.scheduleJobs()

    def scheduleJobs(self):
        self.job_queue.sort(key=lambda x: (-x.priority, x.submit_time))
        for order in self.job_queue:
            if order.submit_time <= self.curr_time:
                jobStartEvent = JobStartEvent(self.newEventId(), self.curr_time, order.job_id)
                self.addEvent(jobStartEvent)
                self.processing_queue.append(order)
                self.job_queue.remove(order)

    def handleJobStartEvent(self, event):
        if self.log_tag:
            print(f"Job {event.job_id} started at time {event.timestamp}")
        if self.jobs[event.job_id].is_canceled:
            return
        self.scheduleOperation(event.job_id, 0, event.timestamp)

    def handleJobFinishEvent(self, event):
        if self.log_tag:
            print(f"Job {event.job_id} finished at time {event.timestamp}")
        self.processing_queue.sort(key=lambda x: (-x.priority, x.submit_time))
        for order in self.processing_queue:
            if order.job_id == event.job_id:
                self.processing_queue.remove(order)
                self.finished_queue.append(order)
                break
        self.makespan = max(self.makespan, event.timestamp)
        self.refreshRealtimeObjectives()

    def handleTransportFinishEvent(self, event):
        if not self._isCurrentTransportFinishEvent(event):
            if self.log_tag:
                print(
                    "Ignoring stale transport event "
                    f"{event.id} at time {event.timestamp}."
                )
            return False
        task = self.jobs[event.job_id].tasks[event.operation_id]
        if task.transport_segments:
            completed_segment = next(
                segment
                for segment in task.transport_segments
                if (
                    not segment["completed"]
                    and segment["target_machine"] == event.machine_id
                    and math.isclose(
                        float(event.timestamp),
                        float(segment["transport_end"]),
                        rel_tol=0,
                        abs_tol=1e-9,
                    )
                )
            )
            completed_segment["completed"] = True
            task.current_location_machine = event.machine_id
            remaining_segments = [
                segment
                for segment in task.transport_segments
                if not segment["completed"]
            ]
            if remaining_segments:
                next_segment = remaining_segments[0]
                task.source_machine = next_segment["source_machine"]
                task.transport_start = next_segment["transport_start"]
                task.transport_end = next_segment["transport_end"]
                task.transport_time = next_segment["transport_time"]
                task.transport_energy = next_segment[
                    "transport_energy"
                ]
                task.transport_completed = False
            else:
                task.transport_completed = True
        else:
            task.transport_completed = True
            task.current_location_machine = event.machine_id
        self._startReadyOperationIfPossible(
            event.machine_id,
            event.timestamp,
        )
        self.refreshRealtimeObjectives()
        return True

    def _startReadyOperationIfPossible(self, machine_id, current_time):
        """Schedule the first queued operation now if all constraints are met."""
        machine = self.machines[machine_id]
        if machine.machine_status in {"failed", "repairing"}:
            return False
        if any(
            task.status == "processing" and task.actual_end is None
            for job in self.jobs
            for task in job.tasks
            if task.assigned_machine == machine_id
        ):
            return False

        operation = machine.nextPendingOperation()
        if operation is None:
            return False
        job = self.jobs[operation.job_id]
        task = job.tasks[operation.operation_id]
        if (
            job.is_canceled
            or task.status not in {"pending", "scheduled"}
            or task.actual_start is not None
            or not task.transport_completed
            or (
                task.ready_not_before is not None
                and current_time + 1e-9 < task.ready_not_before
            )
        ):
            return False

        if task.operation_id == 0:
            if current_time + 1e-9 < job.ready_time:
                return False
        else:
            predecessor = job.tasks[task.operation_id - 1]
            if (
                predecessor.status != "completed"
                or predecessor.actual_end is None
                or current_time + 1e-9 < predecessor.actual_end
            ):
                return False

        start_time = current_time
        end_time = (
            start_time + task.processing_times[operation.machine_id]
        )
        operation.start_time = start_time
        operation.end_time = end_time
        operation.status = "scheduled"
        task.planned_start = start_time
        task.planned_end = end_time
        task.waiting_time = max(
            0,
            start_time
            - (
                task.transport_end
                if task.transport_end is not None
                else (
                    predecessor.actual_end
                    if task.operation_id > 0
                    else job.ready_time
                )
            ),
        )
        machine.ready_time = end_time

        self.event_queue = [
            queued_event
            for queued_event in self.event_queue
            if not (
                isinstance(queued_event, OperationStartEvent)
                and queued_event.job_id == task.job_id
                and queued_event.operation_id == task.operation_id
                and queued_event.machine_id == operation.machine_id
            )
        ]
        self.addEvent(
            OperationStartEvent(
                self.newEventId(),
                start_time,
                task.job_id,
                task.operation_id,
                operation.machine_id,
            )
        )
        return True
    
    def scheduleProcessStage(self, job_id, stage_id, timestamp):
        """Backward-compatible single-Job process-stage scheduling."""
        return self.scheduleProcessStageBatch(
            {job_id: float(timestamp)},
            stage_id,
            timestamp,
        )

    def _estimateBatchMachine(
        self,
        job_id,
        operation_id,
        fallback_time,
        not_before,
    ):
        """Choose the machine with the earliest estimated completion."""
        task = self.jobs[job_id].tasks[operation_id]
        candidates = []
        for machine_id in task.eligible_machines:
            if machine_id is None:
                continue
            machine = self.machines[machine_id]
            if machine.machine_status in {"failed", "repairing"}:
                continue
            (
                release_time,
                _,
                _,
                _,
                _,
            ) = self.operationReleaseTime(
                job_id,
                operation_id,
                machine_id,
                fallback_time,
            )
            start_time = max(
                release_time,
                machine.ready_time,
                not_before,
            )
            end_time = (
                start_time + task.processing_times[machine_id]
            )
            candidates.append(
                (
                    end_time,
                    task.processing_times[machine_id],
                    machine_id,
                )
            )
        if not candidates:
            job = self.jobs[job_id]
            raise RuntimeError(
                f"No machine can process job {job_id} "
                f"operation {operation_id} "
                f"for job priority {job.priority}"
            )
        return min(candidates)[2]

    def scheduleProcessStageBatch(
        self,
        job_ready_times,
        stage_id,
        timestamp=None,
    ):
        """
        Schedule one complete target process for a batch of Jobs.

        Jobs are released from their individual arrival times, while machine
        allocation is coordinated once for the whole batch. This preserves
        transport timing and avoids rebuilding the Web plan for every Job.
        """
        stage_id = int(stage_id)
        normalized_job_ready_times = {
            int(job_id): float(ready_time)
            for job_id, ready_time in job_ready_times.items()
        }
        batch_time = max(
            normalized_job_ready_times.values(),
            default=self.curr_time,
        )
        if timestamp is not None:
            batch_time = max(float(timestamp), self.curr_time)

        operation_queue = []
        for job_id, ready_time in normalized_job_ready_times.items():
            job = self.jobs[job_id]
            if job.is_canceled:
                continue
            stage_tasks = [
                task
                for task in job.tasks
                if task.stage_id == stage_id
            ]
            for task in stage_tasks:
                if task.status == "blocked":
                    task.status = "pending"
            first_task = next(
                (
                    task
                    for task in stage_tasks
                    if task.status == "pending"
                ),
                None,
            )
            if first_task is None:
                continue
            heapq.heappush(
                operation_queue,
                (
                    max(ready_time, job.ready_time),
                    -job.priority,
                    job_id,
                    first_task.operation_id,
                    ready_time,
                ),
            )

        planned_operations = []
        touched_machines = set()
        while operation_queue:
            (
                _queue_release_time,
                _,
                job_id,
                operation_id,
                fallback_time,
            ) = heapq.heappop(operation_queue)
            job = self.jobs[job_id]
            task = job.tasks[operation_id]
            if (
                job.is_canceled
                or task.stage_id != stage_id
                or task.status != "pending"
            ):
                continue

            machine_id = self._estimateBatchMachine(
                job_id,
                operation_id,
                fallback_time,
                batch_time,
            )
            (
                release_time,
                inbound_transport,
                inbound_energy,
                transport_start,
                transport_end,
            ) = self.operationReleaseTime(
                job_id,
                operation_id,
                machine_id,
                fallback_time,
            )
            machine = self.machines[machine_id]
            start_time = max(
                release_time,
                machine.ready_time,
                batch_time,
            )
            end_time = (
                start_time + task.processing_times[machine_id]
            )
            planned = PlannedOperation(
                job_id=job_id,
                operation_id=operation_id,
                machine_id=machine_id,
                start_time=start_time,
                end_time=end_time,
            )
            task.status = "scheduled"
            task.assigned_machine = machine_id
            task.planned_start = start_time
            task.planned_end = end_time
            task.source_machine = (
                job.tasks[operation_id - 1].assigned_machine
                if operation_id > 0
                else None
            )
            task.transport_time = inbound_transport
            task.transport_energy = inbound_energy
            task.transport_start = transport_start
            task.transport_end = transport_end
            task.transport_completed = (
                operation_id == 0
                or (
                    transport_end is not None
                    and transport_end <= batch_time + 1e-9
                )
            )
            task.transport_segments = []
            if (
                task.source_machine is not None
                and inbound_transport > 0
                and transport_start is not None
                and transport_end is not None
            ):
                task.transport_segments.append(
                    {
                        "source_machine": task.source_machine,
                        "target_machine": machine_id,
                        "transport_start": transport_start,
                        "transport_end": transport_end,
                        "transport_time": inbound_transport,
                        "transport_energy": inbound_energy,
                        "completed": task.transport_completed,
                    }
                )
            task.current_location_machine = (
                task.source_machine
                if (
                    task.source_machine is not None
                    and not task.transport_completed
                )
                else machine_id
            )
            self.assignTaskPlan(task, planned)
            machine.enqueueOperation(planned)
            machine.ready_time = end_time
            self.scheduled_operations[machine_id].append(
                [job_id, operation_id]
            )
            self.planned_operations.append(planned)
            planned_operations.append(planned)
            touched_machines.add(machine_id)

            next_task = next(
                (
                    candidate
                    for candidate in job.tasks
                    if (
                        candidate.stage_id == stage_id
                        and candidate.status == "pending"
                    )
                ),
                None,
            )
            if next_task is not None:
                heapq.heappush(
                    operation_queue,
                    (
                        end_time,
                        -job.priority,
                        job_id,
                        next_task.operation_id,
                        end_time,
                    ),
                )

        planned_keys = {
            (operation.job_id, operation.operation_id)
            for operation in planned_operations
        }
        for machine_id in sorted(touched_machines):
            next_operation = next(
                (
                    operation
                    for operation
                    in self.machines[machine_id].pending_operations
                    if (
                        operation.job_id,
                        operation.operation_id,
                    ) in planned_keys
                ),
                None,
            )
            if next_operation is None:
                continue
            self.addEvent(
                OperationStartEvent(
                    self.newEventId(),
                    next_operation.start_time,
                    next_operation.job_id,
                    next_operation.operation_id,
                    next_operation.machine_id,
                )
            )
        self.scheduleTransportFinishEvents(
            planned_operations,
            after_time=batch_time,
        )
        self.updateEventQueue()
        return planned_operations

    def scheduleOperation(self, job_id, operation_id, timestamp):
        if self.log_tag:
            print(f"Operation {job_id}-{operation_id} scheduled at time {timestamp}")
        if (
            (job_id, operation_id)
            in self.deferred_anomaly_tasks
        ):
            return
        if (
            self.jobs[job_id].is_canceled
            or self.jobs[job_id].tasks[operation_id].status == "canceled"
        ):
            return
        machine_id = self.placeOperation(job_id, operation_id)
        if machine_id == -1:
            raise RuntimeError(
                f"No machine can process job {job_id} operation {operation_id}"
            )
        (
            release_time,
            inbound_transport,
            inbound_energy,
            transport_start,
            transport_end,
        ) = (
            self.operationReleaseTime(
                job_id,
                operation_id,
                machine_id,
                timestamp,
            )
        )
        start_time = max(
            release_time,
            self.machines[machine_id].ready_time,
        )
        finish_time = start_time + self.jobs[job_id].operation_times[operation_id][machine_id]
        planned_operation = PlannedOperation(
            job_id=job_id,
            operation_id=operation_id,
            machine_id=machine_id,
            start_time=start_time,
            end_time=finish_time,
        )
        self.machines[machine_id].scheduleOperation(finish_time)
        self.machines[machine_id].enqueueOperation(planned_operation)
        task = self.jobs[job_id].tasks[operation_id]
        task.status = "scheduled"
        task.assigned_machine = machine_id
        task.planned_start = start_time
        task.planned_end = finish_time
        task.source_machine = (
            self.jobs[job_id].tasks[operation_id - 1].assigned_machine
            if operation_id > 0
            else None
        )
        task.transport_time = inbound_transport
        task.transport_energy = inbound_energy
        task.transport_start = transport_start
        task.transport_end = transport_end
        task.transport_completed = self._inboundTransportCompleted(
            job_id,
            operation_id,
            inbound_transport,
        )
        task.current_location_machine = (
            task.source_machine
            if task.source_machine is not None
            and not task.transport_completed
            else machine_id
        )
        self.assignTaskPlan(task, planned_operation)
        self.scheduled_operations[machine_id].append([job_id, operation_id])
        self.planned_operations.append(planned_operation)
        operationStartEvent = OperationStartEvent(self.newEventId(), start_time, job_id, operation_id, machine_id)
        self.addEvent(operationStartEvent)

    def operationReleaseTime(
        self,
        job_id,
        operation_id,
        machine_id,
        fallback_time,
    ):
        """计算任务最早可开始时间及入站运输信息。"""
        job = self.jobs[job_id]
        if operation_id == 0:
            return max(fallback_time, job.ready_time), 0, 0, None, None

        predecessor = job.tasks[operation_id - 1]
        predecessor_end = (
            predecessor.actual_end
            if predecessor.actual_end is not None
            else predecessor.planned_end
        )
        if (
            predecessor.assigned_machine is None
            or predecessor_end is None
        ):
            return fallback_time, 0, 0, None, None

        transport_time = self._jobTransportTime(
            job_id,
            predecessor.assigned_machine,
            machine_id,
        )
        transport_energy = self._jobTransportEnergy(
            job_id,
            predecessor.assigned_machine,
            machine_id,
        )
        transport_start = max(fallback_time, predecessor_end)
        transport_end = transport_start + transport_time
        return (
            transport_end,
            transport_time,
            transport_energy,
            transport_start,
            transport_end,
        )

    def _jobTransportTime(self, job_id, source_machine, target_machine):
        job = self.jobs[job_id]
        matrix = job.transport_time_matrix or self.transport_time
        return matrix[source_machine][target_machine]

    def _jobTransportEnergy(self, job_id, source_machine, target_machine):
        job = self.jobs[job_id]
        matrix = job.transport_energy_matrix or self.transport_energy
        return matrix[source_machine][target_machine]

    def _inboundTransportCompleted(
        self,
        job_id,
        operation_id,
        inbound_transport,
    ):
        """Return whether zero-time inbound transport has actually completed."""
        if operation_id == 0:
            return True
        if inbound_transport > 0:
            return False
        predecessor = self.jobs[job_id].tasks[operation_id - 1]
        return (
            predecessor.status == "completed"
            and predecessor.actual_end is not None
        )

    def _transportChainMatchesPredecessor(
        self,
        job_id,
        segments,
        predecessor,
    ):
        """Check that an existing transport chain is still causally valid."""
        if not segments:
            return False
        predecessor_end = (
            predecessor.actual_end
            if predecessor.actual_end is not None
            else self._taskEffectiveEnd(predecessor)
        )
        if (
            predecessor_end is None
            or predecessor.assigned_machine is None
            or segments[0]["source_machine"]
            != predecessor.assigned_machine
            or segments[0]["transport_start"]
            < predecessor_end - 1e-9
        ):
            return False

        time_matrix = (
            self.jobs[job_id].transport_time_matrix
            or self.transport_time
        )
        for index, segment in enumerate(segments):
            source = segment["source_machine"]
            target = segment["target_machine"]
            expected_time = time_matrix[source][target]
            if not math.isclose(
                segment["transport_time"],
                expected_time,
                rel_tol=0,
                abs_tol=1e-9,
            ):
                return False
            if not math.isclose(
                segment["transport_end"] - segment["transport_start"],
                expected_time,
                rel_tol=0,
                abs_tol=1e-9,
            ):
                return False
            if index > 0:
                previous = segments[index - 1]
                if (
                    source != previous["target_machine"]
                    or not math.isclose(
                        segment["transport_start"],
                        previous["transport_end"],
                        rel_tol=0,
                        abs_tol=1e-9,
                    )
                ):
                    return False
        return True

    def assignTaskPlan(self, task, planned_operation):
        """Copy machine, transport and timing details to task and plan."""
        if task.transport_start is not None:
            arrival_time = task.transport_end
        elif task.operation_id > 0:
            predecessor = self.jobs[task.job_id].tasks[
                task.operation_id - 1
            ]
            arrival_time = (
                predecessor.actual_end
                if predecessor.actual_end is not None
                else predecessor.planned_end
            )
        else:
            arrival_time = self.jobs[task.job_id].ready_time
        if arrival_time is None:
            arrival_time = self.jobs[task.job_id].ready_time

        task.waiting_time = max(0, task.planned_start - arrival_time)
        planned_operation.source_machine = task.source_machine
        planned_operation.transport_start = task.transport_start
        planned_operation.transport_end = task.transport_end
        planned_operation.transport_time = task.transport_time
        planned_operation.transport_energy = task.transport_energy
        planned_operation.transport_segments = [
            dict(segment) for segment in task.transport_segments
        ]
        planned_operation.waiting_time = task.waiting_time
        planned_operation.status = task.status
        planned_operation.stage_id = task.stage_id
        planned_operation.stage_operation_id = (
            task.stage_operation_id
        )

    def placeOperation(self, job_id, operation_id):
        job = self.jobs[job_id]
        minMachineId = -1
        minTime = float('inf')  # 初始化为无穷大
        for machine_id in range(len(self.machines)):
            if self.machines[machine_id].machine_status in {
                "failed",
                "repairing",
            }:
                continue
            if job.operation_times[operation_id][machine_id] < minTime:
                minTime = job.operation_times[operation_id][machine_id]
                minMachineId = machine_id
        return minMachineId

    def isOperationPlanned(self, job_id, operation_id):
        for machine in self.machines:
            if any(
                operation.job_id == job_id
                and operation.operation_id == operation_id
                for operation in machine.pending_operations
            ):
                return True

        for event in self.event_queue:
            if (
                isinstance(event, OperationStartEvent)
                and event.job_id == job_id
                and event.operation_id == operation_id
            ):
                return True

        return any(
            (job_id, operation_id) in machine_schedule
            for machine_schedule in self.schedule.schedule_items
        )

    def _operationMaterialRequirements(self, job_id, operation_id):
        """Return direct material demand for one operation."""
        job = self.jobs[job_id]
        task = job.tasks[operation_id]
        if task.material_consumption:
            return {
                str(material_id): float(quantity)
                for material_id, quantity
                in task.material_consumption.items()
            }
        if task.stage_id == 1 and task.stage_operation_id == 0:
            stage_materials = job.material_consumption.get(1, {})
            return {
                str(material_id): float(quantity)
                for material_id, quantity
                in stage_materials.get("job_materials", {}).items()
            }
        return {}

    @staticmethod
    def _materialShortages(machine, requirements):
        return {
            material_id: required - float(
                machine.materials.get(material_id, 0.0)
            )
            for material_id, required in requirements.items()
            if (
                float(machine.materials.get(material_id, 0.0))
                + 1e-9
                < required
            )
        }

    def _queueOperationStartForTask(self, task, timestamp):
        existing = next(
            (
                event
                for event in self.event_queue
                if (
                    isinstance(event, OperationStartEvent)
                    and event.job_id == task.job_id
                    and event.operation_id == task.operation_id
                    and event.machine_id == task.assigned_machine
                )
            ),
            None,
        )
        if existing is not None:
            existing.timestamp = min(existing.timestamp, timestamp)
            return existing
        event = OperationStartEvent(
            self.newEventId(),
            timestamp,
            task.job_id,
            task.operation_id,
            task.assigned_machine,
        )
        self.addEvent(event)
        return event

    def _ensureMaterialRecoveryEvents(
        self,
        task,
        machine,
        requirements,
        current_time,
    ):
        """Create one replenishment/recovery pair for a blocked operation."""
        if task.material_consumption_committed or not requirements:
            return None, None
        key = (task.job_id, task.operation_id, machine.machine_id)
        pending_recovery_id = self.pending_material_recoveries.get(key)
        if pending_recovery_id is not None and any(
            event.id == pending_recovery_id
            and isinstance(event, MaterialRecoveryEvent)
            for event in self.event_queue
        ):
            return None, None
        self.pending_material_recoveries.pop(key, None)

        shortages = self._materialShortages(machine, requirements)
        if not shortages:
            return None, None
        target_materials = {
            material_id: (
                required * self.material_replenishment_target_factor
            )
            for material_id, required in requirements.items()
        }
        replenishment_materials = {
            material_id: max(
                0.0,
                target - float(machine.materials.get(material_id, 0.0)),
            )
            for material_id, target in target_materials.items()
        }
        available = {
            material_id: float(
                machine.materials.get(material_id, 0.0)
            )
            for material_id in requirements
        }
        replenishment_event = MaterialReplenishmentEvent(
            self.newEventId(),
            current_time,
            machine.machine_id,
            task.job_id,
            task.operation_id,
            requirements,
            replenishment_materials,
            available,
            target_materials=target_materials,
            shortage_materials=shortages,
        )
        recovery_event = MaterialRecoveryEvent(
            self.newEventId(),
            current_time + self.material_replenishment_lead_time,
            machine.machine_id,
            task.job_id,
            task.operation_id,
            requirements,
            replenishment_materials,
            target_materials=target_materials,
            shortage_materials=shortages,
            replenishment_event_id=replenishment_event.id,
            lead_time=self.material_replenishment_lead_time,
        )
        self.pending_material_recoveries[key] = recovery_event.id
        self.addEvent(replenishment_event)
        self.addEvent(recovery_event)
        return replenishment_event, recovery_event

    def handleMaterialReplenishmentEvent(self, event):
        """Dispatch the missing quantity toward the selected machine."""
        if not 0 <= event.machine_id < len(self.machines):
            return False
        job = self.jobs[event.job_id]
        task = job.tasks[event.operation_id]
        if (
            job.is_canceled
            or task.status in {"canceled", "completed"}
            or task.material_consumption_committed
        ):
            return False

        machine = self.machines[event.machine_id]
        before = {
            material_id: float(
                machine.materials.get(material_id, 0.0)
            )
            for material_id in event.required_materials
        }
        after = {
            material_id: float(
                machine.materials.get(material_id, 0.0)
            )
            for material_id in event.required_materials
        }
        event.available_materials = before
        event.added_materials = {}
        event.result = {
            "success": True,
            "machine_id": event.machine_id,
            "job_id": event.job_id,
            "operation_id": event.operation_id,
            "replenishment_status": "in_transit",
            "replenishment_order": dict(
                event.replenishment_materials
            ),
            "target_materials": dict(event.target_materials),
            "shortage_materials": dict(event.shortage_materials),
            "materials_before": dict(before),
            "materials_after": dict(after),
            "recovered_at": event.timestamp,
            "recovery_at": (
                event.timestamp
                + self.material_replenishment_lead_time
            ),
        }
        return True

    def handleMaterialRecoveryEvent(self, event):
        """Release an operation start event once stock is sufficient."""
        if not 0 <= event.machine_id < len(self.machines):
            return False
        job = self.jobs[event.job_id]
        task = job.tasks[event.operation_id]
        key = (event.job_id, event.operation_id, event.machine_id)
        machine = self.machines[event.machine_id]
        before = {
            material_id: float(
                machine.materials.get(material_id, 0.0)
            )
            for material_id in event.required_materials
        }
        if job.is_canceled or task.status in {
            "canceled",
            "completed",
            "processing",
        }:
            self.pending_material_recoveries.pop(key, None)
            return False
        if task.assigned_machine != event.machine_id:
            self.pending_material_recoveries.pop(key, None)
            event.result = {
                "success": False,
                "reason": "operation_moved",
                "machine_id": event.machine_id,
                "job_id": event.job_id,
                "operation_id": event.operation_id,
                "assigned_machine": task.assigned_machine,
                "recovered_at": event.timestamp,
            }
            return True

        added = {}
        for material_id, planned_quantity in (
            event.replenishment_materials.items()
        ):
            required = event.required_materials[material_id]
            target = event.target_materials.get(
                material_id,
                required * self.material_replenishment_target_factor,
            )
            current = float(machine.materials.get(material_id, 0.0))
            quantity = min(
                planned_quantity,
                max(0.0, target - current),
            )
            if quantity <= 0:
                continue
            machine.materials[material_id] = current + quantity
            added[material_id] = quantity
        event.materials_before_recovery = before
        event.added_materials = added
        event.available_materials = {
            material_id: float(
                machine.materials.get(material_id, 0.0)
            )
            for material_id in event.required_materials
        }
        shortages = self._materialShortages(
            machine,
            event.required_materials,
        )
        if shortages:
            self.pending_material_recoveries.pop(key, None)
            self._ensureMaterialRecoveryEvents(
                task,
                machine,
                event.required_materials,
                event.timestamp,
            )
            event.result = {
                "success": False,
                "machine_id": event.machine_id,
                "job_id": event.job_id,
                "operation_id": event.operation_id,
                "shortage_materials": shortages,
                "recovered_at": event.timestamp,
            }
            return True

        self.pending_material_recoveries.pop(key, None)
        start_event = None
        if (
            task.assigned_machine == event.machine_id
            and task.status in {"pending", "scheduled"}
            and (
                machine.nextPendingOperation() is not None
                and machine.nextPendingOperation().job_id
                == event.job_id
                and machine.nextPendingOperation().operation_id
                == event.operation_id
            )
        ):
            start_event = self._queueOperationStartForTask(
                task,
                event.timestamp,
            )
        event.result = {
            "success": True,
            "machine_id": event.machine_id,
            "job_id": event.job_id,
            "operation_id": event.operation_id,
            "materials_available": not shortages,
            "replenished_materials": dict(added),
            "target_materials": dict(event.target_materials),
            "recovered_at": event.timestamp,
            "replenishment_lead_time": event.lead_time,
            "operation_start_event_id": (
                start_event.id if start_event is not None else None
            ),
        }
        return True

    def handleOperationStartEvent(self, event):
        if self.log_tag:
            print(f"Operation {event.job_id}-{event.operation_id} started on machine {event.machine_id} at time {event.timestamp}")
        job = self.jobs[event.job_id]
        task = job.tasks[event.operation_id]
        if job.is_canceled or task.status == "canceled":
            return False
        if (
            task.status == "processing"
            or task.actual_start is not None
            or task.actual_end is not None
        ):
            return False
        machine = self.machines[event.machine_id]
        if any(
            other.status == "processing"
            and other.actual_end is None
            and other.assigned_machine == event.machine_id
            for job_item in self.jobs
            for other in job_item.tasks
        ):
            return False
        if (
            machine.machine_status in {"failed", "repairing"}
            or (
                task.ready_not_before is not None
                and event.timestamp + 1e-9 < task.ready_not_before
            )
        ):
            return False
        if event.operation_id > 0:
            predecessor = job.tasks[event.operation_id - 1]
            if (
                predecessor.status != "completed"
                or predecessor.actual_end is None
                or event.timestamp + 1e-9 < predecessor.actual_end
            ):
                return False
            if not task.transport_completed:
                transport_end = (
                    task.transport_segments[-1]["transport_end"]
                    if task.transport_segments
                    else task.transport_end
                )
                if (
                    transport_end is not None
                    and transport_end > event.timestamp + 1e-9
                ):
                    return False
                task.transport_completed = True
                for segment in task.transport_segments:
                    if (
                        segment["transport_end"]
                        <= event.timestamp + 1e-9
                    ):
                        segment["completed"] = True
        elif not task.transport_completed:
            return False
        time1 = event.timestamp
        time2 = job.operation_times[event.operation_id][event.machine_id]
        if (
            machine.machine_status == "degraded"
            and machine.recovery_time is not None
            and time1 < machine.recovery_time
        ):
            time2 = math.floor(
                time2 * DEGRADED_PROCESSING_FACTOR
            )
        next_planned_operation = machine.nextPendingOperation()
        if (
            next_planned_operation is None
            or next_planned_operation.job_id != event.job_id
            or next_planned_operation.operation_id
            != event.operation_id
        ):
            return False
        requirements = self._operationMaterialRequirements(
            event.job_id,
            event.operation_id,
        )
        event.required_materials = dict(requirements)
        event.consumed_materials = {}
        if (
            requirements
            and not task.material_consumption_committed
        ):
            shortages = self._materialShortages(
                machine,
                requirements,
            )
            if shortages:
                replenishment_event, recovery_event = (
                    self._ensureMaterialRecoveryEvents(
                        task,
                        machine,
                        requirements,
                        event.timestamp,
                    )
                )
                event.material_shortages = shortages
                event.result = {
                    "success": False,
                    "reason": "insufficient_materials",
                    "machine_id": event.machine_id,
                    "job_id": event.job_id,
                    "operation_id": event.operation_id,
                    "shortage_materials": shortages,
                    "replenishment_event_id": (
                        replenishment_event.id
                        if replenishment_event is not None
                        else None
                    ),
                    "recovery_event_id": (
                        recovery_event.id
                        if recovery_event is not None
                        else None
                    ),
                }
                self.updateEventQueue()
                return True

            consumed = {}
            for material_id, required in requirements.items():
                current = float(
                    machine.materials.get(material_id, 0.0)
                )
                remaining = max(0.0, current - required)
                machine.materials[material_id] = remaining
                consumed[material_id] = required
            task.material_consumption_committed = True
            event.consumed_materials = consumed
        elif not requirements:
            task.material_consumption_committed = True

        event.result = {
            "success": True,
            "reason": "materials_ready",
            "machine_id": event.machine_id,
            "job_id": event.job_id,
            "operation_id": event.operation_id,
            "required_materials": dict(requirements),
            "consumed_materials": dict(event.consumed_materials),
        }
        finish_time = time1 + time2
        task.status = "processing"
        task.assigned_machine = event.machine_id
        task.actual_start = time1
        task.planned_start = time1
        task.planned_end = finish_time
        task.transport_completed = True
        task.current_location_machine = event.machine_id
        planned_operation = next(
            (
                operation
                for operation in self.planned_operations
                if (
                    operation.job_id == event.job_id
                    and operation.operation_id == event.operation_id
                )
            ),
            None,
        )
        if planned_operation is not None:
            planned_operation.start_time = time1
            planned_operation.end_time = finish_time
            planned_operation.status = "processing"
        self._alignSuccessorTransportToActualFinish(
            event.job_id,
            event.operation_id,
            finish_time,
        )
        for segment in task.transport_segments:
            segment["completed"] = True
        machine.popNextOperation()
        if self.scheduled_operations[event.machine_id]:
            self.scheduled_operations[event.machine_id].pop(0)
        operationFinishEvent = OperationFinishEvent(self.newEventId(), finish_time, event.job_id, event.operation_id, event.machine_id)
        self.addEvent(operationFinishEvent)
        self.machines[event.machine_id].addOperation(finish_time)
        self.schedule.addOperation(event.job_id, event.operation_id, event.machine_id, time1, finish_time)
        return True

    def handleOperationFinishEvent(self, event):
        if self.log_tag:
            print(f"Operation {event.job_id}-{event.operation_id} finished on machine {event.machine_id} at time {event.timestamp}")
        self.completed_operations.add(
            (event.job_id, event.operation_id)
        )
        task = self.jobs[event.job_id].tasks[event.operation_id]
        task.status = "completed"
        task.assigned_machine = event.machine_id
        task.actual_end = event.timestamp
        task.current_location_machine = event.machine_id
        planned_operation = next(
            (
                operation
                for operation in self.planned_operations
                if (
                    operation.job_id == event.job_id
                    and operation.operation_id == event.operation_id
                )
            ),
            None,
        )
        if planned_operation is not None:
            planned_operation.status = "completed"
        self._alignSuccessorTransportToActualFinish(
            event.job_id,
            event.operation_id,
            event.timestamp,
        )
        if event.operation_id + 1 < self.jobs[
            event.job_id
        ].operation_count:
            successor = self.jobs[event.job_id].tasks[
                event.operation_id + 1
            ]
            if (
                successor.status == "scheduled"
                and successor.transport_completed
                and successor.assigned_machine is not None
            ):
                self._startReadyOperationIfPossible(
                    successor.assigned_machine,
                    event.timestamp,
                )
        scheduled_count = len(self.scheduled_operations[event.machine_id])
        self.machines[event.machine_id].finishOperation(event.timestamp, scheduled_count)

        if not self._startReadyOperationIfPossible(
            event.machine_id,
            event.timestamp,
        ):
            next_planned_operation = self.machines[
                event.machine_id
            ].nextPendingOperation()
        else:
            next_planned_operation = None
        if next_planned_operation is not None:
            start_time = max(
                event.timestamp,
                next_planned_operation.start_time,
            )
            self.addEvent(
                OperationStartEvent(
                    self.newEventId(),
                    start_time,
                    next_planned_operation.job_id,
                    next_planned_operation.operation_id,
                    next_planned_operation.machine_id,
                )
            )
        elif (
            not self.jobs[event.job_id].is_canceled
            and
            event.operation_id < self.jobs[event.job_id].operation_count - 1
            and self.jobs[event.job_id].tasks[
                event.operation_id + 1
            ].status != "blocked"
            and not self.isOperationPlanned(
                event.job_id,
                event.operation_id + 1,
            )
        ):
            self.scheduleOperation(
                event.job_id,
                event.operation_id + 1,
                event.timestamp,
            )

        job = self.jobs[event.job_id]
        next_task = (
            job.tasks[event.operation_id + 1]
            if event.operation_id + 1 < job.operation_count
            else None
        )
        if (
            not job.is_canceled
            and next_task is not None
            and next_task.stage_id != task.stage_id
        ):
            self.addEvent(
                ProcessStageFinishEvent(
                    self.newEventId(),
                    event.timestamp,
                    event.job_id,
                    task.stage_id,
                    next_task.stage_id,
                )
            )
        if (
            not job.is_canceled
            and event.operation_id == job.operation_count - 1
        ):
            job.completion_time = event.timestamp
            jobFinishedEvent = JobFinishEvent(self.newEventId(), event.timestamp, event.job_id)
            self.addEvent(jobFinishedEvent)
        self.refreshRealtimeObjectives()

    def handleProcessStageFinishEvent(self, event):
        """Queue the next process for one shared batch scheduling window."""
        job = self.jobs[event.job_id]
        if job.is_canceled:
            return True
        current_stage_tasks = [
            task
            for task in job.tasks
            if task.stage_id == event.from_stage
        ]
        if any(
            task.status != "completed"
            for task in current_stage_tasks
        ):
            return False
        next_stage_tasks = [
            task
            for task in job.tasks
            if task.stage_id == event.to_stage
        ]
        first_task = next_stage_tasks[0]
        batch_event = next(
            (
                queued_event
                for queued_event in self.event_queue
                if (
                    isinstance(
                        queued_event,
                        ProcessStageBatchScheduleEvent,
                    )
                    and queued_event.stage_id == event.to_stage
                )
            ),
            None,
        )
        if batch_event is None:
            batch_event = ProcessStageBatchScheduleEvent(
                self.newEventId(),
                event.timestamp + self.process_stage_batch_window,
                event.to_stage,
                self.process_stage_batch_window,
            )
            self.addEvent(batch_event)
        batch_event.add_job(event.job_id, event.timestamp)
        self.updateEventQueue()
        event.result = {
            "job_id": event.job_id,
            "from_stage": event.from_stage,
            "to_stage": event.to_stage,
            "released_operation_id": first_task.operation_id,
            "batch_event_id": batch_event.id,
            "batch_scheduled_for": batch_event.timestamp,
            "batch_job_count": batch_event.job_count,
        }
        return True

    def handleProcessStageBatchScheduleEvent(self, event):
        """Schedule one complete target process for all Jobs in the batch."""
        job_ready_times = {
            job_id: ready_time
            for job_id, ready_time in event.job_ready_times.items()
            if (
                0 <= job_id < len(self.jobs)
                and not self.jobs[job_id].is_canceled
            )
        }
        planned_operations = self.scheduleProcessStageBatch(
            job_ready_times,
            event.stage_id,
            event.timestamp,
        )
        materialized_transport_events = []
        for operation in planned_operations:
            task = self.jobs[operation.job_id].tasks[
                operation.operation_id
            ]
            completed_segment = next(
                (
                    segment
                    for segment in reversed(task.transport_segments)
                    if segment["completed"]
                ),
                None,
            )
            if completed_segment is None:
                continue
            materialized_transport_events.append(
                TransportFinishEvent(
                    self.newEventId(),
                    completed_segment["transport_end"],
                    task.job_id,
                    task.operation_id,
                    operation.machine_id,
                    historical=True,
                    transport_start=completed_segment["transport_start"],
                    transport_end=completed_segment["transport_end"],
                )
            )
        event.materialized_events = materialized_transport_events
        event.result = {
            "stage_id": event.stage_id,
            "job_ids": list(job_ready_times),
            "job_count": len(job_ready_times),
            "planned_operation_count": len(planned_operations),
            "materialized_transport_event_count": len(
                materialized_transport_events
            ),
            "batch_window": event.batch_window,
            "scheduled_at": event.timestamp,
        }
        return True

    def _alignSuccessorTransportToActualFinish(
        self,
        job_id,
        operation_id,
        finish_time,
    ):
        """Move a not-started successor transport to actual completion time."""
        job = self.jobs[job_id]
        successor_id = operation_id + 1
        if successor_id >= job.operation_count:
            return
        successor = job.tasks[successor_id]
        if (
            successor.status not in {"pending", "scheduled"}
            or successor.actual_start is not None
            or successor.transport_completed
        ):
            return
        if (
            successor.transport_start is not None
            and successor.transport_start <= self.curr_time + 1e-9
            and successor.transport_end is not None
            and successor.transport_end > self.curr_time + 1e-9
        ):
            # An already started transport must finish before it can be
            # rerouted. Only future transport legs may be moved here.
            return

        source_machine = job.tasks[operation_id].assigned_machine
        target_machine = successor.assigned_machine
        if source_machine is None or target_machine is None:
            return

        segments = [
            dict(segment)
            for segment in successor.transport_segments
        ]
        if (
            not segments
            or segments[0]["source_machine"] != source_machine
            or segments[-1]["target_machine"] != target_machine
        ):
            segments = []
            if source_machine != target_machine:
                segments = [{
                    "source_machine": source_machine,
                    "target_machine": target_machine,
                    "transport_start": finish_time,
                    "transport_end": (
                        finish_time
                        + self._jobTransportTime(
                            job_id,
                            source_machine,
                            target_machine,
                        )
                    ),
                    "transport_time": self._jobTransportTime(
                        job_id,
                        source_machine,
                        target_machine,
                    ),
                    "transport_energy": self._jobTransportEnergy(
                        job_id,
                        source_machine,
                        target_machine,
                    ),
                    "completed": False,
                }]
        else:
            cursor = finish_time
            for segment in segments:
                source = segment["source_machine"]
                target = segment["target_machine"]
                transport_time = self._jobTransportTime(
                    job_id,
                    source,
                    target,
                )
                segment["transport_start"] = cursor
                segment["transport_end"] = cursor + transport_time
                segment["transport_time"] = transport_time
                segment["transport_energy"] = (
                    self._jobTransportEnergy(
                        job_id,
                        source,
                        target,
                    )
                )
                segment["completed"] = False
                cursor = segment["transport_end"]

        successor.transport_segments = segments
        if segments:
            first_segment = segments[0]
            last_segment = segments[-1]
            successor.source_machine = first_segment[
                "source_machine"
            ]
            successor.transport_start = first_segment[
                "transport_start"
            ]
            successor.transport_end = first_segment["transport_end"]
            successor.transport_time = first_segment["transport_time"]
            successor.transport_energy = first_segment[
                "transport_energy"
            ]
            successor.transport_completed = False
            successor.current_location_machine = source_machine
            arrival_time = last_segment["transport_end"]
        else:
            successor.source_machine = source_machine
            successor.transport_start = None
            successor.transport_end = None
            successor.transport_time = 0
            successor.transport_energy = 0
            successor.transport_completed = True
            successor.current_location_machine = target_machine
            arrival_time = finish_time
        successor.waiting_time = max(
            0,
            successor.planned_start - arrival_time,
        )

        planned = next(
            (
                operation
                for operation in self.planned_operations
                if (
                    operation.job_id == job_id
                    and operation.operation_id == successor_id
                )
            ),
            None,
        )
        if planned is not None:
            planned.source_machine = successor.source_machine
            planned.transport_start = successor.transport_start
            planned.transport_end = successor.transport_end
            planned.transport_time = successor.transport_time
            planned.transport_energy = successor.transport_energy
            planned.transport_segments = [
                dict(segment) for segment in segments
            ]
            planned.waiting_time = successor.waiting_time

        self.event_queue = [
            queued_event
            for queued_event in self.event_queue
            if not (
                isinstance(queued_event, TransportFinishEvent)
                and queued_event.job_id == job_id
                and queued_event.operation_id == successor_id
            )
        ]
        for segment in segments:
            if segment["transport_time"] <= 0:
                continue
            self.addEvent(
                TransportFinishEvent(
                    self.newEventId(),
                    segment["transport_end"],
                    job_id,
                    successor_id,
                    segment["target_machine"],
                )
            )

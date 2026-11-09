from system.job import Job
from system.machine import Machine
from system.schedule import PlannedOperation, Schedule
from system.order import Order
from simulator.event import *
from simulator.clock import SimulationClock
from simulator.config import DEFAULT_CONFIG_PATH, load_simulator_config
from simulator.dataset import load_multi_objective_dataset
from simulator.job_generator import generate_random_job
import random
import time
import math
import heapq
import threading
from pathlib import Path

EVENT_QUEUE_PRIORITIES = {
    ScheduleEvent: 0,
    JobSubmitEvent: 1,
    JobStartEvent: 2,
    TransportFinishEvent: 3,
    OperationStartEvent: 4,
    OperationFinishEvent: 5,
    JobFinishEvent: 6,
}


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
        self.pending_event_timestamp = None
        self.curr_event_id = -1
        self.curr_time = 0

        self.jobs = []
        self.initial_job_count = 0
        self.machines = []

        self.job_queue = []
        self.processing_queue = []
        self.finished_queue = []
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
        if not self.realtime:
            self.clock.wait_until(simulation_timestamp)
            return True

        while self.clock.current_simulation_time < simulation_timestamp:
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

    def init(self, file_path=None, additional_file_path=None):
        """读取多目标优化数据，初始化工件、任务和机器。"""
        raw_path = Path(file_path or self.input_file)
        if additional_file_path is not None:
            additional_path = Path(additional_file_path)
        elif file_path is not None and raw_path.parent.name == "raw":
            additional_path = raw_path.parent.parent / "add" / raw_path.name
        else:
            additional_path = Path(self.additional_file)

        dataset = load_multi_objective_dataset(raw_path, additional_path)
        self.dataset = dataset
        self.jobs = list(dataset.jobs)
        self.initial_job_count = len(self.jobs)
        machine_count = dataset.num_machines
        self.transport_time = dataset.transport_time
        self.transport_energy = dataset.transport_energy

        self.machines = []
        for machine_id in range(machine_count):
            self.machines.append(
                Machine(
                    machine_id,
                    "idle",
                    0,
                    dataset.transport_time[machine_id],
                    dataset.transport_energy[machine_id],
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

        # 初始化时为所有 Job 创建 Order，等待初始 ScheduleEvent 调度
        self.job_queue = [
            Order(job.job_id, job.priority, job.ready_time)
            for job in self.jobs
        ]
        self.processing_queue = []
        self.finished_queue = []

        # 初始 ScheduleEvent 从 job_queue 获取作业，生成完整机器队列
        self.handleScheduleEvent(ScheduleEvent(self.newEventId(), 0))


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
            while len(self.event_queue) > 0:
                with self.event_lock:
                    self._discardStaleTransportEvents()
                    if not self.event_queue:
                        break
                    target_timestamp = self.event_queue[0].timestamp
                    self.pending_event_timestamp = target_timestamp

                if not self._wait_until(target_timestamp):
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
        finally:
            self.pending_event_timestamp = None
            self.clock.stop()

        if self.log_tag:
            print(f"\nSimulation finished at time {self.makespan}.")
        elapsed_real_time = time.monotonic() - start_time
        if self.log_tag:
            print(f"Total simulation time: {elapsed_real_time:.2f} seconds.")
        self.calculateObjectives()
        self.schedule.printItems(self.schedule_file, self.gantt_file, self.machines)
        self.schedule.testSchedule()

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

    def scheduleTransportFinishEvents(
        self,
        planned_operations,
        after_time=0,
    ):
        for operation in planned_operations:
            if (
                operation.transport_time <= 0
                or operation.transport_end is None
                or operation.transport_end < after_time
            ):
                continue
            task = self.jobs[operation.job_id].tasks[
                operation.operation_id
            ]
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

        return (
            task.status in {"pending", "scheduled"}
            and task.actual_start is None
            and not task.transport_completed
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

    def replanRemainingOperations(self):
        """取消未完成工序事件，并从当前时刻重建全部剩余机器队列。"""
        operation_event_types = (
            JobSubmitEvent,
            JobStartEvent,
            JobFinishEvent,
            TransportFinishEvent,
            OperationStartEvent,
            OperationFinishEvent,
        )
        self.event_queue = [
            event
            for event in self.event_queue
            if not isinstance(event, operation_event_types)
        ]

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
                    task.current_location_machine = None
                    task.waiting_time = 0

        for job in self.jobs:
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
            if next_operation_id < job.operation_count:
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
                task.processing_energy
                for task in job.tasks
                if task.actual_end is not None
                and task.assigned_machine is not None
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
            all_completed = len(completed_times) == job.operation_count
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

    def reoptimizeUnfinishedOperations(
        self,
        machine_assignments,
        current_time=None,
    ):
        """
        使用外部模型给出的机器分配重建未加工工序队列。

        已完成和正在加工的任务保持原机器与时间；未开始任务使用新机器分配，
        并根据工件的实际所在机器重新计算机器可用时间、运输时间和运输能耗。
        已到达新目标机器的运输不会重复生成。
        """
        now = self.curr_time if current_time is None else float(current_time)
        assignments = {
            tuple(key): int(machine_id)
            for key, machine_id in machine_assignments.items()
        }
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
            if task.status == "processing" and task.actual_end is None
        ]
        effective_ends = {
            (job.job_id, task.operation_id): self._taskEffectiveEnd(task)
            for job in self.jobs
            for task in job.tasks
        }

        unfinished_tasks = [
            (job.job_id, task)
            for job in self.jobs
            for task in job.tasks
            if task.status in {"pending", "scheduled"}
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
            machine.clearPendingOperations()
            machine.ready_time = now
            machine.machine_status = "idle"
            self.scheduled_operations[machine_id] = []

        for task in processing_tasks:
            expected_end = effective_ends[(task.job_id, task.operation_id)]
            machine = self.machines[task.assigned_machine]
            machine.ready_time = max(
                machine.ready_time,
                expected_end,
            )
            machine.machine_status = "busy"

        obsolete_event_types = (
            OperationStartEvent,
            OperationFinishEvent,
            JobFinishEvent,
            TransportFinishEvent,
        )
        kept_events = []
        for event in self.event_queue:
            if isinstance(event, obsolete_event_types):
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
            task.current_location_machine = previous_transport[
                "current_location_machine"
            ]
            task.waiting_time = 0

        operation_queue = []
        for job in self.jobs:
            next_operation_id = 0
            while (
                next_operation_id < job.operation_count
                and job.tasks[next_operation_id].status == "completed"
            ):
                next_operation_id += 1
            while (
                next_operation_id < job.operation_count
                and job.tasks[next_operation_id].status == "processing"
            ):
                next_operation_id += 1
            if next_operation_id >= job.operation_count:
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

        self.planned_operations = [
            self._plannedOperationFromTask(task)
            for job in self.jobs
            for task in job.tasks
            if task.status in {"completed", "processing"}
        ]
        moved_operations = []
        transport_time_added = 0
        transport_energy_added = 0

        finished_job_ids = {
            order.job_id for order in self.finished_queue
        }
        for job in self.jobs:
            if (
                all(task.status == "completed" for task in job.tasks)
                and job.job_id not in finished_job_ids
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
            transport_reused = False

            if operation_id == 0:
                source_machine = None
                inbound_transport = 0
                inbound_energy = 0
                release_time = max(release_time, now, job.ready_time)
                current_location = machine_id
                transport_completed = True
            elif (
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
                transport_reused = True
                transport_completed = True
            else:
                if previous_transport["transport_completed"]:
                    source_machine = previous_transport[
                        "current_location_machine"
                    ]
                    task.committed_transport_energy += previous_transport[
                        "transport_energy"
                    ]
                    transport_available_time = max(now, release_time)
                else:
                    source_machine = job.tasks[
                        operation_id - 1
                    ].assigned_machine
                    transport_available_time = max(
                        now,
                        release_time,
                    )

                if (
                    source_machine is None
                    or source_machine == machine_id
                ):
                    inbound_transport = 0
                    inbound_energy = 0
                    release_time = transport_available_time
                    current_location = machine_id
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
                transport_completed = self._inboundTransportCompleted(
                    job_id,
                    operation_id,
                    inbound_transport,
                )

            start_time = max(release_time, machine.ready_time)
            end_time = start_time + task.processing_times[machine_id]
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
            task.source_machine = source_machine
            task.transport_time = inbound_transport
            task.transport_energy = inbound_energy
            task.transport_start = transport_start
            task.transport_end = transport_end
            task.transport_completed = transport_completed
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
            if not transport_reused:
                transport_time_added += inbound_transport
                transport_energy_added += inbound_energy

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
                        "transport_time": inbound_transport,
                        "transport_energy": inbound_energy,
                        "transport_start": task.transport_start,
                        "transport_end": task.transport_end,
                        "start_time": start_time,
                        "waiting_time": task.waiting_time,
                    }
                )

            if operation_id + 1 < job.operation_count:
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
            self.planned_operations,
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
        }

    def submitRandomJobsAndReoptimize(self, current_time=None, seed=0):
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

        assignments = {
            (existing_job.job_id, task.operation_id): min(
                task.eligible_machines,
                key=lambda machine_id: (
                    task.processing_times[machine_id],
                    machine_id,
                ),
            )
            for existing_job in self.jobs
            for task in existing_job.tasks
            if task.status in {"pending", "scheduled"}
        }
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
            return (
                task.actual_start
                + task.processing_times[task.assigned_machine]
            )
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
            waiting_time=task.waiting_time,
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
        elif isinstance(event, JobSubmitEvent):
            self.handleJobSubmitEvent(event)
        elif isinstance(event, JobStartEvent):
            self.handleJobStartEvent(event)
        elif isinstance(event, JobFinishEvent):
            self.handleJobFinishEvent(event)
        elif isinstance(event, TransportFinishEvent):
            self.handleTransportFinishEvent(event)
        elif isinstance(event, OperationStartEvent):
            self.handleOperationStartEvent(event)
        elif isinstance(event, OperationFinishEvent):
            self.handleOperationFinishEvent(event)
        else:
            print(f"Error: Unknown event type {type(event)} with ID {event.id}.")

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

        for job in self.jobs:
            if job.job_id not in queued_job_ids:
                continue
            job.completion_time = None
            job.earliness = 0
            job.tardiness = 0
            job.processing_energy = 0
            job.transport_energy = 0
            for task in job.tasks:
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
                task.current_location_machine = None
                task.waiting_time = 0

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
            if next_operation_id < job.operation_count:
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
            return
        task = self.jobs[event.job_id].tasks[event.operation_id]
        task.transport_completed = True
        task.current_location_machine = event.machine_id
        self.refreshRealtimeObjectives()
    
    def scheduleOperation(self, job_id, operation_id, timestamp):
        if self.log_tag:
            print(f"Operation {job_id}-{operation_id} scheduled at time {timestamp}")
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

    def assignTaskPlan(self, task, planned_operation):
        """Copy machine, transport and timing details to task and plan."""
        if task.transport_start is not None:
            arrival_time = task.transport_end
        else:
            arrival_time = self.jobs[task.job_id].ready_time

        task.waiting_time = max(0, task.planned_start - arrival_time)
        planned_operation.source_machine = task.source_machine
        planned_operation.transport_start = task.transport_start
        planned_operation.transport_end = task.transport_end
        planned_operation.transport_time = task.transport_time
        planned_operation.transport_energy = task.transport_energy
        planned_operation.waiting_time = task.waiting_time

    def placeOperation(self, job_id, operation_id):
        job = self.jobs[job_id]
        minMachineId = -1
        minTime = float('inf')  # 初始化为无穷大
        for machine_id in range(len(self.machines)):
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
    
    def handleOperationStartEvent(self, event):
        if self.log_tag:
            print(f"Operation {event.job_id}-{event.operation_id} started on machine {event.machine_id} at time {event.timestamp}")
        time1 = event.timestamp
        time2 = self.jobs[event.job_id].operation_times[event.operation_id][event.machine_id]
        finish_time = time1 + time2
        task = self.jobs[event.job_id].tasks[event.operation_id]
        task.status = "processing"
        task.assigned_machine = event.machine_id
        task.actual_start = time1
        task.transport_completed = True
        task.current_location_machine = event.machine_id
        next_planned_operation = self.machines[
            event.machine_id
        ].nextPendingOperation()
        operation_matches = (
            next_planned_operation is not None
            and next_planned_operation.job_id == event.job_id
            and next_planned_operation.operation_id == event.operation_id
        )
        if operation_matches:
            self.machines[event.machine_id].popNextOperation()
            if self.scheduled_operations[event.machine_id]:
                self.scheduled_operations[event.machine_id].pop(0)
        else:
            if self.log_tag:
                print(f"Error: Scheduled operation mismatch for job {event.job_id} operation {event.operation_id} on machine {event.machine_id}.")
            # print(f"Scheduled operations: {self.scheduled_operations[event.machine_id]}")
        operationFinishEvent = OperationFinishEvent(self.newEventId(), finish_time, event.job_id, event.operation_id, event.machine_id)
        self.addEvent(operationFinishEvent)
        self.machines[event.machine_id].addOperation(finish_time)
        self.schedule.addOperation(event.job_id, event.operation_id, event.machine_id, time1, finish_time)

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
        scheduled_count = len(self.scheduled_operations[event.machine_id])
        self.machines[event.machine_id].finishOperation(event.timestamp, scheduled_count)

        next_planned_operation = self.machines[
            event.machine_id
        ].nextPendingOperation()
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
            event.operation_id < self.jobs[event.job_id].operation_count - 1
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

        if event.operation_id == self.jobs[event.job_id].operation_count - 1:
            self.jobs[event.job_id].completion_time = event.timestamp
            jobFinishedEvent = JobFinishEvent(self.newEventId(), event.timestamp, event.job_id)
            self.addEvent(jobFinishedEvent)
        self.refreshRealtimeObjectives()

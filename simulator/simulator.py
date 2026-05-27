from system.job import Job
from system.machine import Machine
from system.schedule import Schedule
from system.order import Order
from simulator.event import *
from model_predict.online_inference import *
import random
import time
import math

class Simulator:
    def __init__(self):
        self.event_queue = []
        self.curr_event_id = -1
        self.curr_time = 0

        self.jobs = []
        self.machines = []

        self.job_queue = []
        self.processing_queue = []
        self.finished_queue = []
        self.scheduled_operations = []

        self.schedule = None
        self.makespan = 0

        self.log_tag = True
        self.schedule_file = "result_schedule.csv"
        self.gantt_file = "gantt_chart.txt"
        # 预测阈值
        self.predict_threshold = 0.93

        self.default_repair_time = 30  # 默认维修时间
        self.default_time_horizon = 5000  # 默认时间范围

        self.model = None  # 预测模型

        # 引入多目标优化相关参数
        self.seed = 42  # 随机种子
        self.due_time_factor = 1.2  # 计算due time的系数, 1.2  1.5  2
        self.auxiliary_energy = 1   # 辅助能耗系数，计算与完工时间相关的辅助能耗，比如照明、空调等设备的能耗

    def init(self, file_path):
        """从文件路径中读取信息，初始化模拟器"""
        if not file_path:
            print("Error: Input file path is empty.")
            return
        
        try:
            with open(file_path, 'r') as input_file:
                lines = input_file.readlines()
        except FileNotFoundError:
            print(f"Error: Cannot open input file: {file_path}")
            return
        
        # 读取第一行：作业数量、机器数量、最大工序数量
        if not lines:
            print("Error: Input file is empty.")
            return
            
        line = lines[0].strip()
        parts = line.split()
        job_count = int(parts[0])
        machine_count = int(parts[1])
        max_operation_count = int(parts[2])
        
        # 读取每个作业的信息
        line_index = 1
        for i in range(job_count):
            if line_index >= len(lines):
                break
                
            line = lines[line_index].strip()
            parts = line.split()
            operation_count = int(parts[0])
            
            # 初始化操作时间矩阵
            operation_times = [[float('inf')] * machine_count for _ in range(operation_count)]
            operation_energy = [[float('inf')] * machine_count for _ in range(operation_count)]
            random.seed(self.seed)

            part_index = 1
            for j in range(operation_count):
                if part_index >= len(parts):
                    break
                count = int(parts[part_index])
                part_index += 1
                
                for k in range(count):
                    if part_index + 1 >= len(parts):
                        break
                    machine_id = int(parts[part_index])
                    operation_time = int(parts[part_index + 1])
                    operation_times[j][machine_id] = operation_time
                    operation_energy[j][machine_id] = random.randint(4, 15)
                    part_index += 2

            earliness_cost = random.randint(1, 10)
            tardiness_cost = random.randint(1, 10)
            ready_time = random.randint(0, 20)
            # due_time = ready_time + c * (sum (average processing time per operation))
            avg_proct = []
            for j in range(operation_count):
                avg_proct.append(sum([t for t in operation_times[j] if t != float('inf')]) / len([t for t in operation_times[j] if t != float('inf')]))
            due_time = int(ready_time +  int(self.due_time_factor * sum(avg_proct)))
            weight = random.randint(1, 20)
            # 创建作业对象并添加到作业列表
            job = Job(i, operation_count, operation_times, operation_energy, ready_time, due_time, earliness_cost, tardiness_cost, weight)
            self.jobs.append(job)
            # 提交作业
            self.submitJob(i, 0, ready_time)
            line_index += 1
        
        # 初始化机器
        transport_time = [[0 for _ in range(machine_count)] for _ in range(machine_count)]
        transport_energy = [[0 for _ in range(machine_count)] for _ in range(machine_count)]
        for i in range(machine_count):
            for j in range(machine_count):
                if i < j:
                    temp_time = random.randint(1, 3)
                    temp_energy = random.randint(1,4) * temp_time
                    transport_time[i][j] = temp_time
                    transport_time[j][i] = temp_time
                    transport_energy[i][j] = temp_energy
                    transport_energy[j][i] = temp_energy

        for i in range(machine_count):
            machine = Machine(i, "idle", 0, transport_time[i], transport_energy[i])
            self.machines.append(machine)
        
        # 初始化调度相关的数据结构
        items = [[] for _ in range(machine_count)]
        start = [[] for _ in range(machine_count)]
        end = [[] for _ in range(machine_count)]
        
        # 初始化每台机器的调度工序列表
        self.scheduled_operations = [[] for _ in range(machine_count)]
        
        # 初始化调度对象
        self.schedule = Schedule(0, machine_count, items, start, end)
        self.model = load_model()


    def generateFailure(self, mtbf, mttr, time_horizon, seed=None):
        """Generate random machine failures using MTBF/MTTR."""

        machine_count = len(self.machines)
        rng = random.Random(seed)
        failures = {machine_id: [] for machine_id in range(machine_count)}

        for machine_id in range(machine_count):
            current_time = 0
            while current_time < time_horizon:
                time_to_failure = rng.expovariate(1.0 / mtbf)
                failure_time = current_time + time_to_failure
                failure_time_int = int(math.ceil(failure_time))  # 将故障时间向上取整为整数
                if failure_time_int >= time_horizon:
                    break
                repair_time = rng.expovariate(1.0 / mttr)
                repair_time_int = max(20, int(math.ceil(repair_time)))  # 将维修时间向上取整为整数，且至少为20
                failures[machine_id].append((failure_time_int, repair_time_int))
                current_time = failure_time_int + repair_time_int
        return failures

    def addFailure(self, type, failures):  
        if type == "predict":
            for machine_id, failure_list in failures.items():
                for failure_time, repair_time in failure_list:
                    self.event_queue.append(MachineFailureEvent(self.newEventId(), failure_time, machine_id, repair_time))
                    self.event_queue.append(FailurePredictEvent(self.newEventId(), max(0, failure_time - 10), machine_id, failure_time, repair_time))
        elif type == "failure":
            for machine_id, failure_list in failures.items():
                for failure_time, repair_time in failure_list:
                    self.event_queue.append(MachineFailureEvent(self.newEventId(), failure_time, machine_id, repair_time))
        elif type == "detect":
            for machine_id, failure_list in failures.items():
                for failure_time, repair_time in failure_list:
                    self.event_queue.append(FailureDetectEvent(self.newEventId(), failure_time+10, machine_id, failure_time, repair_time))
        pass

    def addPredictEvent(self):
        for i in range(0, 800, 10):
            for j in range(len(self.machines)):
                self.event_queue.append(FailurePredictEvent(self.newEventId(), i, j))

    def addDetectEvent(self):
        for i in range(10, 800, 1):
            for j in range(len(self.machines)):
                self.event_queue.append(FailureDetectEvent(self.newEventId(), i, j))

    def run(self):
        # self.event_queue.append(FailurePredictEvent(self.newEventId(), 10, 4, 30, 60))  # 表示在时间10机器4预测将在时间30发生故障，维修时间60
        # self.event_queue.append(MachineFailureEvent(self.newEventId(), 30, 4, 60))   # 表示在时间20机器1发生故障，维修时间40
        # self.event_queue.append(OrderAddEvent(self.newEventId(), 5, 2, 1))         # 表示在时间5添加作业2，优先级1
        # self.event_queue.append(OperationTimeUpdateEvent(self.newEventId(), 10, 2, 0, 1, 10))   # 表示在时间10更新作业2的工序0在机器1上的加工时间为10
        
        start_time = time.time()
        while len(self.event_queue) > 0:
            event = self.event_queue[0]
            self.event_queue.pop(0)
            if event.timestamp < self.curr_time:
                self.printEvent(event)
                print(f"Warning: Event {event.id} has a timestamp earlier than the current time ({event.timestamp} < {self.curr_time}). Skipping.")
                break
            self.curr_time = event.timestamp
            self.handleEvent(event)
            self.updateEventQueue()
        if self.log_tag:
            print(f"\nSimulation finished at time {self.makespan}.")
        end_time = time.time()
        print(f"Total simulation time: {end_time - start_time:.2f} seconds.")
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
        elif isinstance(event, OperationScheduleEvent):
            print(f"Operation Scheduled: Job ID {event.job_id}, Operation ID {event.operation_id}")
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
        elif isinstance(event, MachineFailureEvent):
            print(f"Machine Failure: Machine ID {event.machine_id}, Repair Time {event.repair_time}")
        elif isinstance(event, MachineRepairEvent):
            print(f"Machine Repair: Machine ID {event.machine_id}")
        elif isinstance(event, FailurePredictEvent):
            print(f"Failure Prediction: Machine ID {event.machine_id}, Predicted Failure Time {event.predicted_failure_time}, Failure Rate {event.failure_rate}")
        elif isinstance(event, FailureDetectEvent):
            print(f"Failure Detection: Machine ID {event.machine_id}, Failure Time {event.failure_time}")
        elif isinstance(event, MachineRestoreEvent):
            print(f"Machine Restore: Machine ID {event.machine_id}")
        print()  

    def addEvent(self, event):
        self.event_queue.append(event)

    def updateEventQueue(self):
        self.event_queue.sort(key=lambda e: (e.timestamp, e.getEventType().value))

    def newEventId(self):
        self.curr_event_id += 1
        return self.curr_event_id
    
    def submitJob(self, job_id, priority, timestamp):
        """提交一个新的作业"""
        event = JobSubmitEvent(self.newEventId(), timestamp, job_id, priority)
        self.addEvent(event)

    def handleEvent(self, event):
        """处理事件"""
        if isinstance(event, JobSubmitEvent):
            self.handleJobSubmitEvent(event)
        elif isinstance(event, JobStartEvent):
            self.handleJobStartEvent(event)
        elif isinstance(event, JobFinishEvent):
            self.handleJobFinishEvent(event)
        elif isinstance(event, OperationScheduleEvent):
            self.handleOperationScheduleEvent(event)
        elif isinstance(event, OperationStartEvent):
            self.handleOperationStartEvent(event)
        elif isinstance(event, OperationFinishEvent):
            self.handleOperationFinishEvent(event)
        # elif isinstance(event, OrderAddEvent):
        #     self.handleOrderAddEvent(event)
        # elif isinstance(event, OrderDeleteEvent):
        #     self.handleOrderDeleteEvent(event)
        # elif isinstance(event, OrderUpdateEvent):
        #     self.handleOrderUpdateEvent(event)
        # elif isinstance(event, OperationTimeUpdateEvent):
        #     self.handleOperationTimeUpdateEvent(event)
        elif isinstance(event, MachineFailureEvent):
            self.handleMachineFailureEvent(event)
        elif isinstance(event, MachineRepairEvent):
            self.handleMachineRepairEvent(event)
        elif isinstance(event, FailurePredictEvent):
            self.handleFailurePredictEvent(event)
        elif isinstance(event, FailureDetectEvent):
            self.handleFailureDetectEvent(event)
        elif isinstance(event, MachineRestoreEvent):
            self.handleMachineRestoreEvent(event)
        else:
            print(f"Error: Unknown event type {type(event)} with ID {event.id}.")

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
        operationScheduleEvent = OperationScheduleEvent(self.newEventId(), event.timestamp, event.job_id, 0)
        self.addEvent(operationScheduleEvent)

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
    
    def handleOperationScheduleEvent(self, event):
        if self.log_tag:
            print(f"Operation {event.job_id}-{event.operation_id} scheduled at time {event.timestamp}")
        machine_id = self.placeOperation(event.job_id, event.operation_id)
        # print(f"----machine {machine_id}: {self.machines[machine_id].machine_status}")
        # print(f"----scheduled_operations: {self.scheduled_operations[machine_id]}")
        if machine_id == -1:
            operationScheduleEvent = OperationScheduleEvent(self.newEventId(), event.timestamp + 20, event.job_id, event.operation_id)
            self.addEvent(operationScheduleEvent)
            return
        if self.machines[machine_id].machine_status == 'idle':  # 如果机器空闲，直接开始操作
            start_time = event.timestamp
        else:
            start_time = max(event.timestamp, self.machines[machine_id].ready_time)
        # print(f"----start_time: {start_time}")
        self.machines[machine_id].scheduleOperation(start_time + self.jobs[event.job_id].operation_times[event.operation_id][machine_id])
        self.scheduled_operations[machine_id].append([event.job_id, event.operation_id])
        operationStartEvent = OperationStartEvent(self.newEventId(), start_time, event.job_id, event.operation_id, machine_id)
        self.addEvent(operationStartEvent)
        # print(f"schedule operation {event.job_id}-{event.operation_id} on machine {machine_id} at time {start_time}")

    def placeOperation(self, job_id, operation_id):
        job = self.jobs[job_id]
        minMachineId = -1
        minTime = float('inf')  # 初始化为无穷大
        for machine_id in range(len(self.machines)):
            if job.operation_times[operation_id][machine_id] < minTime and \
                self.machines[machine_id].machine_status != "failed" and \
                self.machines[machine_id].machine_status != "pre-failed" and \
                self.machines[machine_id].machine_status != "repairing":
                minTime = job.operation_times[operation_id][machine_id]
                minMachineId = machine_id
        return minMachineId
    
    def handleOperationStartEvent(self, event):
        if self.log_tag:
            print(f"Operation {event.job_id}-{event.operation_id} started on machine {event.machine_id} at time {event.timestamp}")
        time1 = event.timestamp
        time2 = self.jobs[event.job_id].operation_times[event.operation_id][event.machine_id]
        finish_time = time1 + time2
        if self.scheduled_operations[event.machine_id][0][0] == event.job_id and \
           self.scheduled_operations[event.machine_id][0][1] == event.operation_id:
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
        scheduled_count = len(self.scheduled_operations[event.machine_id])
        self.machines[event.machine_id].finishOperation(event.timestamp, scheduled_count)
        if event.operation_id < self.jobs[event.job_id].operation_count - 1:
            next_operation_event = OperationScheduleEvent(self.newEventId(), event.timestamp, event.job_id, event.operation_id + 1)
            self.addEvent(next_operation_event)
        else:
            jobFinishedEvent = JobFinishEvent(self.newEventId(), event.timestamp, event.job_id)
            self.addEvent(jobFinishedEvent)

    def handleOrderAddEvent(self, event):
        if self.log_tag:
            print(f"Order {event.job_id} added with priority {event.priority} at time {event.timestamp}")
        self.submitJob(event.job_id, event.priority, event.timestamp)

    def handleOrderDeleteEvent(self, event):
        if self.log_tag:
            print(f"Order {event.job_id} deleted at time {event.timestamp}")
        for order in self.job_queue:
            if order.job_id == event.job_id:
                self.job_queue.remove(order)
                return
        for order in self.processing_queue:
            if order.job_id == event.job_id:
                self.processing_queue.remove(order)
                # TODO: Handle any necessary cleanup for the processing queue

                return
        for order in self.finished_queue:
            if order.job_id == event.job_id:
                self.finished_queue.remove(order)
                break

    def handleOrderUpdateEvent(self, event):
        if self.log_tag:
            print(f"Order {event.job_id} updated to new priority {event.new_priority} at time {event.timestamp}")
        for order in self.job_queue:
            if order.job_id == event.job_id:
                order.priority = event.new_priority
                return
        for order in self.processing_queue:
            if order.job_id == event.job_id:
                order.priority = event.new_priority
                return
        for order in self.finished_queue:
            if order.job_id == event.job_id:
                order.priority = event.new_priority
                break

    def handleOperationTimeUpdateEvent(self, event):
        if self.log_tag:
            print(f"Operation {event.job_id}-{event.operation_id} on machine {event.machine_id} updated to {event.new_time} at time {event.timestamp}")
        self.jobs[event.job_id].operation_times[event.operation_id][event.machine_id] = event.new_time
        # Update the schedule if necessary
        if self.schedule.schedule_items[event.machine_id][-1][0] == event.job_id and \
            self.schedule.schedule_items[event.machine_id][-1][1] == event.operation_id  and \
            self.schedule.start_time[event.machine_id][-1] <= event.timestamp and \
            self.schedule.end_time[event.machine_id][-1] > event.timestamp:
            self.reschedule(event.machine_id)
            self.machines[event.machine_id].machine_status = "idle"
            self.scheduled_operations[event.machine_id] = []
            self.machines[event.machine_id].ready_time = event.timestamp
            self.schedule.schedule_items[event.machine_id].pop()
            self.schedule.start_time[event.machine_id].pop()
            self.schedule.end_time[event.machine_id].pop()
            pass
    
    def handleMachineFailureEvent(self, event):
        if self.log_tag:
            print(f"Machine {event.machine_id} failure at time {event.timestamp}")
        self.rescheduleFailure(event.machine_id)
        self.machines[event.machine_id].machine_status = "failed"
        self.scheduled_operations[event.machine_id] = []
        self.machines[event.machine_id].ready_time = event.timestamp + event.repair_time
        machineRepairEvent = MachineRepairEvent(self.newEventId(), event.timestamp + event.repair_time, event.machine_id)
        self.addEvent(machineRepairEvent)
        pass

    def handleMachineRepairEvent(self, event):
        if self.log_tag:
            print(f"Machine {event.machine_id} repaired at time {event.timestamp}")
        self.machines[event.machine_id].machine_status = "idle"
        self.machines[event.machine_id].ready_time = event.timestamp
        self.scheduled_operations[event.machine_id] = []
        pass

    def handleFailurePredictEvent(self, event):
        if self.log_tag:
            print(f"Machine {event.machine_id} predicted failure at time {event.timestamp}")
        if self.machines[event.machine_id].machine_status == "failed" or \
            self.machines[event.machine_id].machine_status == "repairing":
            return 
        if self.curr_time > 3500 or \
            (len(self.job_queue) == 0 and len(self.processing_queue) == 0):
            return
        win = get_history_window(self.machines[event.machine_id].df, event.timestamp)
        p = predict(self.model, win) 
        if p >= self.predict_threshold:
            print(f"Machine {event.machine_id} predicted failure at time {event.timestamp} with probability {p:.4f}")
            self.reschedulePredict(event.machine_id, event.timestamp)
            self.machines[event.machine_id].machine_status = "pre-failed"
            machineRepairEvent = MachineRestoreEvent(self.newEventId(), event.timestamp + 20, event.machine_id)
            self.addEvent(machineRepairEvent)
        # l = get_label(self.machines[event.machine_id].df, event.timestamp, 0)
        # if l == 1:
        #     machineFailureEvent = MachineFailureEvent(self.newEventId(), event.timestamp, event.machine_id, self.default_repair_time)
        #     self.addEvent(machineFailureEvent)
        pass

    def handleFailureDetectEvent(self, event):
        if self.log_tag:
            print(f"Machine {event.machine_id} detected failure at time {event.timestamp}")
        # self.rescheduleDetect1(event.machine_id, event.failure_time, event.failure_time + event.repair_time)
        if self.curr_time > 3500 or self.machines[event.machine_id].machine_status == "failed" or self.machines[event.machine_id].machine_status == "repairing" or \
            (len(self.job_queue) == 0 and len(self.processing_queue) == 0):
            return
        l = get_label(self.machines[event.machine_id].df, event.timestamp, 10)
        if l == 1:
            # print(f"----machine {event.machine_id} detected failure at time {event.timestamp}, will be repaired at time {event.timestamp + self.default_repair_time}")
            # print(f"----machine {event.machine_id} status: {self.machines[event.machine_id].machine_status}")
            self.machines[event.machine_id].failures.append([event.timestamp - 10, event.timestamp, event.timestamp + self.default_repair_time])
            self.rescheduleDetect1(event.machine_id, event.timestamp -10, event.timestamp)
            self.machines[event.machine_id].machine_status = "repairing"
            self.rescheduleFailure(event.machine_id)
            machineRepairEvent = MachineRepairEvent(self.newEventId(), event.timestamp + self.default_repair_time, event.machine_id)
            self.addEvent(machineRepairEvent)
        pass

    def handleMachineRestoreEvent(self, event):
        if self.log_tag:
            print(f"Machine {event.machine_id} restored at time {event.timestamp}")
        if self.machines[event.machine_id].machine_status == "pre-failed":
            # print(f"----machine {event.machine_id} status: {self.machines[event.machine_id].machine_status}")
            self.machines[event.machine_id].machine_status = "idle"
            self.machines[event.machine_id].ready_time = event.timestamp
            self.scheduled_operations[event.machine_id] = []
        pass

    # 故障发生时能够立马检测到并立即进行重调度，将受影响的工序重新调度
    def rescheduleFailure(self, machine_id):
        if len(self.schedule.start_time[machine_id]) > 0 and \
           self.schedule.start_time[machine_id][-1] <= self.curr_time and \
           self.schedule.end_time[machine_id][-1] > self.curr_time:
            job_id, operation_id = self.schedule.schedule_items[machine_id][-1]
            self.schedule.schedule_items[machine_id].pop()
            self.schedule.start_time[machine_id].pop()
            self.schedule.end_time[machine_id].pop()
            # print(f"job_id: {job_id}, operation_id: {operation_id}, machine_id: {machine_id}")
            for event in self.event_queue:
                if isinstance(event, OperationFinishEvent) and event.job_id == job_id and event.operation_id == operation_id and event.machine_id == machine_id:
                    self.event_queue.remove(event)
                    operationScheduleEvent = OperationScheduleEvent(self.newEventId(), self.curr_time, job_id, operation_id)
                    self.addEvent(operationScheduleEvent)
                    break
        for i in range(len(self.scheduled_operations[machine_id])):
            job_id, operation_id = self.scheduled_operations[machine_id][i]
            for event in self.event_queue:
                if isinstance(event, OperationStartEvent) and event.job_id == job_id and event.operation_id == operation_id and event.machine_id == machine_id:
                    self.event_queue.remove(event)
                    operationScheduleEvent = OperationScheduleEvent(self.newEventId(), self.curr_time, job_id, operation_id)
                    self.addEvent(operationScheduleEvent)
                    break
        pass

    # 提前预知到故障时进行重调度，将受影响的工序重新调度
    def reschedulePredict(self, machine_id, predicted_failure_time):
        if len(self.schedule.start_time[machine_id]) > 0 and \
           self.schedule.start_time[machine_id][-1] <= self.curr_time and \
           self.schedule.end_time[machine_id][-1] > predicted_failure_time:
            job_id, operation_id = self.schedule.schedule_items[machine_id][-1]
            self.schedule.schedule_items[machine_id].pop()
            self.schedule.start_time[machine_id].pop()
            self.schedule.end_time[machine_id].pop()
            # print(f"job_id: {job_id}, operation_id: {operation_id}, machine_id: {machine_id}")
            for event in self.event_queue:
                if isinstance(event, OperationFinishEvent) and event.job_id == job_id and event.operation_id == operation_id and event.machine_id == machine_id:
                    self.event_queue.remove(event)
                    operationScheduleEvent = OperationScheduleEvent(self.newEventId(), self.curr_time, job_id, operation_id)
                    self.addEvent(operationScheduleEvent)
                    break
        for i in range(len(self.scheduled_operations[machine_id])):
            job_id, operation_id = self.scheduled_operations[machine_id][i]
            for event in self.event_queue:
                if isinstance(event, OperationStartEvent) and event.job_id == job_id and event.operation_id == operation_id and event.machine_id == machine_id:
                    self.event_queue.remove(event)
                    operationScheduleEvent = OperationScheduleEvent(self.newEventId(), self.curr_time, job_id, operation_id)
                    self.addEvent(operationScheduleEvent)
                    break
        pass

    # 未及时发现异常，导致监测到异常时已经出现了不合格的工件需要重新加工故障期间的工序，该工序对应的工件重新加工
    def rescheduleDetect1(self, machine_id, failure_time, repair_time):
        affected_job_ids = set()
        for i in range(len(self.schedule.schedule_items[machine_id])):
            job_id, operation_id = self.schedule.schedule_items[machine_id][i]
            start_time = self.schedule.start_time[machine_id][i]
            end_time = self.schedule.end_time[machine_id][i]
            if start_time >= failure_time and start_time <= repair_time or \
               end_time >= failure_time and end_time <= repair_time:
                affected_job_ids.add(job_id)
                for event in self.event_queue:
                    if (isinstance(event, OperationStartEvent) or isinstance(event, OperationFinishEvent) or isinstance(event, OperationScheduleEvent) or isinstance(event, JobFinishEvent)) and \
                        event.job_id == job_id:
                        self.event_queue.remove(event)
                for order in self.processing_queue:
                    if order.job_id == job_id:
                        self.processing_queue.remove(order)
                        break
                for order in self.finished_queue:
                    if order.job_id == job_id:
                        self.finished_queue.remove(order)
                        break
        for job_id in affected_job_ids:
            self.submitJob(job_id, 0, self.curr_time)
            print(f"Resubmit job {job_id} at time {self.curr_time}")
        for i in range(len(self.machines)):
            self.scheduled_operations[i] = [op for op in self.scheduled_operations[i] if op[0] not in affected_job_ids]
        # for i in range(len(self.scheduled_operations[machine_id])):
        #     job_id, operation_id = self.scheduled_operations[machine_id][i]
        #     for event in self.event_queue:
        #         if isinstance(event, OperationStartEvent) and event.job_id == job_id and event.operation_id == operation_id and event.machine_id == machine_id:
        #             self.event_queue.remove(event)
        #             operationScheduleEvent = OperationScheduleEvent(self.newEventId(), self.curr_time, job_id, operation_id)
        #             self.addEvent(operationScheduleEvent)
        #             break
        pass

     # 未及时发现异常，导致监测到异常时已经出现了不合格的工件需要重新加工故障期间的工序，重新调度该工序，并重做后续工序
    def rescheduleDetect2(self, machine_id, failure_time, repair_time):
        for i in range(len(self.schedule.schedule_items[machine_id])):
            job_id, operation_id = self.schedule.schedule_items[machine_id][i]
            start_time = self.schedule.start_time[machine_id][i]
            end_time = self.schedule.end_time[machine_id][i]
            if start_time >= failure_time and start_time <= repair_time or \
               end_time >= failure_time and end_time <= repair_time:
                for event in self.event_queue:
                    if (isinstance(event, OperationStartEvent) or isinstance(event, OperationFinishEvent) or isinstance(event, OperationScheduleEvent)) and \
                        event.job_id == job_id and event.operation_id >= operation_id:
                        self.event_queue.remove(event)
                    if isinstance(event, JobFinishEvent) and event.job_id == job_id:
                        for order in self.finished_queue:
                            if order.job_id == job_id:
                                self.finished_queue.remove(order)
                                break
                        self.event_queue.remove(event)
                operationScheduleEvent = OperationScheduleEvent(self.newEventId(), self.curr_time, job_id, operation_id)
                self.addEvent(operationScheduleEvent)
                for j in range(len(self.machines)):
                    self.scheduled_operations[j] = [op for op in self.scheduled_operations[j] if not (op[0] == job_id and op[1] >= operation_id)]
        pass
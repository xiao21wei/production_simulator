from enum import Enum

class EventType(Enum):
    MACHINE_RESTORE = "machine_restore"
    MACHINE_REPAIR = "machine_repair"
    FAILURE_DETECT = "failure_detect"
    OPERATION_FINISH = "operation_finish"
    JOB_FINISH = "job_finish"
    MACHINE_PREDICT = "failure_predict"
    MACHINE_FAILURE = "machine_failure"
    ORDER_ADD = "order_add"
    ORDER_DELETE = "order_delete"
    ORDER_UPDATE = "order_update"
    OPERATION_TIME_UPDATE = "operation_time_update"
    JOB_SUBMIT = "job_submit"
    JOB_START = "job_start"
    OPERATION_SCHEDULE = "operation_schedule"
    OPERATION_START = "operation_start"


class BaseEvent:
    def __init__(self, id, timestamp):
        self.id = id
        self.timestamp = timestamp
    
    def getEventType(self):
        if isinstance(self, JobSubmitEvent):
            return EventType.JOB_SUBMIT
        elif isinstance(self, JobStartEvent):
            return EventType.JOB_START
        elif isinstance(self, JobFinishEvent):
            return EventType.JOB_FINISH
        elif isinstance(self, OperationScheduleEvent):
            return EventType.OPERATION_SCHEDULE
        elif isinstance(self, OperationStartEvent):
            return EventType.OPERATION_START
        elif isinstance(self, OperationFinishEvent):
            return EventType.OPERATION_FINISH
        # elif isinstance(self, OrderAddEvent):
        #     return EventType.ORDER_ADD
        # elif isinstance(self, OrderDeleteEvent):
        #     return EventType.ORDER_DELETE
        # elif isinstance(self, OrderUpdateEvent):
        #     return EventType.ORDER_UPDATE
        # elif isinstance(self, OperationTimeUpdateEvent):
        #     return EventType.OPERATION_TIME_UPDATE
        elif isinstance(self, MachineFailureEvent):
            return EventType.MACHINE_FAILURE
        elif isinstance(self, MachineRepairEvent):
            return EventType.MACHINE_REPAIR
        elif isinstance(self, FailurePredictEvent):
            return EventType.MACHINE_PREDICT
        elif isinstance(self, FailureDetectEvent):
            return EventType.FAILURE_DETECT
        elif isinstance(self, MachineRestoreEvent):
            return EventType.MACHINE_RESTORE
        else:
            raise ValueError("Unknown event type")

class JobSubmitEvent(BaseEvent):
    def __init__(self, id, timestamp, job_id, priority):
        super().__init__(id, timestamp)
        self.job_id = job_id
        self.priority = priority

class JobStartEvent(BaseEvent):
    def __init__(self, id, timestamp, job_id):
        super().__init__(id, timestamp)
        self.job_id = job_id

class JobFinishEvent(BaseEvent):
    def __init__(self, id, timestamp, job_id):
        super().__init__(id, timestamp)
        self.job_id = job_id

class OperationScheduleEvent(BaseEvent):
    def __init__(self, id, timestamp, job_id, operation_id):
        super().__init__(id, timestamp)
        self.job_id = job_id
        self.operation_id = operation_id

class OperationStartEvent(BaseEvent):
    def __init__(self, id, timestamp, job_id, operation_id, machine_id):
        super().__init__(id, timestamp)
        self.job_id = job_id
        self.operation_id = operation_id
        self.machine_id = machine_id

class OperationFinishEvent(BaseEvent):
    def __init__(self, id, timestamp, job_id, operation_id, machine_id):
        super().__init__(id, timestamp)
        self.job_id = job_id
        self.operation_id = operation_id
        self.machine_id = machine_id

# class OrderAddEvent(BaseEvent):
#     def __init__(self, id, timestamp, job_id, priority):
#         super().__init__(id, timestamp)
#         self.job_id = job_id
#         self.priority = priority

# class OrderDeleteEvent(BaseEvent):
#     def __init__(self, id, timestamp, job_id):
#         super().__init__(id, timestamp)
#         self.job_id = job_id

# class OrderUpdateEvent(BaseEvent):
#     def __init__(self, id, timestamp, job_id, new_priority):
#         super().__init__(id, timestamp)
#         self.job_id = job_id
#         self.new_priority = new_priority

# class OperationTimeUpdateEvent(BaseEvent):
#     def __init__(self, id, timestamp, job_id, operation_id, machine_id, new_time):
#         super().__init__(id, timestamp)
#         self.job_id = job_id
#         self.operation_id = operation_id
#         self.machine_id = machine_id
#         self.new_time = new_time

class MachineFailureEvent(BaseEvent):
    def __init__(self, id, timestamp, machine_id, repair_time):
        super().__init__(id, timestamp)
        self.machine_id = machine_id
        self.repair_time = repair_time

class MachineRepairEvent(BaseEvent):
    def __init__(self, id, timestamp, machine_id):
        super().__init__(id, timestamp)
        self.machine_id = machine_id

class FailurePredictEvent(BaseEvent):
    def __init__(self, id, timestamp, machine_id):
        super().__init__(id, timestamp)
        self.machine_id = machine_id

class FailureDetectEvent(BaseEvent):
    def __init__(self, id, timestamp, machine_id):
        super().__init__(id, timestamp)
        self.machine_id = machine_id

class MachineRestoreEvent(BaseEvent):
    def __init__(self, id, timestamp, machine_id):
        super().__init__(id, timestamp)
        self.machine_id = machine_id
        
from enum import Enum

class EventType(Enum):
    SCHEDULE = "schedule"
    OPERATION_FINISH = "operation_finish"
    JOB_FINISH = "job_finish"
    ORDER_INSERT = "order_insert"
    ORDER_CANCEL = "order_cancel"
    ORDER_UPDATE = "order_update"
    OPERATION_TIME_UPDATE = "operation_time_update"
    JOB_SUBMIT = "job_submit"
    JOB_START = "job_start"
    TRANSPORT_FINISH = "transport_finish"
    OPERATION_START = "operation_start"
    PROCESS_STAGE_FINISH = "process_stage_finish"
    PROCESS_STAGE_BATCH_SCHEDULE = "process_stage_batch_schedule"
    MACHINE_ANOMALY = "machine_anomaly"
    MACHINE_RECOVERY = "machine_recovery"
    MATERIAL_REPLENISHMENT = "material_replenishment"
    MATERIAL_RECOVERY = "material_recovery"


class BaseEvent:
    def __init__(self, id, timestamp):
        self.id = id
        self.timestamp = timestamp
    
    def getEventType(self):
        if isinstance(self, ScheduleEvent):
            return EventType.SCHEDULE
        elif isinstance(self, OrderInsertEvent):
            return EventType.ORDER_INSERT
        elif isinstance(self, OrderCancelEvent):
            return EventType.ORDER_CANCEL
        elif isinstance(self, JobSubmitEvent):
            return EventType.JOB_SUBMIT
        elif isinstance(self, JobStartEvent):
            return EventType.JOB_START
        elif isinstance(self, JobFinishEvent):
            return EventType.JOB_FINISH
        elif isinstance(self, TransportFinishEvent):
            return EventType.TRANSPORT_FINISH
        elif isinstance(self, OperationStartEvent):
            return EventType.OPERATION_START
        elif isinstance(self, OperationFinishEvent):
            return EventType.OPERATION_FINISH
        elif isinstance(self, ProcessStageFinishEvent):
            return EventType.PROCESS_STAGE_FINISH
        elif isinstance(self, ProcessStageBatchScheduleEvent):
            return EventType.PROCESS_STAGE_BATCH_SCHEDULE
        elif isinstance(self, MachineAnomalyEvent):
            return EventType.MACHINE_ANOMALY
        elif isinstance(self, MachineRecoveryEvent):
            return EventType.MACHINE_RECOVERY
        elif isinstance(self, MaterialReplenishmentEvent):
            return EventType.MATERIAL_REPLENISHMENT
        elif isinstance(self, MaterialRecoveryEvent):
            return EventType.MATERIAL_RECOVERY
        # elif isinstance(self, OrderUpdateEvent):
        #     return EventType.ORDER_UPDATE
        # elif isinstance(self, OperationTimeUpdateEvent):
        #     return EventType.OPERATION_TIME_UPDATE
        else:
            raise ValueError("Unknown event type")

class ScheduleEvent(BaseEvent):
    pass

class OrderInsertEvent(BaseEvent):
    """Dynamically insert a generated batch of orders and Jobs."""

    def __init__(self, id, timestamp, seed=0, source="manual"):
        super().__init__(id, timestamp)
        self.seed = int(seed)
        self.order_source = str(source)
        self.order_id = None
        self.job_ids = []
        self.job_count = 0
        self.result = None

class OrderCancelEvent(BaseEvent):
    """Cancel one order or a prevalidated batch of orders."""

    def __init__(
        self,
        id,
        timestamp,
        job_ids,
        batch=False,
        order_ids=None,
    ):
        super().__init__(id, timestamp)
        normalized_job_ids = []
        for job_id in job_ids:
            if isinstance(job_id, bool):
                raise ValueError(
                    "job_ids must contain only integers."
                )
            try:
                normalized_job_ids.append(int(job_id))
            except (TypeError, ValueError) as exc:
                raise ValueError(
                    "job_ids must contain only integers."
                ) from exc
        self.job_ids = normalized_job_ids
        self.batch = bool(batch)
        self.order_ids = [
            str(order_id) for order_id in (order_ids or [])
        ]
        self.result = None

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

class TransportFinishEvent(BaseEvent):
    def __init__(
        self,
        id,
        timestamp,
        job_id,
        operation_id,
        machine_id,
        historical=False,
        transport_start=None,
        transport_end=None,
    ):
        super().__init__(id, timestamp)
        self.job_id = job_id
        self.operation_id = operation_id
        self.machine_id = machine_id
        self.historical = bool(historical)
        if transport_start is not None:
            self.transport_start = float(transport_start)
        if transport_end is not None:
            self.transport_end = float(transport_end)

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


class MaterialReplenishmentEvent(BaseEvent):
    """Replenish materials that are insufficient for an operation."""

    def __init__(
        self,
        id,
        timestamp,
        machine_id,
        job_id,
        operation_id,
        required_materials,
        replenishment_materials,
        available_materials=None,
        target_materials=None,
        shortage_materials=None,
        lead_time=0.0,
    ):
        super().__init__(id, timestamp)
        self.machine_id = int(machine_id)
        self.job_id = int(job_id)
        self.operation_id = int(operation_id)
        self.required_materials = {
            str(material_id): float(quantity)
            for material_id, quantity in required_materials.items()
        }
        self.replenishment_materials = {
            str(material_id): float(quantity)
            for material_id, quantity
            in replenishment_materials.items()
        }
        self.available_materials = {
            str(material_id): float(quantity)
            for material_id, quantity
            in (available_materials or {}).items()
        }
        self.target_materials = {
            str(material_id): float(quantity)
            for material_id, quantity
            in (target_materials or {}).items()
        }
        self.shortage_materials = {
            str(material_id): float(quantity)
            for material_id, quantity
            in (shortage_materials or {}).items()
        }
        self.lead_time = float(lead_time)
        self.added_materials = {}
        self.result = None


class MaterialRecoveryEvent(BaseEvent):
    """Recheck replenished stock and release the blocked operation."""

    def __init__(
        self,
        id,
        timestamp,
        machine_id,
        job_id,
        operation_id,
        required_materials,
        replenishment_materials=None,
        target_materials=None,
        shortage_materials=None,
        replenishment_event_id=None,
        lead_time=0.0,
    ):
        super().__init__(id, timestamp)
        self.machine_id = int(machine_id)
        self.job_id = int(job_id)
        self.operation_id = int(operation_id)
        self.required_materials = {
            str(material_id): float(quantity)
            for material_id, quantity in required_materials.items()
        }
        self.replenishment_materials = {
            str(material_id): float(quantity)
            for material_id, quantity
            in (replenishment_materials or {}).items()
        }
        self.target_materials = {
            str(material_id): float(quantity)
            for material_id, quantity
            in (target_materials or {}).items()
        }
        self.shortage_materials = {
            str(material_id): float(quantity)
            for material_id, quantity
            in (shortage_materials or {}).items()
        }
        self.replenishment_event_id = replenishment_event_id
        self.lead_time = float(lead_time)
        self.added_materials = {}
        self.available_materials = {}
        self.result = None


class ProcessStageFinishEvent(BaseEvent):
    def __init__(
        self,
        id,
        timestamp,
        job_id,
        from_stage,
        to_stage,
    ):
        super().__init__(id, timestamp)
        self.job_id = job_id
        self.from_stage = from_stage
        self.to_stage = to_stage
        self.result = None


class ProcessStageBatchScheduleEvent(BaseEvent):
    """Schedule Jobs that entered one target process inside a batch window."""

    def __init__(
        self,
        id,
        timestamp,
        stage_id,
        batch_window,
    ):
        super().__init__(id, timestamp)
        self.stage_id = int(stage_id)
        self.to_stage = int(stage_id)
        self.batch_window = float(batch_window)
        self.job_ids = []
        self.job_ready_times = {}
        self.job_count = 0
        self.result = None

    def add_job(self, job_id, ready_time):
        job_id = int(job_id)
        if job_id not in self.job_ready_times:
            self.job_ids.append(job_id)
        self.job_ready_times[job_id] = float(ready_time)
        self.job_count = len(self.job_ids)



class MachineAnomalyEvent(BaseEvent):
    def __init__(
        self,
        id,
        timestamp,
        machine_id,
        anomaly_type,
        duration,
    ):
        super().__init__(id, timestamp)
        self.machine_id = int(machine_id)
        self.anomaly_type = anomaly_type
        self.duration = float(duration)
        self.machine_status = None
        self.result = None


class MachineRecoveryEvent(BaseEvent):
    def __init__(
        self,
        id,
        timestamp,
        machine_id,
        anomaly_type,
        anomaly_started_at=None,
    ):
        super().__init__(id, timestamp)
        self.machine_id = machine_id
        self.anomaly_type = anomaly_type
        self.anomaly_started_at = anomaly_started_at
        self.machine_status = None
        self.result = None

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


from system.schedule import PlannedOperation


class Machine:
    def __init__(
        self,
        machine_id,
        machine_status,
        ready_time,
        operation_times,
        operation_energy,
        stage_id=1,
        local_machine_id=None,
        materials=None,
    ):
        self.machine_id = machine_id
        self.machine_status = machine_status  # "idle", "busy", "scheduled"
        self.ready_time = ready_time
        self.operation_times = operation_times
        self.operation_energy = operation_energy
        self.stage_id = int(stage_id)
        self.local_machine_id = (
            self.machine_id
            if local_machine_id is None
            else int(local_machine_id)
        )
        self.pending_operations = []
        self.materials = {
            str(material_id): float(quantity)
            for material_id, quantity in (materials or {}).items()
        }
        self.anomaly_type = None
        self.anomaly_started_at = None
        self.recovery_time = None
        self.performance_factor = 1.0

    def enqueueOperation(self, operation):
        if not isinstance(operation, PlannedOperation):
            raise TypeError("operation must be a PlannedOperation.")
        for existing in self.pending_operations:
            if (
                existing.job_id == operation.job_id
                and existing.operation_id == operation.operation_id
            ):
                existing.machine_id = operation.machine_id
                existing.start_time = operation.start_time
                existing.end_time = operation.end_time
                existing.transport_segments = list(
                    operation.transport_segments
                )
                return
        self.pending_operations.append(operation)

    def nextPendingOperation(self):
        if not self.pending_operations:
            return None
        return self.pending_operations[0]

    def popNextOperation(self):
        if not self.pending_operations:
            return None
        return self.pending_operations.pop(0)

    def clearPendingOperations(self):
        self.pending_operations.clear()

    def scheduleOperation(self, time):
        self.machine_status = "scheduled"
        self.ready_time = time

    def addOperation(self, time):
        if (
            self.anomaly_type != "degraded"
            and self.machine_status not in {"failed", "repairing"}
        ):
            self.machine_status = "busy"

    def finishOperation(self, time, scheduled_count):
        if self.machine_status in {"failed", "repairing", "degraded"}:
            return
        if scheduled_count > 0:
            self.machine_status = "scheduled"
        elif scheduled_count == 0:
            self.machine_status = "idle"

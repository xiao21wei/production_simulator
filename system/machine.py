from system.schedule import PlannedOperation


class Machine:
    def __init__(
        self,
        machine_id,
        machine_status,
        ready_time,
        operation_times,
        operation_energy,
    ):
        self.machine_id = machine_id
        self.machine_status = machine_status  # "idle", "busy", "scheduled"
        self.ready_time = ready_time
        self.operation_times = operation_times
        self.operation_energy = operation_energy
        self.pending_operations = []

    def enqueueOperation(self, operation):
        if not isinstance(operation, PlannedOperation):
            raise TypeError("operation must be a PlannedOperation.")
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
        self.machine_status = "busy"

    def finishOperation(self, time, scheduled_count):
        if scheduled_count > 0:
            self.machine_status = "scheduled"
        elif scheduled_count == 0:
            self.machine_status = "idle"

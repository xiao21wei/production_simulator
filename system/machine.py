from model_predict.online_inference import *


class Machine:
    def __init__(self, machine_id, machine_status, ready_time, operation_times, operation_energy):
        self.machine_id = machine_id
        self.machine_status = machine_status  # "idle", "busy", "scheduled", "failed", "pre-failed"
        self.ready_time = ready_time
        self.operation_times = operation_times
        self.operation_energy = operation_energy
        self.df = load_data(machine_id)
        self.failures = []

    def scheduleOperation(self, time):
        self.machine_status = "scheduled"
        self.ready_time = time

    def addOperation(self, time):
        self.machine_status = "busy"

    def finishOperation(self, time, scheduled_count):
        if scheduled_count > 0 and self.machine_status != "failed":
            self.machine_status = "scheduled"
        elif scheduled_count == 0 and self.machine_status != "failed":
            self.machine_status = "idle"
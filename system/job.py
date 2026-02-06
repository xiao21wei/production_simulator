import random

class Job:
    def __init__(self, job_id, operation_count, operation_times, operation_energy, ready_time, due_time, earliness_cost, tardiness_cost, weight):
        self.job_id = job_id
        self.operation_count = operation_count
        self.operation_times = operation_times
        self.operation_energy = operation_energy
        self.ready_time = ready_time
        self.due_time = due_time
        self.earliness_cost = earliness_cost
        self.tardiness_cost = tardiness_cost
        self.weight = weight

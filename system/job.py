import random


class Task:
    def __init__(
        self,
        task_id,
        job_id,
        operation_id,
        processing_times,
        processing_energies,
        predecessor_id=None,
        successor_id=None,
    ):
        self.task_id = task_id
        self.job_id = job_id
        self.operation_id = operation_id
        self.processing_times = dict(processing_times)
        self.processing_energies = dict(processing_energies)
        self.predecessor_id = predecessor_id
        self.successor_id = successor_id

        self.eligible_machines = tuple(sorted(self.processing_times))
        self.status = "pending"
        self.assigned_machine = None
        self.planned_start = None
        self.planned_end = None
        self.actual_start = None
        self.actual_end = None
        self.source_machine = None
        self.transport_start = None
        self.transport_end = None
        self.transport_time = 0
        self.transport_energy = 0
        self.transport_completed = False
        self.committed_transport_energy = 0
        self.current_location_machine = None
        self.waiting_time = 0

    @property
    def processing_time(self):
        if self.assigned_machine is None:
            return None
        return self.processing_times[self.assigned_machine]

    @property
    def processing_energy(self):
        if self.assigned_machine is None:
            return None
        return self.processing_energies[self.assigned_machine]

    @property
    def total_transport_energy(self):
        current_leg = (
            self.transport_energy
            if self.transport_completed
            else 0
        )
        return self.committed_transport_energy + current_leg


class Job:
    def __init__(
        self,
        job_id,
        operation_count,
        operation_times,
        operation_energy,
        ready_time,
        due_time,
        earliness_cost,
        tardiness_cost,
        weight,
        tasks=None,
        priority=0,
        transport_time_matrix=None,
        transport_energy_matrix=None,
    ):
        self.job_id = job_id
        self.operation_count = operation_count
        self.operation_times = operation_times
        self.operation_energy = operation_energy
        self.ready_time = ready_time
        self.due_time = due_time
        self.earliness_cost = earliness_cost
        self.tardiness_cost = tardiness_cost
        self.weight = weight
        self.tasks = tasks or []
        self.priority = priority
        self.transport_time_matrix = transport_time_matrix
        self.transport_energy_matrix = transport_energy_matrix

        self.release_time = ready_time
        self.due_date = due_time
        self.earliness_penalty = earliness_cost
        self.tardiness_penalty = tardiness_cost
        self.completion_time = None
        self.earliness = 0
        self.tardiness = 0
        self.processing_energy = 0
        self.transport_energy = 0

    @property
    def total_energy(self):
        return self.processing_energy + self.transport_energy

    @property
    def delivery_penalty(self):
        return self.weight * (
            self.earliness_penalty * self.earliness
            + self.tardiness_penalty * self.tardiness
        )

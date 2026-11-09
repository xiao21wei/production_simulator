"""Random job generation compatible with the multi-objective dataset format."""

from __future__ import annotations

import random

from system.job import Job, Task


def generate_random_job(
    existing_jobs,
    num_machines,
    current_time,
    seed,
    template_jobs=None,
):
    """Create one job using the value ranges from datasets/create_ins.py."""
    templates = [
        job for job in (template_jobs or existing_jobs)
        if job.operation_count > 0 and job.tasks
    ]
    if not templates:
        raise ValueError("At least one existing job is required.")

    rng = random.Random(seed)
    template_job = rng.choice(templates)
    operation_count = template_job.operation_count
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

    operation_times = [
        [float("inf")] * num_machines
        for _ in range(operation_count)
    ]
    operation_energy = [
        [float("inf")] * num_machines
        for _ in range(operation_count)
    ]
    tasks = []
    operation_means = []

    for operation_id in range(operation_count):
        template_task = template_job.tasks[operation_id]
        machines = tuple(template_task.eligible_machines)
        if not machines:
            raise ValueError(
                f"Template task {template_task.task_id} has no machines."
            )
        template_times = [
            int(template_task.processing_times[machine_id])
            for machine_id in machines
        ]
        time_low = max(1, min(template_times))
        time_high = max(time_low, max(template_times))
        processing_times = {
            machine_id: rng.randint(time_low, time_high)
            for machine_id in machines
        }
        processing_energies = {
            machine_id: rng.randint(4, 15)
            for machine_id in machines
        }
        for machine_id in machines:
            operation_times[operation_id][machine_id] = (
                processing_times[machine_id]
            )
            operation_energy[operation_id][machine_id] = (
                processing_energies[machine_id]
            )
        operation_means.append(
            sum(processing_times.values()) / len(processing_times)
        )
        tasks.append(
            Task(
                task_id=next_task_id + operation_id,
                job_id=job_id,
                operation_id=operation_id,
                processing_times=processing_times,
                processing_energies=processing_energies,
                predecessor_id=(
                    next_task_id + operation_id - 1
                    if operation_id > 0
                    else None
                ),
            )
        )

    for operation_id in range(operation_count - 1):
        tasks[operation_id].successor_id = tasks[
            operation_id + 1
        ].task_id

    weight = rng.randint(1, 5)
    ready_time = float(current_time) + rng.randint(0, 20)
    due_time = int(
        ready_time + sum(operation_means) * 1.5
    )
    earliness_cost = rng.randint(1, 10)
    tardiness_cost = rng.randint(1, 10)

    transport_time = [
        [0.0] * num_machines
        for _ in range(num_machines)
    ]
    transport_energy = [
        [0.0] * num_machines
        for _ in range(num_machines)
    ]
    for source in range(num_machines):
        for target in range(source + 1, num_machines):
            time_cost = float(rng.randint(1, 3))
            energy_cost = float(rng.randint(1, 4))
            transport_time[source][target] = time_cost
            transport_time[target][source] = time_cost
            transport_energy[source][target] = energy_cost
            transport_energy[target][source] = energy_cost

    return Job(
        job_id=job_id,
        operation_count=operation_count,
        operation_times=operation_times,
        operation_energy=operation_energy,
        ready_time=ready_time,
        due_time=due_time,
        earliness_cost=earliness_cost,
        tardiness_cost=tardiness_cost,
        weight=weight,
        tasks=tasks,
        priority=0,
        transport_time_matrix=transport_time,
        transport_energy_matrix=transport_energy,
    )

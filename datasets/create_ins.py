import hashlib
import os
import random


def main():
    raw_path = "datasets/raw/Brandimarete"
    add_path = "datasets/add/Brandimarete"
    seed = 42

    if not os.path.isdir(raw_path):
        return

    os.makedirs(add_path, exist_ok=True)

    for file_name in sorted(os.listdir(raw_path)):
        input_file = os.path.join(raw_path, file_name)
        if not os.path.isfile(input_file):
            continue
        output_file = os.path.join(add_path, file_name)
        create_instance(input_file, output_file, seed)


def _parse_job_line(line):
    numbers = [int(value) for value in line.split()]
    operation_count = numbers[0]
    index = 1
    operation_mean_times = []
    operations = []

    for _ in range(operation_count):
        machine_count = numbers[index]
        index += 1
        options = []
        time_sum = 0
        for _ in range(machine_count):
            machine = numbers[index]
            processing_time = numbers[index + 1]
            options.append((machine, processing_time))
            time_sum += processing_time
            index += 2
        operation_mean_times.append(time_sum / machine_count)
        operations.append(options)

    mean_time = sum(operation_mean_times)
    return operation_count, operations, mean_time


def _format_job_line(operation_count, operations):
    parts = [str(operation_count)]
    for options in operations:
        parts.append(str(len(options)))
        for machine, processing_time in options:
            parts.append(str(machine))
            parts.append(str(random.randint(4, 15)))
    return " ".join(parts)


def _estimate_job_duration(operations):
    return sum(sum(processing_time for _, processing_time in options) for options in operations)


def _build_transport_matrix(machine_count, upper_bound):
    transport_matrix = [[0 for _ in range(machine_count)] for _ in range(machine_count)]
    for i in range(machine_count):
            for j in range(machine_count):
                if i < j:
                    temp = random.randint(1, upper_bound)
                    transport_matrix[i][j] = temp
                    transport_matrix[j][i] = temp
    return transport_matrix


def _matrix_to_lines(matrix):
    return [" ".join(str(value) for value in row) for row in matrix]


def create_instance(input_file, output_file, seed):
    with open(input_file, "r") as source:
        raw_lines = [line.strip() for line in source if line.strip()]

    if not raw_lines:
        raise ValueError(f"empty input file: {input_file}")

    header_tokens = raw_lines[0].split()

    job_lines = raw_lines[1:]
    job_count = int(header_tokens[0])
    machine_count = int(header_tokens[1])
    job_structures = [_parse_job_line(line) for line in job_lines]

    random.seed(seed)

    processing_energy_lines = [
        _format_job_line(operation_count, operations) 
        for operation_count, operations, _ in job_structures
    ]

    job_info_lines = []
    for _ in range(job_count):
        weight = random.randint(1, 5)
        ready_time = random.randint(0, 20)
        due_time = int(ready_time + job_structures[_][2] * 1.5)
        earliness_cost = random.randint(1, 10)
        tardiness_cost = random.randint(1, 10)
        job_info_lines.append(f"{weight} {ready_time} {due_time} {earliness_cost} {tardiness_cost}")

    transport_time_matrix = _build_transport_matrix(machine_count, 3)
    transport_energy_matrix = _build_transport_matrix(machine_count, 4)

    output_lines = []
    output_lines.extend(processing_energy_lines)
    output_lines.extend(job_info_lines)
    output_lines.extend(_matrix_to_lines(transport_time_matrix))
    output_lines.extend(_matrix_to_lines(transport_energy_matrix))

    output_directory = os.path.dirname(output_file)
    if output_directory:
        os.makedirs(output_directory, exist_ok=True)

    with open(output_file, "w") as target:
        target.write("\n".join(output_lines))
        target.write("\n")

if __name__ == "__main__":
    main()


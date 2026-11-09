from dataclasses import dataclass
from pathlib import Path

from system.job import Job, Task


class DatasetValidationError(ValueError):
    """Raised when a multi-objective dataset is inconsistent or incomplete."""


@dataclass(frozen=True)
class MultiObjectiveDataset:
    raw_path: Path
    additional_path: Path
    num_jobs: int
    num_machines: int
    metadata: int
    jobs: list
    transport_time: list
    transport_energy: list

    @property
    def num_operations(self):
        return sum(job.operation_count for job in self.jobs)


def list_dataset_sources(dataset_root, default_raw_path=None):
    """Return valid raw/add dataset pairs found below a dataset root."""
    root = Path(dataset_root)
    raw_dir = root / "raw"
    add_dir = root / "add"
    if not raw_dir.is_dir() or not add_dir.is_dir():
        raise DatasetValidationError(
            f"Dataset root must contain raw/ and add/: {root}"
        )

    default_name = (
        Path(default_raw_path).name if default_raw_path is not None else None
    )
    sources = []
    for raw_path in sorted(raw_dir.glob("*.fjs")):
        additional_path = add_dir / raw_path.name
        if not additional_path.is_file():
            continue
        try:
            header = raw_path.read_text(encoding="utf-8").splitlines()[0].split()
            num_jobs = int(header[0])
            num_machines = int(header[1])
        except (OSError, IndexError, ValueError):
            continue

        dataset_id = raw_path.stem
        sources.append(
            {
                "id": dataset_id,
                "name": dataset_id.removeprefix("fjsp."),
                "label": f"{dataset_id.removeprefix('fjsp.')} · "
                         f"{num_jobs} jobs × {num_machines} machines",
                "num_jobs": num_jobs,
                "num_machines": num_machines,
                "raw_file": str(raw_path.resolve()),
                "additional_file": str(additional_path.resolve()),
                "is_default": raw_path.name == default_name,
            }
        )
    return sources


def get_dataset_source(dataset_root, dataset_id):
    """Resolve one dataset ID from a catalog root."""
    if not dataset_id or Path(dataset_id).name != dataset_id:
        raise DatasetValidationError("Invalid dataset ID.")

    sources = list_dataset_sources(dataset_root)
    for source in sources:
        if source["id"] == dataset_id:
            return source
    raise DatasetValidationError(
        f"Dataset '{dataset_id}' was not found under {dataset_root}."
    )


def load_multi_objective_dataset(raw_path, additional_path):
    raw_path = Path(raw_path)
    additional_path = Path(additional_path)
    raw_lines = _read_nonempty_lines(raw_path)
    additional_lines = _read_nonempty_lines(additional_path)

    if not raw_lines:
        raise DatasetValidationError(f"Raw dataset is empty: {raw_path}")
    if not additional_lines:
        raise DatasetValidationError(
            f"Additional dataset is empty: {additional_path}"
        )

    header = _parse_integers(raw_lines[0], "raw header", raw_path, 1)
    if len(header) < 3:
        raise DatasetValidationError(
            f"{raw_path}:1 raw header must contain "
            "num_jobs num_machines metadata"
        )
    num_jobs, num_machines, metadata = header[:3]
    if num_jobs <= 0 or num_machines <= 0:
        raise DatasetValidationError(
            f"{raw_path}:1 job and machine counts must be positive"
        )

    expected_raw_lines = 1 + num_jobs
    if len(raw_lines) != expected_raw_lines:
        raise DatasetValidationError(
            f"{raw_path}: expected {expected_raw_lines} non-empty lines, "
            f"found {len(raw_lines)}"
        )

    parsed_jobs = []
    for job_id, line in enumerate(raw_lines[1:]):
        parsed_jobs.append(
            _parse_operation_options(
                line=line,
                machine_count=num_machines,
                source=raw_path,
                line_number=job_id + 2,
                label=f"job {job_id} processing times",
                value_name="processing time",
                require_positive=True,
            )
        )

    feature_start = num_jobs
    if len(additional_lines) < feature_start + num_jobs:
        raise DatasetValidationError(
            f"{additional_path}: missing processing energy or job feature rows"
        )

    parsed_energies = []
    for job_id, line in enumerate(additional_lines[:num_jobs]):
        parsed_energies.append(
            _parse_operation_options(
                line=line,
                machine_count=num_machines,
                source=additional_path,
                line_number=job_id + 1,
                label=f"job {job_id} processing energy",
                value_name="processing energy",
                require_positive=False,
            )
        )

    jobs = []
    task_id = 0
    for job_id, raw_job in enumerate(parsed_jobs):
        energy_job = parsed_energies[job_id]
        if len(energy_job) != len(raw_job):
            raise DatasetValidationError(
                f"job {job_id}: raw and additional files contain "
                "different operation counts"
            )

        operation_count = len(raw_job)
        operation_times = [
            [float("inf")] * num_machines
            for _ in range(operation_count)
        ]
        operation_energy = [
            [float("inf")] * num_machines
            for _ in range(operation_count)
        ]
        tasks = []

        for operation_id in range(operation_count):
            time_options = raw_job[operation_id]
            energy_options = energy_job[operation_id]
            if set(time_options) != set(energy_options):
                raise DatasetValidationError(
                    f"job {job_id} operation {operation_id}: raw and "
                    "additional machine sets differ"
                )

            for machine_id, processing_time in time_options.items():
                operation_times[operation_id][machine_id] = processing_time
                operation_energy[operation_id][machine_id] = (
                    energy_options[machine_id]
                )

            tasks.append(
                Task(
                    task_id=task_id,
                    job_id=job_id,
                    operation_id=operation_id,
                    processing_times=time_options,
                    processing_energies=energy_options,
                    predecessor_id=(task_id - 1 if operation_id > 0 else None),
                )
            )
            task_id += 1

        for operation_id in range(operation_count - 1):
            tasks[operation_id].successor_id = tasks[operation_id + 1].task_id

        feature_line_number = feature_start + job_id + 1
        features = _parse_numbers(
            additional_lines[feature_start + job_id],
            f"job {job_id} features",
            additional_path,
            feature_line_number,
        )
        if len(features) != 5:
            raise DatasetValidationError(
                f"{additional_path}:{feature_line_number}: job {job_id} "
                "must contain exactly 5 features: "
                "weight ready_time due_time earliness_penalty "
                "tardiness_penalty"
            )
        weight, ready_time, due_time, early_penalty, tardy_penalty = features
        if weight <= 0:
            raise DatasetValidationError(
                f"{additional_path}:{feature_line_number}: "
                "job weight must be positive"
            )
        if ready_time < 0 or early_penalty < 0 or tardy_penalty < 0:
            raise DatasetValidationError(
                f"{additional_path}:{feature_line_number}: "
                "job ready time and penalties must be non-negative"
            )
        if due_time < ready_time:
            raise DatasetValidationError(
                f"{additional_path}:{feature_line_number}: "
                "job due time cannot be earlier than ready time"
            )

        jobs.append(
            Job(
                job_id=job_id,
                operation_count=operation_count,
                operation_times=operation_times,
                operation_energy=operation_energy,
                ready_time=_number_value(ready_time),
                due_time=_number_value(due_time),
                earliness_cost=_number_value(early_penalty),
                tardiness_cost=_number_value(tardy_penalty),
                weight=_number_value(weight),
                tasks=tasks,
                priority=0,
            )
        )

    matrix_start = feature_start + num_jobs
    matrix_values = []
    for line in additional_lines[matrix_start:]:
        matrix_values.extend(
            _parse_numbers(
                line,
                "transport matrix",
                additional_path,
                matrix_start + 1,
            )
        )

    matrix_size = num_machines * num_machines
    if len(matrix_values) != matrix_size * 2:
        raise DatasetValidationError(
            f"{additional_path}: transport section must contain "
            f"{matrix_size * 2} values, found {len(matrix_values)}"
        )

    transport_time = _reshape_matrix(
        matrix_values[:matrix_size],
        num_machines,
        "transport time",
    )
    transport_energy = _reshape_matrix(
        matrix_values[matrix_size:],
        num_machines,
        "transport energy",
    )
    _validate_transport_matrix(transport_time, "transport time")
    _validate_transport_matrix(transport_energy, "transport energy")

    return MultiObjectiveDataset(
        raw_path=raw_path,
        additional_path=additional_path,
        num_jobs=num_jobs,
        num_machines=num_machines,
        metadata=metadata,
        jobs=jobs,
        transport_time=transport_time,
        transport_energy=transport_energy,
    )


def _read_nonempty_lines(path):
    try:
        return [
            line.strip()
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
    except FileNotFoundError as exc:
        raise DatasetValidationError(f"Dataset file not found: {path}") from exc


def _parse_operation_options(
    line,
    machine_count,
    source,
    line_number,
    label,
    value_name,
    require_positive,
):
    tokens = line.split()
    try:
        operation_count = int(tokens[0])
    except (IndexError, ValueError) as exc:
        raise DatasetValidationError(
            f"{source}:{line_number}: {label} has an invalid operation count"
        ) from exc

    if operation_count <= 0:
        raise DatasetValidationError(
            f"{source}:{line_number}: {label} operation count must be positive"
        )

    position = 1
    operations = []
    for operation_id in range(operation_count):
        if position >= len(tokens):
            raise DatasetValidationError(
                f"{source}:{line_number}: {label} ends at operation "
                f"{operation_id}"
            )
        try:
            option_count = int(tokens[position])
        except ValueError as exc:
            raise DatasetValidationError(
                f"{source}:{line_number}: invalid option count for "
                f"operation {operation_id}"
            ) from exc
        position += 1
        if option_count <= 0:
            raise DatasetValidationError(
                f"{source}:{line_number}: operation {operation_id} "
                "must have at least one machine option"
            )

        options = {}
        for _ in range(option_count):
            if position + 1 >= len(tokens):
                raise DatasetValidationError(
                    f"{source}:{line_number}: incomplete machine/value "
                    f"pair for operation {operation_id}"
                )
            try:
                machine_id = int(tokens[position]) - 1
                value = float(tokens[position + 1])
            except ValueError as exc:
                raise DatasetValidationError(
                    f"{source}:{line_number}: invalid machine/value pair "
                    f"for operation {operation_id}"
                ) from exc
            position += 2

            if not 0 <= machine_id < machine_count:
                raise DatasetValidationError(
                    f"{source}:{line_number}: machine {machine_id + 1} "
                    f"is outside 1..{machine_count}"
                )
            if machine_id in options:
                raise DatasetValidationError(
                    f"{source}:{line_number}: operation {operation_id} "
                    f"repeats machine {machine_id + 1}"
                )
            if require_positive and value <= 0:
                raise DatasetValidationError(
                    f"{source}:{line_number}: {value_name} must be positive "
                    f"for operation {operation_id} on machine {machine_id + 1}"
                )
            if not require_positive and value < 0:
                raise DatasetValidationError(
                    f"{source}:{line_number}: {value_name} must be "
                    f"non-negative for operation {operation_id} on "
                    f"machine {machine_id + 1}"
                )
            options[machine_id] = _number_value(value)

        operations.append(options)

    if position != len(tokens):
        raise DatasetValidationError(
            f"{source}:{line_number}: {label} contains {len(tokens) - position} "
            "unexpected trailing values"
        )
    return operations


def _parse_integers(line, label, source, line_number):
    try:
        return [int(token) for token in line.split()]
    except ValueError as exc:
        raise DatasetValidationError(
            f"{source}:{line_number}: {label} must contain integers"
        ) from exc


def _parse_numbers(line, label, source, line_number):
    try:
        return [float(token) for token in line.split()]
    except ValueError as exc:
        raise DatasetValidationError(
            f"{source}:{line_number}: {label} contains a non-numeric value"
        ) from exc


def _number_value(value):
    return int(value) if float(value).is_integer() else float(value)


def _reshape_matrix(values, machine_count, label):
    if any(value < 0 for value in values):
        raise DatasetValidationError(f"{label} contains a negative value")
    return [
        list(values[row * machine_count:(row + 1) * machine_count])
        for row in range(machine_count)
    ]


def _validate_transport_matrix(matrix, label):
    size = len(matrix)
    for row in range(size):
        if len(matrix[row]) != size:
            raise DatasetValidationError(f"{label} must be square")
        if matrix[row][row] != 0:
            raise DatasetValidationError(
                f"{label} diagonal must contain only zero"
            )
        for column in range(size):
            if matrix[row][column] != matrix[column][row]:
                raise DatasetValidationError(
                    f"{label} must be symmetric at "
                    f"({row}, {column})"
                )

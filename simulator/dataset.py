import json
import math
from dataclasses import dataclass
from pathlib import Path

from system.job import Job, Task


PROCESS_STAGE_DEFINITIONS = (
    (1, "冲压", "raw", "add", 0),
    (2, "焊装", "raw1", "add1", 1800),
    (3, "涂装", "raw2", "add2", 3600),
    (4, "总装", "raw3", "add3", 5400),
)


class DatasetValidationError(ValueError):
    """Raised when a multi-objective dataset is inconsistent or incomplete."""


@dataclass(frozen=True)
class MultiObjectiveDataset:
    raw_path: Path
    additional_path: Path
    delivery_cost_path: Path | None
    num_jobs: int
    num_machines: int
    metadata: int
    jobs: list
    transport_time: list
    transport_energy: list

    @property
    def num_operations(self):
        return sum(job.operation_count for job in self.jobs)


@dataclass(frozen=True)
class ProcessMaterialData:
    inventory: dict[int, dict[str, float]]
    job_consumption: dict[int, dict[str, float]]
    task_consumption: dict[int, dict[int, dict[str, float]]]


def infer_delivery_cost_path(additional_path):
    """Return the delivery-cost path associated with an add/addN file."""
    additional_path = Path(additional_path)
    if not additional_path.parent.name.startswith("add"):
        return None
    return (
        additional_path.parent.parent
        / "delivery_cost"
        / additional_path.name
    )


def infer_process_id(additional_path):
    """Return the process id represented by an add/addN directory."""
    additional_path = Path(additional_path)
    return next(
        (
            stage_id
            for stage_id, _, _, add_dir, _ in PROCESS_STAGE_DEFINITIONS
            if additional_path.parent.name == add_dir
        ),
        None,
    )


def infer_process_material_paths(additional_path):
    """Return material inventory/consumption paths for an add/addN file."""
    additional_path = Path(additional_path)
    root = additional_path.parent.parent
    process_id = infer_process_id(additional_path)
    if process_id is None:
        return None, None
    config_name = additional_path.with_suffix(".json").name
    process_dir = f"process_{process_id}"
    inventory_path = (
        root / "material_configs" / process_dir / config_name
    )
    consumption_path = (
        root / "material_consumption" / process_dir / config_name
    )
    return (
        inventory_path if inventory_path.is_file() else None,
        consumption_path if consumption_path.is_file() else None,
    )


def list_process_sources(dataset_root, raw_path):
    """Return the four process data sources for one scheduling instance."""
    root = Path(dataset_root)
    raw_path = Path(raw_path)
    processes = []
    machine_offset = 0
    for stage_id, name, raw_dir, add_dir, detection_start in (
        PROCESS_STAGE_DEFINITIONS
    ):
        stage_raw = (
            raw_path
            if stage_id == 1
            else root / raw_dir / raw_path.name
        )
        stage_add = (
            root / add_dir / raw_path.name
            if stage_id > 1
            else raw_path.parent.parent / "add" / raw_path.name
        )
        if not stage_raw.is_file() or not stage_add.is_file():
            continue
        try:
            header = stage_raw.read_text(
                encoding="utf-8"
            ).splitlines()[0].split()
            num_jobs = int(header[0])
            num_machines = int(header[1])
        except (OSError, IndexError, ValueError):
            continue
        delivery_path = infer_delivery_cost_path(stage_add)
        inventory_path, consumption_path = infer_process_material_paths(
            stage_add
        )
        processes.append(
            {
                "id": stage_id,
                "name": name,
                "raw_file": str(stage_raw.resolve()),
                "additional_file": str(stage_add.resolve()),
                "delivery_cost_file": (
                    str(delivery_path.resolve())
                    if delivery_path is not None
                    and delivery_path.is_file()
                    else None
                ),
                "num_jobs": num_jobs,
                "num_machines": num_machines,
                "material_inventory_file": (
                    str(inventory_path.resolve())
                    if inventory_path is not None
                    else None
                ),
                "material_consumption_file": (
                    str(consumption_path.resolve())
                    if consumption_path is not None
                    else None
                ),
                "machine_offset": machine_offset,
                "detection_start_t": detection_start,
            }
        )
        machine_offset += num_machines
    return processes


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
        delivery_cost_path = infer_delivery_cost_path(additional_path)
        if (
            delivery_cost_path is not None
            and not delivery_cost_path.is_file()
        ):
            delivery_cost_path = None
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
                "delivery_cost_file": (
                    str(delivery_cost_path.resolve())
                    if delivery_cost_path is not None
                    else None
                ),
                "is_default": raw_path.name == default_name,
                "processes": list_process_sources(root, raw_path),
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


def load_process_material_data(
    inventory_path,
    consumption_path,
    process_id,
    num_jobs,
    num_machines,
    operation_counts=None,
):
    """Load and validate one process's inventory and consumption data."""
    if inventory_path is None and consumption_path is None:
        return ProcessMaterialData({}, {}, {})
    if inventory_path is None or consumption_path is None:
        raise DatasetValidationError(
            "Material inventory and consumption files must both exist "
            f"for process {process_id}."
        )

    inventory_path = Path(inventory_path)
    consumption_path = Path(consumption_path)
    inventory_doc = _load_json_object(
        inventory_path,
        "material inventory",
    )
    consumption_doc = _load_json_object(
        consumption_path,
        "material consumption",
    )
    for path, document in (
        (inventory_path, inventory_doc),
        (consumption_path, consumption_doc),
    ):
        if int(document.get("process_id", -1)) != process_id:
            raise DatasetValidationError(
                f"{path}: process_id must be {process_id}"
            )

    inventory = {}
    for machine in _require_list(
        inventory_doc.get("machines"),
        f"{inventory_path}: machines",
    ):
        machine_id = _require_int(
            machine.get("machine_id"),
            f"{inventory_path}: machine_id",
        )
        if not 1 <= machine_id <= num_machines:
            raise DatasetValidationError(
                f"{inventory_path}: machine {machine_id} is outside "
                f"1..{num_machines}"
            )
        if machine_id in inventory:
            raise DatasetValidationError(
                f"{inventory_path}: duplicate machine {machine_id}"
            )
        inventory[machine_id] = _parse_material_items(
            machine.get("materials"),
            f"{inventory_path}: machine {machine_id}",
        )
    expected_machine_ids = set(range(1, num_machines + 1))
    if set(inventory) != expected_machine_ids:
        missing = sorted(expected_machine_ids - set(inventory))
        extra = sorted(set(inventory) - expected_machine_ids)
        raise DatasetValidationError(
            f"{inventory_path}: machine set mismatch; "
            f"missing={missing}, extra={extra}"
        )

    job_consumption = {}
    task_consumption = {}
    seen_job_ids = set()
    for job in _require_list(
        consumption_doc.get("jobs"),
        f"{consumption_path}: jobs",
    ):
        job_id = _require_int(
            job.get("job_id"),
            f"{consumption_path}: job_id",
        )
        if not 0 <= job_id < num_jobs:
            raise DatasetValidationError(
                f"{consumption_path}: job {job_id} is outside "
                f"0..{num_jobs - 1}"
            )
        if job_id in seen_job_ids:
            raise DatasetValidationError(
                f"{consumption_path}: duplicate job {job_id}"
            )
        seen_job_ids.add(job_id)

        if process_id == 1:
            job_consumption[job_id] = _parse_material_items(
                job.get("materials"),
                f"{consumption_path}: job {job_id}",
            )
            continue

        expected_operation_count = (
            int(operation_counts[job_id])
            if operation_counts is not None
            else None
        )
        stage_tasks = {}
        for task in _require_list(
            job.get("tasks"),
            f"{consumption_path}: job {job_id} tasks",
        ):
            operation_id = _require_int(
                task.get("stage_operation_id"),
                f"{consumption_path}: job {job_id} operation_id",
            )
            if operation_id < 0:
                raise DatasetValidationError(
                    f"{consumption_path}: job {job_id} has negative "
                    "stage_operation_id"
                )
            if operation_id in stage_tasks:
                raise DatasetValidationError(
                    f"{consumption_path}: job {job_id} repeats "
                    f"operation {operation_id}"
                )
            stage_tasks[operation_id] = _parse_material_items(
                task.get("materials"),
                (
                    f"{consumption_path}: job {job_id} "
                    f"operation {operation_id}"
                ),
            )
        if (
            expected_operation_count is not None
            and set(stage_tasks)
            != set(range(expected_operation_count))
        ):
            raise DatasetValidationError(
                f"{consumption_path}: job {job_id} task set does not "
                f"match {expected_operation_count} process operations"
            )
        task_consumption[job_id] = stage_tasks

    expected_job_ids = set(range(num_jobs))
    if seen_job_ids != expected_job_ids:
        missing = sorted(expected_job_ids - seen_job_ids)
        extra = sorted(seen_job_ids - expected_job_ids)
        raise DatasetValidationError(
            f"{consumption_path}: job set mismatch; "
            f"missing={missing}, extra={extra}"
        )

    used_materials = {
        material_id
        for materials in job_consumption.values()
        for material_id in materials
    }
    used_materials.update(
        material_id
        for tasks in task_consumption.values()
        for materials in tasks.values()
        for material_id in materials
    )
    for machine_id, materials in inventory.items():
        missing = sorted(used_materials - set(materials))
        if missing:
            raise DatasetValidationError(
                f"{inventory_path}: machine {machine_id} is missing "
                f"material quantities for {missing}"
            )

    return ProcessMaterialData(
        inventory=inventory,
        job_consumption=job_consumption,
        task_consumption=task_consumption,
    )


def load_multi_objective_dataset(
    raw_path,
    additional_path,
    delivery_cost_path=None,
):
    raw_path = Path(raw_path)
    additional_path = Path(additional_path)
    if delivery_cost_path is None:
        delivery_cost_path = infer_delivery_cost_path(additional_path)
    else:
        delivery_cost_path = Path(delivery_cost_path)
    if (
        delivery_cost_path is not None
        and not delivery_cost_path.is_file()
    ):
        raise DatasetValidationError(
            f"Delivery-cost dataset not found: {delivery_cost_path}"
        )
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

    if len(additional_lines) < num_jobs:
        raise DatasetValidationError(
            f"{additional_path}: missing processing energy rows"
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

    if delivery_cost_path is not None:
        feature_lines = [
            line
            for line in _read_nonempty_lines(delivery_cost_path)
            if not line.startswith("#")
        ]
        if len(feature_lines) != num_jobs:
            raise DatasetValidationError(
                f"{delivery_cost_path}: expected {num_jobs} delivery rows, "
                f"found {len(feature_lines)}"
            )
        feature_source = delivery_cost_path
        matrix_start = num_jobs
    else:
        feature_start = num_jobs
        if len(additional_lines) < feature_start + num_jobs:
            raise DatasetValidationError(
                f"{additional_path}: missing embedded job feature rows"
            )
        feature_lines = additional_lines[
            feature_start:feature_start + num_jobs
        ]
        feature_source = additional_path
        matrix_start = feature_start + num_jobs

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

        feature_line_number = job_id + 1
        features = _parse_numbers(
            feature_lines[job_id],
            f"job {job_id} features",
            feature_source,
            feature_line_number,
        )
        if len(features) != 5:
            raise DatasetValidationError(
                f"{feature_source}:{feature_line_number}: job {job_id} "
                "must contain exactly 5 features: "
                "weight ready_time due_time earliness_penalty "
                "tardiness_penalty"
            )
        weight, ready_time, due_time, early_penalty, tardy_penalty = features
        if weight <= 0:
            raise DatasetValidationError(
                f"{feature_source}:{feature_line_number}: "
                "job weight must be positive"
            )
        if ready_time < 0 or early_penalty < 0 or tardy_penalty < 0:
            raise DatasetValidationError(
                f"{feature_source}:{feature_line_number}: "
                "job ready time and penalties must be non-negative"
            )
        if due_time < ready_time:
            raise DatasetValidationError(
                f"{feature_source}:{feature_line_number}: "
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
        delivery_cost_path=delivery_cost_path,
        num_jobs=num_jobs,
        num_machines=num_machines,
        metadata=metadata,
        jobs=jobs,
        transport_time=transport_time,
        transport_energy=transport_energy,
    )


def load_model_additional_text(
    raw_path,
    additional_path,
    delivery_cost_path=None,
):
    """Merge split delivery rows into the model-compatible add layout."""
    raw_path = Path(raw_path)
    additional_path = Path(additional_path)
    if delivery_cost_path is None:
        delivery_cost_path = infer_delivery_cost_path(additional_path)
    elif delivery_cost_path is not None:
        delivery_cost_path = Path(delivery_cost_path)
    if (
        delivery_cost_path is None
        or not Path(delivery_cost_path).is_file()
    ):
        return additional_path.read_text(encoding="utf-8")

    raw_lines = _read_nonempty_lines(raw_path)
    additional_lines = _read_nonempty_lines(additional_path)
    delivery_lines = [
        line
        for line in _read_nonempty_lines(delivery_cost_path)
        if not line.startswith("#")
    ]
    num_jobs = int(raw_lines[0].split()[0])
    if len(additional_lines) < num_jobs:
        raise DatasetValidationError(
            f"{additional_path}: missing processing energy rows"
        )
    if len(delivery_lines) != num_jobs:
        raise DatasetValidationError(
            f"{delivery_cost_path}: expected {num_jobs} delivery rows, "
            f"found {len(delivery_lines)}"
        )
    merged_lines = (
        additional_lines[:num_jobs]
        + delivery_lines
        + additional_lines[num_jobs:]
    )
    return "\n".join(merged_lines) + "\n"


def _load_json_object(path, label):
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise DatasetValidationError(
            f"{label} file not found: {path}"
        ) from exc
    except (OSError, json.JSONDecodeError) as exc:
        raise DatasetValidationError(
            f"{path}: invalid {label} JSON"
        ) from exc
    if not isinstance(document, dict):
        raise DatasetValidationError(
            f"{path}: {label} root must be an object"
        )
    return document


def _require_list(value, label):
    if not isinstance(value, list):
        raise DatasetValidationError(f"{label} must be a list")
    return value


def _require_int(value, label):
    if isinstance(value, bool):
        raise DatasetValidationError(f"{label} must be an integer")
    try:
        number = int(value)
    except (TypeError, ValueError) as exc:
        raise DatasetValidationError(
            f"{label} must be an integer"
        ) from exc
    if float(value) != number:
        raise DatasetValidationError(f"{label} must be an integer")
    return number


def _parse_material_items(value, label):
    materials = {}
    for item in _require_list(value, label):
        if not isinstance(item, dict):
            raise DatasetValidationError(
                f"{label}: each material entry must be an object"
            )
        material_id = item.get("material_id")
        if not isinstance(material_id, str) or not material_id.strip():
            raise DatasetValidationError(
                f"{label}: material_id must be a non-empty string"
            )
        material_id = material_id.strip()
        quantity = item.get("quantity")
        if isinstance(quantity, bool):
            raise DatasetValidationError(
                f"{label}: quantity for {material_id} must be numeric"
            )
        try:
            quantity = float(quantity)
        except (TypeError, ValueError) as exc:
            raise DatasetValidationError(
                f"{label}: quantity for {material_id} must be numeric"
            ) from exc
        if not math.isfinite(quantity) or quantity < 0:
            raise DatasetValidationError(
                f"{label}: quantity for {material_id} must be finite "
                "and non-negative"
            )
        if material_id in materials:
            raise DatasetValidationError(
                f"{label}: duplicate material {material_id}"
            )
        materials[material_id] = _number_value(quantity)
    return materials


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

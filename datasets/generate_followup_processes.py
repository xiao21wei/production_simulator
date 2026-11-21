#!/usr/bin/env python3
"""Generate welding, painting and assembly datasets from stamping data.

The existing ``raw/`` directory represents the first automotive process
(stamping). This script generates all remaining data from those raw files:

* ``add``: stamping energy and transport data
* ``raw1/add1``: welding
* ``raw2/add2``: painting
* ``raw3/add3``: assembly
* ``delivery_cost``: one four-process delivery record per instance

Every source pair keeps its filename so jobs can be joined across processes.
Generation is deterministic and does not modify the source ``raw`` data.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import math
import random
from dataclasses import dataclass
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent
SOURCE_RAW_DIR = ROOT / "raw"
SOURCE_ADD_DIR = ROOT / "add"
MANIFEST_PATH = ROOT / "followup_processes_manifest.json"
DELIVERY_ROOT = ROOT / "delivery_cost"
PROCESS_GENERATION_CONFIG_ROOT = ROOT / "process_generation_configs"
MATERIAL_CONFIG_ROOT = ROOT / "material_configs"
MATERIAL_CONSUMPTION_ROOT = ROOT / "material_consumption"
MATERIAL_MASTER_PATH = ROOT / "material_master.csv"
DELIVERY_HEADER = (
    "# priority ready_time due_time earliness_cost tardiness_cost"
)
INTERSTAGE_TRANSPORT_TIME = (2, 4, 3)
DUE_BUFFER_FACTOR = 1.50
MATERIAL_RESERVE_FACTOR = 1.20


@dataclass(frozen=True)
class TaskTemplate:
    task_code: str
    operation_type: str
    description: str
    base_time: int
    base_energy: int


@dataclass(frozen=True)
class ProcessSpec:
    directory: str
    process_id: int
    process_name: str
    machine_min: int
    machine_max: int
    machine_s_factor: float
    machine_j_factor: float
    option_min: int
    option_max: int
    time_ratio_min: float
    time_ratio_default: float
    time_ratio_max: float
    energy_ratio_min: float
    energy_ratio_default: float
    energy_ratio_max: float
    task_time_min: int
    task_energy_min: int
    task_time_max: int
    task_energy_max: int
    transport_time_min: int
    transport_time_max: int
    transport_energy_min: int
    transport_energy_max: int
    tasks: tuple[TaskTemplate, ...]


PROCESS_SPECS = (
    ProcessSpec(
        directory="1",
        process_id=2,
        process_name="焊装",
        machine_min=5,
        machine_max=8,
        machine_s_factor=0.60,
        machine_j_factor=0.04,
        option_min=1,
        option_max=3,
        time_ratio_min=0.55,
        time_ratio_default=0.65,
        time_ratio_max=0.80,
        energy_ratio_min=0.55,
        energy_ratio_default=0.70,
        energy_ratio_max=0.85,
        task_time_min=4,
        task_energy_min=2,
        task_time_max=25,
        task_energy_max=24,
        transport_time_min=1,
        transport_time_max=3,
        transport_energy_min=2,
        transport_energy_max=6,
        tasks=(
            TaskTemplate("W0", "PANEL_KITTING", "冲压件齐套、定位和夹紧", 4, 2),
            TaskTemplate("W1", "BODY_SPOT_WELD", "车身主结构电阻点焊", 18, 16),
            TaskTemplate("W2", "MIG_LASER_BRAZING", "局部填充焊或激光钎焊", 12, 15),
            TaskTemplate("W3", "STRUCTURAL_ADHESIVE", "结构胶和折边胶", 10, 12),
            TaskTemplate("W4", "MECHANICAL_JOIN_AND_SEAL", "铆接、螺柱、螺栓和密封", 19, 20),
            TaskTemplate("W5", "BODY_INSPECTION", "连接质量和尺寸检查", 4, 2),
        ),
    ),
    ProcessSpec(
        directory="2",
        process_id=3,
        process_name="涂装",
        machine_min=4,
        machine_max=7,
        machine_s_factor=0.50,
        machine_j_factor=0.03,
        option_min=1,
        option_max=2,
        time_ratio_min=0.40,
        time_ratio_default=0.50,
        time_ratio_max=0.65,
        energy_ratio_min=0.45,
        energy_ratio_default=0.58,
        energy_ratio_max=0.75,
        task_time_min=7,
        task_energy_min=5,
        task_time_max=25,
        task_energy_max=25,
        transport_time_min=2,
        transport_time_max=5,
        transport_energy_min=3,
        transport_energy_max=8,
        tasks=(
            TaskTemplate("P0", "PRETREAT_ECOAT", "前处理和阴极电泳", 10, 10),
            TaskTemplate("P1", "SEAL_ANTI_CHIP_CAVITY", "密封、抗石击和空腔防腐", 12, 14),
            TaskTemplate("P2", "PRIMER", "底漆及固化剂", 9, 10),
            TaskTemplate("P3", "BASECOAT_COMBO", "车身和车顶面漆", 10, 13),
            TaskTemplate("P4", "CLEARCOAT", "清漆及固化剂", 8, 10),
            TaskTemplate("P5", "BAKE_INSPECTION", "烘烤和检查", 7, 7),
        ),
    ),
    ProcessSpec(
        directory="3",
        process_id=4,
        process_name="总装",
        machine_min=6,
        machine_max=10,
        machine_s_factor=0.75,
        machine_j_factor=0.05,
        option_min=1,
        option_max=3,
        time_ratio_min=0.60,
        time_ratio_default=0.78,
        time_ratio_max=0.90,
        energy_ratio_min=0.45,
        energy_ratio_default=0.59,
        energy_ratio_max=0.75,
        task_time_min=6,
        task_energy_min=4,
        task_time_max=32,
        task_energy_max=24,
        transport_time_min=1,
        transport_time_max=3,
        transport_energy_min=1,
        transport_energy_max=5,
        tasks=(
            TaskTemplate("A0", "DOOR_AND_HARNESS", "车门、线束和电子模块", 12, 8),
            TaskTemplate("A1", "INTERIOR_AND_COCKPIT", "内饰、座舱和空调", 10, 7),
            TaskTemplate("A2", "POWERTRAIN_CHASSIS_MARRIAGE", "动力总成和底盘合装", 20, 16),
            TaskTemplate("A3", "ENERGY_MODULE_INSTALLATION", "电池或燃油模块", 8, 8),
            TaskTemplate("A4", "GLASS_AND_SEAT", "玻璃和座椅", 10, 8),
            TaskTemplate("A5", "WHEEL_EXTERIOR_AND_DOOR", "车轮、外饰和车门", 10, 8),
            TaskTemplate("A6", "FLUID_FILL", "整车油液加注", 8, 5),
            TaskTemplate("A7", "FINAL_INSPECTION", "电检和功能检查", 6, 4),
        ),
    ),
)


MATERIALS = {
    "M1_STEEL_CR_LOW_CARBON": ("冷轧低碳钢板", "piece", "冲压板料"),
    "M1_STEEL_CR_HIGH_STRENGTH": ("高强度冷轧钢板", "piece", "冲压板料"),
    "M1_STEEL_HOT_ROLLED": ("热轧钢板", "piece", "冲压板料"),
    "M1_ALUMINUM": ("铝合金板", "piece", "冲压板料"),
    "M2_WELD_WIRE": ("焊接填充丝", "kg", "焊装材料"),
    "M2_STRUCTURAL_ADHESIVE": ("结构胶", "kg", "焊装材料"),
    "M2_BODY_SEALANT": ("车身密封胶", "kg", "焊装材料"),
    "M2_RIVET": ("自冲铆钉", "piece", "焊装材料"),
    "M2_STUD": ("焊接螺柱", "piece", "焊装材料"),
    "M2_BOLT_NUT": ("螺栓和螺母", "set", "焊装材料"),
    "M3_ECOAT_REPLENISH": ("电泳漆补加材料", "L", "涂装材料"),
    "M3_PVC_SEALER": ("PVC 密封胶", "kg", "涂装材料"),
    "M3_ANTI_CHIP_COATING": ("UBC 抗石击涂料", "kg", "涂装材料"),
    "M3_CAVITY_WAX": ("空腔蜡", "kg", "涂装材料"),
    "M3_PRIMER": ("中涂/底漆", "L", "涂装材料"),
    "M3_PRIMER_HARDENER": ("底漆固化剂", "L", "涂装材料"),
    "M3_BASECOAT_SKY_GRAY": ("天空灰面漆", "L", "涂装材料"),
    "M3_BASECOAT_CRYSTAL_WHITE": ("水晶珍珠白面漆", "L", "涂装材料"),
    "M3_BASECOAT_GLOSS_BLACK": ("闪耀黑面漆", "L", "涂装材料"),
    "M3_BASECOAT_FLYING_BLUE": ("飞行蓝面漆", "L", "涂装材料"),
    "M3_CLEARCOAT": ("清漆", "L", "涂装材料"),
    "M3_CLEARCOAT_HARDENER": ("清漆固化剂", "L", "涂装材料"),
    "M4_DOOR_MODULE": ("车门模块", "set", "总装材料"),
    "M4_WIRING_HARNESS": ("整车线束", "set", "总装材料"),
    "M4_ELECTRONIC_MODULE": ("电子控制模块", "set", "总装材料"),
    "M4_COCKPIT_INTERIOR_KIT": ("座舱内饰模块", "set", "总装材料"),
    "M4_HVAC_MODULE": ("空调热管理模块", "set", "总装材料"),
    "M4_ICE_ENGINE": ("燃油发动机总成", "set", "总装材料"),
    "M4_E_DRIVE": ("电驱总成", "set", "总装材料"),
    "M4_TRANSMISSION": ("变速器或减速器", "set", "总装材料"),
    "M4_CHASSIS_MODULE": ("底盘模块", "set", "总装材料"),
    "M4_BATTERY_PACK": ("动力电池包", "set", "总装材料"),
    "M4_FUEL_SYSTEM": ("燃油系统模块", "set", "总装材料"),
    "M4_GLASS_SET": ("玻璃总成", "set", "总装材料"),
    "M4_SEAT_SET": ("座椅和安全带总成", "set", "总装材料"),
    "M4_WHEEL_TIRE_SET": ("车轮和轮胎总成", "set", "总装材料"),
    "M4_EXTERIOR_KIT": ("外饰和车门安装件", "set", "总装材料"),
    "M4_ENGINE_OIL": ("发动机机油", "L", "总装材料"),
    "M4_TRANSMISSION_FLUID": ("变速器油", "L", "总装材料"),
    "M4_COOLANT": ("冷却液", "L", "总装材料"),
    "M4_BRAKE_FLUID": ("制动液", "L", "总装材料"),
    "M4_REFRIGERANT": ("空调冷媒", "kg", "总装材料"),
    "M4_WASHER_FLUID": ("风挡玻璃水", "L", "总装材料"),
}

BODY_COLORS = (
    "M3_BASECOAT_SKY_GRAY",
    "M3_BASECOAT_CRYSTAL_WHITE",
    "M3_BASECOAT_GLOSS_BLACK",
    "M3_BASECOAT_FLYING_BLUE",
)

STAGE_MATERIALS = {
    1: (
        "M1_STEEL_CR_LOW_CARBON",
        "M1_STEEL_CR_HIGH_STRENGTH",
        "M1_STEEL_HOT_ROLLED",
        "M1_ALUMINUM",
    ),
    2: (
        "M2_WELD_WIRE",
        "M2_STRUCTURAL_ADHESIVE",
        "M2_BODY_SEALANT",
        "M2_RIVET",
        "M2_STUD",
        "M2_BOLT_NUT",
    ),
    3: (
        "M3_ECOAT_REPLENISH",
        "M3_PVC_SEALER",
        "M3_ANTI_CHIP_COATING",
        "M3_CAVITY_WAX",
        "M3_PRIMER",
        "M3_PRIMER_HARDENER",
        *BODY_COLORS,
        "M3_CLEARCOAT",
        "M3_CLEARCOAT_HARDENER",
    ),
    4: tuple(
        material_id
        for material_id in MATERIALS
        if material_id.startswith("M4_")
    ),
}


@dataclass(frozen=True)
class JobVariant:
    powertrain_type: str
    drive_type: str
    body_color: str
    roof_color: str
    two_tone: bool
    stamping_material: str


def read_lines(path: Path) -> list[str]:
    return [
        line.strip()
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def parse_options(line: str, num_machines: int, label: str) -> list[list[tuple[int, int]]]:
    values = [int(value) for value in line.split()]
    if not values:
        raise ValueError(f"{label}: empty option row")
    operation_count = values[0]
    cursor = 1
    operations: list[list[tuple[int, int]]] = []
    for operation_id in range(operation_count):
        if cursor >= len(values):
            raise ValueError(f"{label}: operation {operation_id} is truncated")
        option_count = values[cursor]
        cursor += 1
        if option_count <= 0:
            raise ValueError(f"{label}: operation {operation_id} has no options")
        options: list[tuple[int, int]] = []
        for _ in range(option_count):
            if cursor + 1 >= len(values):
                raise ValueError(f"{label}: option row is truncated")
            machine_id = values[cursor]
            value = values[cursor + 1]
            cursor += 2
            if not 1 <= machine_id <= num_machines:
                raise ValueError(
                    f"{label}: machine {machine_id} outside 1..{num_machines}"
                )
            if value < 0:
                raise ValueError(f"{label}: negative option value")
            options.append((machine_id, value))
        operations.append(options)
    if cursor != len(values):
        raise ValueError(f"{label}: trailing values")
    return operations


def parse_source(
    raw_path: Path,
    add_path: Path,
) -> dict[str, Any]:
    raw_lines = read_lines(raw_path)
    add_lines = read_lines(add_path)
    header = [int(value) for value in raw_lines[0].split()]
    if len(header) < 3:
        raise ValueError(f"{raw_path}: header requires at least 3 values")
    num_jobs, num_machines, metadata = header[:3]
    if len(raw_lines) != num_jobs + 1:
        raise ValueError(f"{raw_path}: unexpected job row count")
    if len(add_lines) < num_jobs:
        raise ValueError(f"{add_path}: missing energy rows")

    raw_jobs = [
        parse_options(line, num_machines, f"{raw_path}:{index + 2}")
        for index, line in enumerate(raw_lines[1:])
    ]
    energy_jobs = [
        parse_options(line, num_machines, f"{add_path}:{index + 1}")
        for index, line in enumerate(add_lines[:num_jobs])
    ]
    matrix_values = [
        int(value)
        for line in add_lines[num_jobs:]
        for value in line.split()
    ]
    matrix_size = num_machines * num_machines
    if len(matrix_values) != matrix_size * 2:
        raise ValueError(f"{add_path}: invalid transport matrix size")
    transport_time = [
        matrix_values[row * num_machines:(row + 1) * num_machines]
        for row in range(num_machines)
    ]
    transport_energy = [
        matrix_values[
            matrix_size + row * num_machines:
            matrix_size + (row + 1) * num_machines
        ]
        for row in range(num_machines)
    ]
    for job_id, (raw_job, energy_job) in enumerate(
        zip(raw_jobs, energy_jobs)
    ):
        if len(raw_job) != len(energy_job):
            raise ValueError(f"job {job_id}: operation counts differ")
        for operation_id, (time_options, energy_options) in enumerate(
            zip(raw_job, energy_job)
        ):
            if {item[0] for item in time_options} != {
                item[0] for item in energy_options
            }:
                raise ValueError(
                    f"job {job_id} operation {operation_id}: "
                    "machine sets differ"
                )
            if any(value <= 0 for _, value in time_options):
                raise ValueError(
                    f"job {job_id} operation {operation_id}: "
                    "processing time must be positive"
                )
    return {
        "num_jobs": num_jobs,
        "num_machines": num_machines,
        "metadata": metadata,
        "raw_jobs": raw_jobs,
        "energy_jobs": energy_jobs,
        "transport_time": transport_time,
        "transport_energy": transport_energy,
    }


def parse_raw_for_add(raw_path: Path) -> dict[str, Any]:
    raw_lines = read_lines(raw_path)
    header = [int(value) for value in raw_lines[0].split()]
    num_jobs, num_machines, metadata = header[:3]
    raw_jobs = [
        parse_options(line, num_machines, f"{raw_path}:{index + 2}")
        for index, line in enumerate(raw_lines[1:])
    ]
    return {
        "num_jobs": num_jobs,
        "num_machines": num_machines,
        "metadata": metadata,
        "raw_jobs": raw_jobs,
    }


def clamp(value: int, minimum: int, maximum: int) -> int:
    return max(minimum, min(maximum, value))


MACHINE_FACTOR_RANGES = {
    2: (0.85, 1.20, 0.90, 1.15),
    3: (0.90, 1.15, 0.92, 1.12),
    4: (0.85, 1.20, 0.90, 1.15),
}


def stable_seed(*parts: Any) -> int:
    value = "|".join(str(part) for part in parts)
    return int(hashlib.sha256(value.encode("utf-8")).hexdigest()[:16], 16)


def job_variants(source_name: str, num_jobs: int) -> list[JobVariant]:
    variants = []
    stamping_materials = STAGE_MATERIALS[1]
    for job_id in range(num_jobs):
        rng = random.Random(
            stable_seed(source_name, job_id, "job-variant-v1")
        )
        powertrain_type = rng.choices(
            ("ICE", "HEV", "BEV"),
            weights=(60, 25, 15),
            k=1,
        )[0]
        body_color = rng.choice(BODY_COLORS)
        two_tone = rng.random() < 0.20
        roof_color = (
            "M3_BASECOAT_GLOSS_BLACK"
            if two_tone
            else body_color
        )
        variants.append(
            JobVariant(
                powertrain_type=powertrain_type,
                drive_type=(
                    "AWD"
                    if powertrain_type == "BEV" or rng.random() < 0.30
                    else "2WD"
                ),
                body_color=body_color,
                roof_color=roof_color,
                two_tone=two_tone,
                stamping_material=stamping_materials[
                    job_id % len(stamping_materials)
                ],
            )
        )
    return variants


def stage_machine_count(spec: ProcessSpec, source: dict[str, Any]) -> int:
    value = math.ceil(
        spec.machine_s_factor * source["num_machines"]
        + spec.machine_j_factor * source["num_jobs"]
    )
    return clamp(value, spec.machine_min, spec.machine_max)


def allocate_integer_values(
    total: int,
    weights: list[float],
    minimum: int,
    maximum: int,
) -> list[int]:
    if not weights:
        return []
    count = len(weights)
    if total < minimum * count or total > maximum * count:
        raise ValueError(
            f"cannot allocate total={total} across {count} tasks "
            f"within {minimum}..{maximum}"
        )
    weight_sum = sum(weights)
    raw_values = [
        total * weight / weight_sum for weight in weights
    ]
    values = [
        clamp(math.floor(value), minimum, maximum)
        for value in raw_values
    ]
    while sum(values) < total:
        index = max(
            range(count),
            key=lambda item: (
                raw_values[item] - values[item],
                weights[item],
                -item,
            ),
        )
        if values[index] >= maximum:
            candidates = [
                item for item in range(count) if values[item] < maximum
            ]
            if not candidates:
                raise ValueError("Task allocation exceeded maximum.")
            index = max(candidates, key=lambda item: weights[item])
        values[index] += 1
    while sum(values) > total:
        index = min(
            range(count),
            key=lambda item: (
                raw_values[item] - values[item],
                weights[item],
                item,
            ),
        )
        if values[index] <= minimum:
            candidates = [
                item for item in range(count) if values[item] > minimum
            ]
            if not candidates:
                raise ValueError("Task allocation fell below minimum.")
            index = min(candidates, key=lambda item: weights[item])
        values[index] -= 1
    return values


def mean_option_value(
    options: list[tuple[int, int]],
) -> float:
    if not options:
        raise ValueError("Task has no machine options.")
    return sum(value for _, value in options) / len(options)


def stamping_baseline(
    source: dict[str, Any],
    job_id: int,
) -> tuple[float, float]:
    time_value = sum(
        mean_option_value(options)
        for options in source["raw_jobs"][job_id]
    )
    energy_value = sum(
        mean_option_value(options)
        for options in source["energy_jobs"][job_id]
    )
    return time_value, energy_value


def product_factor(
    process_id: int,
    variant: JobVariant,
) -> tuple[float, float]:
    if process_id == 3 and variant.two_tone:
        return 1.05, 1.03
    if process_id == 4 and variant.powertrain_type == "BEV":
        return 1.05, 1.04
    if process_id == 4 and variant.powertrain_type == "HEV":
        return 1.03, 1.02
    return 1.0, 1.0


def task_material_requirements(
    process_id: int,
    task_index: int,
    variant: JobVariant,
) -> list[dict[str, Any]]:
    requirements: list[tuple[str, float]] = []
    if process_id == 2:
        requirements = {
            2: [("M2_WELD_WIRE", 0.8)],
            3: [("M2_STRUCTURAL_ADHESIVE", 1.2)],
            4: [
                ("M2_RIVET", 40.0),
                ("M2_STUD", 16.0),
                ("M2_BOLT_NUT", 8.0),
                ("M2_BODY_SEALANT", 0.6),
            ],
        }.get(task_index, [])
    elif process_id == 3:
        requirements = {
            0: [("M3_ECOAT_REPLENISH", 2.5)],
            1: [
                ("M3_PVC_SEALER", 1.0),
                ("M3_ANTI_CHIP_COATING", 1.5),
                ("M3_CAVITY_WAX", 0.5),
            ],
            2: [
                ("M3_PRIMER", 1.8),
                ("M3_PRIMER_HARDENER", 0.2),
            ],
            3: [
                (variant.body_color, 2.5),
                *(
                    [(variant.roof_color, 0.6)]
                    if variant.two_tone
                    else []
                ),
            ],
            4: [
                ("M3_CLEARCOAT", 1.8),
                ("M3_CLEARCOAT_HARDENER", 0.3),
            ],
        }.get(task_index, [])
    elif process_id == 4:
        requirements = {
            0: [
                ("M4_DOOR_MODULE", 1.0),
                ("M4_WIRING_HARNESS", 1.0),
                ("M4_ELECTRONIC_MODULE", 1.0),
            ],
            1: [
                ("M4_COCKPIT_INTERIOR_KIT", 1.0),
                ("M4_HVAC_MODULE", 1.0),
            ],
            2: [
                *(
                    [
                        ("M4_ICE_ENGINE", 1.0),
                        ("M4_TRANSMISSION", 1.0),
                    ]
                    if variant.powertrain_type in {"ICE", "HEV"}
                    else [
                        ("M4_E_DRIVE", 1.0),
                        ("M4_TRANSMISSION", 1.0),
                    ]
                ),
                ("M4_CHASSIS_MODULE", 1.0),
            ],
            3: (
                [
                    ("M4_BATTERY_PACK", 1.0),
                    ("M4_FUEL_SYSTEM", 1.0),
                ]
                if variant.powertrain_type == "HEV"
                else [("M4_BATTERY_PACK", 1.0)]
                if variant.powertrain_type == "BEV"
                else [("M4_FUEL_SYSTEM", 1.0)]
            ),
            4: [
                ("M4_GLASS_SET", 1.0),
                ("M4_SEAT_SET", 1.0),
            ],
            5: [
                ("M4_WHEEL_TIRE_SET", 1.0),
                ("M4_EXTERIOR_KIT", 1.0),
            ],
            6: [
                *(
                    [("M4_ENGINE_OIL", 4.5)]
                    if variant.powertrain_type in {"ICE", "HEV"}
                    else []
                ),
                (
                    "M4_TRANSMISSION_FLUID",
                    6.0 if variant.powertrain_type == "ICE" else 1.5,
                ),
                ("M4_COOLANT", 6.0),
                ("M4_BRAKE_FLUID", 1.0),
                ("M4_REFRIGERANT", 0.6),
                ("M4_WASHER_FLUID", 2.0),
            ],
        }.get(task_index, [])
    return [
        {
            "material_id": material_id,
            "quantity": float(quantity),
            "unit": MATERIALS[material_id][1],
        }
        for material_id, quantity in requirements
    ]


def format_options(operations: list[list[tuple[int, int]]]) -> str:
    values = [str(len(operations))]
    for options in operations:
        values.append(str(len(options)))
        for machine_id, value in options:
            values.extend((str(machine_id), str(value)))
    return " ".join(values)


def build_transport_matrices(
    num_machines: int,
    rng: random.Random,
    time_range=(1, 3),
    energy_range=(1, 4),
):
    transport_time = [[0] * num_machines for _ in range(num_machines)]
    transport_energy = [[0] * num_machines for _ in range(num_machines)]
    for first in range(num_machines):
        for second in range(first + 1, num_machines):
            duration = rng.randint(*time_range)
            energy = rng.randint(*energy_range)
            transport_time[first][second] = duration
            transport_time[second][first] = duration
            transport_energy[first][second] = energy
            transport_energy[second][first] = energy
    return transport_time, transport_energy


def process_filename(source_name: str) -> str:
    return Path(source_name).with_suffix(".json").name


def render_stage1_file(raw_path: Path) -> dict[str, Any]:
    """Generate stamping energy, transport and traceable Job metadata."""
    source = parse_raw_for_add(raw_path)
    rng = random.Random(stable_seed(raw_path.name, "stage1-add", "v2"))
    variants = job_variants(raw_path.name, source["num_jobs"])
    energy_jobs: list[list[list[tuple[int, int]]]] = []
    jobs = []

    for job_id, raw_job in enumerate(source["raw_jobs"]):
        variant = variants[job_id]
        energy_operations: list[list[tuple[int, int]]] = []
        task_configs = []
        for task_index, options in enumerate(raw_job):
            energy_options = [
                (machine_id, rng.randint(4, 15))
                for machine_id, _ in options
            ]
            energy_by_machine = dict(energy_options)
            energy_operations.append(energy_options)
            machine_options = [
                {
                    "machine_id": machine_id,
                    "processing_time": processing_time,
                    "processing_energy": energy_by_machine[machine_id],
                }
                for machine_id, processing_time in options
            ]
            materials = (
                [
                    {
                        "material_id": variant.stamping_material,
                        "quantity": 1.0,
                        "unit": MATERIALS[variant.stamping_material][1],
                    }
                ]
                if task_index == 0
                else []
            )
            task_configs.append(
                {
                    "stage_operation_id": task_index,
                    "task_code": f"OP{task_index:02d}",
                    "operation_type": f"STAMPING_OP_{task_index}",
                    "description": (
                        "冲压领料与首道成形"
                        if task_index == 0
                        else f"冲压后续工序 {task_index}"
                    ),
                    "base_processing_time": round(
                        sum(value for _, value in options) / len(options),
                        4,
                    ),
                    "base_processing_energy": round(
                        sum(value for _, value in energy_options)
                        / len(energy_options),
                        4,
                    ),
                    "machine_options": machine_options,
                    "materials": materials,
                }
            )
        energy_jobs.append(energy_operations)
        jobs.append(
            {
                "job_id": job_id,
                "variant": {
                    "powertrain_type": variant.powertrain_type,
                    "drive_type": variant.drive_type,
                    "body_color": variant.body_color,
                    "roof_color": variant.roof_color,
                    "two_tone": variant.two_tone,
                    "stamping_material": variant.stamping_material,
                    "synthetic": True,
                },
                "target_processing_time": round(
                    sum(task["base_processing_time"] for task in task_configs),
                    4,
                ),
                "target_processing_energy": round(
                    sum(
                        task["base_processing_energy"]
                        for task in task_configs
                    ),
                    4,
                ),
                "raw_tasks": raw_job,
                "energy_tasks": energy_operations,
                "tasks": task_configs,
            }
        )

    transport_time, transport_energy = build_transport_matrices(
        source["num_machines"],
        rng,
    )
    generated_source = {
        **source,
        "energy_jobs": energy_jobs,
        "transport_time": transport_time,
        "transport_energy": transport_energy,
    }
    lines = [format_options(job) for job in energy_jobs]
    lines.extend(
        " ".join(str(value) for value in row)
        for matrix in (transport_time, transport_energy)
        for row in matrix
    )
    all_times = [
        task["base_processing_time"]
        for job in jobs
        for task in job["tasks"]
    ]
    all_energies = [
        task["base_processing_energy"]
        for job in jobs
        for task in job["tasks"]
    ]
    operation_counts = [len(job["raw_tasks"]) for job in jobs]
    metadata = {
        "process_id": 1,
        "process_name": "冲压",
        "num_jobs": source["num_jobs"],
        "source_num_machines": source["num_machines"],
        "num_machines": source["num_machines"],
        "num_operations": sum(operation_counts),
        "min_operations_per_job": min(operation_counts),
        "max_operations_per_job": max(operation_counts),
        "min_processing_time": min(all_times),
        "max_processing_time": max(all_times),
        "min_processing_energy": min(all_energies),
        "max_processing_energy": max(all_energies),
    }
    return {
        "raw_text": raw_path.read_text(encoding="utf-8"),
        "add_text": "\n".join(lines) + "\n",
        "metadata": metadata,
        "jobs": jobs,
        "source": generated_source,
        "transport_time": transport_time,
        "transport_energy": transport_energy,
    }


def generate_transport(
    source: dict[str, Any],
    target_machines: int,
    spec: ProcessSpec,
    rng: random.Random,
) -> tuple[list[list[int]], list[list[int]]]:
    return build_transport_matrices(
        target_machines,
        rng,
        (spec.transport_time_min, spec.transport_time_max),
        (spec.transport_energy_min, spec.transport_energy_max),
    )


def bounded_int(
    value: float,
    minimum: int,
    maximum: int,
) -> int:
    return max(minimum, min(maximum, int(round(value))))


def generate_process_job(
    source: dict[str, Any],
    spec: ProcessSpec,
    job_id: int,
    variant: JobVariant,
    target_machines: int,
    seed_key: str,
) -> dict[str, Any]:
    rng = random.Random(
        stable_seed(seed_key, spec.process_id, job_id, "process-job-v2")
    )
    stamping_time, stamping_energy = stamping_baseline(source, job_id)
    time_product_factor, energy_product_factor = product_factor(
        spec.process_id,
        variant,
    )
    time_ratio = max(
        spec.time_ratio_min,
        min(
            spec.time_ratio_max,
            spec.time_ratio_default + rng.uniform(-0.03, 0.03),
        ),
    )
    energy_ratio = max(
        spec.energy_ratio_min,
        min(
            spec.energy_ratio_max,
            spec.energy_ratio_default + rng.uniform(-0.03, 0.03),
        ),
    )
    task_count = len(spec.tasks)
    target_time = bounded_int(
        stamping_time
        * time_ratio
        * time_product_factor
        * rng.uniform(0.95, 1.05),
        spec.task_time_min * task_count,
        spec.task_time_max * task_count,
    )
    target_energy = bounded_int(
        stamping_energy
        * energy_ratio
        * energy_product_factor
        * rng.uniform(0.95, 1.05),
        spec.task_energy_min * task_count,
        spec.task_energy_max * task_count,
    )
    task_times = allocate_integer_values(
        target_time,
        [task.base_time for task in spec.tasks],
        spec.task_time_min,
        spec.task_time_max,
    )
    task_energies = allocate_integer_values(
        target_energy,
        [task.base_energy for task in spec.tasks],
        spec.task_energy_min,
        spec.task_energy_max,
    )
    speed_min, speed_max, energy_min, energy_max = (
        MACHINE_FACTOR_RANGES[spec.process_id]
    )
    time_options = []
    energy_options = []
    task_configs = []
    for task_index, task in enumerate(spec.tasks):
        option_count = min(
            target_machines,
            rng.randint(spec.option_min, spec.option_max),
        )
        machines = sorted(
            rng.sample(range(1, target_machines + 1), option_count)
        )
        task_time_options = []
        task_energy_options = []
        machine_configs = []
        for machine_id in machines:
            machine_time = max(
                1,
                int(
                    round(
                        task_times[task_index]
                        * rng.uniform(speed_min, speed_max)
                    )
                ),
            )
            machine_energy = max(
                1,
                int(
                    round(
                        task_energies[task_index]
                        * rng.uniform(energy_min, energy_max)
                    )
                ),
            )
            task_time_options.append((machine_id, machine_time))
            task_energy_options.append((machine_id, machine_energy))
            machine_configs.append(
                {
                    "machine_id": machine_id,
                    "processing_time": machine_time,
                    "processing_energy": machine_energy,
                }
            )
        materials = task_material_requirements(
            spec.process_id,
            task_index,
            variant,
        )
        time_options.append(task_time_options)
        energy_options.append(task_energy_options)
        task_configs.append(
            {
                "stage_operation_id": task_index,
                "task_code": task.task_code,
                "operation_type": task.operation_type,
                "description": task.description,
                "base_processing_time": task_times[task_index],
                "base_processing_energy": task_energies[task_index],
                "machine_options": machine_configs,
                "materials": materials,
            }
        )
    return {
        "job_id": job_id,
        "variant": {
            "powertrain_type": variant.powertrain_type,
            "drive_type": variant.drive_type,
            "body_color": variant.body_color,
            "roof_color": variant.roof_color,
            "two_tone": variant.two_tone,
            "synthetic": True,
        },
        "stamping_time": stamping_time,
        "stamping_energy": stamping_energy,
        "time_ratio": time_ratio,
        "energy_ratio": energy_ratio,
        "target_processing_time": target_time,
        "target_processing_energy": target_energy,
        "raw_tasks": time_options,
        "energy_tasks": energy_options,
        "tasks": task_configs,
    }


def render_stage_pair(
    source: dict[str, Any],
    spec: ProcessSpec,
    source_name: str,
) -> dict[str, Any]:
    rng = random.Random(
        stable_seed(source_name, spec.directory, "stage-pair-v2")
    )
    target_machines = stage_machine_count(spec, source)
    variants = job_variants(source_name, source["num_jobs"])
    raw_lines = [
        f"{source['num_jobs']}\t{target_machines}\t{source['metadata']}"
    ]
    energy_lines = []
    operation_counts = []
    all_times = []
    all_energies = []
    jobs = []

    for job_id in range(source["num_jobs"]):
        job = generate_process_job(
            source,
            spec,
            job_id,
            variants[job_id],
            target_machines,
            source_name,
        )
        jobs.append(job)
        raw_lines.append(format_options(job["raw_tasks"]))
        energy_lines.append(format_options(job["energy_tasks"]))
        operation_counts.append(len(job["raw_tasks"]))
        all_times.extend(
            option["processing_time"]
            for task in job["tasks"]
            for option in task["machine_options"]
        )
        all_energies.extend(
            option["processing_energy"]
            for task in job["tasks"]
            for option in task["machine_options"]
        )

    transport_time, transport_energy = generate_transport(
        source,
        target_machines,
        spec,
        rng,
    )
    matrix_lines = [
        " ".join(str(value) for value in row)
        for row in transport_time
    ]
    matrix_lines.extend(
        " ".join(str(value) for value in row)
        for row in transport_energy
    )
    metadata = {
        "process_id": spec.process_id,
        "process_name": spec.process_name,
        "num_jobs": source["num_jobs"],
        "source_num_machines": source["num_machines"],
        "num_machines": target_machines,
        "num_operations": sum(operation_counts),
        "min_operations_per_job": min(operation_counts),
        "max_operations_per_job": max(operation_counts),
        "min_processing_time": min(all_times),
        "max_processing_time": max(all_times),
        "min_processing_energy": min(all_energies),
        "max_processing_energy": max(all_energies),
    }
    generated_source = {
        "num_jobs": source["num_jobs"],
        "num_machines": target_machines,
        "metadata": source["metadata"],
        "raw_jobs": [job["raw_tasks"] for job in jobs],
        "energy_jobs": [job["energy_tasks"] for job in jobs],
        "transport_time": transport_time,
        "transport_energy": transport_energy,
    }
    return {
        "raw_text": "\n".join(raw_lines) + "\n",
        "add_text": "\n".join(energy_lines + matrix_lines) + "\n",
        "metadata": metadata,
        "jobs": jobs,
        "source": generated_source,
        "transport_time": transport_time,
        "transport_energy": transport_energy,
    }


def render_process_generation_config(
    source_name: str,
    result: dict[str, Any],
) -> dict[str, Any]:
    metadata = result["metadata"]
    rules: dict[str, Any] = {
        "deterministic_seed": (
            "sha256(instance, process, job, version)"
        ),
        "processing_energy_unit": "energy_unit",
        "transport_energy_unit": "energy_unit",
    }
    spec = next(
        (
            item
            for item in PROCESS_SPECS
            if item.process_id == metadata["process_id"]
        ),
        None,
    )
    if spec is not None:
        rules.update(
            {
                "fixed_task_count": len(spec.tasks),
                "time_ratio_range": [
                    spec.time_ratio_min,
                    spec.time_ratio_max,
                ],
                "time_ratio_default": spec.time_ratio_default,
                "energy_ratio_range": [
                    spec.energy_ratio_min,
                    spec.energy_ratio_max,
                ],
                "energy_ratio_default": spec.energy_ratio_default,
                "machine_speed_factor_range": [
                    MACHINE_FACTOR_RANGES[spec.process_id][0],
                    MACHINE_FACTOR_RANGES[spec.process_id][1],
                ],
                "machine_energy_factor_range": [
                    MACHINE_FACTOR_RANGES[spec.process_id][2],
                    MACHINE_FACTOR_RANGES[spec.process_id][3],
                ],
            }
        )
    energy_jobs = []
    for job in result["jobs"]:
        energy_job = dict(job)
        energy_job["tasks"] = [
            {
                key: value
                for key, value in task.items()
                if key != "materials"
            }
            for task in job["tasks"]
        ]
        energy_jobs.append(energy_job)
    return {
        "format_version": 1,
        "instance": source_name,
        "process_id": metadata["process_id"],
        "process_name": metadata["process_name"],
        "num_jobs": metadata["num_jobs"],
        "num_machines": metadata["num_machines"],
        "num_operations": metadata["num_operations"],
        "rules": rules,
        "jobs": energy_jobs,
        "transport_time": result["transport_time"],
        "transport_energy": result["transport_energy"],
    }


def _quantity_resolution(unit: str) -> float:
    return 1.0 if unit in {"piece", "set"} else 0.1


def _round_material_quantity(value: float, unit: str) -> float:
    resolution = _quantity_resolution(unit)
    rounded = math.ceil((value / resolution) - 1e-9) * resolution
    return int(rounded) if resolution == 1.0 else round(rounded, 1)


def _material_usage(
    requirements: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    totals: dict[str, float] = {}
    for requirement in requirements:
        material_id = requirement["material_id"]
        if material_id not in MATERIALS:
            raise ValueError(f"Unknown material: {material_id}")
        quantity = float(requirement["quantity"])
        if quantity < 0:
            raise ValueError(
                f"Negative quantity for material {material_id}"
            )
        totals[material_id] = totals.get(material_id, 0.0) + quantity
    return [
        {
            "material_id": material_id,
            "quantity": round(quantity, 4),
        }
        for material_id, quantity in totals.items()
    ]


def render_material_consumption(
    source_name: str,
    process_id: int,
    jobs: list[dict[str, Any]],
) -> dict[str, Any]:
    """Render Job-level stamping or Task-level later-process consumption."""
    consumption_jobs = []
    for job in jobs:
        if process_id == 1:
            consumption_jobs.append(
                {
                    "job_id": job["job_id"],
                    "materials": _material_usage(
                        [
                            requirement
                            for task in job["tasks"]
                            for requirement in task["materials"]
                        ]
                    ),
                }
            )
            continue
        consumption_jobs.append(
            {
                "job_id": job["job_id"],
                "tasks": [
                    {
                        "stage_operation_id": task["stage_operation_id"],
                        "materials": _material_usage(
                            task["materials"]
                        ),
                    }
                    for task in job["tasks"]
                ],
            }
        )
    return {
        "instance": source_name,
        "process_id": process_id,
        "jobs": consumption_jobs,
    }


def _material_demand(
    process_id: int,
    consumption: dict[str, Any],
) -> dict[str, float]:
    demand = {
        material_id: 0.0
        for material_id in STAGE_MATERIALS[process_id]
    }
    for job in consumption["jobs"]:
        if process_id == 1:
            material_groups = [job["materials"]]
        else:
            material_groups = [
                task["materials"] for task in job["tasks"]
            ]
        for materials in material_groups:
            for material in materials:
                material_id = material["material_id"]
                demand[material_id] += float(material["quantity"])
    return demand


def _machine_material_demand(
    process_id: int,
    jobs: list[dict[str, Any]] | None,
    num_machines: int,
) -> dict[int, dict[str, float]]:
    """Provision every Task demand on every machine able to process it."""
    machine_demand = {
        machine_id: {
            material_id: 0.0
            for material_id in STAGE_MATERIALS[process_id]
        }
        for machine_id in range(1, num_machines + 1)
    }
    if jobs is None:
        return machine_demand

    for job in jobs:
        for task in job["tasks"]:
            requirements = task.get("materials", [])
            if not requirements:
                continue
            machine_ids = sorted(
                {
                    int(option["machine_id"])
                    for option in task.get("machine_options", [])
                }
            )
            if not machine_ids:
                raise ValueError(
                    f"Job {job['job_id']} operation "
                    f"{task['stage_operation_id']} consumes materials "
                    "but has no eligible machine."
                )
            unavailable_machines = [
                machine_id
                for machine_id in machine_ids
                if machine_id not in machine_demand
            ]
            if unavailable_machines:
                raise ValueError(
                    f"Job {job['job_id']} operation "
                    f"{task['stage_operation_id']} references machines "
                    f"{unavailable_machines} outside 1..{num_machines}."
                )
            for requirement in requirements:
                material_id = requirement["material_id"]
                quantity = float(requirement["quantity"])
                for machine_id in machine_ids:
                    machine_demand[machine_id][material_id] += quantity
    return machine_demand


def render_material_config(
    source_name: str,
    process_id: int,
    num_machines: int,
    consumption: dict[str, Any],
    jobs: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Render stock for all initial Tasks each machine may process."""
    demand = _material_demand(process_id, consumption)
    machine_demand = _machine_material_demand(
        process_id,
        jobs,
        num_machines,
    )
    if all(
        quantity <= 0
        for demands in machine_demand.values()
        for quantity in demands.values()
    ):
        machine_demand = {
            machine_id: {
                material_id: (
                    demand[material_id] / num_machines
                )
                for material_id in STAGE_MATERIALS[process_id]
            }
            for machine_id in range(1, num_machines + 1)
        }

    machine_quantities = {
        machine_id: {
            material_id: _round_material_quantity(
                (
                    demand_by_material[material_id]
                    * MATERIAL_RESERVE_FACTOR
                ),
                MATERIALS[material_id][1],
            )
            for material_id in STAGE_MATERIALS[process_id]
        }
        for machine_id, demand_by_material
        in machine_demand.items()
    }

    machines = [
        {
            "machine_id": machine_id,
            "materials": [
                {
                    "material_id": material_id,
                    "quantity": machine_quantities[machine_id][
                        material_id
                    ],
                }
                for material_id in STAGE_MATERIALS[process_id]
            ],
        }
        for machine_id in range(1, num_machines + 1)
    ]

    return {
        "instance": source_name,
        "process_id": process_id,
        "machines": machines,
    }


def render_material_master() -> str:
    stream = io.StringIO()
    writer = csv.writer(stream, lineterminator="\n")
    writer.writerow(
        ["material_id", "material_name", "unit", "category"]
    )
    for material_id, (name, unit, category) in MATERIALS.items():
        writer.writerow([material_id, name, unit, category])
    return stream.getvalue()


def average_off_diagonal(matrix: list[list[int]]) -> float:
    values = [
        value
        for row_index, row in enumerate(matrix)
        for column_index, value in enumerate(row)
        if row_index != column_index
    ]
    return sum(values) / len(values) if values else 0


def expected_stage_cycles(source: dict[str, Any]) -> list[float]:
    average_transport = average_off_diagonal(
        source["transport_time"]
    )
    pressure = source["num_jobs"] / source["num_machines"]
    queue_factor = min(
        0.60,
        max(0.0, pressure - 1.0) * 0.15,
    )
    cycles = []
    for raw_job in source["raw_jobs"]:
        processing = sum(
            sum(value for _, value in options) / len(options)
            for options in raw_job
        )
        intra_transport = max(0, len(raw_job) - 1) * average_transport
        queue_allowance = processing * queue_factor
        cycles.append(
            processing + intra_transport + queue_allowance
        )
    return cycles


def delivery_rows_for_instance(
    source_name: str,
    num_jobs: int,
) -> list[list[float]]:
    rng = random.Random(
        stable_seed(source_name, "delivery-v3")
    )
    return [
        [
            float(rng.randint(1, 5)),
            float(rng.randint(0, 20)),
            0.0,
            float(rng.randint(1, 10)),
            float(rng.randint(1, 10)),
        ]
        for _ in range(num_jobs)
    ]


def render_delivery_file(
    source_name: str,
    stage_sources: list[dict[str, Any]] | None = None,
) -> str:
    if stage_sources is None:
        stage_sources = [
            parse_source(
                ROOT / raw_directory / source_name,
                ROOT / add_directory / source_name,
            )
            for raw_directory, add_directory in (
                ("raw", "add"),
                ("raw1", "add1"),
                ("raw2", "add2"),
                ("raw3", "add3"),
            )
        ]
    num_jobs = stage_sources[0]["num_jobs"]
    if any(
        source["num_jobs"] != num_jobs
        for source in stage_sources[1:]
    ):
        raise ValueError(
            f"{source_name}: process files have different Job counts"
        )
    rows = delivery_rows_for_instance(source_name, num_jobs)
    stage_cycles = [
        expected_stage_cycles(source) for source in stage_sources
    ]
    interstage_time = sum(INTERSTAGE_TRANSPORT_TIME)
    for job_id, row in enumerate(rows):
        total_cycle = (
            sum(cycles[job_id] for cycles in stage_cycles)
            + interstage_time
        )
        row[2] = float(
            math.ceil(
                row[1] + total_cycle * DUE_BUFFER_FACTOR
            )
        )
    lines = [
        "\t".join(str(int(value)) for value in row)
        for row in rows
    ]
    return DELIVERY_HEADER + "\n" + "\n".join(lines) + "\n"


def check_or_write(
    path: Path,
    expected: str,
    check: bool,
    mismatches: list[str],
) -> None:
    if check:
        if (
            not path.is_file()
            or path.read_text(encoding="utf-8") != expected
        ):
            mismatches.append(str(path))
        return
    path.write_text(expected, encoding="utf-8")


def json_text(value: dict[str, Any]) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Generate add/raw1/add1/raw2/add2/raw3/add3, delivery data, "
            "energy configs, material consumption and inventory configs."
        )
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Verify generated files without writing.",
    )
    args = parser.parse_args()

    raw_paths = sorted(SOURCE_RAW_DIR.glob("*.fjs"))
    if not raw_paths:
        raise SystemExit(f"No raw datasets found in {SOURCE_RAW_DIR}")

    expected_names = {path.name for path in raw_paths}
    expected_config_names = {
        process_filename(path.name) for path in raw_paths
    }
    process_dirs = {
        "process_1": (ROOT / "raw", ROOT / "add", "冲压"),
        "process_2": (ROOT / "raw1", ROOT / "add1", "焊装"),
        "process_3": (ROOT / "raw2", ROOT / "add2", "涂装"),
        "process_4": (ROOT / "raw3", ROOT / "add3", "总装"),
    }
    generated_dirs = [
        SOURCE_ADD_DIR,
        DELIVERY_ROOT,
        *[
            path
            for raw_dir, add_dir, _ in process_dirs.values()
            for path in (raw_dir, add_dir)
            if path != SOURCE_RAW_DIR
        ],
        *[
            PROCESS_GENERATION_CONFIG_ROOT / f"process_{process_id}"
            for process_id in range(1, 5)
        ],
        *[
            MATERIAL_CONFIG_ROOT / f"process_{process_id}"
            for process_id in range(1, 5)
        ],
        *[
            MATERIAL_CONSUMPTION_ROOT / f"process_{process_id}"
            for process_id in range(1, 5)
        ],
    ]
    if not args.check:
        for directory in generated_dirs:
            directory.mkdir(parents=True, exist_ok=True)
        for directory in generated_dirs:
            expected = (
                expected_config_names
                if (
                    directory.parent == PROCESS_GENERATION_CONFIG_ROOT
                    or directory.parent == MATERIAL_CONFIG_ROOT
                    or directory.parent == MATERIAL_CONSUMPTION_ROOT
                )
                else expected_names
            )
            suffix = ".json" if directory.parent in {
                PROCESS_GENERATION_CONFIG_ROOT,
                MATERIAL_CONFIG_ROOT,
                MATERIAL_CONSUMPTION_ROOT,
            } else ".fjs"
            for stale_path in directory.glob(f"*{suffix}"):
                if stale_path.name not in expected:
                    stale_path.unlink()

    mismatches: list[str] = []
    process_metadata: dict[str, list[dict[str, Any]]] = {
        f"process_{process_id}": [] for process_id in range(1, 5)
    }

    for raw_path in raw_paths:
        source_name = raw_path.name
        stage1 = render_stage1_file(raw_path)
        stage_results = {1: stage1}
        base_source = stage1["source"]
        for spec in PROCESS_SPECS:
            stage_results[spec.process_id] = render_stage_pair(
                base_source,
                spec,
                source_name,
            )

        for process_id, result in stage_results.items():
            metadata = result["metadata"]
            metadata["source"] = source_name
            process_metadata[f"process_{process_id}"].append(metadata)

            raw_dir, add_dir, _ = process_dirs[f"process_{process_id}"]
            if process_id != 1:
                check_or_write(
                    raw_dir / source_name,
                    result["raw_text"],
                    args.check,
                    mismatches,
                )
            check_or_write(
                add_dir / source_name,
                result["add_text"],
                args.check,
                mismatches,
            )

            config_name = process_filename(source_name)
            process_generation_config = (
                render_process_generation_config(source_name, result)
            )
            check_or_write(
                PROCESS_GENERATION_CONFIG_ROOT
                / f"process_{process_id}"
                / config_name,
                json_text(process_generation_config),
                args.check,
                mismatches,
            )
            material_consumption = render_material_consumption(
                source_name,
                process_id,
                result["jobs"],
            )
            check_or_write(
                MATERIAL_CONSUMPTION_ROOT
                / f"process_{process_id}"
                / config_name,
                json_text(material_consumption),
                args.check,
                mismatches,
            )
            material_config = render_material_config(
                source_name,
                process_id,
                metadata["num_machines"],
                material_consumption,
                result["jobs"],
            )
            check_or_write(
                MATERIAL_CONFIG_ROOT
                / f"process_{process_id}"
                / config_name,
                json_text(material_config),
                args.check,
                mismatches,
            )

        delivery_text = render_delivery_file(
            source_name,
            [stage_results[index]["source"] for index in range(1, 5)],
        )
        check_or_write(
            DELIVERY_ROOT / source_name,
            delivery_text,
            args.check,
            mismatches,
        )

    check_or_write(
        MATERIAL_MASTER_PATH,
        render_material_master(),
        args.check,
        mismatches,
    )

    manifest: dict[str, Any] = {
        "format_version": 8,
        "generated_from": "raw",
        "instance_count": len(raw_paths),
        "material_inventory": "material_configs",
        "material_consumption": "material_consumption",
        "material_master": MATERIAL_MASTER_PATH.name,
        "material_inventory_rules": {
            "demand_source": (
                "Initial Task material consumption provisioned on every "
                "machine eligible to process that Task"
            ),
            "reserve_factor": MATERIAL_RESERVE_FACTOR,
            "rounding": (
                "piece/set to 1, kg/L to 0.1, rounded upward"
            ),
            "allocation": (
                "Each machine receives reserve-adjusted demand for all "
                "initial Tasks it can process; dynamic Jobs are not "
                "included in this baseline inventory"
            ),
        },
        "processes": {},
    }
    for process_id in range(1, 5):
        key = f"process_{process_id}"
        raw_dir, add_dir, process_name = process_dirs[key]
        spec = next(
            (
                item
                for item in PROCESS_SPECS
                if item.process_id == process_id
            ),
            None,
        )
        rules: dict[str, Any]
        if spec is None:
            rules = {
                "task_source": "raw",
                "processing_energy_options": [4, 15],
                "transport_time_range": [1, 3],
                "transport_energy_range": [1, 4],
                "stamping_material_rule": (
                    "OP0 consumes one Job material; later Tasks consume zero"
                ),
            }
        else:
            rules = {
                "fixed_task_count": len(spec.tasks),
                "machine_count_formula": (
                    "clamp(ceil(machine_s_factor * S + "
                    "machine_j_factor * J), machine_min, machine_max)"
                ),
                "machine_s_factor": spec.machine_s_factor,
                "machine_j_factor": spec.machine_j_factor,
                "machine_count_range": [
                    spec.machine_min,
                    spec.machine_max,
                ],
                "options_per_operation": [
                    spec.option_min,
                    spec.option_max,
                ],
                "time_ratio_range": [
                    spec.time_ratio_min,
                    spec.time_ratio_max,
                ],
                "time_ratio_default": spec.time_ratio_default,
                "energy_ratio_range": [
                    spec.energy_ratio_min,
                    spec.energy_ratio_max,
                ],
                "energy_ratio_default": spec.energy_ratio_default,
                "task_time_range": [
                    spec.task_time_min,
                    spec.task_time_max,
                ],
                "task_energy_range": [
                    spec.task_energy_min,
                    spec.task_energy_max,
                ],
                "transport_time_range": [
                    spec.transport_time_min,
                    spec.transport_time_max,
                ],
                "transport_energy_range": [
                    spec.transport_energy_min,
                    spec.transport_energy_max,
                ],
            }
        manifest["processes"][key] = {
            "name": process_name,
            "raw": (
                str(raw_dir.relative_to(ROOT))
                if process_id != 1
                else "raw"
            ),
            "add": str(add_dir.relative_to(ROOT)),
            "delivery_cost": "delivery_cost",
            "process_generation_configs": (
                f"process_generation_configs/{key}"
            ),
            "material_configs": f"material_configs/{key}",
            "material_consumption": (
                f"material_consumption/{key}"
            ),
            "material_consumption_granularity": (
                "job" if process_id == 1 else "task"
            ),
            "rules": rules,
            "files": process_metadata[key],
        }

    manifest["delivery_cost_rules"] = {
        "scope": "one record per Job shared by all four processes",
        "fields": [
            "priority",
            "ready_time",
            "due_time",
            "earliness_cost",
            "tardiness_cost",
        ],
        "interstage_transport_time": list(
            INTERSTAGE_TRANSPORT_TIME
        ),
        "due_buffer_factor": DUE_BUFFER_FACTOR,
        "due_time_formula": (
            "ready_time + ceil(1.50 * (sum(stage processing, "
            "intra-stage transport and queue allowance) "
            "+ interstage transport))"
        ),
    }
    check_or_write(
        MANIFEST_PATH,
        json_text(manifest),
        args.check,
        mismatches,
    )

    if mismatches:
        raise SystemExit(
            "Generated dataset check failed for:\n"
            + "\n".join(mismatches[:20])
        )
    print(
        f"instances={len(raw_paths)} process_pairs=4 "
        f"process_generation_configs=4 material_configs=4 "
        f"material_consumption=4 checked={args.check}"
    )
    print(f"manifest={MANIFEST_PATH}")


if __name__ == "__main__":
    main()

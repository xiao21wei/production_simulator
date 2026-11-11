"""pydantic 响应模型（同时生成 OpenAPI schema）。

对大矩阵字段使用宽松 list，避免每请求校验 1500 个浮点数的开销。
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class WindowBlock(BaseModel):
    rows: int
    cols: int
    layout: str
    features: list[str]
    row_start: int
    row_end: int
    dtype: str
    normalization: str
    data: list = Field(default_factory=list)
    note: str | None = None


class WindowResponse(BaseModel):
    machine_id: int
    t: int
    t_effective: int
    wrapped: bool
    cycles: int
    T: int
    contract: dict
    window: WindowBlock


class Frame(BaseModel):
    t: int
    t_effective: int
    wrapped: bool
    cycles: int
    horizon_wrap: bool
    values: dict[str, float]
    label: int
    warn: int


class StreamResponse(BaseModel):
    machine_id: int
    T: int
    prediction_horizon: int
    features: list[str]
    frames: list[Frame]
    wrapped_at: list[int]


class LabelResponse(BaseModel):
    machine_id: int
    t: int
    t1: int
    t_effective: int
    target_effective: int
    label: int
    wrapped_target: bool
    note: str


class WarnResponse(BaseModel):
    machine_id: int
    t: int
    t_effective: int
    prediction_horizon: int
    warn: int
    label: int


class MetaResponse(BaseModel):
    service: str
    version: str
    contract: dict
    features_detail: list[dict]
    display_subset: list[str]
    colors: dict
    machines: dict
    endpoints: list[str]


class MachineItem(BaseModel):
    machine_id: int
    rows: int
    T: int
    pre_generated: bool
    anomaly_ratio: float
    label_count: int


class MachinesResponse(BaseModel):
    pre_generated: int
    total_available: int
    machines: list[MachineItem]


class HealthResponse(BaseModel):
    status: str
    data_dir_ready: bool
    pre_generated: int
    contract_version: str


class ErrorResponse(BaseModel):
    code: int
    message: str
    detail: Any = None

"""REST 路由 /api/v1。"""
from __future__ import annotations

import pathlib

from fastapi import APIRouter, Query

from app.config import CFG, ROOT
from app.data import registry
from app.data.features import FEATURES, features_detail
from app.errors import ApiError
from app.schemas import (WindowResponse, StreamResponse, LabelResponse,
                         WarnResponse, MetaResponse, MachinesResponse,
                         HealthResponse)
from app.services import window as svc_window
from app.services import labels as svc_labels
from app.services import display as svc_display

router = APIRouter(prefix="/api/v1")


def _guard(fn, *args, **kwargs):
    """把参数/数据错误统一翻译为 ApiError(400/422)。"""
    try:
        return fn(*args, **kwargs)
    except ValueError as ex:
        msg = str(ex)
        status = 422 if ("过短" in msg or "缺少必要列" in msg) else 400
        raise ApiError(status, msg)
    except FileNotFoundError as ex:
        raise ApiError(404, f"数据文件不存在: {ex}")


@router.get("/window", response_model=WindowResponse,
            summary="模型输入窗口（核心）",
            description="返回喂给 CNN-LSTM 的 (100,15) 窗口，不含任何标签。")
def get_window(
    machine_id: int = Query(..., ge=0, description="机器 ID，0 起"),
    t: int = Query(..., ge=0, description="时间点，无上界，内部取模"),
    layout: str = Query("time_major", description="time_major | channel_major"),
):
    return _guard(svc_window.get_window, machine_id, t, layout)


@router.get("/stream", response_model=StreamResponse,
            summary="前端展示帧/批次",
            description="含特征真值 label 与预警提前区 warn，仅用于展示。")
def get_stream(
    machine_id: int = Query(..., ge=0),
    from_t: int = Query(0, ge=0, description="起始时间点"),
    count: int = Query(1, ge=1, le=300, description="返回帧数 1..300"),
    features: str | None = Query(None, description="逗号分隔特征名，缺省用 /meta 的 display_subset"),
):
    flist = [s.strip() for s in features.split(",") if s.strip()] if features else None
    return _guard(svc_display.get_stream, machine_id, from_t, count, flist)


@router.get("/labels", response_model=LabelResponse,
            summary="标签/真值查询",
            description="对应旧 get_label(df, t, t1)：返回时间点 t-t1 的标签。")
def get_labels(
    machine_id: int = Query(..., ge=0),
    t: int = Query(..., ge=0),
    t1: int = Query(0, ge=0, description="回溯多少时间点"),
):
    return _guard(svc_labels.get_label, machine_id, t, t1)


@router.get("/warn", response_model=WarnResponse,
            summary="预警提前区查询",
            description="warn(t)=1 表示 [t, t+prediction_horizon) 内将发生故障。")
def get_warn(
    machine_id: int = Query(..., ge=0),
    t: int = Query(..., ge=0),
):
    return _guard(svc_labels.get_warn, machine_id, t)


@router.get("/meta", response_model=MetaResponse,
            summary="契约自描述",
            description="三方对接首选：特征顺序/量纲/形状/归一化/配色/机器数。")
def get_meta():
    c = CFG["contract"]
    return {
        "service": "streaming-simulator",
        "version": "1.0",
        "contract": {
            "window_size": c["window_size"],
            "step": c["step"],
            "warmup_rows": c["warmup_rows"],
            "time_step": c["time_step"],
            "prediction_horizon": c["prediction_horizon"],
            "features": list(FEATURES),
            "normalization": c["normalization"],
            "dtype": c["dtype"],
            "model_input_shape": c["model_input_shape"],
            "layouts": ["time_major", "channel_major"],
            "version": c["version"],
        },
        "features_detail": features_detail(CFG["display"]["subset"]),
        "display_subset": list(CFG["display"]["subset"]),
        "colors": dict(CFG["display"]["colors"]),
        "machines": {
            "pre_generated": CFG["data"]["pre_generated_machines"],
            "lazy_generate": True,
        },
        "endpoints": ["/api/v1/window", "/api/v1/stream", "/api/v1/labels",
                      "/api/v1/warn", "/api/v1/machines", "/api/v1/meta",
                      "/health"],
    }


@router.get("/machines", response_model=MachinesResponse,
            summary="机器列表与统计")
def get_machines():
    items = _guard(registry.list_machines)
    return {
        "pre_generated": CFG["data"]["pre_generated_machines"],
        "total_available": len(items),
        "machines": items,
    }


@router.get("/health", response_model=HealthResponse, summary="存活探针")
def health():
    ready = pathlib.Path(CFG["data"]["base_data_path"]).exists()
    return {
        "status": "ok" if ready else "degraded",
        "data_dir_ready": ready,
        "pre_generated": CFG["data"]["pre_generated_machines"],
        "contract_version": CFG["contract"]["version"],
    }

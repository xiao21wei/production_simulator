"""FastAPI 应用入口：app.main:app

启动： ./start.sh  （等价 uvicorn app.main:app --host 0.0.0.0 --port 8000）
在线接口文档： /docs  /redoc  /openapi.json
演示页：       /
"""
from __future__ import annotations

import pathlib

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse

from app.api.v1 import router as v1_router
from app.config import CFG, ROOT
from app.errors import ApiError
from app.schemas import ErrorResponse

app = FastAPI(
    title="流式数据模拟服务",
    version="1.0",
    description=(
        "为模拟器提供流式数据：按 (machine_id, 时间点 t) 取模型输入窗口与前端展示帧。"
        "模型部署在外部「异常管控平台」，本服务不加载模型、不做推理。"
    ),
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=CFG["server"]["cors_origins"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(v1_router)


@app.exception_handler(ApiError)
async def api_error_handler(request: Request, exc: ApiError):
    return JSONResponse(
        status_code=exc.status,
        content={"code": exc.status, "message": exc.message, "detail": exc.detail},
    )


@app.exception_handler(RequestValidationError)
async def validation_error_handler(request: Request, exc: RequestValidationError):
    """参数校验失败也统一为 {code, message, detail}（文档约定的 400）。"""
    return JSONResponse(
        status_code=400,
        content={"code": 400, "message": "参数校验失败",
                 "detail": jsonable_encoder(exc.errors())},
    )


@app.get("/health", include_in_schema=False)
def health_root():
    ready = pathlib.Path(CFG["data"]["base_data_path"]).exists()
    return {"status": "ok" if ready else "degraded",
            "data_dir_ready": ready,
            "pre_generated": CFG["data"]["pre_generated_machines"],
            "contract_version": CFG["contract"]["version"]}


@app.get("/", include_in_schema=False)
def index():
    """独立前端演示页（单文件、零外部依赖、随包附带）。"""
    page = ROOT / "frontend" / "index.html"
    if page.exists():
        return FileResponse(page)
    return JSONResponse({"error": "frontend/index.html 缺失"}, status_code=404)

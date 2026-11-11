# 流式数据模拟服务（simulator）

把 `production_simulator` 里「按 `machine_id + 时间点 t` 取历史窗口」的能力，改造为**独立的流式数据模拟 HTTP 服务**：

- 服务只**产数据 / 取窗口 / 取标签**，不加载模型、不推理；
- 故障预测 CNN-LSTM 部署在外部「异常管控平台」，由它调 `/window` 取数、自行推理；
- 另给「调度展示平台」的前端页面提供实时数据流与故障标记接口；
- 数据集**预生成 + 超量按需确定性扩展**；`t` 取模循环。

> 本目录为**自包含、已实现可运行**的工程：所需数据文件已复制进来，整体打包到别的服务器即可运行（见「自包含 / 打包移植」）。
> 参考工程 `/home/zhangll24/works/production_simulator` **只读、不改动、不引用其绝对路径**。
> 当前状态：**后端服务 + 参考前端页 + 3 份文档 + 测试均已交付，18 个单测全通过、HTTP 全端点与真实 uvicorn 启动已实测。**

---

## 已对齐决策

| 决策点 | 选择 |
|---|---|
| 技术形态 | Python + FastAPI 独立服务（自带 Swagger/OpenAPI） |
| 数据/异常方案 | 沿用原切块拼接方案、只修缺陷；增强项默认关闭、逐项可验证 |
| 模型输入契约 | 与旧 CNN-LSTM 完全一致（窗口 100 行 / 1 时间点=2 行 / 15 特征固定顺序 / 原始值 / `(1,15,100)`） |
| 前端取数 | 前端驱动时钟 + 轮询 `GET /stream` |

## 文档导航

| 文档 | 看什么 |
|---|---|
| [docs/实施方案.md](docs/实施方案.md) | **主方案**：架构、时间/窗口/取模语义、数据集与异常分布、契约、测试、实施步骤 |
| [docs/接口文档.md](docs/接口文档.md) | 全部 REST 端点、参数、JSON Schema、示例、错误码、两方对接步骤 |
| [docs/数据与前端对接说明.md](docs/数据与前端对接说明.md) | 15 特征数据字典、异常字典、前端布局/配色/特征子集/集成方式 |

实现后另具备在线接口文档：`/docs`、`/redoc`、`/openapi.json`。

## 核心接口一览

| 端点 | 消费者 | 作用 |
|---|---|---|
| `GET /api/v1/window` | 异常管控平台 | 模型输入窗口 `(100,15)`，不含标签；`t` 取模、返回 `wrapped`/`cycles` |
| `GET /api/v1/stream` | 前端 | 一帧/一批展示数据（值 + `label` + `warn` + `horizon_wrap` + seam） |
| `GET /api/v1/labels` | 异常平台/前端 | 对应旧 `get_label(df,t,t1)` |
| `GET /api/v1/warn` | 前端/评估 | `warn(t)` = `[t,t+20)` 内是否将故障 |
| `GET /api/v1/meta` | 全部 | 契约自描述（特征字典、量纲、形状、配色） |
| `GET /api/v1/machines` | 调度平台 | 机器列表与统计 |
| `GET /health` | 运维 | 存活探针 |

## 关键语义速记

- `1 时间点 = 2 行`；`window(t) = rows[2t : 100+2t]`，形状 `(100,15)`；
- 前 `100` 行为预热历史；`T = (L-100)//2 + 1`；`t_effective = t % T`；
- `label(t)` = 时间点 `t` 是否故障（红）；`warn(t)` = `[t, t+20)` 内是否将故障（橙，预警提前区）；
- 模型输入**不含标签**，标签只在 `/labels`、`/stream` 提供（防泄漏）；
- `LPS` / `Oil_level` / `Caudal_impulses` 为常量：模型输入保留、前端展示剔除。

## 实现后快速启动（规划）

```bash
pip install -r requirements.txt      # 仅 fastapi/uvicorn/pydantic/PyYAML，不含 torch/numpy/pandas
./start.sh                           # 等价: uvicorn app.main:app --host 0.0.0.0 --port 8000
# 打开 http://localhost:8000/           看实时数据流演示页
# 打开 http://localhost:8000/docs       看在线接口文档
curl "http://localhost:8000/api/v1/window?machine_id=0&t=0"
python3 -m unittest discover -s tests -v    # 18 个单测，含契约回归
```
`data/` 已随工程附带 `anomaly.csv` 与 15 台 `machine_*.csv`，**无需再复制任何文件**。

## 配置入口

全部参数集中在 `config.yaml`：`data.*`（生成/预生成/增强开关）、`contract.*`（模型契约，改动需升版本并重跑回归测试）、`server.*`（端口/CORS）。详见《实施方案》§4.6。

## 自包含 / 打包移植

工程根目录即本文件夹 `simulator/`，**内部一律相对路径、无外部绝对路径依赖**。

**已随包附带（打包勿遗漏）**
- `data/anomaly.csv`：MetroPT 真实故障基底（4040 行）
- `data/machines/machine_*.csv`：已生成的 15 台机器数据（约 37MB）
- `docs/`：实施方案、接口文档、数据与前端对接说明
- `config.yaml` / `requirements.txt` / `start.sh` / `app/` / `frontend/index.html`（实现后）

**打包与运行**
```bash
tar czf simulator.tgz simulator/           # 排除 __pycache__/ *.pyc 日志 .git/
# 目标服务器：
tar xzf simulator.tgz && cd simulator
pip install -r requirements.txt
./start.sh                                  # HOST/PORT 可用环境变量覆盖
curl localhost:8000/health
```

**可移植性保证**
- 不改动、不引用 `production_simulator/`；所有数据/配置路径相对工程根。
- 服务端仅 `fastapi/uvicorn/pydantic/PyYAML`，**不装 torch/tf/numpy/pandas**（模型在异常管控平台）；数据处理全用标准库，数据为 CSV，无数据库/外部服务。
- 前端为单文件 `index.html` + **纯原生 Canvas 2D**，零 CDN / 零外部依赖，离线与内网环境直接可用。
- 体积瘦身：只带 `anomaly.csv`、把 `pre_generated_machines=0`，服务启动时确定性生成，结果一致。

## 验收基线

实现时**先**跑《实施方案》§5.4「契约一致性回归测试」：证明 `/window` 返回与旧版 `get_history_window` 逐值一致、同模型概率一致；再逐项开启增强开关。

# production_simulator

## Conda 环境

项目使用名为 `simulator` 的 Python 3.11 Conda 环境：

```bash
conda create -y -n simulator python=3.11 pip
conda activate simulator
python -m pip install -r requirements.txt
```

如果当前 shell 尚未初始化 Conda，可以直接使用：

```bash
source /data/luopw/miniconda3/etc/profile.d/conda.sh
conda activate simulator
```

验证环境：

```bash
python --version
```

## 基础环境配置

项目根目录的 `simulator_config.json` 集中保存基础环境配置：

| 配置项 | 说明 |
| --- | --- |
| `time.real_time_step` | 一个仿真步对应的现实秒数 |
| `time.speed` | 倍速；每 1 秒现实时间推进的仿真时间单位 |
| `time.realtime` | 是否按现实时间等待 |
| `paths.*` | 输入文件、排程结果和甘特图路径 |
| `simulation.*` | 日志、随机种子、交期系数和辅助能耗等参数 |
| `visualization.speed` | Web 动画使用的默认倍速 |
| `visualization.display_percent` | 工序动画显示比例，范围 25–300，默认 100 |

仿真器默认读取该文件。命令行中的 `--speed`、`--time-step`、
`--realtime` 和 `--fast-forward` 只覆盖本次运行，不修改 JSON 文件。

### 最新运行日志

每次启动仿真都会重建 `log/latest/`，保存最新一次运行的检查数据：

| 文件 | 内容 |
| --- | --- |
| `metadata.json` | 数据源、配置、倍速和启动时间 |
| `events.jsonl` | 按时间顺序记录的完整事件流 |
| `operations.jsonl` | 每道工序的运输开始/完成、加工开始/完成及任务状态 |
| `objectives.jsonl` | 每个事件后的实时能耗、辅助能耗、惩罚和 makespan |
| `reoptimizations.jsonl` | 重调度请求、模型结果、换机位置和运输开销 |
| `summary.json` | 最终目标、机器状态、作业和工序完整汇总 |
| `error.json` | 仅运行异常时生成 |

目录位置可以通过 `paths.log_dir` 修改。

## 多目标优化数据

默认实例为 `datasets/raw/fjsp.brandimarte.Mk03.m8j15c5.fjs`，并通过
`paths.additional_file` 读取同名的 `datasets/add/*.fjs` 文件。

每个工件包含：

- `weight`
- `ready_time` / `release_time`
- `due_time` / `due_date`
- `earliness_cost` / `earliness_penalty`
- `tardiness_cost` / `tardiness_penalty`
- `tasks`
- 完成时间、提前时间、延期时间、加工能耗和运输能耗

每个任务包含：

- `task_id`、`job_id`、`operation_id`
- 可加工机器集合
- 机器对应的加工时间和加工能耗
- 前后序任务 ID
- `pending/scheduled/processing/completed` 状态
- 计划与实际起止时间、分配机器
- 入站运输时间、运输能耗和来源机器

数据加载时会验证：

- `raw` 与 `add` 文件完整且同名配对
- 作业数、机器数、工序数和每个工序的候选机器一致
- 机器编号、加工时间和能耗范围合法
- 工件特征严格为 5 项
- 运输时间和运输能耗矩阵完整、对称且对角线为零

调度结束后计算三个目标：

```text
makespan = 最大完工时间
energy   = 加工能耗 + 运输能耗 + 辅助能耗
penalty  = 提前/延期惩罚
```

三个目标也会在仿真过程中实时更新：

- 运输完成事件到达时，立即计入运输能耗。
- 工序完成事件到达时，立即计入加工能耗。
- 工件最后一道工序完成时，立即计算该工件的提前/延期惩罚。
- 辅助能耗按当前仿真时间持续更新。
- Web 顶部的总能耗和交付成本会在运行过程中变化，不需要等到仿真结束。

任务开始时间按以下约束计算：

```text
首道任务：
start = max(job.ready_time, machine.ready_time)

后续任务：
start = max(
    predecessor.actual_end + transport_time[predecessor_machine][machine],
    machine.ready_time
)
```

因此首道工序不会早于工件就绪时间，后续工序不会早于前序完工并完成跨机器
运输的时间。

Web 时间轴会在目标机器轨道上显示机器间运输段。运输开始前隐藏，运输期间
使用同工件颜色的虚线动画，并标注来源机器与目标机器；若目标机器尚未空闲，
任务会等待到 `machine.ready_time` 后开始加工。
运输完成后，对应运输段以低亮状态保留在主时间线左侧，便于回看历史运输
开销；右侧事件列表同时保留运输完成事件。
任务的 `actual_end` 已包含入站运输造成的开始时间推迟，因此最终
`makespan = max(task.actual_end)` 包含全部工序间运输时间。

## 调度流程

初始化时，每个 `Job` 会先创建一个 `Order` 并放入 `job_queue`。初始
`ScheduleEvent` 从 `job_queue` 读取作业，一次性生成完整调度方案，把每道
工序按计划开始时间放入对应机器的 `pending_operations` 队列；调度成功后，
这些 `Order` 会从 `job_queue` 移入 `processing_queue`。仿真运行时，每台
机器只启动队列中的首道工序；当前工序完成后，直接从本机队列取出下一项并
创建 `OperationStartEvent`。工件全部完成后，对应 `Order` 再移入
`finished_queue`。

## 重调度 API

仿真运行期间提供两种 API 调用方式。两种方式都会先暂停仿真，完成机器
重新分配并重新计算运输和加工时间后恢复仿真。

### 方式一：调用算法专用接口

#### DRL

DRL 使用 `mofjsp/model.pt` 优化待加工工序：

```bash
curl -X POST http://127.0.0.1:8000/api/reoptimize \
  -H 'Content-Type: application/json' \
  -d '{
    "num_samples": 1,
    "seed": 0
  }'
```

请求参数：

- `num_samples`：DRL 候选采样数量。
- `seed`：随机种子。

DRL 接口正在进行加工的工序保留原机器和实际开始时间，已完成工序不参与
重新分配。剩余任务会根据前序任务位置、机器可用时间和运输矩阵重新计算：

- 来源机器与目标机器。
- 运输开始和结束时间。
- 运输时间与运输能耗。
- 目标机器等待时间。
- 新工序开始和结束时间。

响应中的 `moved_operations` 列出换机任务；`processing_operations` 列出
保持原位、正在加工的任务。

#### HLS

HLS 使用 `HLS_test` 中的 makespan 优化器选择待加工工序的加工机器：

```bash
curl -X POST http://127.0.0.1:8000/api/hls-reoptimize \
  -H 'Content-Type: application/json' \
  -d '{
    "seed": 0,
    "total_time_seconds": 20,
    "search_mode": 0.6,
    "random_strategy": 0.5,
    "max_repeat_count": 1000,
    "max_iter_count": 45,
    "population_size": 32,
    "tabu_length": 30
  }'
```

`total_time_seconds`、搜索策略和迭代参数均可省略，省略时使用
`HLS_test/config.json` 中的默认值。HLS 不参与运输时间计算，接口只使用
其返回的 `machine_id`，随后由仿真器根据工件当前位置重新计算运输开始/
完成时间、等待时间、工序开始/完成时间及运输能耗。
响应中的 `hls_schedule_times_used=false` 表示 HLS 时间未被采用，
`transport_time_recalculated=true` 表示运输及加工时间已由仿真器重算。
HLS 求解器需要完整的静态 FJSP 实例，因此请求使用当前数据源的全部工序；
求解结果中只有 `pending` 和 `scheduled` 工序的机器分配会被应用。

### 方式二：调用统一重调度指令接口

外部程序还可以通过 `POST /api/reoptimize-command` 使用统一协议选择算法
并传入对应参数。接口接收 `method` 和 `config`，可选值如下：

- `method=DRL`：`config` 支持 `num_samples`、`seed`。
- `method=HLS`：`config` 支持 `seed`、`total_time_seconds`、
  `search_mode`、`random_strategy`、`max_repeat_count`、
  `max_iter_count`、`population_size`、`tabu_length`。

DRL 指令示例：

```bash
curl -X POST http://127.0.0.1:8000/api/reoptimize-command \
  -H 'Content-Type: application/json' \
  -d '{
    "method": "DRL",
    "config": {"num_samples": 1, "seed": 0}
  }'
```

HLS 指令示例：

```bash
curl -X POST http://127.0.0.1:8000/api/reoptimize-command \
  -H 'Content-Type: application/json' \
  -d '{
    "method": "HLS",
    "config": {"seed": 0, "total_time_seconds": 20}
  }'
```

服务端收到指令后会暂停仿真，按指定算法和参数执行重调度，重新计算运输及
加工时间；成功或失败后都会恢复仿真。多个指令并发到达时由管理器的互斥锁
串行执行。

### 加工过程中提交新 Job

仿真运行期间可以调用：

```text
POST /api/jobs/submit
```

请求示例：

```bash
curl -X POST http://127.0.0.1:8000/api/jobs/submit \
  -H 'Content-Type: application/json' \
  -d '{"seed": 7}'
```

接口每次随机生成一批 Job，并将对应 Order 加入 `job_queue`。新增数量为：

```text
max(3, 初始 Job 数量 // 2)
```

例如 MK03 初始包含 15 个 Job，因此每次调用会新增 7 个 Job。随机字段范围
参考 `datasets/create_ins.py`：

| 字段 | 范围 |
| --- | --- |
| 加工能耗 | 4–15 |
| 工件重量 | 1–5 |
| 就绪时间 | 当前仿真时间 + 0–20 |
| 提前/延期成本系数 | 1–10 |
| 运输时间 | 1–3 |
| 运输能耗 | 1–4 |

工序数量及候选机器结构从当前数据集已有 Job 中随机选择模板；加工时间在
模板工序的候选加工时间范围内随机生成。交付期限按
`ready_time + 平均加工时间总和 × 1.5` 计算。每个动态 Job 保存独立的
运输时间和运输能耗矩阵。

提交后自动执行混合重调度：

1. 保留已完成工序和正在加工工序。
2. 收集 `job_queue` 中的所有 Order，以及所有机器上的未开工工序。
3. 为全部未开工工序重新分配机器。
4. 从当前仿真时刻重新计算运输、等待和加工时间。
5. 将新 Order 从 `job_queue` 移入 `processing_queue`。
6. 自动恢复仿真。

响应中的 `new_jobs` 会包含本批次新增 Job 的加工选项、交付参数和运输
矩阵，并返回 `submitted_job_count`、`initial_job_count`、本次重调度的
工序数量和换机信息。

Web 工具栏提供“自动插单”复选框。启用后，服务端在每次事件处理后检查
未完成 Job 数量，并在数量降到 `max(1, 初始 Job 数量 // 3)` 时调用一次
动态 Job 提交接口。当前 MK03 的初始 Job 数量为 15，因此剩余 5 个 Job
时自动新增 7 个 Job。只要复选框保持开启，每次剩余 Job 数再次降到 5 个
时都会继续自动插单；关闭复选框后停止后续触发。
旁边的“手动插单”按钮可以在仿真运行期间立即触发一次相同的批量插单。

自动插单开关也可以通过 API 设置：

```bash
curl -X POST http://127.0.0.1:8000/api/auto-job-submission \
  -H 'Content-Type: application/json' \
  -d '{"enabled": true}'
```

### Web 实机重调度测试脚本

在 Web 页面中手动选择 `MK03`、将倍速设置为 `2x` 并启动仿真后，运行：

```bash
python scripts/live_reoptimization_test.py
```

脚本只调用 `/api/reoptimize-command`，依次发送
`DRL → HLS → DRL → HLS` 四次重调度请求，不包含启动仿真、倍速设置或
状态轮询逻辑。每次请求返回后等待 20 秒，再发送下一次请求，避免短时间内
连续触发重调度。

## 仿真时钟配置

仿真器通过以下参数将仿真时间映射到现实时间：

| 参数 | 含义 | 默认值 |
| --- | --- | --- |
| `real_time_step` | 一个仿真步对应的现实秒数 | `1.0` |
| `speed` | 倍速；每 1 秒现实时间推进的仿真时间单位 | `10.0` |
| `simulation_time_step` | 一个仿真步推进的时间单位，由前两项计算得到 | `real_time_step * speed` |
| `realtime` | 是否按现实时间等待；设为 `False` 时不等待 | `True` |

因此，仿真时间 `N` 对应的现实等待时间为：

```text
N / speed
```

例如，以 60 倍速运行：

```bash
python run.py --speed 60
```

指定每个仿真步对应 0.1 秒现实时间、并运行在 10 倍速下：

```bash
python run.py --time-step 0.1 --speed 10
```

快速完成批量计算而禁用现实等待：

```bash
python run.py --fast-forward
```

在代码中也可以直接配置：

```python
simulator = Simulator(real_time_step=0.1, speed=10, realtime=True)
simulator.speed = 20  # 运行中修改倍速，时钟会从当前仿真时刻重新校准
```

使用其他配置文件：

```python
simulator = Simulator(config_path="my_simulator_config.json")
```

或从命令行指定：

```bash
python run.py --config my_simulator_config.json
```

也可以单独使用时钟组件：

```python
from simulator.clock import SimulationClock

clock = SimulationClock(real_time_step=0.1, speed=10)
clock.start()
clock.wait_until(100)
```

运行时钟测试：

```bash
python -m unittest discover -s tests
```

## Web 可视化

直接运行主入口：

```bash
source /data/luopw/miniconda3/etc/profile.d/conda.sh
conda activate simulator
cd /data/luopw/production_simulator
python run.py
```

启动后会首先输出 Web 地址：

```text
WEB_DASHBOARD=http://192.168.1.68:8000
```

运行期间浏览器访问：

```text
http://192.168.1.68:8000
```

页面左侧显示机器工序时间轴动画，右侧显示完整调度事件流。当前仿真时刻固定
在时间轴中央，左侧为已完成工序，右侧为待加工工序，跨过中心线的工序为当前
加工中工序。默认使用 `simulator_config.json` 中
`visualization.speed=5` 的展示倍速。

每台机器的时间轴右侧还有独立的待加工队列。待加工工序按计划开始时间排列；
当前工序完成后，队首工序会自动从待加工队列进入中央当前工序时间线。
未开工工序只在待加工队列中显示，不会提前绘制到主调度时间线；工序开始后
才会从队列移除并进入当前加工区域，完成后保留在中央时间线左侧。
待加工队列与主时间线各占机器标签以外的可用宽度的一半，并根据实际空间
动态显示最多 8 道工序。同一工件的待加工、加工中和已完成工序保持同一色相。

浏览器使用动画帧在状态轮询之间连续推进时间线，切换倍速时会重新校准动画
时钟，避免等待下一批事件造成明显停顿。

调度面板默认填满浏览器可用高度。页面顶部可调整工序显示比例，比例会同时
缩放机器行、工序条、文字和横向时间窗口；放大后可通过时间轴右侧滚动条查看
全部机器。

页面顶部提供数据源选择框，数据来自 `datasets/raw` 与 `datasets/add` 中
完整配对的文件。选择数据源后点击“启动仿真”，服务端才会创建该实例的
Simulator。仿真结束后 Web 服务保持运行，可以切换数据源再次启动。

Web 服务通常保持运行，按 `Ctrl+C` 停止服务。如需临时指定倍速：

```bash
python run.py --speed 2
```

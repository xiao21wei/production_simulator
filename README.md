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
| `simulation.process_stage_batch_window` | 工艺流转批次窗口，默认 `10.0` 仿真时间单位 |
| `simulation.material_replenishment_lead_time` | 物料补料到恢复的到达时间，默认 `5.0` 仿真时间单位 |
| `simulation.material_replenishment_target_factor` | 补料阈值相对当前工序需求的倍数，默认 `3.0` |
| `anomaly_handling.enabled` | 是否启用设备异常处置，默认 `false` |
| `visualization.speed` | Web 动画使用的默认倍速 |
| `visualization.display_percent` | 中央看板显示比例，范围 25–300，默认 100 |
| `detection_data.base_url` | 流式异常检测服务地址 |
| `detection_data.timeout` | 检测接口请求超时秒数 |
| `detection_data.history_points` | 每台设备展示的历史点数量，1–300 |
| `detection_data.poll_interval_ms` | overview 数据流刷新间隔，默认 1000 毫秒 |
| `detection_data.prediction_interval` | 模型预测调用的仿真时间间隔，默认 5 |

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

默认实例为 `datasets/raw/fjsp.brandimarte.Mk03.m8j15c5.fjs`。同名的
`datasets/add/*.fjs` 保存加工能耗和运输矩阵，
`datasets/delivery_cost/*.fjs` 保存优先级、就绪时间、交付时间、
提前成本和延期成本。加载器会自动按文件名关联三份数据；DRL/HLS 请求时会
自动把交付字段重新拼装为模型需要的附加数据格式。

四工艺交付时间按完整工艺链计算，包括各阶段平均加工时间、阶段内运输时间、
机器负荷排队缓冲，以及冲压到焊装、焊装到涂装、涂装到总装的三段工艺间
转运时间。生成规则和参数记录在
`datasets/followup_processes_manifest.json`。

### 四工艺调度

Web 启动仿真时会将同一实例的四个工艺数据加载到同一事件队列：

| 工艺 | 数据目录 | Mk03 机器数 |
| --- | --- | ---: |
| 冲压 | `raw/add` | 8 |
| 焊装 | `raw1/add1` | 6 |
| 涂装 | `raw2/add2` | 5 |
| 总装 | `raw3/add3` | 7 |

逐实例工艺生成配置位于 `datasets/process_generation_configs/process_1` 至
`process_4`，逐实例、逐机器的初始物料配置位于
`datasets/material_configs/process_1` 至 `process_4`。工艺物料消耗位于
`datasets/material_consumption/process_1` 至 `process_4`；冲压按 Job
记录，焊装、涂装和总装按 Task 记录。物料主数据位于
`datasets/material_master.csv`。运行
`python datasets/generate_followup_processes.py` 会从 `datasets/raw`
一次性重建四工艺数据、交付数据和上述配置。

模拟器初始化时会自动加载这两套物料数据：每台 `Machine` 的 `materials`
保存机器物料总量；每个合并 `Job` 的 `material_consumption` 按工艺保存
Job 级和 Task 级消耗，后三工艺的具体 Task 同时保存自己的
`material_consumption`。机器初始量覆盖所有可加工的初始 Task，并按
`1.20` 倍准备基础余量；动态 Job 不计入初始库存。四个工艺的每道工序开始前都会校验
当前机器库存：库存足够时按该工序的实际需求量一次性扣减并开始加工；
库存不足时保持工序在机器队首，依次生成物料补充事件和物料恢复事件，
两者默认间隔 `5.0` 个仿真时间单位，用于模拟物料到达机器；恢复确认后
再重新触发生效的工序开始事件。

每个 Job 保留同一个 `job_id`，所有工艺的工序使用全局连续的
`operation_id`，并通过 `stage_id` 区分所属工艺。Job 只有完成总装最后一道
工序后才进入完成状态。工艺间运输时间依次为 `2`、`4`、`3`。

动态插单同样会生成完整的四工艺路由，不会退化为单工艺 Job。

工艺采用按 Job 懒释放和按目标工艺批量排程的策略：初始只调度冲压工序；
某 Job 完成当前工艺最后一道工序后产生 `ProcessStageFinishEvent`，进入下一
工艺的批次窗口。窗口内到达的多个 Job 会合并到一个
`ProcessStageBatchScheduleEvent`，窗口结束时一次完成目标工艺的机器分配。
窗口由 `simulation.process_stage_batch_window` 控制，默认 `10.0` 个仿真
时间单位；设置为 `0` 时仍使用批量事件，但只合并同一时刻到达的 Job。

批次排程保留每个 Job 的真实到达时刻，运输可从各自前序工序完成时开始，不会
额外等待整个批次窗口。机器选择按预计最早完工时间进行，并同时考虑运输完成、
机器既有队列和加工时间。如果工艺间运输在批次窗口内已经完成，批次调度时
仍会补写完整运输段，并生成 `historical=true` 的 `TransportFinishEvent`；
该事件时间戳保留真实运输完成时刻，不会回拨仿真时钟。该机制统一应用于
焊装、涂装和总装，减少逐 Job 追加计划造成的 Web 全量重绘。

Web 的 `plan_revision` 只在机器分配或计划结构发生变化时递增。批次排程、
插单、取消订单、DRL/HLS 重调度引起的版本变化只增量刷新受影响的待加工队列
和运输段，不再重建整张时间轴。只有首次启动、切换工艺及设备异常/恢复事件
需要完整重建；普通工序开始、完成和运输状态更新仅刷新对应机器。

“工序调度”、“设备状态看板”和“物料库存看板”均提供冲压、焊装、涂装、
总装四个工艺标签：

- 工序调度标签只显示当前工艺的机器、计划、待加工队列和运输段。
- 设备状态看板标签只显示当前工艺机器数量的检测卡片。
- 物料库存看板标签只显示当前工艺每台机器的物料名称、编号和库存数量。
- 四个工艺检测时间使用不同初始起点：`0`、`1800`、`3600`、`5400`。
- 检测预测发现的异常会按当前工艺机器偏移映射到全局机器编号，再创建设备异常事件。

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
主时间轴只绘制“加工中”和“已完成”的工序；`pending/scheduled` 的待加工
工序只显示在右侧待加工队列中，直到实际开始事件发生后才进入主时间轴，从而
避免未来计划工序与当前工序、运输段在视觉上重叠。
运输完成后，对应运输段以低亮状态保留在主时间线左侧，便于回看历史运输
开销。时间轴只显示当前时间窗内的运输段，更早的历史运输会移出可视范围；
同一机器且运输时间为 `0` 的工序切换不会生成运输段。运输段的同步独立于
调度结构版本，新增或更新后会立即刷新，不会等到下一次工艺批量排程。
待加工队列按可见槽位进行限频更新，避免短工序连续完成时反复重排动画。
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
重新分配并重新计算运输和加工时间后恢复仿真。请求可通过 `process_id`
选择重调度范围：

- `1`：冲压。
- `2`：焊装。
- `3`：涂装。
- `4`：总装。

省略 `process_id` 时默认只重调度 `1`（冲压）。每次只使用所选工艺的数据集
和机器池，重建所选工艺的机器待加工队列；其他工艺的任务状态、机器队列和
计划事件保持不变。

### 方式一：调用算法专用接口

#### DRL

DRL 使用 `mofjsp/model.pt` 优化待加工工序：

```bash
curl -X POST http://127.0.0.1:8000/api/reoptimize \
  -H 'Content-Type: application/json' \
  -d '{
    "process_id": 2,
    "num_samples": 1,
    "seed": 0
  }'
```

请求参数：

- `num_samples`：DRL 候选采样数量。
- `seed`：随机种子。
- `process_id`：重调度工艺编号，`1`–`4`，默认 `1`。

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
    "process_id": 2,
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
`process_id` 用于选择对应工艺的数据集和全局机器编号偏移，同样默认 `1`。
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
    "process_id": 2,
    "config": {"num_samples": 1, "seed": 0}
  }'
```

HLS 指令示例：

```bash
curl -X POST http://127.0.0.1:8000/api/reoptimize-command \
  -H 'Content-Type: application/json' \
  -d '{
    "method": "HLS",
    "process_id": 4,
    "config": {"seed": 0, "total_time_seconds": 20}
  }'
```

服务端收到指令后会暂停仿真，按指定算法和参数、在 `process_id` 指定的工艺
范围内执行重调度，重新计算所选工艺的运输及加工时间；成功或失败后都会恢复
仿真。其他工艺的待加工队列不会被清空、重排或重新分配。多个指令并发到达时
由管理器的互斥锁串行执行。

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
“自动插单”和“手动插单”位于页面左侧作业状态面板中，“手动插单”可以在
仿真运行期间立即触发一次相同的批量插单。

Web 左侧订单列表按 Job 的提交批次展示订单：

- 初始数据源中的全部 Job 属于第一个订单，仿真时刻 `0` 下命名为 `T+0`。
- 每次自动插单或手动插单生成的全部 Job 包装为一个新订单。
- 订单名称使用提交时的仿真时间戳；同一时刻重复提交时依次追加 `#2`、
  `#3`，保证订单号可用于取消和日志追踪。
- 订单状态根据其 Job 汇总为进行中、已完成、已取消或部分完成。

自动插单开关也可以通过 API 设置：

```bash
curl -X POST http://127.0.0.1:8000/api/auto-job-submission \
  -H 'Content-Type: application/json' \
  -d '{"enabled": true}'
```

### 订单取消 API

仿真运行期间可以取消尚未完成的 Job：

```bash
curl -X POST http://127.0.0.1:8000/api/jobs/cancel \
  -H 'Content-Type: application/json' \
  -d '{"job_id": 3}'
```

批量取消使用 `job_ids` 数组：

```bash
curl -X POST http://127.0.0.1:8000/api/jobs/cancel \
  -H 'Content-Type: application/json' \
  -d '{"job_ids": [3, 5, 8]}'
```

也可以使用订单语义的等价接口：

```bash
curl -X POST http://127.0.0.1:8000/api/orders/cancel \
  -H 'Content-Type: application/json' \
  -d '{"order_ids": ["T+20", "T+40"]}'
```

订单级取消会取消订单中的全部 Job；也可以同时传 `job_ids` 取消额外选中的
作业。旧的 `job_id`/`order_id` 单 Job 调用方式继续兼容。取消规则如下：

1. 已进入 `processing` 状态的当前工序不中断，继续完成加工。
2. 该 Job 尚未开始的工序全部移出机器待加工队列，并标记为 `canceled`。
3. 删除这些待加工工序对应的启动、完成和运输事件。
4. 从 `processing_queue` 移除对应 Order，并加入新增的
   `canceled_orders` 列表。
5. 如果取消的工序位于某台机器队列首位，自动为下一道有效工序补建启动
   事件，保证其他 Job 继续运行。
6. 后续 DRL/HLS 或插单重调度不会重新分配已取消的工序。
7. 已完成 Job 也可以转为已取消；已有工序的加工记录会保留，但对应 Order
   会从 `finished_queue` 移入 `canceled_orders`。
8. 取消完成后自动调用与动态插单相同的模拟器内置贪心启发式：剩余未完成
   工序重新选择加工时间最短的合格机器，并从当前仿真时刻重建机器队列、
   运输时间和开始时间，避免保留被取消工序造成的空闲槽。
9. 被取消工序的入站运输段按实际发生状态处理：
   - 运输尚未开始时，清除该工序的运输起止、运输时间、运输能耗和已提交
     运输能耗。
   - 运输已经开始时，不中断运输；运输完成事件会继续执行并结算能耗。
   - 运输已经完成、但后续工序仍在等待加工时，保留运输记录并计入运输
     能耗。目标机器等待不会推迟已经具备条件的运输。
   - 如果重调度把进行中的运输改派到另一台机器，先按原起止时间完成到原
     目标机器的第一段运输，再从原目标机器向新目标机器执行第二段运输。
     两段运输分别产生完成事件、动画记录并累加时间与能耗。
   - 重调度前会校验旧运输段的来源机器和前序实际完工时间；如果前序工序
     在后续重调度中被推迟，旧运输段会被废弃并按新的前序完工时间重算，
     不允许物料早于前序完工开始运输。
   - 前序工序提前完工时，尚未开始的后续运输会同步前移到实际完工时刻。
   - 运输完成或机器工序完成时，如果该工序是机器队列首项、前序已完成且
     目标机器空闲，会取消未来启动事件并立即在当前时刻开始加工，不再等待
     原始计划开始时间。

Web 左侧作业状态面板提供“取消订单”按钮。弹窗顶部列出订单号，勾选订单
会同步勾选其全部可取消 Job；下方仍可按 Job 多选。已取消订单和作业作为
历史状态展示并禁止重复取消。确认后通过一次批量请求提交 `order_ids` 和
`job_ids`。

响应中的主要字段：

- `removed_operation_count`：本次移除的待加工工序数量。
- `removed_operations`：被取消工序的机器、计划时间、状态及被清理的运输
  起止时间、运输时间、运输能耗和运输完成标志。
- 计划和日志中的 `transport_segments` 保存逐段运输；单段运输保持原字段
  兼容，多段运输可分别查看来源、目标、起止时间、时长、能耗和完成状态。

Web 的活动计划快照会在每次事件和仿真结束时重新同步。仿真完成后，待加工
队列和运输动画只使用当前 `planned_operations`；已取消但运输已经发生的
历史记录仍保留在运行日志和能耗统计中，不会作为活动待加工项显示。

仿真器结束时会检查所有工序状态。如果事件队列已经为空，但仍存在
`pending`、`scheduled` 或 `processing` 工序，仿真会标记为失败，而不是错误
显示为正常完成。Web 中只有全部工序均为 `completed` 的 Job 才显示“已完成”。

页面中部提供三个可点击标签：

- “工序调度”：显示机器时间线、当前加工、待加工队列和运输关系。
- “设备状态看板”：每台设备使用独立卡片显示流式检测数据和趋势图。
- “物料库存看板”：每台设备使用独立卡片显示当前工艺的全部直接物料库存。

设备状态看板不读取模拟器机器状态或本地 CSV，而是按照
`前端对接文档.md` 调用流式检测服务：

- `GET /api/v1/meta`：读取字段类型、单位和固定显示范围。
- `GET /api/v1/machines`：读取设备编号列表。
- `GET /api/v1/overview`：每秒获取一次当前调度数据集对应机器数量的
  检测值、`label` 和 `warn`。
- `GET /api/v1/predict`：每 5 个仿真秒调用一次，`t` 与同一时刻的
  `overview` 请求一致；预测结果 `is_alarm=true` 时，通过模拟器现有的
  `MachineAnomalyEvent` 流程为对应机器随机注入一种设备异常并更新机器状态。

服务地址和刷新参数在 `simulator_config.json → detection_data` 中配置，默认
地址为 `http://192.168.1.68:8068`。前端维护每台设备最近 `60` 次
`overview` 快照，并使用 ECharts 绘制以下字段：

`overview` 请求会按当前调度数据集的 `num_machines` 传入
`machine_count`。切换数据源时，检测缓冲和卡片会清空，并按新的机器数量
重新开始每秒请求。

Web 倍速只提供 `1x`、`2x`、`5x`。每个现实秒按当前倍速获取对应数量的
overview 逻辑时间点：

- `1x`：每秒获取 1 组数据。
- `2x`：每秒获取 2 组数据。
- `5x`：每秒获取 5 组数据。

预测调用只选择时间点能被 `prediction_interval` 整除的 `overview` 数据，
同一仿真中相同时间点最多处理一次。预测命中后，按仿真种子、时间点和机器
编号随机选择短故障、中等故障、长故障或降额运行，并分别使用默认持续时间
`3`、`10`、`30`、`15` 个仿真秒。已经处于故障、维修或降额状态的机器不会
重复注入。Web 后端代理接口为：

```http
GET /api/detection/predict?t=85&machine_count=8
```

响应除模型预测结果外，还包含 `injected_machine_ids`、`injected_events` 和
`skipped_machines`，便于确认哪些预测告警实际改变了模拟器状态。

设备检测数据流与仿真状态同步：

- 仿真开始运行后才启动首次 overview 请求和每秒轮询。
- 暂停或进入重调度时停止轮询，图表保留并冻结。
- 恢复运行时从原逻辑时间继续追加数据。
- 停止或仿真完成时停止轮询，保留最后采集数据。
- 再次启动仿真时清空旧缓冲，并按新仿真的机器数量重新采集。

| 字段 | 含义 | 单位 |
| --- | --- | --- |
| `TP2` | 压力特征 | bar |
| `TP3` | 压力特征 | bar |
| `H1` | 压力特征 | bar |
| `DV_pressure` | 压差 | bar |
| `Reservoirs` | 储气罐压力 | bar |
| `Oil_temperature` | 油温 | °C |
| `Motor_current` | 电机电流 | A |

由于七个字段量纲不同，折线图使用 `/meta` 返回的全局固定范围进行归一化，
Tooltip 仍显示原始值。图中的橙色背景表示 `warn` 预警区，红橙色背景表示
`label` 故障区；数据集回绕时折线会断开。展示层只使用 7 个连续检测字段：

`TP2`、`TP3`、`H1`、`DV_pressure`、`Reservoirs`、
`Oil_temperature`、`Motor_current`。卡片显示这些字段的当前值并绘制趋势，
每次 overview 响应只追加一个时间点，浏览器最多保留最近 60 个点。
ECharts `5.5.1` 已保存到 `web/vendor/echarts.min.js`，不依赖外部 CDN。

- `processing_operations`：取消时已经加工、继续执行到完成的工序。
- `canceled_job_ids`：模拟器 `canceled_orders` 中记录的取消 Job 编号。
- `newly_canceled_job_ids`：本次批量请求中新取消的 Job。
- `already_canceled_job_ids`：请求中此前已经取消、未重复修改的 Job。
- `greedy_reschedule`：取消后的贪心重调度结果，包括未完成工序数量和换机数量。
- `already_canceled`：重复取消时返回 `true`，不会重复修改仿真状态。

### 仿真暂停与继续 API

仿真运行期间可以暂停或恢复仿真：

```bash
curl -X POST http://127.0.0.1:8000/api/pause \
  -H 'Content-Type: application/json' \
  -d '{"paused": true}'
```

将 `paused` 设置为 `false` 即可恢复仿真。暂停期间仿真时钟停止推进，
Web 页面中的“暂停仿真”按钮会切换为“继续仿真”。暂停状态下不允许执行
重调度、插单或订单取消，恢复后才能继续调用这些接口。

运行或暂停期间也可以点击“停止仿真”彻底结束当前仿真线程：

```bash
curl -X POST http://127.0.0.1:8000/api/stop \
  -H 'Content-Type: application/json' \
  -d '{}'
```

停止后状态为 `stopped`，已执行的事件和部分运行结果会保留，Web 服务继续
运行，可以重新选择数据源并再次启动。

### 机器故障设定与处置 API

仿真目前支持短故障、中等故障、长故障和降额运行四类设备异常。异常从当前
仿真时刻开始，持续时间必须为整数，并且必须位于对应类型允许的范围内。

异常处置由 `simulator_config.json` 控制：

```json
{
  "anomaly_handling": {
    "enabled": false
  }
}
```

默认关闭，此时只进行正常调度仿真：

- 检测预测仍可调用，但 `is_alarm=true` 不会向模拟器注入异常。
- “插入设备异常”和“自动插入异常”控件禁用。
- 异常处置 API 和自动异常设置会返回错误。
- 不创建 `MachineAnomalyEvent` 或 `MachineRecoveryEvent`，也不会触发异常重调度。
- 设备状态看板的数据展示不受影响。

设置为 `true` 后恢复全部异常处置逻辑。

| `anomaly_type` | 机器状态 | 可选范围 | 默认值 | 处置方式 |
| --- | --- | ---: | ---: | --- |
| `short_failure` | `repairing` | 1–5 | 3 | 中断当前工序，放回原机器待加工队列队首，等待恢复后重新加工 |
| `medium_failure` | `repairing` | 5–15 | 10 | 中断当前工序，优先转移到其他可加工机器队首；没有替代机器时留在原机器 |
| `long_failure` | `failed` | 15–45 | 30 | 中断当前工序，故障时执行 DRL 重调度，恢复时再次执行；故障机器不参与分配 |
| `degraded` | `degraded` | 10–20 | 15 | 不中断加工，恢复前加工时间乘以 1.5 后向下取整，加工能耗保持不变 |

异常恢复时间统一计算为：

```text
recovery_time = anomaly_started_at + duration
```

每次异常都会产生 `MachineAnomalyEvent`，持续时间结束后产生
`MachineRecoveryEvent`。恢复事件会清除机器异常类型、恢复时间和性能系数，
释放设置了 `ready_not_before` 的工序，并重新检查机器队列是否可以继续加工。

#### 长故障

长故障适用于机器需要长时间停机的场景：

1. 机器状态设置为 `failed`。
2. 当前加工工序被中断，原 `OperationFinishEvent` 被取消。
3. 已经发生的部分加工能耗保存在 `interrupted_processing_energy`。
4. 只有故障机器可以加工的工序进入等待恢复列表。
5. 故障时立即调用 DRL 调度器，为未完成工序重新分配加工机器，故障机器
   被强制排除在候选机器之外。
6. 到达 `recovery_time` 后恢复机器，再次调用 DRL 重调度，将恢复后的机器
   重新纳入候选机器。
7. DRL 输出中仍包含故障机器或缺少动态新增 Job 的工序时，模拟器会排除
   故障机器并补齐这些工序的机器分配，随后重新计算运输时间、运输能耗和
   工序开始时间。

#### 短故障

短故障适用于不需要转机的短时间维修：

1. 机器状态设置为 `repairing`。
2. 当前工序被中断，实际开始时间清空。
3. 工序插入原机器待加工队列队首。
4. 工序的 `ready_not_before` 设置为恢复时间。
5. 恢复事件到达后，如果前序工序和运输已经完成，则重新启动该工序。
6. 不调用 DRL。

#### 中等故障

中等故障会优先尝试把当前工序转移到其他机器：

1. 机器状态设置为 `repairing`。
2. 当前工序被中断，并记录已消耗的加工能耗。
3. 排除当前机器以及所有处于 `failed`、`repairing` 状态的机器。
4. 在剩余可加工机器中选择加工时间最短的一台。
5. 工序插入目标机器待加工队列队首，并生成新的运输时间和运输能耗。
6. 如果没有其他机器可以加工，则同短故障一样放回原机器队首。
7. 工序等待原机器恢复事件到达后再启动；不调用 DRL。

#### 降额运行

降额运行不会中断机器上的加工任务：

1. 机器状态设置为 `degraded`，`performance_factor` 设置为 `1.5`。
2. 当前工序的新结束时间按下式计算：

   ```text
   actual_start + floor(base_processing_time × 1.5)
   ```

3. 在机器恢复前新启动的工序也使用相同公式。
4. 加工能耗仍使用基础加工能耗，不随加工时间延长而增加。
5. 恢复事件到达后，机器性能系数恢复为 `1.0`。
6. 不调用 DRL。

#### 异常中断后的数据规则

- 原机器上的待加工启动事件会被清理。
- 已经产生的实际加工能耗不会丢失。
- 重新加工时从新的实际开始时间重新计算完整加工耗时。
- 中等故障转机时保留逐段运输记录，并重新计算时间和能耗。
- 机器处于 `failed` 或 `repairing` 时不能再次注入故障；降额机器仍可被后续异常中断。

#### Web 操作方式

Web 右侧“异常列表”显示以下四类事件：

- 插单：`OrderInsertEvent`
- 订单取消：`OrderCancelEvent`
- 设备异常：`MachineAnomalyEvent`
- 设备恢复：`MachineRecoveryEvent`

“插入设备异常”弹窗中，设备只显示设备号。切换异常类型时，持续时间输入框
会自动更新可选范围和默认值。

启用“自动插入异常”后，从启用时刻开始每隔 `40` 个仿真时间单位执行一次：

1. 从当前 `failed`、`repairing`、`degraded` 之外且没有活动异常的机器中
   随机选择一台。
2. 随机选择短故障、中等故障、长故障或降额运行。
3. 在该异常类型的可选范围内随机生成整数持续时间。
4. 按正常异常流程创建 `MachineAnomalyEvent`；持续时间结束后创建
   `MachineRecoveryEvent`。

如果触发时所有机器都有活动异常，本次不插入异常，并在下一个 `40` 个
仿真时间单位后再次检查。关闭选项后不再产生新的自动异常。

#### 机器异常 API

仿真运行期间可以模拟加工机器异常：

```bash
curl -X POST http://127.0.0.1:8000/api/anomalies/machine \
  -H 'Content-Type: application/json' \
  -d '{
    "machine_id": 3,
    "anomaly_type": "long_failure",
    "duration": 30
  }'
```

响应中会包含 `machine_id`、`anomaly_type`、`machine_status`、
`anomaly_started_at`、`recovery_time`、`processing_time_factor`、
`affected_operations`、`event_id`、`event_type` 和
`reschedule_method` 等信息。

### 机器异常批量测试脚本

先运行 `python run.py` 启动 Web 服务；脚本会自动启动仿真，然后执行：

```bash
python scripts/live_machine_anomaly_test.py
```

默认配置为：

- 默认 4 轮中，短故障、中等故障和降额各注入 `4` 次，长故障只注入
  `2` 次，共 `14` 次。
- 注入顺序为长故障、短故障、中等故障、降额。
- 优先选择正在加工且没有活动异常的机器。
- 出现重复故障时为每类异常选用不同机器。
- 仿真倍速设置为 `2x`。
- 默认异常时长为：长故障 `15/20`、短故障 `2/3`、中等故障 `5/7`、
  降额运行 `10/12`。
- 注入完成后等待仿真结束并输出汇总。

常用参数：

```bash
python scripts/live_machine_anomaly_test.py \
  --rounds 6 \
  --long-failure-count 3 \
  --interval 2 \
  --speed 2 \
  --machine-ids 0,1,2,3,4,5,6,7
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

页面左侧先按提交时间戳显示订单列表，订单内展示该批次全部 Job；下方按
作业明细按“冲压中”、“焊装中”、“涂装中”、“总装中”、“已完成”和
“已取消”六个可折叠分组显示 Job 的实时状态。加工中的 Job 根据
`current_stage` 自动移动到对应工艺分组。
取消时仍在加工的 Job 会保留当前加工信息，直到该工序完成。自动插单和
手动插单按钮也位于该面板中。顶部
提供暂停/继续仿真按钮。页面中部显示机器工序时间轴动画，右侧显示完整
设备异常与恢复列表，并提供“插入设备异常”按钮，可选择设备、异常类型和
持续时间。当前
仿真时刻固定在时间轴中央，左侧为已完成工序，右侧为待加工工序，跨过中心线
的工序为当前加工中工序。默认使用 `simulator_config.json` 中
`visualization.speed=2` 的展示倍速。

每台机器的时间轴右侧还有独立的待加工队列。待加工工序按计划开始时间排列；
当前工序完成后，队首工序会自动从待加工队列进入中央当前工序时间线。
未开工工序只在待加工队列中显示，不会提前绘制到主调度时间线；工序开始后
才会从队列移除并进入当前加工区域，完成后保留在中央时间线左侧。
待加工队列与主时间线各占机器标签以外的可用宽度的一半，并根据实际空间
动态显示最多 8 道工序。同一工件的待加工、加工中和已完成工序保持同一色相。

浏览器使用动画帧在状态轮询之间连续推进时间线，切换倍速时会重新校准动画
时钟，避免等待下一批事件造成明显停顿。

调度面板默认填满浏览器可用高度。页面顶部可调整显示比例，比例会同时缩放
工序调度的机器行、工序条、文字和横向时间窗口，也会缩放设备检测卡片、
检测图表、物料库存卡片及其文字；放大后可通过时间轴右侧滚动条查看
全部机器。

页面顶部提供数据源选择框，默认数据来自 `datasets/raw`、`datasets/add`
与 `datasets/delivery_cost` 中完整配对的文件。选择数据源后点击
“启动仿真”，服务端才会创建该实例的 Simulator。仿真结束后 Web 服务保持
运行，可以切换数据源再次启动。

Web 服务通常保持运行，按 `Ctrl+C` 停止服务。如需临时指定倍速：

```bash
python run.py --speed 2
```

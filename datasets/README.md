# datasets 数据说明

当前 `datasets` 目录包含两套数据：

- 用于生产调度的四工艺 FJSP 数据。
- 用于设备状态和异常检测的流式设备数据。

## 1. 四工艺调度数据

当前包含 `309` 组同名调度实例，覆盖冲压、焊装、涂装、总装四个流程。

| 工艺 | 加工时间目录 | 能耗与运输目录 | 文件数 |
| --- | --- | --- | ---: |
| 冲压 | `raw/` | `add/` | 309 |
| 焊装 | `raw1/` | `add1/` | 309 |
| 涂装 | `raw2/` | `add2/` | 309 |
| 总装 | `raw3/` | `add3/` | 309 |

四个工艺通过相同文件名关联同一个实例和 Job，例如：

```text
raw/example.fjs
add/example.fjs
raw1/example.fjs
add1/example.fjs
raw2/example.fjs
add2/example.fjs
raw3/example.fjs
add3/example.fjs
delivery_cost/example.fjs
process_generation_configs/process_1/example.json
process_generation_configs/process_2/example.json
process_generation_configs/process_3/example.json
process_generation_configs/process_4/example.json
material_configs/process_1/example.json
material_configs/process_2/example.json
material_configs/process_3/example.json
material_configs/process_4/example.json
material_consumption/process_1/example.json
material_consumption/process_2/example.json
material_consumption/process_3/example.json
material_consumption/process_4/example.json
```

四个工艺的所有数据均由以下命令从 `raw/` 一次性确定性生成：

```bash
python datasets/generate_followup_processes.py
python datasets/generate_followup_processes.py --check
```

## 2. 调度数据格式

### 2.1 raw 文件

第一行为：

```text
num_jobs num_machines metadata
```

后续每个 Job 一行：

```text
operation_count
option_count machine_id processing_time
option_count machine_id processing_time
...
```

说明：

- `num_jobs`：当前实例的 Job 数量。
- `num_machines`：当前工艺的机器数量。
- `operation_count`：该 Job 在当前工艺中的工序数量。
- `option_count`：该工序的可选机器数量。
- `machine_id`：机器编号，从 `1` 开始。
- `processing_time`：该机器加工该工序所需时间。

### 2.2 add 文件

`add/add1/add2/add3` 只保存加工能耗和运输数据，不保存交付信息。

文件内容顺序：

1. 前 `num_jobs` 行：每个 Job 的加工能耗，结构同 raw 文件，机器后第二个
   数值表示该机器对应的加工能耗。
2. 接下来 `num_machines` 行：运输时间矩阵。
3. 最后 `num_machines` 行：运输能耗矩阵。

运输矩阵大小均为 `num_machines × num_machines`，矩阵对称，对角线为 `0`。

## 3. 交付成本数据

`delivery_cost/` 包含 `309` 个文件，每个调度实例对应一个交付成本文件。
四个工艺共享同一份实例交付信息，不按工艺重复存储。

文件第一行为字段说明：

```text
# priority ready_time due_time earliness_cost tardiness_cost
```

后续每个 Job 一行：

```text
priority ready_time due_time earliness_cost tardiness_cost
```

| 字段 | 含义 |
| --- | --- |
| `priority` | Job 优先级/权重，对应模型中的 `weight` |
| `ready_time` | Job 最早可开始加工时间 |
| `due_time` | 完成四个工艺后的计划交付时间 |
| `earliness_cost` | 单位提前完成成本系数 |
| `tardiness_cost` | 单位延期完成成本系数 |

交付成本计算：

```text
delivery_cost = priority × (
    earliness × earliness_cost
    + tardiness × tardiness_cost
)
```

## 4. 工艺生成配置与物料数据

### 4.1 逐实例工艺生成配置

`process_generation_configs/` 按工艺分为 `process_1/` 至 `process_4/`，每个实例对应
一个同名 `.json` 文件，记录：

- 实例名、工艺编号、工艺名和文件版本。
- Job 数、机器数和工序数。
- 每个 Job 的产品变体及冲压基准时间、基准能耗。
- 每个 Task 的加工时间、加工能耗和可选机器。
- 每个机器选项的加工时间和加工能耗。
- 机器间运输时间矩阵和运输能耗矩阵。
- 时间比例、能耗比例、机器效率系数和固定种子规则。

物料消耗不写入工艺生成配置，统一保存在独立的
`material_consumption/` 数据集。

### 4.2 工艺物料消耗

`material_consumption/` 按工艺分为 `process_1/` 至 `process_4/`。该数据集
只保存 Job 或 Task 的物料编号和用量，不包含加工时间、能耗、机器、产品描述
或其他调度字段。

冲压采用 Job 级结构：

```json
{
  "instance": "example.fjs",
  "process_id": 1,
  "jobs": [
    {
      "job_id": 0,
      "materials": [
        {
          "material_id": "M1_STEEL_CR_LOW_CARBON",
          "quantity": 1.0
        }
      ]
    }
  ]
}
```

冲压 Stage 内只有领料工序消耗一片板料，因此每个 Job 只记录一组 Job 级
物料用量，不按冲压 Task 重复记录。

焊装、涂装和总装采用 Task 级结构：

```json
{
  "instance": "example.fjs",
  "process_id": 2,
  "jobs": [
    {
      "job_id": 0,
      "tasks": [
        {
          "stage_operation_id": 2,
          "materials": [
            {
              "material_id": "M2_WELD_WIRE",
              "quantity": 0.8
            }
          ]
        }
      ]
    }
  ]
}
```

后三个工艺的每个 Task 都会出现在 `tasks` 中；不消耗直接材料的 Task 使用
空数组 `"materials": []`。物料单位通过 `material_master.csv` 中的
`material_id` 关联，不在每个用量记录中重复保存。

### 4.3 每台机器的物料总量

`material_configs/` 按工艺分为 `process_1/` 至 `process_4/`。每个实例的
配置文件只保存该实例中每台机器、每种物料的初始总量：

```json
{
  "instance": "example.fjs",
  "process_id": 2,
  "machines": [
    {
      "machine_id": 1,
      "materials": [
        {
          "material_id": "M2_WELD_WIRE",
          "quantity": 2.6
        }
      ]
    }
  ]
}
```

每台机器都包含本工艺全部直接物料。机器数量由工艺生成配置中的
`num_machines` 确定。生成器先读取每个 Task 的物料消耗及其可选机器，
并将该 Task 的完整物料需求计入每一台可加工它的机器。这样无论初始排程
最终把 Task 分配到哪台可选机器，初始 Job 都有对应物料可用。机器不能
加工的任何 Task 不会贡献库存，因此无关物料数量仍可以为 `0`。

每台机器、每种物料的目标库存为：

```text
目标库存 = ceil(
    该机器可加工的全部初始 Task 物料需求之和
    × 1.20 / 计量精度
) × 计量精度
```

其中 `1.20` 为初始工序覆盖量之外的备料系数。由于同一 Task 可能选择多台
兼容机器，初始库存总量通常高于单次实际 BOM 总消耗，但只覆盖数据集内已有
Job，不包含后续动态插入的 Job。因此无插单时不会因机器换选而频繁缺料，
动态插单后则会新增消耗并触发物料异常。件和套按整数取整，kg 和 L 按
`0.1` 向上取整；同实例、同工艺、同输入数据的结果完全确定。

`material_configs` 不再包含安全库存、容量、补货数量、补货提前期、物料名称
或工艺描述。这些附加策略需要时由后续物料管理模块单独维护。

`material_master.csv` 是上述配置共用的物料主数据，字段为：

```text
material_id,material_name,unit,category
```

### 4.4 模拟器运行时加载

`simulator/dataset.py` 会根据 `add/add1/add2/add3` 文件自动定位同实例的
`material_configs/process_N` 和 `material_consumption/process_N` 文件。
四工艺初始化时，机器使用本工艺的本地机器编号读取库存，Job 使用相同 Job
编号和 Task 的 `stage_operation_id` 读取消耗数据。

| 运行时对象 | 字段 | 内容 |
| --- | --- | --- |
| `Machine` | `materials` | `{material_id: quantity}` 形式的机器物料总量 |
| `Job` | `material_consumption` | 按工艺编号保存 Job 级和后三工艺 Task 级消耗 |
| `Task` | `material_consumption` | 当前 Task 的 `{material_id: quantity}` 消耗 |

`Job.material_consumption[stage_id]` 的结构为：

```json
{
  "job_materials": {
    "M1_STEEL_CR_LOW_CARBON": 1.0
  },
  "tasks": {
    "2": {
      "M2_WELD_WIRE": 0.8
    }
  }
}
```

冲压工艺只写入 `job_materials`，`tasks` 为空；焊装、涂装和总装只写入
`tasks`，`job_materials` 为空。动态插单生成的 Job 会从所选取的模板 Job
复制同一套物料消耗配置。

模拟器会在四个工艺的每道工序开始前检查当前机器的 `materials` 库存。
满足需求时，在工序真正开始时扣减对应物料；不满足时，工序不会消耗时间或
开始加工，而是生成 `MaterialReplenishmentEvent` 和
`MaterialRecoveryEvent`。补料事件登记该机器需要到达的缺口物料，恢复事件
在默认 `5.0` 个仿真时间单位后执行实际入库并再次校验，随后重新投放
`OperationStartEvent`，然后完成扣料并开始加工。该到货时间可通过
`simulation.material_replenishment_lead_time` 配置。

补料不是只补到工序刚好够用，而是把当前工序涉及的全部物料统一补到：

```text
补料阈值 = 当前工序对该物料的需求量 × 3.0
```

因此本次工序扣料完成后，每种物料仍保留约两份当前工序用量。即使某一种
物料只是略低于阈值，只要该工序触发补料，其他低于阈值的工序物料也会一起
补足。阈值倍数可通过
`simulation.material_replenishment_target_factor` 配置。

## 5. 四工艺数据的字段关系

- 四个阶段使用相同的 Job 数量。
- 同一 Job 在四个阶段使用相同 Job 顺序。
- Job 的优先级、就绪时间、交付时间和成本系数来自同一份
  `delivery_cost/<instance>.fjs`。
- 各工艺分别拥有自己的机器数量、工序数量、加工时间、加工能耗和运输矩阵。

### 5.1 数据范围与生成依据总表

#### 5.1.1 实例规模、Task 和机器数量

| 数据项 | 范围或固定值 | 生成依据 |
| --- | --- | --- |
| 数据集实例数 | `309` | 以 `raw/*.fjs` 的实际文件数量为准 |
| 每实例 Job 数 | `6–30` | 直接继承原始实例，四个工艺保持一致 |
| 冲压机器数 | `4–18` | 直接继承原始实例 |
| 每 Job 冲压 Task 数 | `3–25` | 直接继承原始实例 |
| 每实例冲压 Task 总数 | `36–387` | 该实例所有 Job 的冲压 Task 数之和 |
| 焊装 Task 数 | 固定 `6` | 焊装工艺模板包含定位、点焊、填充焊、胶接、连接与密封、检查 |
| 涂装 Task 数 | 固定 `6` | 涂装工艺模板包含前处理电泳、密封防石击、底漆、面漆、清漆、烘烤检查 |
| 总装 Task 数 | 固定 `8` | 总装工艺模板包含车门线束、内饰、动力底盘、能源模块、玻璃座椅、车轮外饰、油液、终检 |
| 后三工艺 Task 合计 | 固定 `20` | 焊装 `6` + 涂装 `6` + 总装 `8` |
| 每 Job 四工艺 Task 总数 | `23–45` | 冲压 `3–25` + 后三工艺 `20` |
| 焊装机器数 | `5–8` | `clamp(ceil(0.60 × 冲压机器数 + 0.04 × Job数), 5, 8)` |
| 涂装机器数 | `4–7` | `clamp(ceil(0.50 × 冲压机器数 + 0.03 × Job数), 4, 7)` |
| 总装机器数 | `6–10` | `clamp(ceil(0.75 × 冲压机器数 + 0.05 × Job数), 6, 10)` |
| 冲压 Task 可选机器数 | 继承 `raw` 中该 Task 的实际选项数 | 不重新生成冲压工序的机器能力 |
| 焊装和总装 Task 可选机器数 | 每 Task `1–3` 台 | 从本工艺机器池中按固定种子无重复抽取 |
| 涂装 Task 可选机器数 | 每 Task `1–2` 台 | 从本工艺机器池中按固定种子无重复抽取 |
| 单实例四工艺调度文件数 | `8` 个 `.fjs` | `raw/add`、`raw1/add1`、`raw2/add2`、`raw3/add3` |
| 单实例配置和交付文件数 | `12` 个 `.json` + `1` 个交付 `.fjs` | 四套工艺生成配置、四套物料消耗、四套机器物料总量，共享一份交付成本文件 |
| 工艺生成配置文件总数 | 每工艺 `309` 个，共 `1236` 个 | 四个工艺各对应全部 `309` 个实例 |
| 物料消耗文件总数 | 每工艺 `309` 个，共 `1236` 个 | 冲压按 Job、后三工艺按 Task 记录物料用量 |
| 机器物料总量文件总数 | 每工艺 `309` 个，共 `1236` 个 | 每个实例、每台机器、每种直接物料记录初始总量 |
| 交付成本文件总数 | `309` 个 | 每个调度实例共享一份四工艺交付信息 |

#### 5.1.2 加工时间和加工能耗

| 数据项 | 范围或公式 | 生成依据 |
| --- | --- | --- |
| 冲压机器加工时间 | 继承原始正整数值 | `raw` 中“工序—机器—加工时间”原始数据 |
| 冲压机器加工能耗 | `4–15` 的整数 | 为 `raw` 中每个实际机器选项生成确定性加工能耗 |
| Job 冲压基准时间 | `Σ Task 所有机器加工时间的平均值` | 多机器 Task 使用平均值，不使用最快机器值 |
| Job 冲压基准能耗 | `Σ Task 所有机器加工能耗的平均值` | 使用生成的冲压机器能耗计算 |
| 焊装时间比例 | 完整范围 `0.55–0.80`，默认 `0.65` | 在默认值 `±0.03` 内扰动后裁剪到完整范围 |
| 焊装能耗比例 | 完整范围 `0.55–0.85`，默认 `0.70` | 在默认值 `±0.03` 内扰动后裁剪到完整范围 |
| 涂装时间比例 | 完整范围 `0.40–0.65`，默认 `0.50` | 在默认值 `±0.03` 内扰动后裁剪到完整范围 |
| 涂装能耗比例 | 完整范围 `0.45–0.75`，默认 `0.58` | 在默认值 `±0.03` 内扰动后裁剪到完整范围 |
| 总装时间比例 | 完整范围 `0.60–0.90`，默认 `0.78` | 在默认值 `±0.03` 内扰动后裁剪到完整范围 |
| 总装能耗比例 | 完整范围 `0.45–0.75`，默认 `0.59` | 在默认值 `±0.03` 内扰动后裁剪到完整范围 |
| 后三工艺确定性扰动 | `0.95–1.05` | 使用实例、工艺和 Job 固定种子生成 |
| 焊装单 Task 基础时间 | `4–25` | Task 模板权重分配后执行上下限裁剪 |
| 焊装单 Task 基础能耗 | `2–24` | Task 模板权重分配后执行上下限裁剪 |
| 涂装单 Task 基础时间 | `7–25` | Task 模板权重分配后执行上下限裁剪 |
| 涂装单 Task 基础能耗 | `5–25` | Task 模板权重分配后执行上下限裁剪 |
| 总装单 Task 基础时间 | `6–32` | Task 模板权重分配后执行上下限裁剪 |
| 总装单 Task 基础能耗 | `4–24` | Task 模板权重分配后执行上下限裁剪 |
| Job 后三工艺目标时间下限 | `Task数 × 单Task最小时间` | 防止 Job 总时间低于所有 Task 最小时间之和 |
| Job 后三工艺目标时间上限 | `Task数 × 单Task最大时间` | 防止 Job 总时间高于所有 Task 最大时间之和 |
| Job 后三工艺目标能耗下限 | `Task数 × 单Task最小能耗` | 防止 Job 总能耗低于所有 Task 最小能耗之和 |
| Job 后三工艺目标能耗上限 | `Task数 × 单Task最大能耗` | 防止 Job 总能耗高于所有 Task 最大能耗之和 |
| Task 时间分配误差 | 调整到同工艺权重最大的 Task | 保证 `Σ Task基础时间 = Job目标时间` |
| Task 能耗分配误差 | 调整到同工艺权重最大的 Task | 保证 `Σ Task基础能耗 = Job目标能耗` |
| 焊装机器时间系数 | `0.85–1.20` | 表示不同焊装设备的速度差异 |
| 焊装机器能耗系数 | `0.90–1.15` | 表示不同焊装设备的能效差异 |
| 涂装机器时间系数 | `0.90–1.15` | 表示不同涂装线的节拍差异 |
| 涂装机器能耗系数 | `0.92–1.12` | 表示不同涂装线的能效差异 |
| 总装机器时间系数 | `0.85–1.20` | 表示不同总装工位的作业效率差异 |
| 总装机器能耗系数 | `0.90–1.15` | 表示不同总装工位的能效差异 |
| 机器选项加工时间 | 至少为 `1` 的正整数 | `round(Task基础时间 × 机器时间系数)`，结果小于 `1` 时取 `1` |
| 机器选项加工能耗 | 至少为 `1` 的正整数 | `round(Task基础能耗 × 机器能耗系数)`，结果小于 `1` 时取 `1` |

产品变体会进一步修正时间和能耗：

| 产品条件 | 时间修正 | 能耗修正 | 生成依据 |
| --- | ---: | ---: | --- |
| 双色涂装 | `×1.05` | `×1.03` | 双色车身需要额外面漆和烘烤作业 |
| HEV 总装 | `×1.03` | `×1.02` | 同时安装燃油系统和动力电池 |
| BEV 总装 | `×1.05` | `×1.04` | 电池包、电驱和高压系统装配复杂度更高 |
| 其他情况 | `×1.00` | `×1.00` | 使用标准产品系数 |

#### 5.1.3 产品变体和物料需求范围

| 数据项 | 范围或固定值 | 生成依据 |
| --- | --- | --- |
| 动力类型 | ICE `60%`、HEV `25%`、BEV `15%` | 按实例和 Job 固定种子加权抽取 |
| 车身颜色 | 4 种颜色均匀选择 | 天空灰、水晶珍珠白、闪耀黑、飞行蓝 |
| 双色车身 | 概率 `20%` | 双色时车顶使用闪耀黑，否则与车身同色 |
| 四驱类型 | BEV 固定 `AWD`；其他车型 `AWD` 概率 `30%` | 模拟不同动力和驱动配置 |
| 冲压板料 | 每个 Job 固定分配 1 种 | 4 种板料按 Job 编号循环分配 |
| 冲压直接材料消耗 | `OP0` 消耗板料 `1 piece`，后续 Task 为 `0` | 同一 Job 的多道冲压工序加工同一张在制品 |
| 焊装直接物料种类 | `6` 种 | 焊丝、结构胶、密封胶、铆钉、螺柱、螺栓螺母 |
| 涂装直接物料种类 | `12` 种 | 电泳补加材料、PVC、UBC、空腔蜡、底漆及固化剂、4 种面漆、清漆及固化剂 |
| 总装直接物料种类 | `21` 种 | 模块、总成、油液和冷媒等主要直接材料 |

焊装固定 Task 物料 BOM：

| Task | 工作内容 | 物料消耗 | 生成依据 |
| --- | --- | --- | --- |
| `W0` | 冲压件齐套、定位和夹紧 | 无直接材料消耗 | 只进行定位夹紧，不扣减材料库存 |
| `W1` | 车身主结构电阻点焊 | 无独立物料记录 | 焊接填充丝统一计入 `W2` |
| `W2` | 局部填充焊或激光钎焊 | 焊接填充丝 `0.8 kg` | 单个白车身的填充焊丝消耗 |
| `W3` | 结构胶和折边胶 | 结构胶 `1.2 kg` | 车身结构连接和折边密封用量 |
| `W4` | 铆接、螺柱、螺栓和密封 | 铆钉 `40 piece`、螺柱 `16 piece`、螺栓螺母 `8 set`、车身密封胶 `0.6 kg` | 机械连接件和车身密封用量 |
| `W5` | 连接质量和尺寸检查 | 无直接材料消耗 | 检查工序不消耗直接材料 |

涂装固定 Task 物料 BOM：

| Task | 工作内容 | 物料消耗 | 生成依据 |
| --- | --- | --- | --- |
| `P0` | 前处理和阴极电泳 | 电泳漆补加材料 `2.5 L` | 按单车电泳槽液补加量折算 |
| `P1` | 密封、抗石击和空腔防腐 | PVC 密封胶 `1.0 kg`、UBC `1.5 kg`、空腔蜡 `0.5 kg` | 车身底部、焊缝和空腔防护用量 |
| `P2` | 底漆 | 底漆 `1.8 L`、固化剂 `0.2 L` | 底漆主剂和固化剂配比 |
| `P3` | 车身和车顶面漆 | 车身颜色面漆 `2.5 L`，双色时车顶面漆额外 `0.6 L` | 单车外表面喷涂面积和双色工艺 |
| `P4` | 清漆 | 清漆 `1.8 L`、固化剂 `0.3 L` | 清漆主剂和固化剂配比 |
| `P5` | 烘烤和检查 | 无直接材料消耗 | 烘烤和检查不扣减涂料库存 |

总装固定 Task 物料 BOM：

| Task | 工作内容 | 物料消耗 | 生成依据 |
| --- | --- | --- | --- |
| `A0` | 车门、线束和电子模块 | 车门模块 `1 set`、整车线束 `1 set`、电子控制模块 `1 set` | 每个 Job 一套 |
| `A1` | 内饰、座舱和空调 | 座舱内饰模块 `1 set`、空调热管理模块 `1 set` | 每个 Job 一套 |
| `A2` | 动力总成和底盘合装 | ICE/HEV：发动机 `1 set`、变速器 `1 set`；BEV：电驱 `1 set`、减速器 `1 set`；另加底盘模块 `1 set` | 按动力类型选择 |
| `A3` | 电池或燃油模块 | ICE：燃油系统 `1 set`；BEV：动力电池包 `1 set`；HEV：燃油系统 `1 set` + 动力电池包 `1 set` | 按动力类型选择 |
| `A4` | 玻璃和座椅 | 玻璃总成 `1 set`、座椅和安全带总成 `1 set` | 每个 Job 一套 |
| `A5` | 车轮、外饰和车门 | 车轮轮胎总成 `1 set`、外饰和车门安装件 `1 set` | 每个 Job 一套 |
| `A6` | 整车油液加注 | ICE/HEV 发动机机油 `4.5 L`；ICE 变速器油 `6.0 L`，HEV/BEV `1.5 L`；冷却液 `6.0 L`、制动液 `1.0 L`、冷媒 `0.6 kg`、玻璃水 `2.0 L` | 动力类型和整车油液容量 |
| `A7` | 电检和功能检查 | 无直接材料消耗 | 检查工序不扣减材料库存 |

#### 5.1.4 运输时间和运输能耗

| 工艺 | 运输时间范围 | 运输能耗范围 | 生成依据 |
| --- | ---: | ---: | --- |
| 冲压 | `1–3` | `1–4` | 基于冲压机器数量生成独立对称运输矩阵 |
| 焊装 | `1–3` | `2–6` | 基于焊装机器数量生成独立对称运输矩阵 |
| 涂装 | `2–5` | `3–8` | 涂装线间转运距离和输送设备能耗较高 |
| 总装 | `1–3` | `1–5` | 基于总装机器数量生成独立对称运输矩阵 |
| 运输矩阵对角线 | 固定 `0` | 固定 `0` | 同一机器内部不需要运输 |
| 运输矩阵方向 | 对称 | 对称 | `time[a][b] = time[b][a]`，能耗同理 |
| 冲压到焊装工艺间运输 | 固定 `2` | 固定 `3` | 用于交付周期和工艺间运输能耗计算 |
| 焊装到涂装工艺间运输 | 固定 `4` | 固定 `5` | 用于交付周期和工艺间运输能耗计算 |
| 涂装到总装工艺间运输 | 固定 `3` | 固定 `4` | 用于交付周期和工艺间运输能耗计算 |
| 工艺间运输时间合计 | 固定 `9` | 不在阶段运输矩阵中重复存储 | `2 + 4 + 3` |

#### 5.1.5 交付时间和成本参数

| 数据项 | 范围或公式 | 生成依据 |
| --- | --- | --- |
| Job 优先级 | `1–5` | 表示不同订单的重要程度 |
| Job 就绪时间 | `0–20` | 表示投产前物料和订单准备时间 |
| 提前成本系数 | `1–10` | 表示单位提前完成时间对应的成本 |
| 延期成本系数 | `1–10` | 表示单位延期完成时间对应的成本 |
| 机器排队系数 | `0–0.60` | `min(0.60, max(0, Job数/机器数 - 1) × 0.15)` |
| 工艺周期加工时间 | 每 Job 独立计算 | 各阶段所有 Task 的机器时间平均值之和 |
| 工艺内运输时间 | `(Task数-1) × 运输矩阵非对角平均值` | 仅估算阶段内的典型运输开销 |
| 工艺排队缓冲 | `该工艺加工时间 × 排队系数` | 机器负荷越高，允许的等待时间越长 |
| 四工艺综合周期 | 四个工艺周期之和 + `9` | 包含加工、阶段内运输、排队和工艺间运输 |
| 交付缓冲系数 | 固定 `1.50` | 在综合周期基础上预留 `50%` 调度缓冲 |
| `due_time` | `ready_time + ceil(1.50 × 四工艺综合周期)` | 完整四工艺数据生成后再计算 |
| 交付成本 | `priority × (提前时间×提前成本 + 延期时间×延期成本)` | 在每个 Job 完成总装后实时计算 |

#### 5.1.6 机器物料总量

| 数据项 | 范围或公式 | 生成依据 |
| --- | --- | --- |
| 每台机器配置的物料种类 | 本工艺全部直接物料 | 冲压 `4`、焊装 `6`、涂装 `12`、总装 `21` 种 |
| 单实例单台机器物料记录数 | 与工艺物料种类数相同 | 每台机器独立保存完整线边库存 |
| 本物料总需求 | `Σ 实例内所有 Job 的该物料消耗` | 汇总全部 Task 级或 Job 级 BOM |
| 单 Task 机器需求 | Task 的完整物料消耗 | 计入每一台可加工该 Task 的机器 |
| 单机器基础需求 | `Σ 该机器可加工初始 Task 的完整物料需求` | 覆盖初始排程可能发生的机器换选 |
| 物料备料系数 | 固定 `1.20` | 为初始 Job 排程波动额外预留 `20%` |
| 目标物料总量 | `ceil(单机器基础需求 × 1.20 / 计量精度) × 计量精度` | 根据计量单位向上取整 |
| 动态 Job 库存来源 | 不预置，通过补料事件形成 | 增单后才产生大量新增物料消耗 |
| 无需求物料总量 | `0` | 该实例不需要该物料时不生成虚假库存 |
| 件和套取整精度 | `1` | 不允许出现小数件 |
| kg 和 L 取整精度 | `0.1` | 保留一位小数并向上取整 |

#### 5.1.7 随机范围和可重复性

| 数据项 | 规则 | 生成依据 |
| --- | --- | --- |
| 随机种子 | `sha256(实例名 + 工艺 + Job + Task/配置类型 + 版本号)` 的固定摘要 | 保证相同输入和脚本版本生成相同结果 |
| 范围裁剪 | 先生成比例和扰动，再裁剪到配置的完整范围 | 防止极端随机值破坏工艺约束 |
| 整数目标值 | 四舍五入后裁剪到 Job 最小/最大范围 | 调度数据只使用整数加工时间和能耗 |
| Task 总量保持 | 分配误差从权重较大的 Task 调整 | 保证 Task 之和严格等于 Job 阶段目标 |
| 机器选项 | 使用不放回抽取，按机器编号排序 | 保证一个 Task 不会重复选择同一机器 |
| 运输矩阵 | 只生成上三角，再复制到下三角 | 保证矩阵严格对称且可重复 |
| 不可行目标 | 直接抛出异常，不使用截断掩盖错误 | 防止生成与配置不一致的数据 |

### 5.2 raw 实例规模范围

当前 `raw/` 下共有 309 个实例，规模统计如下：

| 指标 | 最小值 | 中位数 | 90% 分位 | 最大值 |
| --- | ---: | ---: | ---: | ---: |
| 每实例 Job 数 | 6 | 15 | 20 | 30 |
| 冲压机器数 | 4 | 10 | 15 | 18 |
| 每 Job 冲压工序数 | 3 | 10 | 15 | 25 |
| 每实例总冲压工序数 | 36 | 100 | 300 | 387 |

raw 只作为冲压阶段输入。后续阶段不能直接按冲压工序数乘固定比例生成。

### 5.3 后三工艺固定 Task 数量

| 工艺 | 固定 Task 数 | 说明 |
| --- | ---: | --- |
| 焊装 | 6 | 定位、点焊、填充焊、胶接、机械连接与密封、检查 |
| 涂装 | 6 | 前处理与电泳、密封与抗石击、底漆、面漆、清漆、烘烤检查 |
| 总装 | 8 | 车门与线束、内饰、动力与底盘、能源模块、玻璃与座椅、车轮与外饰、油液、检查 |
| 后三工艺合计 | 20 | 完整 Job 为 raw 冲压 Task 数加 20 |

Task 数量保持固定；不同产品变体通过 `operation_type`、物料和系数体现差异。

各固定 Task 的工作内容、物料、默认加工时间和加工能耗详见项目根目录的
`物料管理设计方案.md`。

### 5.4 后三工艺机器数量

设 `S` 为冲压机器数，`J` 为 Job 数：

```text
welding_machines = clamp(ceil(0.60 × S + 0.04 × J), 5, 8)
painting_machines = clamp(ceil(0.50 × S + 0.03 × J), 4, 7)
assembly_machines = clamp(ceil(0.75 × S + 0.05 × J), 6, 10)
```

典型规模：

| 冲压规模 | 冲压机器 | Job 数 | 焊装 | 涂装 | 总装 |
| --- | ---: | ---: | ---: | ---: | ---: |
| 小规模 | 4–5 | 6–10 | 6 Task / 5 Machine | 6 / 4 | 8 / 6 |
| 中等规模 | 6–10 | 10–20 | 6 / 6–7 | 6 / 5–6 | 8 / 7–9 |
| 大规模 | 11–18 | 15–30 | 6 / 8 | 6 / 7 | 8 / 10 |

机器数表示可并行调度的聚合资源组，不是真实工厂机器人或装配工位总数。
机器能力应通过 `machine_capabilities` 或等价配置限制，不能默认所有机器可做
所有工序。

### 5.5 加工时间与能耗生成

#### 5.5.1 冲压基准

对 Job `j`：

```text
stamping_time(j) =
sum(mean_processing_time(task))

stamping_energy(j) =
sum(mean_processing_energy(task))
```

当 Task 有多个机器选项时，使用可选机器的平均值，不使用最快机器值。

#### 5.5.2 后三工艺目标比例

| 工艺 | 总时间/冲压时间 | 总能耗/冲压能耗 |
| --- | ---: | ---: |
| 焊装 | 0.55–0.80，默认 0.65 | 0.55–0.85，默认 0.70 |
| 涂装 | 0.40–0.65，默认 0.50 | 0.45–0.75，默认 0.58 |
| 总装 | 0.60–0.90，默认 0.78 | 0.45–0.75，默认 0.59 |

计算：

```text
target_time(stage,j) =
stamping_time(j)
× base_time_ratio(stage)
× product_time_factor(stage,variant)
× deterministic_noise

target_energy(stage,j) =
stamping_energy(j)
× base_energy_ratio(stage)
× product_energy_factor(stage,variant)
× deterministic_noise
```

`deterministic_noise` 建议在 `0.95–1.05` 之间。

#### 5.5.3 分配到各 Task

使用固定 Task 模板中的基础时间/能耗作为权重：

```text
task_time =
target_time(stage,j)
× fixed_base_time(task) / sum(fixed_base_time for stage)

task_energy =
target_energy(stage,j)
× fixed_base_energy(task) / sum(fixed_base_energy for stage)
```

取整后的误差调整到同工艺权重最大的 Task，确保：

```text
工艺 Task 时间之和 = target_time(stage,j)
工艺 Task 能耗之和 = target_energy(stage,j)
```

#### 5.5.4 机器选项

每个 Task 只为具备对应能力的机器生成选项：

```text
machine_task_time =
task_time × machine_speed_factor × deterministic_noise

machine_task_energy =
task_energy × machine_energy_factor × deterministic_noise
```

| 工艺 | 速度系数 | 能耗系数 | 机器选项数 |
| --- | ---: | ---: | ---: |
| 焊装 | 0.85–1.20 | 0.90–1.15 | 1–3 |
| 涂装 | 0.90–1.15 | 0.92–1.12 | 1–2 |
| 总装 | 0.85–1.20 | 0.90–1.15 | 1–3 |

#### 5.5.5 合并 Task

```text
merged_time =
sum(component_time) × overlap_factor

merged_energy =
sum(component_energy) + additional_setup_energy
```

默认使用顺序执行：

```text
overlap_factor = 1.0
additional_setup_energy = 0
```

只有设备确实可并行执行子工序时，才允许 `overlap_factor=0.75–0.95`。

### 5.6 生成结果校验

生成 `raw1/add1`、`raw2/add2`、`raw3/add3` 后必须检查：

- 四个工艺的 Job 数及 Job 顺序一致。
- 后三工艺每 Job Task 数分别为 6、6、8。
- 每道 Task 至少有一个有效机器选项。
- 加工时间、加工能耗和运输值均非负。
- 工艺总时间和总能耗位于推荐比例范围内。
- Task 时间和能耗取整后，Job 阶段总量保持不变。
- Task 拆分后的物料需求之和等于父 Task 需求。
- Task 合并后的物料需求包含全部子工序需求。
- 运输时间和等待时间不计入加工时间或加工能耗。
- 交付时间在完整四工艺时间和运输时间生成后再计算。
- 生成过程使用固定种子，保证相同实例和配置可复现。

当前 `raw1/add1`、`raw2/add2`、`raw3/add3` 已按上述规则重新生成，
`--check` 可在不写入文件的情况下确认全部生成结果与固定种子一致。

## 6. 设备检测数据

`simulator-data/` 是设备状态看板和异常检测服务的数据与代码目录。

```text
simulator-data/
├── data/
│   ├── anomaly.csv
│   └── machines/
│       ├── machine_0.csv
│       ├── ...
│       └── machine_14.csv
├── config.yaml
├── app/
├── frontend/
└── docs/
```

数据说明：

- `data/anomaly.csv`：异常检测服务的原始基底数据。
- `data/machines/machine_0.csv` 至 `machine_14.csv`：当前随数据提供的
  `15` 台机器检测数据。
- `config.yaml`：检测服务的数据路径、生成参数、预测窗口和展示字段配置。

设备 CSV 字段：

```text
timestamp,
TP2, TP3, H1,
DV_pressure, Reservoirs, Oil_temperature, Motor_current,
COMP, DV_eletric, Towers, MPG, LPS,
Pressure_switch, Oil_level, Caudal_impulses,
label
```

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `timestamp` | 整数 | 设备数据时间点 |
| `TP2`、`TP3`、`H1` | 连续量 | 压力测量 |
| `DV_pressure` | 连续量 | 压差 |
| `Reservoirs` | 连续量 | 储气罐压力 |
| `Oil_temperature` | 连续量 | 油温 |
| `Motor_current` | 连续量 | 电机电流 |
| `COMP` | 二值量 | 压缩机状态 |
| `DV_eletric` | 二值量 | 电磁阀状态 |
| `Towers` | 二值量 | 冷却塔状态 |
| `MPG` | 二值量 | 辅助设备状态 |
| `LPS` | 常量/二值量 | 低压开关数据 |
| `Pressure_switch` | 二值量 | 压力开关状态 |
| `Oil_level` | 常量/二值量 | 油位状态 |
| `Caudal_impulses` | 常量/二值量 | 流量脉冲 |
| `label` | 0/1 | 当前时间点是否异常 |

`simulator-data/app/` 提供设备检测 API，`simulator-data/frontend/` 提供独立
检测展示页，`simulator-data/docs/` 保存接口和数据对接文档。

## 7. 数据集清单文件

- `manifest.json`：基础调度数据源、实例规模、文件哈希和排除项。
- `followup_processes_manifest.json`：焊装、涂装、总装的生成参数和文件统计。

## 8. Python 脚本说明与数据集生成

### 8.1 当前推荐生成流程

当前四工艺仿真数据以 `raw/` 为输入，统一使用
`generate_followup_processes.py` 生成。执行前应确认已经安装
`simulator` Conda 环境：

```bash
cd /data/luopw/production_simulator

# 根据 raw/ 一次性生成四工艺调度、交付、工艺配置和物料数据
conda run -n simulator python datasets/generate_followup_processes.py

# 不写入文件，只验证当前数据集是否与固定生成规则一致
conda run -n simulator python datasets/generate_followup_processes.py --check
```

该命令生成或校验以下数据：

| 输出 | 内容 |
| --- | --- |
| `add/` | 冲压加工能耗、运输时间、运输能耗 |
| `raw1/add1/` | 焊装加工时间、加工能耗和运输数据 |
| `raw2/add2/` | 涂装加工时间、加工能耗和运输数据 |
| `raw3/add3/` | 总装加工时间、加工能耗和运输数据 |
| `delivery_cost/` | 每个实例共享的四工艺交付时间和成本参数 |
| `process_generation_configs/` | 每个实例、每个工艺的时间/能耗生成配置和运输矩阵 |
| `material_consumption/` | 冲压 Job 级及后三工艺 Task 级物料用量 |
| `material_configs/` | 每个实例、工艺、机器和物料的总量 |
| `material_master.csv` | 全部直接物料的主数据 |
| `followup_processes_manifest.json` | 生成规则、文件统计和目录索引 |

`raw/` 是输入数据，生成脚本不会重写其中的冲压工序时间和机器选项。

### 8.2 datasets 根目录 Python 脚本

| 脚本 | 作用 | 执行方式 | 输入与输出 |
| --- | --- | --- | --- |
| `create_ins.py` | 旧版辅助脚本，为 `raw/Brandimarete` 下的文件生成加工能耗、交付信息和运输矩阵 | `python datasets/create_ins.py` | 输入 `datasets/raw/Brandimarete/`，输出 `datasets/add/Brandimarete/`；不属于当前标准四工艺生成链 |
| `prepare_dataset.py` | 将 `datasets/*.txt` 标准 JSP/FJSP 基准实例转换为运行格式，并生成基础加工能耗、交付信息和运输矩阵 | `conda run -n simulator python datasets/prepare_dataset.py` | 输入 `datasets/*.txt`，输出 `raw/`、`add/`、`delivery_cost/` 和 `manifest.json` |
| `generate_followup_processes.py` | 当前标准生成脚本，从 `raw/` 生成四工艺数据、交付数据、工艺生成配置和全部物料数据 | `conda run -n simulator python datasets/generate_followup_processes.py` | 输入 `datasets/raw/*.fjs`，输出四工艺目录、配置、物料和清单 |
| `split_delivery_cost.py` | 检查 `add/add1/add2/add3` 是否只包含能耗和运输数据，并将旧的嵌入式交付字段拆到 `delivery_cost/` | `conda run -n simulator python datasets/split_delivery_cost.py` | 输入 `raw*/add*`，输出或校验 `delivery_cost/`，同时更新 `manifest.json` |

`prepare_dataset.py` 只有在 `datasets/` 根目录存在源 `.txt` 文件时才能完整执行。
当前目录以 `raw/` 下的 `.fjs` 为实际输入，因此日常重建四工艺数据应使用
`generate_followup_processes.py`。

### 8.3 simulator-data Python 脚本

以下脚本属于设备流式数据模拟服务，不参与四工艺调度数据生成。

| 脚本 | 作用 | 是否直接生成数据集 |
| --- | --- | --- |
| `simulator-data/app/__init__.py` | Python 包标识 | 否 |
| `simulator-data/app/api/__init__.py` | API 子包标识 | 否 |
| `simulator-data/app/api/v1.py` | 定义 `/api/v1/window`、`stream`、`labels`、`warn`、`meta`、`machines` 等接口 | 请求未预生成的机器时可触发按需生成 |
| `simulator-data/app/config.py` | 加载 `config.yaml`、合并默认参数并解析数据路径 | 否 |
| `simulator-data/app/data/__init__.py` | 数据子包标识 | 否 |
| `simulator-data/app/data/features.py` | 定义 15 个模型输入特征、展示字段、量纲和配色 | 否 |
| `simulator-data/app/data/generator.py` | 从 `data/anomaly.csv` 按机器编号和固定种子生成机器 CSV | 是，生成 `data/machines/machine_<id>.csv` |
| `simulator-data/app/data/registry.py` | 加载机器 CSV、维护 LRU 缓存并协调按需生成 | 间接生成缺失机器文件 |
| `simulator-data/app/errors.py` | 统一 API 错误类型 | 否 |
| `simulator-data/app/main.py` | FastAPI 应用入口、CORS、异常处理和演示页 | 否 |
| `simulator-data/app/schemas.py` | API 请求与响应数据模型及 OpenAPI Schema | 否 |
| `simulator-data/app/services/__init__.py` | 服务子包标识 | 否 |
| `simulator-data/app/services/display.py` | 组装前端展示数据流及 `label`、`warn` 标记 | 否 |
| `simulator-data/app/services/labels.py` | 查询时间点标签和未来预测窗口预警 | 否 |
| `simulator-data/app/services/window.py` | 生成模型输入窗口并支持时间点循环和两种矩阵布局 | 否 |
| `simulator-data/tests/__init__.py` | 测试包标识 | 否 |
| `simulator-data/tests/test_contract_regression.py` | 验证窗口、标签与旧版接口逐值一致且模型输入无标签泄漏 | 否，仅测试 |
| `simulator-data/tests/test_window.py` | 验证窗口形状、取模、标签、展示流和惰性生成规则 | 否，仅测试 |

### 8.4 设备检测数据生成

`simulator-data/data/anomaly.csv` 是真实基底数据，
`simulator-data/data/machines/machine_0.csv` 至 `machine_14.csv` 是随包
预生成的数据。

编号大于等于 `pre_generated_machines` 的机器会在首次请求时按需生成：

```bash
cd /data/luopw/production_simulator/datasets/simulator-data
./start.sh

curl "http://127.0.0.1:8000/api/v1/window?machine_id=15&t=0"
```

第一个请求会调用 `app/data/generator.py`，生成：

```text
data/machines/machine_15.csv
```

生成参数位于 `simulator-data/config.yaml` 的 `data` 和
`contract` 部分。机器数据的运行和契约测试命令：

```bash
cd /data/luopw/production_simulator/datasets/simulator-data
python -m unittest discover -s tests -v
```

### 8.5 脚本使用注意事项

| 注意事项 | 说明 |
| --- | --- |
| 标准四工艺重建 | 使用 `generate_followup_processes.py`，不要使用旧版 `create_ins.py` |
| 不覆盖原始冲压数据 | 标准脚本只读取 `raw/`，不会修改原始时间数据和机器选项 |
| 可重复性 | 后三工艺、配置、物料和交付数据均由固定 SHA-256 种子生成 |
| 写入前验证 | 可使用各脚本的 `--check` 参数检查结果而不写文件 |
| 旧文件清理 | 标准脚本会清理目标生成目录中不属于当前 `raw/` 实例集合的旧文件 |
| 设备数据 | 15 台机器数据已预生成，其他机器由流式服务首次请求时按需生成 |

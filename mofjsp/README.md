# DRL-MOFJSP 模型部署准备说明

本目录按照《TGAgent 模型部署教程》整理，提供该柔性作业车间调度（FJSP）模型在 TGAgent 上部署所需的模型文件、`service.py`、依赖清单、输入/输出 Schema 和可直接用于测试的样例。

## 模型介绍与描述

### 解决的问题

本部署包中的 DRL-MOFJSP 是一个面向柔性作业车间调度问题的强化学习决策模型。问题包含多个具有固定工序先后顺序的作业，每道工序可以从一组可行机器中选择一台进行加工，不同加工选择对应不同的加工时间和加工能耗。模型还需要考虑作业就绪时间、交期、提前和延期惩罚，以及机器之间的运输时间和运输能耗。

模型的任务不是预测分类标签，而是逐步构造一套完整、可执行的调度方案：确定每道工序使用的机器、工序的开始和结束时间、同一机器上的加工顺序，以及作业内部的工序先后关系。调度结果同时优化三个越小越好的目标：

- 最大完工时间 `makespan`。
- 总加工能耗与运输能耗 `energy`。
- 作业提前或延期交付产生的惩罚 `penalty`。

### 使用的方法

1. **柔性作业车间环境建模。** 状态同时描述作业、工序、机器和调度进度。工序特征包含可选机器数量、平均加工时间、所属作业未调度工序数、预计开始和完成时间、交期、提前/延期惩罚以及预计能耗；机器特征包含可加工工序数量、可用时间、利用率和运输相关信息。

2. **异构图神经网络编码。** 工序和机器分别作为两类节点，工序到可行机器形成加工边，相邻工序之间形成先后约束边。模型使用基于边的图注意力网络聚合机器邻居信息，并使用多层感知机聚合工序关联信息，将节点转换为用于动作决策的嵌入。当前配置包含两层图传播，每层 1 个注意力头，工序和机器嵌入维度均为 16。

3. **强化学习序贯决策。** 每个决策步只允许选择一个当前可执行且资源可用的工序-机器组合；正在加工和已经完成的作业、忙碌的机器以及不可加工机器会被动作掩码排除。环境执行动作后更新机器可用时间、工序状态、作业完成情况、运输信息和三个目标值，直到所有工序完成。该过程使模型能够在满足资源冲突和工序先后约束的前提下逐步构造调度方案。

4. **PPO Actor-Critic 训练。** Actor 网络输出候选工序-机器组合的概率，Critic 网络估计状态价值。训练使用 PPO 的裁剪策略目标，并结合价值损失和策略熵正则项。奖励由最大完工时间、能耗和惩罚三项目标的相对改进量加权组成；当前三项奖励权重均为 `1.0`。

5. **DRL-S 多轨迹采样。** 推理时将同一实例复制 `num_samples` 次，按照策略概率采样多条不同的调度轨迹。每条轨迹完成后都会检查机器重叠、作业工序顺序和工序完整性，然后从可行候选中选择综合目标最优的方案。

6. **多目标候选筛选。** 当前推理代码先将三个目标分别除以本批候选中的最小值，再计算归一化目标向量的均方根距离，选择距离最小的候选作为 `best_sample`。因此不会只比较单一目标，而是在三个目标之间做折中。

当前权重原文件为 `save_best_15_8_110.pt`，部署时命名为 `model.pt`。它主要面向 15 个作业、8 台机器的数据训练；输入接口支持从文件头读取其他规模，但未在当前权重上验证过同等泛化能力。

## 1. 当前接口

部署服务类名为 `FJSPDeploymentService`，API 方法名为 `schedule`。每次请求输入一个 FJSP 实例的原始文件文本和附加信息文件文本，服务使用 DRL-S 随机采样生成多条调度轨迹，在全部可行候选中选择综合目标最优的方案并返回。

三个优化目标均为越小越好：

- `makespan`：最大完工时间。
- `energy`：总加工能耗与运输能耗。
- `penalty`：提前/延期交付惩罚。

当前权重文件为部署根目录下的 `model.pt`，原始文件名为 `save_best_15_8_110.pt`。配置中的网络维度必须与该权重严格一致，因此不要删除 `drl_fjsp` 运行时代码，也不要只上传 `model.pt`。

## 2. 目录与上传对应关系

```text
部署根目录（当前为 mofjsp/）
├── config.json                # 推理、环境和网络结构配置
├── model.pt                   # 真实 PyTorch 权重
├── service.py                 # TGAgent/BentoML 推理入口
├── requirements.txt           # 模型运行依赖
├── input_schema.json          # 平台输入 Schema
├── output_schema.json         # 平台输出 Schema
├── test_input.json            # 可直接粘贴到测试页的完整输入
├── README.md                  # 本说明
├── drl_fjsp/                  # 推理所需的最小运行时代码
│   ├── __init__.py
│   ├── inference.py           # 输入校验、调度和 JSON 转换
│   ├── env.py                 # FJSP 环境与可行性校验
│   ├── load_data.py           # FJSP 文件解析
│   ├── ppo_model.py           # HGNN/PPO 网络定义
│   ├── hgnn.py                # 图神经网络组件
│   └── mlp.py                 # Actor/Critic 组件
```

上传时建议保持上述相对结构：

1. 将 `service.py` 和 `requirements.txt` 保存到部署根目录。
2. 将 `drl_fjsp/` 作为推理代码一并上传，并保持与 `service.py` 同级。
3. 将根目录下的 `model.pt` 和 `config.json` 作为模型文件上传。
4. 将 `input_schema.json` 和 `output_schema.json` 的内容分别粘贴到平台的输入、输出 Schema 编辑区。
5. 将 `test_input.json` 的内容粘贴到模型测试页；也可以基于业务数据按同样字段自行生成请求。

`service.py` 使用 `Path(__file__).parent` 定位部署根目录，不依赖本机绝对路径。运行时优先从部署根目录读取 `config.json`、`model.pt` 和 `drl_fjsp/`；如果 TGAgent 将上传资源统一放入 `model/`，代码也会自动从该目录读取。

## 3. 推理输入

平台接收 JSON 对象，必填字段为 `raw_lines` 和 `additional_lines`。字段值是原文件内容字符串，而不是文件路径或文件列表。

```json
{
  "instance_name": "fjsp.brandimarte.Mk03.m8j15c5",
  "raw_lines": "15 8 5\n<15 行作业数据>",
  "additional_lines": "<15 行加工能耗>\n<15 行作业特征>\n<运输时间矩阵>\n<运输能耗矩阵>",
  "num_samples": 2,
  "seed": 42
}
```

字段说明：

| 字段 | 类型 | 必填 | 含义 |
| --- | --- | --- | --- |
| `raw_lines` | string | 是 | 原 `raw/*.fjs` 文件全文；首行为 `num_jobs num_machines metadata`，第三项当前不参与调度 |
| `additional_lines` | string | 是 | 对应 `add/*.fjs` 文件全文 |
| `instance_name` | string | 否 | 展示名称，默认 `instance`，会清除路径和特殊字符 |
| `num_samples` | integer | 否 | DRL-S 采样条数，范围 `1-100`，默认 `10` |
| `seed` | integer | 否 | 采样随机种子，默认 `0` |

`raw_lines` 和 `additional_lines` 必须来自同一个实例。目录 `datasets/raw/` 与 `datasets/add/` 中的同名文件应成对使用；旧数据也可以继续使用 `data_test1/1508/raw/` 与 `data_test1/1508/add/` 中的同名文件。

当前权重面向 15 个作业、8 台机器的数据训练。运行时虽然会从 `raw_lines` 文件头读取实例规模，但其他尺寸的调度质量没有经过当前权重的部署验证，生产测试应优先使用 15x8 实例。

## 4. 推理输出

成功时返回 JSON，主要字段如下：

```json
{
  "success": true,
  "instance_name": "fjsp.brandimarte.Mk03.m8j15c5",
  "model": "model.pt",
  "device": "cpu",
  "num_samples": 2,
  "best_sample": 1,
  "n_jobs": 15,
  "n_machines": 8,
  "n_operations": 150,
  "objectives": {
    "makespan": 0.0,
    "energy": 0.0,
    "penalty": 0.0
  },
  "feasible": true,
  "schedule": [
    {
      "job_id": 0,
      "operation_index": 0,
      "operation_id": 0,
      "machine_id": 0,
      "start_time": 0.0,
      "end_time": 0.0,
      "processing_time": 0.0
    }
  ]
}
```

上面的目标值和调度时间为字段结构示例，不是模型性能基准。实际数值由权重和采样结果决定。

- `best_sample` 从 0 开始编号。
- `job_id`、`operation_index`、`operation_id` 和 `machine_id` 均从 0 开始编号。
- `schedule` 按开始时间、机器编号、作业编号排序。
- `feasible` 只有在机器不重叠、作业内工序顺序正确且所有工序均已调度时才为 `true`。
- 服务只返回 JSON 可序列化对象，不直接返回 Tensor 或 NumPy 数组。

输出 Schema 与实际返回字段保持一致。修改返回字段时，必须同步修改 `output_schema.json`。

## 5. 部署配置

`service.py` 使用教程推荐的基础镜像和依赖声明方式：

```python
image = (
    bentoml.images.Image(
        base_image="tgagent/bentoml-base",
        lock_python_packages=False,
    )
    .requirements_file("requirements.txt")
)
```

`requirements.txt` 固定 CPU 版 PyTorch 版本，并限制 NumPy 主版本，避免平台构建时解析到不兼容版本。当前推理只需要：

- `torch==2.4.1+cpu`
- `numpy<2`

如果需要改用 GPU，应根据平台服务器的 CUDA 版本替换 PyTorch 安装源和版本，并先完成一次部署测试。

## 6. 本地检查

在不安装运行依赖的情况下，可以先检查 Python 语法和 JSON 结构：

```bash
cd mofjsp
python -m py_compile service.py drl_fjsp/*.py
python -m json.tool config.json >/dev/null
python -m json.tool input_schema.json >/dev/null
python -m json.tool output_schema.json >/dev/null
python -m json.tool test_input.json >/dev/null
```

完整推理测试需要安装 `requirements.txt` 中的依赖，然后在能够导入 `bentoml` 和 `torch` 的环境中启动服务。当前 `test_input.json` 使用 `datasets/raw/fjsp.brandimarte.Mk03.m8j15c5.fjs` 和 `datasets/add/fjsp.brandimarte.Mk03.m8j15c5.fjs` 实例，并将采样数设为 `2`，便于在部署页面先做快速连通性测试。

## 7. 部署前检查清单

- `service.py` 已保存，并使用 `@bentoml.service(image=image)`。
- `schedule` API 已保存，HTTP 测试时使用平台生成的对应路由。
- `model.pt` 和 `config.json` 均已上传，文件没有损坏。
- `drl_fjsp/` 与 `service.py` 保持同级，运行时代码完整。
- `requirements.txt` 已上传，且 `service.py` 引用了该文件。
- 输入 Schema、输出 Schema 已填写。
- `test_input.json` 包含全部必填字段，且 `raw_lines` 和 `additional_lines` 成对。
- 测试页返回 `success: true` 和 `feasible: true`。
- 输出字段、类型和 `output_schema.json` 完全一致。

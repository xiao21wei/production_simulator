# HLS-FJSP TGAgent 部署包

本目录按照 `mofjsp/` 和《TGAgent 模型部署配置参考》整理，提供可上传的 BentoML 服务、输入/输出 Schema、测试输入以及无 COPT 依赖的 Linux 原生求解程序。

## 模型介绍与描述

### 解决的问题

本部署包中的模型是一个面向柔性作业车间调度问题（Flexible Job Shop Scheduling
Problem，FJSP）的混合搜索求解器。实例包含多个作业，每个作业具有固定的工序顺序；
同一道工序可以在若干台兼容机器中选择一台加工，不同机器上的加工时间可以不同。

模型需要在不违反以下约束的前提下，为所有工序确定加工机器和加工顺序：

- 同一作业的工序必须按给定顺序执行。
- 同一台机器在同一时间只能加工一道工序。
- 同一作业在同一时间只能有一道工序处于加工状态。
- 所选机器必须在该工序的可行机器集合中。

部署服务以 **makespan**，即最后一道工序的完成时间作为优化目标，目标是得到尽可能小且
满足约束的完整调度。输出不仅包括 makespan，还包括每道工序的机器编号、开始时间、
结束时间和加工时间。

该模型不是带 `model.pt` 权重的神经网络分类或回归模型，而是由 C++ 编写的组合优化搜索
程序。部署时上传的 `runtime/bin/production_scheduling` 就是实际执行调度搜索的模型
运行文件。

### 使用的方法

1. **多起点启发式初始解。** 在没有 COPT 的情况下，使用基于工序就绪时间、机器可用
   时间和最早完工时间的列表调度构造初始解，并从多个作业顺序起点中选择较好的可行解。

2. **Greedy 关键工序搜索。** 围绕零松弛关键工序和近关键工序执行同机重插入、跨机迁移
   等邻域动作，并精确重新计算候选排程的 makespan，只接受能够改善目标的方案。

3. **Genetic Algorithm。** 使用机器选择编码和工序排序编码构建种群，通过交叉、变异和
   选择迭代搜索不同机器分配与机器序列组合，并使用精确解码评价每个候选的可行性。

4. **Tabu Search。** 在关键块移动、跨机迁移、工序交换和同机重插入等邻域中搜索，通过
   禁忌表避免短期重复，并允许在特定条件下接受非改进解以跳出局部最优。

5. **Guided Insertion。** 对规模满足条件的实例，从关键工序、近关键工序和近期搜索轨迹
   中生成跨机插入候选，再进行分层筛选和精确目标评价。

6. **自适应方法选择与重启。** 求解过程根据各搜索方法最近的改进情况、搜索收益、停滞
   状态和时间预算选择下一步使用的方法；停滞时可以启用多样化起点和搜索重启。

7. **基于调度图的精确评价。** 作业工序顺序和机器加工顺序共同构造成有向无环图，通过
   拓扑排序和最长路径计算开始时间与 makespan。候选若产生环、漏排工序或机器冲突，会被
   判定为不可行；最终结果还会同时进行稀疏和稠密 makespan 一致性校验。

当前 TGAgent 包关闭 COPT、Greedy RL 和 Tabu RL，只使用 HLS 自身初始解与上述启发式、
元启发式搜索方法。`additional_lines` 可以被接口接收和校验，但它描述的是多目标扩展
信息，不参与当前单目标 makespan 优化。

## 1. 数据格式核对结论

当前 HLS C++ 加载器能够读取 `datasets/datasets/raw/*.fjs` 的主体格式：

```text
num_jobs num_machines metadata
operation_count option_count machine_id processing_time ...
```

兼容性处理如下：

- 加载器支持小数 `metadata`，因此 Brandimarte 的 `3.5`、`1.5` 等文件头也能读取。
- 机器号可以是标准数据的 `0..m-1`，也可以是 `raw/` 中的 `1..m`；加载器会按实例自动归一化为内部 `0..m-1`。
- 每道工序有多个机器选项时，按 `option_count` 后接多组 `machine_id processing_time`。
- `add/*.fjs` 不属于当前 HLS 的输入。它描述加工能耗、交期、提前/延期惩罚和运输信息，而 HLS 当前只优化 makespan，因此部署服务只验证该字段格式，并明确返回 `additional_data_used: false`。

需要在其他服务器上运行数据处理脚本时，使用仓库根目录的 `prepare_hls_dataset.py` 生成目标 `raw/` 格式。

## 2. COPT 默认关闭

本部署程序使用 `-DHLS_WITH_COPT=OFF` 构建，不链接 `libcopt_cpp.so` 或 `libcopt.so`，也不需要 COPT 许可证。默认同时静态链接系统运行库，使 Linux x86_64 程序不依赖目标服务器上的项目库。初始解由 HLS 的确定性多起点启发式生成，之后继续执行 Greedy、Genetic Algorithm、Tabu Search 和规模满足条件时的 Guided Search。

本地仍需要 COPT 的实验可显式使用：

```bash
cmake -S /path/to/HLS -B /path/to/HLS/build/copt -DHLS_WITH_COPT=ON
cmake --build /path/to/HLS/build/copt -j"$(nproc)"
```

默认 CMake 配置和程序默认 COPT 时限都已经关闭 COPT。
无 COPT 构建默认启用 `-DHLS_STATIC_EXECUTABLE=ON`；若目标环境要求动态链接，可显式设为 `OFF`。

### 原生程序执行权限

TGAgent 或其他归档上传流程可能只保留文件内容，不保留 Linux 可执行权限。此时容器中虽然能
找到 `runtime/bin/production_scheduling`，但服务启动会因缺少执行位而失败。

`hls_engine.py` 会在初始化时自动处理：

1. 如果程序已有执行权限，直接使用。
2. 如果模型目录可写，为程序补充用户、组和其他用户的执行权限。
3. 如果模型目录只读或权限修改失败，将程序复制到容器的临时目录并设置 `0755`。
4. 仍然无法执行时返回明确的 `PermissionError`。

因此不需要依赖上传系统保留可执行位，也不需要在每个新容器中手动执行 `chmod`。

## 3. 目录与上传对应关系

```text
HLS_test/
├── service.py
├── hls_engine.py
├── requirements.txt
├── config.json
├── input_schema.json
├── output_schema.json
├── test_input.json
├── README.md
└── runtime/
    └── bin/
        └── production_scheduling
```

上传时保持上述相对结构。若 TGAgent 将模型资源放到 `model/`，`service.py` 也会从部署根目录的 `model/` 查找配置和运行文件。

`service.py`、`hls_engine.py` 和 `requirements.txt` 可放在部署根目录；`config.json` 和 `runtime/` 作为模型资源上传。平台若要求模型文件不能执行，需要把完整 `HLS_test/` 作为代码包上传，并确认容器允许执行 `runtime/bin/production_scheduling`。

## 4. 接口

服务类为 `HLSDeploymentService`，API 为 `schedule`。必填字段是 `raw_lines`；`additional_lines` 可选，仅用于配对数据校验。

未提供 `total_time_seconds` 时，默认使用 `20` 秒搜索预算。快速连通性测试可以在请求中显式传入更小值；需要更充分的搜索时，也可以在允许范围内手动提高该值。

```json
{
  "instance_name": "fjsp.brandimarte.Mk03.m8j15c5",
  "raw_lines": "15\t8\t5\n<其余 15 行 raw 作业数据>",
  "seed": 42
}
```

`test_input.json` 已使用 `datasets/datasets/raw/fjsp.brandimarte.Mk03.m8j15c5.fjs` 的真实文件内容，并未设置 `total_time_seconds`，因此测试会实际使用 20 秒默认预算。

返回内容包括：

- `objectives.makespan`：当前 HLS 优化的目标。
- `schedule`：按作业和工序返回所选机器、开始时间、结束时间和加工时间。
- `feasible`：机器不重叠、作业工序顺序正确且工序完整时为 `true`。
- `copt_enabled`：本包固定为 `false`。
- `additional_data_valid`：请求带 `additional_lines` 时表示该文件结构是否有效。
- `additional_data_used`：本包固定为 `false`。

## 5. 本地检查

```bash
cd /home/luopw24/HLS/HLS_test
python3.10 -m py_compile service.py hls_engine.py
python3.10 -m json.tool config.json >/dev/null
python3.10 -m json.tool input_schema.json >/dev/null
python3.10 -m json.tool output_schema.json >/dev/null
python3.10 -m json.tool test_input.json >/dev/null
```

完整服务启动需要 TGAgent/BentoML 基础镜像。即使本机没有 BentoML，也可以直接测试推理引擎：

```bash
cd /home/luopw24/HLS/HLS_test
python3.10 - <<'PY'
import json
from pathlib import Path
from hls_engine import HLSDeploymentEngine

config = json.loads(Path("config.json").read_text(encoding="utf-8"))
request = json.loads(Path("test_input.json").read_text(encoding="utf-8"))
engine = HLSDeploymentEngine(
    config,
    Path(config["runtime"]["binary"]).resolve(),
)
print(json.dumps(engine.predict(request), ensure_ascii=False, indent=2))
PY
```

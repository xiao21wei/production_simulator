# NSGA2-FJSP 柔性作业车间调度问题求解器

[![Python](https://img.shields.io/badge/Python-3.7+-blue.svg)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

## 项目简介

本项目实现了基于NSGA2（非支配排序遗传算法II）的柔性作业车间调度问题（FJSP）求解器。该求解器能够同时优化完工时间（makespan）和机器总负载两个目标，为决策者提供多个Pareto最优解。

## 快速开始

**🚀 5分钟快速上手**: 查看 [快速入门指南](QUICKSTART.md)

**💡 使用示例**: 运行 `python example_usage.py`

**🏗️ 代码架构**: 查看 [架构说明](ARCHITECTURE.md)

**📊 示例结果**: 对于10工件6机器的测试案例，能找到完工时间为53的最优解

## 目录结构

```
production_simulator/
├── input.txt                   # FJSP问题输入数据
├── output.txt                  # 算法运行结果
├── result.csv                  # 详细调度方案
├── gantt_chart_1.txt          # 甘特图文件
├── common/
│   ├── fjsp_reader.py         # FJSP数据读取模块
│   └── utils.py               # 工具函数
├── NSGA2/
│   └── nsga2_sceduling.py     # NSGA2算法主程序
├── system/
│   ├── job.py                 # 工件类
│   ├── machine.py             # 机器类
│   ├── order.py               # 订单类
│   └── schedule.py            # 调度方案类
└── simulator/
    ├── event.py               # 事件类
    └── simulator.py           # 仿真器
```

## 快速开始

### 环境要求

- Python 3.7+
- NumPy

### 安装依赖

```bash
pip install numpy
```

### 运行方法

1. **准备输入数据**：将FJSP问题数据放在 `input.txt` 文件中
2. **运行算法**：
   ```bash
   python NSGA2/nsga2_sceduling.py
   ```
3. **查看结果**：
   - `output.txt`：算法运行结果和Pareto前沿解
   - `result.csv`：详细的机器调度方案
   - `gantt_chart_1.txt`：甘特图文件（Mermaid格式）

### 输入数据格式

`input.txt` 采用标准FJSP格式：

```
工件数 机器数 最大工序数
工件1的工序数 工序1可选机器数 机器ID1 处理时间1 机器ID2 处理时间2 ... 工序2可选机器数 ...
工件2的工序数 ...
...
```

**示例**：
```
3 3 2
2  2  0 3  1 2    1  1 4
2  1  0 2         2  1 3  2 1  
1  2  0 1  2 3
```

## 核心模块说明

### 1. FJSP数据读取模块 (`common/fjsp_reader.py`)

#### 主要类

- **`FJSPInstance`**: FJSP问题实例类
  - `jobs`: 工件列表
  - `machines`: 机器列表
  - `job_count`: 工件数量
  - `machine_count`: 机器数量

- **`Operation`**: 工序类
  - `operation_id`: 工序ID
  - `job_id`: 所属工件ID
  - `machines`: 可用机器列表 `[(machine_id, processing_time), ...]`

- **`FJSPJob`**: 工件类
  - `job_id`: 工件ID
  - `operations`: 工序列表

#### 主要函数

```python
def read_fjsp_file(filename):
    """读取FJSP格式的数据文件"""
    # 返回FJSPInstance对象
```

### 2. NSGA2算法模块 (`NSGA2/nsga2_sceduling.py`)

#### 核心类

##### `Individual` - 个体类

表示一个调度方案的染色体编码。

**属性**：
- `machine_assignment`: 字典，`(job_id, op_id) -> machine_id`，记录每个工序的机器分配
- `operation_sequence`: 列表，`[(job_id, op_id), ...]`，工序执行顺序
- `makespan`: 完工时间
- `total_machine_load`: 机器总负载

**主要方法**：
```python
def generate_random_solution(self):
    """生成随机可行解"""
    
def evaluate(self):
    """评估个体的目标函数值"""
    
def _generate_feasible_sequence(self):
    """生成满足工序约束的可行序列"""
```

##### `NSGA2_FJSP` - NSGA2算法类

实现完整的NSGA2多目标优化算法。

**参数**：
- `population_size`: 种群规模（默认100）
- `max_generations`: 最大进化代数（默认200）

**主要方法**：
```python
def initialize_population(self):
    """初始化种群"""
    
def fast_non_dominated_sort(self, population):
    """快速非支配排序"""
    
def calculate_crowding_distance(self, front_indices, population):
    """计算拥挤距离"""
    
def crossover(self, parent1, parent2):
    """交叉操作"""
    
def mutate(self, individual):
    """变异操作"""
    
def run(self):
    """运行NSGA2算法"""
```

#### 算法流程

1. **初始化种群**：生成初始可行解
2. **评价个体**：计算目标函数值
3. **非支配排序**：对个体进行分层
4. **拥挤距离计算**：保持解的多样性
5. **选择操作**：锦标赛选择
6. **遗传操作**：交叉和变异
7. **环境选择**：选择下一代个体
8. **重复步骤2-7**，直到达到终止条件

### 3. 调度方案类 (`system/schedule.py`)

#### `Schedule` 类

管理和输出调度结果。

**属性**：
- `schedule_items`: 每台机器的工序分配
- `start_time`: 每个工序的开始时间
- `end_time`: 每个工序的结束时间

**主要方法**：
```python
def addOperation(self, job_id, operation_id, machine_id, start_time, end_time):
    """添加工序到调度方案"""
    
def printItems(self):
    """输出调度结果到CSV和甘特图文件"""
```

## 算法特点

### 双目标优化
- **目标1**：最小化完工时间（makespan）
- **目标2**：最小化机器总负载

### 约束处理
- **工序顺序约束**：同一工件的工序必须按顺序执行
- **机器兼容性约束**：每个工序只能在指定的机器上处理
- **资源约束**：每台机器同时只能处理一个工序

### 编码方式
采用双层编码结构：
1. **机器分配编码**：为每个工序指定执行机器
2. **工序排序编码**：确定工序的执行顺序

### 遗传操作
- **交叉**：机器分配随机交换 + 工序序列重新生成
- **变异**：机器选择变异 + 序列重新生成
- **选择**：基于非支配关系和拥挤距离的锦标赛选择

## 输出结果

### 1. 控制台输出
```
读取FJSP数据...
问题规模: 10个工件, 6台机器
初始化种群...
代数 1/100
当前最佳完工时间: 70
...
Pareto前沿包含 4 个解:
解 1: 完工时间=49.00, 机器总负载=253.00
解 2: 完工时间=52.00, 机器总负载=249.00
解 3: 完工时间=54.00, 机器总负载=242.00
解 4: 完工时间=55.00, 机器总负载=240.00
```

### 2. output.txt
包含算法运行结果和所有Pareto最优解的详细信息。

### 3. result.csv
详细的调度方案，包含每台机器的工序分配和时间安排：
```csv
machine0,3-0,8-1,0-0,7-2,1-2,...
start_time,0,5,6,13,14,...
end_time,1,6,11,14,16,...
```

### 4. gantt_chart_1.txt
Mermaid格式的甘特图，可以直接在支持Mermaid的编辑器中查看：
```
gantt
    title Schedule 1
    dateFormat  X
    axisFormat  %s
    section Machine 0
        J3-0: J3, 0, 1
        J8-1: J8, 5, 6
        ...
```

## 参数调优

可以通过修改以下参数来调整算法性能：

```python
# 在main()函数中
nsga2 = NSGA2_FJSP(
    fjsp_instance, 
    population_size=50,      # 种群规模
    max_generations=100      # 进化代数
)
```

### 建议设置
- **小规模问题**（<20个工件）：population_size=50, max_generations=50
- **中等规模问题**（20-50个工件）：population_size=100, max_generations=100
- **大规模问题**（>50个工件）：population_size=200, max_generations=200

## 扩展使用

### 添加新的目标函数
在`Individual.evaluate()`方法中添加新的目标：

```python
def evaluate(self):
    # 现有目标计算...
    self.makespan = ...
    self.total_machine_load = ...
    
    # 添加新目标
    self.energy_consumption = self.calculate_energy()
```

### 修改约束条件
在`_generate_feasible_sequence()`方法中修改序列生成逻辑以满足新约束。

### 自定义遗传操作
修改`crossover()`和`mutate()`方法以适应特定问题需求。

## 故障排除

### 常见问题

1. **没有找到有效解**
   - 检查输入数据格式是否正确
   - 确认每个工序至少有一台可用机器

2. **算法收敛慢**
   - 增加种群规模
   - 调整交叉和变异概率

3. **内存不足**
   - 减少种群规模
   - 减少进化代数

## 贡献

欢迎提交改进建议和bug报告。主要改进方向：
- 算法性能优化
- 新的遗传操作算子
- 更多约束类型支持
- 可视化界面

## 许可证

MIT License
# production_simulator

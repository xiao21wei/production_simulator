# 代码架构说明

## 系统架构图

```
┌─────────────────────────────────────────────────────────────┐
│                    NSGA2-FJSP 求解器                        │
├─────────────────────────────────────────────────────────────┤
│                      主程序层                                │
│  ┌─────────────────┐  ┌────────────────┐                   │
│  │ nsga2_sceduling │  │ example_usage  │                   │
│  │     .py        │  │     .py        │                   │
│  └─────────────────┘  └────────────────┘                   │
├─────────────────────────────────────────────────────────────┤
│                     算法核心层                               │
│  ┌─────────────────┐  ┌────────────────┐                   │
│  │   Individual    │  │  NSGA2_FJSP    │                   │
│  │   (个体表示)     │  │  (算法主体)     │                   │
│  │                │  │                │                   │
│  │ • 机器分配      │  │ • 初始化种群    │                   │
│  │ • 工序排序      │  │ • 非支配排序    │                   │
│  │ • 目标评估      │  │ • 拥挤距离     │                   │
│  │ • 约束处理      │  │ • 遗传操作     │                   │
│  └─────────────────┘  └────────────────┘                   │
├─────────────────────────────────────────────────────────────┤
│                      数据层                                 │
│  ┌─────────────────┐  ┌────────────────┐                   │
│  │  fjsp_reader    │  │   Schedule     │                   │
│  │  (数据读取)      │  │  (结果输出)     │                   │
│  │                │  │                │                   │
│  │ • FJSPInstance │  │ • CSV导出      │                   │
│  │ • Operation    │  │ • 甘特图生成    │                   │
│  │ • FJSPJob      │  │ • 结果验证     │                   │
│  └─────────────────┘  └────────────────┘                   │
├─────────────────────────────────────────────────────────────┤
│                     系统支撑层                              │
│  ┌─────────────────┐  ┌────────────────┐                   │
│  │     Job         │  │    Machine     │                   │
│  │   (工件类)       │  │   (机器类)      │                   │
│  └─────────────────┘  └────────────────┘                   │
└─────────────────────────────────────────────────────────────┘
```

## 数据流图

```
Input Data (input.txt)
         ↓
    [fjsp_reader.py] ← 读取FJSP问题数据
         ↓
    FJSPInstance ← 问题实例对象
         ↓
    [NSGA2_FJSP] ← 创建算法实例
         ↓
    Initialize Population ← 初始化种群
         ↓
    ┌─→ Evaluation ← 评估个体
    │       ↓
    │  Non-dominated Sort ← 非支配排序
    │       ↓
    │  Crowding Distance ← 拥挤距离计算
    │       ↓
    │  Selection ← 选择操作
    │       ↓
    │  Crossover & Mutation ← 遗传操作
    │       ↓
    └── Next Generation? ← 是否继续进化
         ↓ (No)
    Pareto Front ← 获得Pareto前沿
         ↓
    [Schedule] ← 生成调度方案
         ↓
    Output Files ← 输出结果文件
    • output.txt
    • result.csv  
    • gantt_chart_1.txt
```

## 核心类关系图

```
┌──────────────┐      uses      ┌─────────────────┐
│ NSGA2_FJSP   │ ──────────────→ │   Individual    │
│              │                │                 │
│ • run()      │                │ • machine_      │
│ • selection()│                │   assignment    │
│ • crossover()│      ┌─────────┤ • operation_    │
│ • mutate()   │      │         │   sequence      │
└──────────────┘      │         │ • evaluate()    │
                      │         │ • generate_     │
                      │         │   random_       │
                      │         │   solution()    │
                      │         └─────────────────┘
                      │                   │
                      │                   │ uses
                      │                   ↓
┌──────────────┐      │         ┌─────────────────┐
│ FJSPInstance │ ←────┘         │    Schedule     │
│              │                │                 │
│ • jobs       │                │ • printItems()  │
│ • machines   │                │ • addOperation()│
│ • job_count  │                │ • testSchedule()│
│ • machine_   │                └─────────────────┘
│   count      │
└──────────────┘
      │ contains
      ↓
┌──────────────┐      contains   ┌─────────────────┐
│   FJSPJob    │ ──────────────→ │   Operation     │
│              │                │                 │
│ • job_id     │                │ • operation_id  │
│ • operations │                │ • job_id        │
└──────────────┘                │ • machines      │
                               └─────────────────┘
```

## 主要设计模式

### 1. 策略模式 (Strategy Pattern)
- **用途**: 不同的遗传操作（交叉、变异）
- **实现**: 在`NSGA2_FJSP`类中的各种操作方法

### 2. 工厂模式 (Factory Pattern)  
- **用途**: 创建个体实例
- **实现**: `Individual.generate_random_solution()`

### 3. 观察者模式 (Observer Pattern)
- **用途**: 算法进度监控
- **实现**: 进化过程中的状态输出

### 4. 模板方法模式 (Template Method Pattern)
- **用途**: NSGA2算法框架
- **实现**: `NSGA2_FJSP.run()`方法定义算法流程

## 扩展点

### 1. 新增目标函数
```python
# 在Individual.evaluate()中添加
self.new_objective = self.calculate_new_objective()
```

### 2. 自定义遗传操作
```python
# 继承Individual类并重写方法
class CustomIndividual(Individual):
    def custom_crossover(self, other):
        # 实现自定义交叉
        pass
```

### 3. 新的约束处理
```python
# 在_generate_feasible_sequence()中添加约束检查
def _generate_feasible_sequence(self):
    # 添加新的约束逻辑
    pass
```

### 4. 不同的问题变体
```python
# 继承NSGA2_FJSP类
class ExtendedNSGA2(NSGA2_FJSP):
    def __init__(self, problem_instance, **kwargs):
        # 处理扩展问题类型
        pass
```

"""
修复后的NSGA2算法解决FJSP问题
"""

import random
import numpy as np
import sys
import os

# 添加项目路径到sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from common.fjsp_reader import read_fjsp_file
from system.schedule import Schedule

class FJSPSolution:
    """FJSP解决方案类"""
    
    def __init__(self, fjsp_instance):
        self.fjsp_instance = fjsp_instance
        self.machine_assignment = {}  # (job_id, op_id) -> machine_id
        self.operation_sequence = []  # [(job_id, op_id), ...]
        self.makespan = float('inf')
        self.total_machine_load = float('inf')
        
    def generate_random_solution(self):
        """生成随机解"""
        # 1. 为每个工序随机选择机器
        self.machine_assignment = {}
        for job_id, job in enumerate(self.fjsp_instance.jobs):
            for op_id, operation in enumerate(job.operations):
                # 随机选择一个可用机器
                machine_idx = random.randint(0, len(operation.machines) - 1)
                selected_machine, _ = operation.machines[machine_idx]
                self.machine_assignment[(job_id, op_id)] = selected_machine
        
        # 2. 生成可行的工序执行顺序
        self.operation_sequence = self._generate_feasible_sequence()
        
    def _generate_feasible_sequence(self):
        """生成满足工序约束的可行序列"""
        # 创建所有工序的列表
        all_operations = []
        for job_id, job in enumerate(self.fjsp_instance.jobs):
            for op_id in range(len(job.operations)):
                all_operations.append((job_id, op_id))
        
        # 使用随机拓扑排序生成可行序列
        sequence = []
        available_ops = []
        job_next_op = [0] * self.fjsp_instance.job_count  # 每个工件的下一个可执行工序
        
        # 初始化：添加所有工件的第一个工序
        for job_id in range(self.fjsp_instance.job_count):
            if len(self.fjsp_instance.jobs[job_id].operations) > 0:
                available_ops.append((job_id, 0))
        
        while available_ops:
            # 随机选择一个可用工序
            selected_idx = random.randint(0, len(available_ops) - 1)
            job_id, op_id = available_ops.pop(selected_idx)
            
            sequence.append((job_id, op_id))
            job_next_op[job_id] += 1
            
            # 如果该工件还有下一个工序，添加到可用列表
            if job_next_op[job_id] < len(self.fjsp_instance.jobs[job_id].operations):
                available_ops.append((job_id, job_next_op[job_id]))
        
        return sequence
    
    def evaluate(self):
        """计算目标函数值"""
        try:
            # 初始化
            machine_ready_time = [0] * self.fjsp_instance.machine_count
            job_completion_time = [0] * self.fjsp_instance.job_count
            
            # 按序列执行工序
            for job_id, op_id in self.operation_sequence:
                operation = self.fjsp_instance.jobs[job_id].operations[op_id]
                selected_machine = self.machine_assignment[(job_id, op_id)]
                
                # 获取处理时间
                processing_time = None
                for machine_id, proc_time in operation.machines:
                    if machine_id == selected_machine:
                        processing_time = proc_time
                        break
                
                if processing_time is None:
                    self.makespan = float('inf')
                    self.total_machine_load = float('inf')
                    return
                
                # 计算开始和结束时间
                start_time = max(machine_ready_time[selected_machine], 
                               job_completion_time[job_id])
                end_time = start_time + processing_time
                
                # 更新状态
                machine_ready_time[selected_machine] = end_time
                job_completion_time[job_id] = end_time
            
            # 计算目标函数
            self.makespan = max(job_completion_time) if job_completion_time else 0
            self.total_machine_load = sum(machine_ready_time)
            
        except Exception as e:
            print(f"评估错误: {e}")
            self.makespan = float('inf')
            self.total_machine_load = float('inf')

class NSGA2_FJSP:
    """NSGA2算法求解FJSP"""
    
    def __init__(self, fjsp_instance, population_size=100, max_generations=100):
        self.fjsp_instance = fjsp_instance
        self.population_size = population_size
        self.max_generations = max_generations
        self.population = []
        
    def initialize_population(self):
        """初始化种群"""
        print("正在初始化种群...")
        self.population = []
        
        for i in range(self.population_size):
            if i % 20 == 0:
                print(f"生成第 {i+1}/{self.population_size} 个个体...")
                
            individual = FJSPSolution(self.fjsp_instance)
            individual.generate_random_solution()
            individual.evaluate()
            self.population.append(individual)
            
            # 输出前几个个体的信息用于调试
            if i < 5:
                print(f"个体 {i+1}: 完工时间={individual.makespan}, 机器负载={individual.total_machine_load}")
    
    def fast_non_dominated_sort(self, population):
        """快速非支配排序"""
        fronts = [[]]
        n = [0] * len(population)  
        s = [[] for _ in range(len(population))]  
        
        for i in range(len(population)):
            for j in range(len(population)):
                if i != j:
                    if self.dominates(population[i], population[j]):
                        s[i].append(j)
                    elif self.dominates(population[j], population[i]):
                        n[i] += 1
            
            if n[i] == 0:
                population[i].rank = 1
                fronts[0].append(i)
        
        i = 0
        while fronts[i]:
            next_front = []
            for j in fronts[i]:
                for k in s[j]:
                    n[k] -= 1
                    if n[k] == 0:
                        population[k].rank = i + 2
                        next_front.append(k)
            i += 1
            fronts.append(next_front)
        
        return fronts[:-1]
    
    def dominates(self, ind1, ind2):
        """判断ind1是否支配ind2"""
        if ind1.makespan == float('inf') and ind2.makespan == float('inf'):
            return False
        if ind1.makespan == float('inf'):
            return False
        if ind2.makespan == float('inf'):
            return True
            
        better_in_one = False
        
        if ind1.makespan < ind2.makespan:
            better_in_one = True
        elif ind1.makespan > ind2.makespan:
            return False
        
        if ind1.total_machine_load < ind2.total_machine_load:
            better_in_one = True
        elif ind1.total_machine_load > ind2.total_machine_load:
            return False
        
        return better_in_one
    
    def calculate_crowding_distance(self, front_indices, population):
        """计算拥挤距离"""
        if len(front_indices) <= 2:
            for idx in front_indices:
                population[idx].crowding_distance = float('inf')
            return
        
        for idx in front_indices:
            population[idx].crowding_distance = 0
        
        objectives = ['makespan', 'total_machine_load']
        
        for obj in objectives:
            front_indices.sort(key=lambda x: getattr(population[x], obj))
            
            population[front_indices[0]].crowding_distance = float('inf')
            population[front_indices[-1]].crowding_distance = float('inf')
            
            obj_max = getattr(population[front_indices[-1]], obj)
            obj_min = getattr(population[front_indices[0]], obj)
            
            if obj_max - obj_min == 0:
                continue
                
            for i in range(1, len(front_indices) - 1):
                distance = (getattr(population[front_indices[i+1]], obj) - 
                          getattr(population[front_indices[i-1]], obj)) / (obj_max - obj_min)
                population[front_indices[i]].crowding_distance += distance
    
    def crossover(self, parent1, parent2):
        """交叉操作"""
        child1 = FJSPSolution(self.fjsp_instance)
        child2 = FJSPSolution(self.fjsp_instance)
        
        # 机器分配交叉
        child1.machine_assignment = parent1.machine_assignment.copy()
        child2.machine_assignment = parent2.machine_assignment.copy()
        
        # 随机交换一些工序的机器分配
        for (job_id, op_id) in parent1.machine_assignment:
            if random.random() < 0.5:
                child1.machine_assignment[(job_id, op_id)] = parent2.machine_assignment[(job_id, op_id)]
                child2.machine_assignment[(job_id, op_id)] = parent1.machine_assignment[(job_id, op_id)]
        
        # 生成新的可行序列
        child1.operation_sequence = child1._generate_feasible_sequence()
        child2.operation_sequence = child2._generate_feasible_sequence()
        
        return child1, child2
    
    def mutate(self, individual):
        """变异操作"""
        # 机器分配变异
        if random.random() < 0.1:
            operations = list(individual.machine_assignment.keys())
            if operations:
                job_id, op_id = random.choice(operations)
                operation = self.fjsp_instance.jobs[job_id].operations[op_id]
                
                if len(operation.machines) > 1:
                    current_machine = individual.machine_assignment[(job_id, op_id)]
                    other_machines = [m[0] for m in operation.machines if m[0] != current_machine]
                    if other_machines:
                        individual.machine_assignment[(job_id, op_id)] = random.choice(other_machines)
        
        # 序列变异 - 重新生成可行序列
        if random.random() < 0.1:
            individual.operation_sequence = individual._generate_feasible_sequence()
    
    def run(self):
        """运行NSGA2算法"""
        self.initialize_population()
        
        # 检查初始种群
        valid_count = sum(1 for ind in self.population if ind.makespan != float('inf'))
        print(f"初始种群中有效解数量: {valid_count}/{self.population_size}")
        
        if valid_count == 0:
            print("初始种群中没有有效解！")
            return None, []
        
        best_makespan_history = []
        
        for generation in range(self.max_generations):
            if generation % 20 == 0:
                print(f"代数 {generation + 1}/{self.max_generations}")
            
            # 生成子代
            offspring = []
            for _ in range(self.population_size // 2):
                parent1, parent2 = random.sample(self.population, 2)
                child1, child2 = self.crossover(parent1, parent2)
                
                self.mutate(child1)
                self.mutate(child2)
                
                child1.evaluate()
                child2.evaluate()
                
                offspring.extend([child1, child2])
            
            # 合并父代和子代
            combined_population = self.population + offspring
            
            # 非支配排序
            fronts = self.fast_non_dominated_sort(combined_population)
            
            # 选择新一代
            new_population = []
            front_idx = 0
            
            while front_idx < len(fronts) and len(new_population) + len(fronts[front_idx]) <= self.population_size:
                self.calculate_crowding_distance(fronts[front_idx], combined_population)
                
                for idx in fronts[front_idx]:
                    new_population.append(combined_population[idx])
                
                front_idx += 1
            
            # 如果需要从最后一个前沿中选择部分个体
            if len(new_population) < self.population_size and front_idx < len(fronts):
                last_front = fronts[front_idx]
                self.calculate_crowding_distance(last_front, combined_population)
                
                last_front.sort(key=lambda x: combined_population[x].crowding_distance, reverse=True)
                
                remaining = self.population_size - len(new_population)
                for i in range(remaining):
                    new_population.append(combined_population[last_front[i]])
            
            self.population = new_population
            
            # 记录最佳完工时间
            valid_individuals = [ind for ind in self.population if ind.makespan != float('inf')]
            if valid_individuals:
                best_makespan = min(ind.makespan for ind in valid_individuals)
                best_makespan_history.append(best_makespan)
                
                if generation % 20 == 0:
                    print(f"当前最佳完工时间: {best_makespan}")
            else:
                best_makespan_history.append(float('inf'))
        
        return self.population, best_makespan_history

def main():
    """主函数"""
    print("读取FJSP数据...")
    fjsp_instance = read_fjsp_file('input.txt')
    
    print(f"问题规模: {fjsp_instance.job_count}个工件, {fjsp_instance.machine_count}台机器")
    
    # 运行NSGA2算法
    nsga2 = NSGA2_FJSP(fjsp_instance, population_size=80, max_generations=50)
    final_population, history = nsga2.run()
    
    if final_population:
        # 找到Pareto前沿
        fronts = nsga2.fast_non_dominated_sort(final_population)
        pareto_front = [final_population[i] for i in fronts[0]]
        
        # 过滤有效解
        valid_pareto = [ind for ind in pareto_front if ind.makespan != float('inf')]
        
        if valid_pareto:
            print(f"\nPareto前沿包含 {len(valid_pareto)} 个有效解:")
            for i, individual in enumerate(valid_pareto):
                print(f"解 {i+1}: 完工时间={individual.makespan:.2f}, 机器总负载={individual.total_machine_load:.2f}")
            
            # 保存最佳解的调度方案
            best_individual = min(valid_pareto, key=lambda x: x.makespan)
            generate_detailed_schedule(best_individual)
            
            print(f"\n最佳解已保存到 result.csv 和甘特图文件")
            print(f"最佳完工时间: {best_individual.makespan}")
            
            # 将结果写入output.txt
            with open('output.txt', 'w') as f:
                f.write(f"NSGA2求解FJSP结果\n")
                f.write(f"问题规模: {fjsp_instance.job_count}个工件, {fjsp_instance.machine_count}台机器\n")
                f.write(f"Pareto前沿包含 {len(valid_pareto)} 个有效解\n\n")
                
                for i, individual in enumerate(valid_pareto):
                    f.write(f"解 {i+1}: 完工时间={individual.makespan:.2f}, 机器总负载={individual.total_machine_load:.2f}\n")
                
                f.write(f"\n最佳完工时间: {best_individual.makespan}")
        else:
            print("Pareto前沿中没有有效解")
    else:
        print("算法运行失败")

def generate_detailed_schedule(solution):
    """生成详细的调度方案"""
    try:
        machine_ready_time = [0] * solution.fjsp_instance.machine_count
        job_completion_time = [0] * solution.fjsp_instance.job_count
        
        schedule_items = [[] for _ in range(solution.fjsp_instance.machine_count)]
        start_times = [[] for _ in range(solution.fjsp_instance.machine_count)]
        end_times = [[] for _ in range(solution.fjsp_instance.machine_count)]
        
        for job_id, op_id in solution.operation_sequence:
            operation = solution.fjsp_instance.jobs[job_id].operations[op_id]
            selected_machine = solution.machine_assignment[(job_id, op_id)]
            
            # 获取处理时间
            processing_time = None
            for machine_id, proc_time in operation.machines:
                if machine_id == selected_machine:
                    processing_time = proc_time
                    break
            
            if processing_time is None:
                continue
            
            # 计算时间
            start_time = max(machine_ready_time[selected_machine], 
                           job_completion_time[job_id])
            end_time = start_time + processing_time
            
            # 记录调度信息
            schedule_items[selected_machine].append((job_id, op_id))
            start_times[selected_machine].append(start_time)
            end_times[selected_machine].append(end_time)
            
            # 更新状态
            machine_ready_time[selected_machine] = end_time
            job_completion_time[job_id] = end_time
        
        # 创建调度对象
        schedule = Schedule(
            schedule_id=1,
            machine_count=solution.fjsp_instance.machine_count,
            schedule_items=schedule_items,
            start_time=start_times,
            end_time=end_times
        )
        
        # 输出结果
        schedule.printItems()
        
    except Exception as e:
        print(f"生成调度方案时出错: {e}")

if __name__ == "__main__":
    main()

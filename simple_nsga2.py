"""
简化版的NSGA2算法解决FJSP问题
专注于正确的初始化和解码
"""

import random
import sys
import os
from collections import defaultdict

# 添加项目路径到sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from common.fjsp_reader import read_fjsp_file
from system.schedule import Schedule

class SimpleFJSPSolution:
    """简化的FJSP解决方案类"""
    
    def __init__(self, fjsp_instance):
        self.fjsp_instance = fjsp_instance
        self.machine_assignment = []  # 每个工序的机器分配
        self.operation_sequence = []  # 工序执行顺序
        self.makespan = float('inf')
        self.total_machine_load = float('inf')
        
    def generate_random_solution(self):
        """生成随机解"""
        # 为每个工序随机选择机器
        self.machine_assignment = []
        operation_idx = 0
        
        for job_id, job in enumerate(self.fjsp_instance.jobs):
            for op_id, operation in enumerate(job.operations):
                # 随机选择一个可用机器
                machine_idx = random.randint(0, len(operation.machines) - 1)
                selected_machine, processing_time = operation.machines[machine_idx]
                self.machine_assignment.append(selected_machine)
                operation_idx += 1
        
        # 生成可行的工序执行顺序
        self.operation_sequence = self._generate_feasible_sequence()
        
    def _generate_feasible_sequence(self):
        """生成满足工序约束的可行序列"""
        sequence = []
        job_op_counters = [0] * self.fjsp_instance.job_count
        job_max_ops = [len(job.operations) for job in self.fjsp_instance.jobs]
        
        # 随机生成序列，但确保每个工件的工序按顺序执行
        total_operations = sum(job_max_ops)
        
        for _ in range(total_operations):
            # 找到所有可以调度的工件（当前工序还未超出限制）
            available_jobs = []
            for job_id in range(self.fjsp_instance.job_count):
                if job_op_counters[job_id] < job_max_ops[job_id]:
                    available_jobs.append(job_id)
            
            if not available_jobs:
                break
                
            # 随机选择一个可用工件
            selected_job = random.choice(available_jobs)
            sequence.append(selected_job)
            job_op_counters[selected_job] += 1
            
        return sequence
    
    def evaluate(self):
        """计算目标函数值"""
        try:
            # 初始化
            machine_ready_time = [0] * self.fjsp_instance.machine_count
            job_completion_time = [0] * self.fjsp_instance.job_count
            job_op_index = [0] * self.fjsp_instance.job_count
            
            machine_idx = 0
            
            # 按序列执行工序
            for job_id in self.operation_sequence:
                if job_op_index[job_id] >= len(self.fjsp_instance.jobs[job_id].operations):
                    continue
                    
                current_op_idx = job_op_index[job_id]
                operation = self.fjsp_instance.jobs[job_id].operations[current_op_idx]
                
                # 获取机器分配
                selected_machine = self.machine_assignment[machine_idx]
                
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
                job_op_index[job_id] += 1
                
                machine_idx += 1
            
            # 计算目标函数
            self.makespan = max(job_completion_time) if job_completion_time else float('inf')
            self.total_machine_load = sum(machine_ready_time)
            
        except Exception as e:
            print(f"评估错误: {e}")
            self.makespan = float('inf')
            self.total_machine_load = float('inf')

class SimpleNSGA2:
    """简化的NSGA2算法"""
    
    def __init__(self, fjsp_instance, population_size=50, max_generations=50):
        self.fjsp_instance = fjsp_instance
        self.population_size = population_size
        self.max_generations = max_generations
        self.population = []
        
    def initialize_population(self):
        """初始化种群"""
        print("正在初始化种群...")
        self.population = []
        
        for i in range(self.population_size):
            if i % 10 == 0:
                print(f"生成第 {i+1}/{self.population_size} 个个体...")
                
            individual = SimpleFJSPSolution(self.fjsp_instance)
            individual.generate_random_solution()
            individual.evaluate()
            self.population.append(individual)
            
            # 输出一些个体的信息用于调试
            if i < 3:
                print(f"个体 {i+1}: 完工时间={individual.makespan}, 机器负载={individual.total_machine_load}")
    
    def run(self):
        """运行简化的算法"""
        print("开始运行简化的NSGA2算法...")
        
        self.initialize_population()
        
        # 找到最佳解
        valid_solutions = [ind for ind in self.population if ind.makespan != float('inf')]
        
        if not valid_solutions:
            print("没有找到有效解!")
            return None
            
        # 按完工时间排序
        valid_solutions.sort(key=lambda x: x.makespan)
        
        print(f"找到 {len(valid_solutions)} 个有效解")
        print(f"最佳完工时间: {valid_solutions[0].makespan}")
        print(f"最佳机器负载: {valid_solutions[0].total_machine_load}")
        
        return valid_solutions[0]

def main():
    """主函数"""
    print("读取FJSP数据...")
    fjsp_instance = read_fjsp_file('input.txt')
    
    print(f"问题规模: {fjsp_instance.job_count}个工件, {fjsp_instance.machine_count}台机器")
    
    # 运行简化的NSGA2
    nsga2 = SimpleNSGA2(fjsp_instance, population_size=100, max_generations=10)
    best_solution = nsga2.run()
    
    if best_solution:
        print(f"\n最佳解找到!")
        print(f"完工时间: {best_solution.makespan}")
        print(f"机器总负载: {best_solution.total_machine_load}")
        
        # 生成详细的调度方案
        generate_schedule(best_solution)
        
        # 保存结果到output.txt
        with open('output.txt', 'w') as f:
            f.write(f"简化NSGA2求解FJSP结果\n")
            f.write(f"问题规模: {fjsp_instance.job_count}个工件, {fjsp_instance.machine_count}台机器\n")
            f.write(f"最佳完工时间: {best_solution.makespan}\n")
            f.write(f"机器总负载: {best_solution.total_machine_load}\n")
    else:
        print("未找到有效解!")

def generate_schedule(solution):
    """生成详细的调度方案"""
    try:
        # 重建调度过程以获取详细信息
        machine_ready_time = [0] * solution.fjsp_instance.machine_count
        job_completion_time = [0] * solution.fjsp_instance.job_count
        job_op_index = [0] * solution.fjsp_instance.job_count
        
        # 调度结果记录
        schedule_items = [[] for _ in range(solution.fjsp_instance.machine_count)]
        start_times = [[] for _ in range(solution.fjsp_instance.machine_count)]
        end_times = [[] for _ in range(solution.fjsp_instance.machine_count)]
        
        machine_idx = 0
        
        for job_id in solution.operation_sequence:
            if job_op_index[job_id] >= len(solution.fjsp_instance.jobs[job_id].operations):
                continue
                
            current_op_idx = job_op_index[job_id]
            operation = solution.fjsp_instance.jobs[job_id].operations[current_op_idx]
            
            selected_machine = solution.machine_assignment[machine_idx]
            
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
            schedule_items[selected_machine].append((job_id, current_op_idx))
            start_times[selected_machine].append(start_time)
            end_times[selected_machine].append(end_time)
            
            # 更新状态
            machine_ready_time[selected_machine] = end_time
            job_completion_time[job_id] = end_time
            job_op_index[job_id] += 1
            
            machine_idx += 1
        
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
        print("调度结果已保存到 result.csv 和甘特图文件")
        
    except Exception as e:
        print(f"生成调度方案时出错: {e}")

if __name__ == "__main__":
    main()

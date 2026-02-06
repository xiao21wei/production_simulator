"""
NSGA2-FJSP 使用示例
演示如何使用本求解器解决柔性作业车间调度问题
"""

import sys
import os

# 添加项目路径
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from common.fjsp_reader import read_fjsp_file
from NSGA2.nsga2_sceduling import NSGA2_FJSP, generate_detailed_schedule

def simple_example():
    """简单使用示例"""
    
    print("=" * 60)
    print("NSGA2-FJSP 柔性作业车间调度问题求解器")
    print("=" * 60)
    
    # 步骤1：读取FJSP问题数据
    print("\n步骤1：读取FJSP数据...")
    try:
        fjsp_instance = read_fjsp_file('input.txt')
        print(f"✓ 成功读取数据：{fjsp_instance.job_count}个工件，{fjsp_instance.machine_count}台机器")
    except FileNotFoundError:
        print("✗ 错误：未找到input.txt文件")
        print("请确保input.txt文件存在并包含正确格式的FJSP数据")
        return
    except Exception as e:
        print(f"✗ 数据读取错误：{e}")
        return
    
    # 步骤2：配置算法参数
    print("\n步骤2：配置NSGA2算法参数...")
    population_size = 50
    max_generations = 50
    print(f"✓ 种群规模：{population_size}")
    print(f"✓ 最大进化代数：{max_generations}")
    
    # 步骤3：创建并运行算法
    print(f"\n步骤3：运行NSGA2算法...")
    nsga2 = NSGA2_FJSP(
        fjsp_instance, 
        population_size=population_size, 
        max_generations=max_generations
    )
    
    try:
        final_population, history = nsga2.run()
        print("✓ 算法运行完成")
    except Exception as e:
        print(f"✗ 算法运行错误：{e}")
        return
    
    # 步骤4：分析结果
    print(f"\n步骤4：分析结果...")
    fronts = nsga2.fast_non_dominated_sort(final_population)
    pareto_front = [final_population[i] for i in fronts[0]]
    
    # 过滤有效解
    valid_pareto = [ind for ind in pareto_front if ind.makespan != float('inf')]
    
    if not valid_pareto:
        print("✗ 未找到有效解")
        return
    
    print(f"✓ 找到 {len(valid_pareto)} 个Pareto最优解")
    
    # 步骤5：输出结果
    print(f"\n步骤5：输出结果...")
    
    print("\nPareto前沿解：")
    print("-" * 50)
    print("序号\t完工时间\t机器总负载")
    print("-" * 50)
    
    for i, individual in enumerate(valid_pareto):
        print(f"{i+1}\t{individual.makespan:.1f}\t\t{individual.total_machine_load:.1f}")
    
    # 找到最佳解（完工时间最短）
    best_individual = min(valid_pareto, key=lambda x: x.makespan)
    
    print(f"\n最佳解（最短完工时间）：")
    print(f"- 完工时间：{best_individual.makespan}")
    print(f"- 机器总负载：{best_individual.total_machine_load}")
    
    # 步骤6：生成详细调度方案
    print(f"\n步骤6：生成调度方案...")
    try:
        schedule = generate_detailed_schedule(best_individual)
        if schedule:
            print("✓ 调度方案已生成并保存到以下文件：")
            print("  - result.csv：详细调度表")
            print("  - gantt_chart_1.txt：甘特图（Mermaid格式）")
        else:
            print("✗ 调度方案生成失败")
    except Exception as e:
        print(f"✗ 调度方案生成错误：{e}")
    
    # 步骤7：保存结果
    print(f"\n步骤7：保存结果...")
    try:
        with open('output.txt', 'w', encoding='utf-8') as f:
            f.write("NSGA2求解FJSP结果\n")
            f.write("=" * 30 + "\n")
            f.write(f"问题规模: {fjsp_instance.job_count}个工件, {fjsp_instance.machine_count}台机器\n")
            f.write(f"算法参数: 种群{population_size}, 代数{max_generations}\n")
            f.write(f"Pareto前沿包含 {len(valid_pareto)} 个解\n\n")
            
            for i, individual in enumerate(valid_pareto):
                f.write(f"解 {i+1}: 完工时间={individual.makespan:.2f}, 机器总负载={individual.total_machine_load:.2f}\n")
            
            f.write(f"\n最佳完工时间: {best_individual.makespan}")
        
        print("✓ 结果已保存到 output.txt")
    except Exception as e:
        print(f"✗ 结果保存错误：{e}")
    
    print(f"\n" + "=" * 60)
    print("求解完成！")
    print("=" * 60)

def custom_parameters_example():
    """自定义参数示例"""
    
    print("\n" + "=" * 60)
    print("自定义参数示例")
    print("=" * 60)
    
    # 读取数据
    fjsp_instance = read_fjsp_file('input.txt')
    
    # 自定义参数
    custom_params = {
        'population_size': 80,      # 增大种群规模
        'max_generations': 100,     # 增加进化代数
    }
    
    print(f"使用自定义参数：")
    for key, value in custom_params.items():
        print(f"- {key}: {value}")
    
    # 运行算法
    nsga2 = NSGA2_FJSP(fjsp_instance, **custom_params)
    final_population, history = nsga2.run()
    
    # 分析收敛性
    print(f"\n收敛历史（前10代）：")
    for i, makespan in enumerate(history[:10]):
        if makespan != float('inf'):
            print(f"代数 {i+1}: 最佳完工时间 = {makespan}")

def batch_solve_example():
    """批量求解示例"""
    
    print("\n" + "=" * 60)
    print("批量求解示例")
    print("=" * 60)
    
    # 不同参数配置
    configs = [
        {'name': '快速模式', 'pop': 30, 'gen': 30},
        {'name': '标准模式', 'pop': 50, 'gen': 50},
        {'name': '精细模式', 'pop': 100, 'gen': 100},
    ]
    
    fjsp_instance = read_fjsp_file('input.txt')
    results = {}
    
    for config in configs:
        print(f"\n运行 {config['name']}...")
        nsga2 = NSGA2_FJSP(
            fjsp_instance, 
            population_size=config['pop'], 
            max_generations=config['gen']
        )
        
        final_population, _ = nsga2.run()
        fronts = nsga2.fast_non_dominated_sort(final_population)
        pareto_front = [final_population[i] for i in fronts[0]]
        valid_solutions = [ind for ind in pareto_front if ind.makespan != float('inf')]
        
        if valid_solutions:
            best_makespan = min(ind.makespan for ind in valid_solutions)
            results[config['name']] = {
                'best_makespan': best_makespan,
                'pareto_size': len(valid_solutions)
            }
        
    print(f"\n批量求解结果对比：")
    print("-" * 40)
    print("模式\t\t最佳完工时间\tPareto解数")
    print("-" * 40)
    for name, result in results.items():
        print(f"{name}\t{result['best_makespan']:.1f}\t\t{result['pareto_size']}")

if __name__ == "__main__":
    # 基础示例
    simple_example()
    
    # 可选：运行其他示例
    # custom_parameters_example()
    # batch_solve_example()

"""
调试FJSP解决方案生成
"""

import random
import sys
import os

# 添加项目路径到sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from common.fjsp_reader import read_fjsp_file

def debug_solution_generation():
    """调试解决方案生成过程"""
    print("读取FJSP数据...")
    fjsp_instance = read_fjsp_file('input.txt')
    
    print(f"问题规模: {fjsp_instance.job_count}个工件, {fjsp_instance.machine_count}台机器")
    
    # 统计总工序数
    total_operations = sum(len(job.operations) for job in fjsp_instance.jobs)
    print(f"总工序数: {total_operations}")
    
    # 生成机器分配
    print("\n生成机器分配...")
    machine_assignment = []
    operation_info = []
    
    for job_id, job in enumerate(fjsp_instance.jobs):
        for op_id, operation in enumerate(job.operations):
            # 随机选择一个可用机器
            machine_idx = random.randint(0, len(operation.machines) - 1)
            selected_machine, processing_time = operation.machines[machine_idx]
            machine_assignment.append(selected_machine)
            operation_info.append((job_id, op_id, selected_machine, processing_time))
            
    print(f"机器分配长度: {len(machine_assignment)}")
    print(f"前10个机器分配: {machine_assignment[:10]}")
    
    # 生成工序序列
    print("\n生成工序序列...")
    sequence = []
    job_op_counters = [0] * fjsp_instance.job_count
    job_max_ops = [len(job.operations) for job in fjsp_instance.jobs]
    
    print(f"每个工件的工序数: {job_max_ops}")
    
    for step in range(total_operations):
        # 找到所有可以调度的工件
        available_jobs = []
        for job_id in range(fjsp_instance.job_count):
            if job_op_counters[job_id] < job_max_ops[job_id]:
                available_jobs.append(job_id)
        
        if not available_jobs:
            print(f"步骤 {step}: 没有可用工件")
            break
            
        # 随机选择一个可用工件
        selected_job = random.choice(available_jobs)
        sequence.append(selected_job)
        job_op_counters[selected_job] += 1
        
        if step < 10:
            print(f"步骤 {step}: 选择工件 {selected_job}, 计数器: {job_op_counters}")
    
    print(f"生成的序列长度: {len(sequence)}")
    print(f"序列前20个: {sequence[:20]}")
    
    # 测试解码
    print("\n测试解码...")
    result = test_decode(fjsp_instance, machine_assignment, sequence, operation_info)
    
    if result:
        print(f"解码成功! 完工时间: {result['makespan']}")
    else:
        print("解码失败!")

def test_decode(fjsp_instance, machine_assignment, sequence, operation_info):
    """测试解码过程"""
    try:
        machine_ready_time = [0] * fjsp_instance.machine_count
        job_completion_time = [0] * fjsp_instance.job_count
        job_op_index = [0] * fjsp_instance.job_count
        
        machine_idx = 0
        
        print(f"开始解码，序列长度: {len(sequence)}, 机器分配长度: {len(machine_assignment)}")
        
        for seq_pos, job_id in enumerate(sequence):
            if machine_idx >= len(machine_assignment):
                print(f"机器分配索引超出范围: {machine_idx} >= {len(machine_assignment)}")
                return None
                
            if job_op_index[job_id] >= len(fjsp_instance.jobs[job_id].operations):
                print(f"工件 {job_id} 工序索引超出范围")
                continue
                
            current_op_idx = job_op_index[job_id]
            operation = fjsp_instance.jobs[job_id].operations[current_op_idx]
            selected_machine = machine_assignment[machine_idx]
            
            # 查找处理时间
            processing_time = None
            for machine_id, proc_time in operation.machines:
                if machine_id == selected_machine:
                    processing_time = proc_time
                    break
            
            if processing_time is None:
                print(f"序列位置 {seq_pos}: 工件 {job_id} 工序 {current_op_idx} 不能在机器 {selected_machine} 上处理")
                print(f"可用机器: {operation.machines}")
                return None
            
            # 计算时间
            start_time = max(machine_ready_time[selected_machine], job_completion_time[job_id])
            end_time = start_time + processing_time
            
            if seq_pos < 10:
                print(f"序列位置 {seq_pos}: J{job_id}-O{current_op_idx} -> M{selected_machine}, 时间 [{start_time}, {end_time}]")
            
            # 更新状态
            machine_ready_time[selected_machine] = end_time
            job_completion_time[job_id] = end_time
            job_op_index[job_id] += 1
            
            machine_idx += 1
        
        makespan = max(job_completion_time) if job_completion_time else 0
        total_load = sum(machine_ready_time)
        
        print(f"解码完成: makespan={makespan}, total_load={total_load}")
        
        return {'makespan': makespan, 'total_load': total_load}
        
    except Exception as e:
        print(f"解码异常: {e}")
        import traceback
        traceback.print_exc()
        return None

if __name__ == "__main__":
    debug_solution_generation()

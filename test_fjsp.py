"""
测试FJSP数据读取和简单的调度
"""

import sys
import os

# 添加项目路径到sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from common.fjsp_reader import read_fjsp_file

def test_fjsp_reader():
    """测试FJSP数据读取"""
    print("测试FJSP数据读取...")
    fjsp_instance = read_fjsp_file('input.txt')
    
    print(f"工件数: {fjsp_instance.job_count}")
    print(f"机器数: {fjsp_instance.machine_count}")
    print(f"最大工序数: {fjsp_instance.max_operations}")
    
    for i, job in enumerate(fjsp_instance.jobs):
        print(f"\n工件 {job.job_id}:")
        for j, op in enumerate(job.operations):
            print(f"  工序 {op.operation_id}: 可用机器 {op.machines}")
    
    # 测试一个简单的随机调度
    import random
    
    # 生成机器选择
    machine_selection = []
    operation_sequence = []
    
    for job in fjsp_instance.jobs:
        for op in job.operations:
            # 随机选择一个可用机器
            machine_idx = random.randint(0, len(op.machines) - 1)
            machine_id, processing_time = op.machines[machine_idx]
            machine_selection.append(machine_id)
            operation_sequence.append(job.job_id)
    
    print(f"\n机器选择序列长度: {len(machine_selection)}")
    print(f"工序排序序列长度: {len(operation_sequence)}")
    print(f"机器选择序列: {machine_selection}")
    print(f"工序排序序列: {operation_sequence}")
    
    # 测试解码
    print("\n测试解码...")
    result = decode_simple_schedule(fjsp_instance, machine_selection, operation_sequence)
    if result:
        print(f"解码成功! 完工时间: {result['makespan']}")
    else:
        print("解码失败!")

def decode_simple_schedule(fjsp_instance, machine_selection, operation_sequence):
    """简单的调度解码"""
    try:
        # 初始化机器空闲时间
        machine_ready_time = [0] * fjsp_instance.machine_count
        # 初始化工件的下一个工序索引
        job_operation_index = [0] * fjsp_instance.job_count
        # 记录每个工件的完工时间
        job_completion_time = [0] * fjsp_instance.job_count
        
        machine_sel_idx = 0
        
        print(f"开始解码调度...")
        print(f"工序序列: {operation_sequence}")
        
        # 按照工序排序序列进行调度
        for seq_idx, job_id in enumerate(operation_sequence):
            print(f"处理序列位置 {seq_idx}, 工件 {job_id}")
            
            if job_operation_index[job_id] >= len(fjsp_instance.jobs[job_id].operations):
                print(f"工件 {job_id} 的所有工序已完成")
                continue
            
            current_op_idx = job_operation_index[job_id]
            operation = fjsp_instance.jobs[job_id].operations[current_op_idx]
            
            print(f"  当前工序: {current_op_idx}, 可用机器: {operation.machines}")
            
            # 获取选定的机器
            if machine_sel_idx >= len(machine_selection):
                print(f"机器选择序列索引超出范围: {machine_sel_idx}")
                return None
                
            selected_machine = machine_selection[machine_sel_idx]
            print(f"  选定机器: {selected_machine}")
            
            # 找到该机器的处理时间
            processing_time = None
            for machine_id, proc_time in operation.machines:
                if machine_id == selected_machine:
                    processing_time = proc_time
                    break
            
            if processing_time is None:
                print(f"机器 {selected_machine} 不能处理工件 {job_id} 的工序 {current_op_idx}")
                return None
            
            print(f"  处理时间: {processing_time}")
            
            # 计算开始时间（考虑机器可用时间和工件前序约束）
            start_time = max(machine_ready_time[selected_machine], job_completion_time[job_id])
            end_time = start_time + processing_time
            
            print(f"  开始时间: {start_time}, 结束时间: {end_time}")
            
            # 更新状态
            machine_ready_time[selected_machine] = end_time
            job_completion_time[job_id] = end_time
            job_operation_index[job_id] += 1
            
            machine_sel_idx += 1
        
        # 计算目标函数值
        makespan = max(job_completion_time)
        total_machine_load = sum(machine_ready_time)
        
        print(f"完工时间: {makespan}, 机器总负载: {total_machine_load}")
        
        return {
            'makespan': makespan,
            'total_machine_load': total_machine_load
        }
        
    except Exception as e:
        print(f"解码错误: {e}")
        import traceback
        traceback.print_exc()
        return None

if __name__ == "__main__":
    test_fjsp_reader()

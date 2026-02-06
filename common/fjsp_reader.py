"""
FJSP数据读取器
读取FJSP标准格式的数据文件
"""

class FJSPInstance:
    """FJSP问题实例"""
    def __init__(self):
        self.jobs = []  # 工件列表
        self.machines = []  # 机器列表
        self.job_count = 0
        self.machine_count = 0
        self.max_operations = 0

class Operation:
    """工序类"""
    def __init__(self, operation_id, job_id):
        self.operation_id = operation_id
        self.job_id = job_id
        self.machines = []  # 可用机器列表 [(machine_id, processing_time), ...]
        
class FJSPJob:
    """FJSP工件类"""
    def __init__(self, job_id):
        self.job_id = job_id
        self.operations = []  # 工序列表

def read_fjsp_file(filename):
    """
    读取FJSP格式的文件
    格式：第一行为 job_count machine_count max_operations
    后续每行为一个工件的信息
    """
    fjsp_instance = FJSPInstance()
    
    with open(filename, 'r') as file:
        lines = file.readlines()
    
    # 读取第一行：工件数、机器数、最大工序数
    first_line = lines[0].strip().split()
    fjsp_instance.job_count = int(first_line[0])
    fjsp_instance.machine_count = int(first_line[1])
    fjsp_instance.max_operations = int(first_line[2])
    
    # 初始化机器列表
    for i in range(fjsp_instance.machine_count):
        fjsp_instance.machines.append(i)
    
    # 读取每个工件的信息
    for job_id in range(fjsp_instance.job_count):
        line = lines[job_id + 1].strip().split()
        job = FJSPJob(job_id)
        
        operation_count = int(line[0])
        index = 1
        
        # 读取每个工序
        for op_id in range(operation_count):
            operation = Operation(op_id, job_id)
            machine_count_for_op = int(line[index])
            index += 1
            
            # 读取该工序可用的机器和处理时间
            for _ in range(machine_count_for_op):
                machine_id = int(line[index])
                processing_time = int(line[index + 1])
                operation.machines.append((machine_id, processing_time))
                index += 2
            
            job.operations.append(operation)
        
        fjsp_instance.jobs.append(job)
    
    return fjsp_instance

def print_fjsp_instance(instance):
    """打印FJSP实例信息"""
    print(f"Jobs: {instance.job_count}, Machines: {instance.machine_count}, Max Operations: {instance.max_operations}")
    
    for job in instance.jobs:
        print(f"Job {job.job_id}:")
        for op in job.operations:
            print(f"  Operation {op.operation_id}: {op.machines}")

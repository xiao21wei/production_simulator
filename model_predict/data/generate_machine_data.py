import pandas as pd
import numpy as np
import os
import random

def generate_machine_datasets(num_machines, min_len, normal_len_lower=250, normal_len_upper=1250, anomaly_len_lower=10, anomaly_len_upper=19, 
                              base_data_path='model_predict/data/anomaly/anomaly.csv', output_dir='model_predict/data/machines', seed = 42,
                              log_tag=True):
    """
    生成机器数据集。

    参数:
    num_machines: int, 生成数据集的数量（即机器数量）。
    min_len: int, 整个数据集的最小长度。
    normal_len_lower: int, 正常数据长度的下界。     取值范围: (0, 2000)
    normal_len_upper: int, 正常数据长度的上界。     取值范围: (0, 2000)
    anomaly_len_lower: int, 异常数据长度的下界。    取值范围: (0, 19]
    anomaly_len_upper: int, 异常数据长度的上界。    取值范围: (0, 19]
    base_data_path: str, 基础数据集的路径。
    output_dir: str, 输出数据集的目录。
    """
    # 一个时间点在数据集中代表两个数据点
    min_len = min_len * 2
    normal_len_lower = normal_len_lower * 2
    normal_len_upper = normal_len_upper * 2
    anomaly_len_lower = anomaly_len_lower * 2
    anomaly_len_upper = anomaly_len_upper * 2
    random.seed(seed)

    # 确保输出目录存在
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    # 读取基础数据集
    try:
        df_base = pd.read_csv(base_data_path)
    except FileNotFoundError:
        print(f"Error: Base data file not found at {base_data_path}")
        return

    # 定义基础数据的切片范围 (根据用户描述)
    # 0-1999行为第一部分标签为0的数据 (长度2000)
    # 2000-2019行为第一部分的标签为1的数据 (长度20)
    # 2020-2038行为第二部分的标签为1的数据 (长度19) - 注意：通常索引是左闭右开，这里假设用户给的是包含首尾的行号
    # 但根据常规，2000-2019通常指index 2000到2019(含)，共20行。
    # 用户描述: 2020-2038 (19行), 2039-4039 (2001行). 
    # 为了严谨，我们先切分出原始的大块数据。
    
    # Python切片是左闭右开，所以需要调整结束索引。
    # 0-1999 -> iloc[0:2000]
    # 2000-2019 -> iloc[2000:2020]
    # 2020-2038 -> iloc[2020:2039]
    # 2039-4039 -> iloc[2039:4040]
    
    part1_label0_base = df_base.iloc[0:2000]
    part1_label1_base = df_base.iloc[2000:2020]
    part2_label1_base = df_base.iloc[2020:2039]
    part2_label0_base = df_base.iloc[2039:4040]

    # 检查参数并限制在基础数据集长度范围内
    max_part1_label0 = len(part1_label0_base)
    max_part2_label0 = len(part2_label0_base)
    max_anomaly = len(part1_label1_base) + len(part2_label1_base) # 39
    
    # 确保正常数据的上下界合理
    normal_len_upper = min(normal_len_upper, max_part1_label0 + max_part2_label0)
    normal_len_lower = min(normal_len_lower, normal_len_upper)
    
    # 确保异常数据的上下界合理
    anomaly_len_upper = min(anomaly_len_upper, max_anomaly)
    anomaly_len_lower = min(anomaly_len_lower, anomaly_len_upper)


    for i in range(num_machines):
        machine_filename = f"machine_{i}.csv"
        machine_filepath = os.path.join(output_dir, machine_filename)
        
        current_machine_data = []
        current_len = 0
        
        if log_tag:
            print(f"Generating {machine_filename}...")

        while current_len <= min_len:
            # --- 操作 1: 处理异常窗口 ---
            # 从anomaly_len_lower-anomaly_len_upper中，随机选取一个数x
            x = random.randint(anomaly_len_lower, anomaly_len_upper)
            # 计算应该减去的窗口长度 y = 39 - x  (最大可能长度39)
            y = max_anomaly - x
            # y除以2得到z (向下取整，因为索引必须是整数)
            z = y // 2
            
            # 第一部分标签为1的数据的末尾减去长度为z
            # 如果 z=0, 则不减
            p1_l1_end_idx = len(part1_label1_base) - z
            current_p1_l1 = part1_label1_base.iloc[:p1_l1_end_idx]
            
            # 第二部分标签为1的数据开头减去长度为z
            # 注意：如果 z 很大可能会导致索引越界或者取空，但这里 y = 39-x，x>=20，y<=19，z<=9
            # len(part1) = 20, len(part2) = 19. 
            # z从两个部分分别减去，所以需要确保z不过大。
            # 这里简单处理，如果不够扣除，则异常部分可能会比预期的x稍短或长，但一般情况x接近39时z接近0
            current_p2_l1 = part2_label1_base.iloc[z:]
            
            # 合并这两部分作为中间的异常部分
            anomaly_segment = pd.concat([current_p1_l1, current_p2_l1])

            # --- 操作 2 & 3: 处理正常数据 ---
            # 随机采样一个总的正常长度
            total_normal_len = random.randint(normal_len_lower, normal_len_upper)
            
            # 平均分配给两部分，可能有余数
            len_p1_l0 = total_normal_len // 2
            len_p2_l0 = total_normal_len - len_p1_l0
            
            # 确保不超过各部分基础数据的最大长度
            len_p1_l0 = min(len_p1_l0, max_part1_label0)
            len_p2_l0 = min(len_p2_l0, max_part2_label0)
            
            # --- 操作 2: 处理第一部分标签为0的数据 ---
            # 从开头减去多余长度的数据，意味着保留末尾的 len_p1_l0 长度的数据
            start_p1_l0 = len(part1_label0_base) - len_p1_l0
            current_p1_l0 = part1_label0_base.iloc[start_p1_l0:]

            # --- 操作 3: 处理第二部分标签为0的数据 ---
            # 从末尾减去多余长度的数据，意味着保留开头的 len_p2_l0 长度的数据
            current_p2_l0 = part2_label0_base.iloc[:len_p2_l0]

            # --- 合并数据 ---
            # 顺序: 操作2(头) -> 操作1(中) -> 操作3(尾)
            segment = pd.concat([current_p1_l0, anomaly_segment, current_p2_l0])
            
            current_machine_data.append(segment)
            current_len += len(segment)

        # 将列表中的所有片段合并为一个DataFrame
        final_machine_df = pd.concat(current_machine_data, ignore_index=True)
        
        # 将timestamp列更新为从0开始计数
        if 'timestamp' in final_machine_df.columns:
            final_machine_df['timestamp'] = range(len(final_machine_df))
        
        # 保存到CSV
        final_machine_df.to_csv(machine_filepath, index=False)
        if log_tag:
            print(f"Saved {machine_filename} with length {len(final_machine_df)}")

# 示例调用
if __name__ == "__main__":
    generate_machine_datasets(num_machines=10, min_len=10000, 
                             normal_len_lower=250, normal_len_upper=1250, 
                             anomaly_len_lower=10, anomaly_len_upper=19)
